#  IRIS Source Code
#  Copyright (C) 2026 - DFIR-IRIS
#  contact@dfir-iris.org

"""Outbound mail — SMTP send + branded notification-email Celery task.

The HTML template is deliberately table-based and uses inline CSS for
compatibility with desktop and mobile mail clients. Plain text remains the
primary MIME part, with HTML added as an alternative.
"""

from __future__ import annotations

import json
import logging
import re
import smtplib
import ssl
from datetime import datetime
from datetime import timezone
from email.message import EmailMessage
from typing import Any
from typing import Optional
from typing import Sequence
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from app import app
from app import celery
from app.iris_engine.mail.config import SmtpConfig
from app.iris_engine.mail.config import get_smtp_config


logger = logging.getLogger(__name__)

_EVENT_LABELS = {
    'mention': 'Вас упомянули',
    'task_assigned': 'Вам назначена задача',
    'case_state_change': 'Изменилось состояние кейса',
    'case_assigned': 'Вам назначен кейс',
    'alert_assigned': 'Вам назначен алерт',
    'alert_escalated': 'Алерт эскалирован',
    'war_room_message': 'Новое сообщение в War Room',
    'war_room_thread_reply': 'Новый ответ в War Room',
    'ai_suggestion': 'Новое предложение ИИ',
    'module_custom': 'Уведомление модуля',
}

_SEVERITIES = {
    'critical': ('CRITICAL', 'критическая', '#f38ba8'),
    'high': ('HIGH', 'высокая', '#f38ba8'),
    'medium': ('MEDIUM', 'средняя', '#fab387'),
    'low': ('LOW', 'низкая', '#89b4fa'),
    'info': ('INFO', 'информационная', '#a6e3a1'),
    'informational': ('INFO', 'информационная', '#a6e3a1'),
}

_STATUSES = {
    'new': 'Новый',
    'open': 'Открыт',
    'in progress': 'В работе',
    'in_progress': 'В работе',
    'pending': 'Ожидает',
    'escalated': 'Эскалирован',
    'resolved': 'Решён',
    'closed': 'Закрыт',
    'false positive': 'Ложное срабатывание',
    'merged': 'Объединён',
}

_SOURCE_FIELD_LABELS = {
    'id': 'ID события Graylog',
    'event_definition_id': 'ID правила Graylog',
    'timestamp': 'Время события Graylog',
    'timestamp_processing': 'Время обработки Graylog',
    'timerange_start': 'Начало окна проверки',
    'timerange_end': 'Конец окна проверки',
    'message': 'Сообщение события',
    'source': 'Хост / источник события',
    'fields': 'Поля события',
    'group_by_fields': 'Поля группировки',
    'tactics_techniques': 'MITRE ATT&CK',
    'tags': 'Метки события',
}

_SENSITIVE_KEY = re.compile(
    r'password|passwd|secret|token|api[_-]?key|authorization|credential|cookie',
    re.IGNORECASE,
)


def _build_message(cfg: SmtpConfig,
                   to: Sequence[str],
                   subject: str,
                   body_text: str,
                   body_html: Optional[str] = None) -> EmailMessage:
    msg = EmailMessage()
    msg['Subject'] = subject
    if cfg.from_name:
        msg['From'] = f'{cfg.from_name} <{cfg.from_address}>'
    else:
        msg['From'] = cfg.from_address
    msg['To'] = ', '.join(to)
    msg.set_content(body_text or '')
    if body_html:
        msg.add_alternative(body_html, subtype='html')
    return msg


def _send_via_smtp(cfg: SmtpConfig, msg: EmailMessage) -> None:
    """Open, authenticate, deliver, close. Blocking."""
    ctx = ssl.create_default_context()
    if cfg.use_ssl:
        with smtplib.SMTP_SSL(cfg.host, cfg.port, context=ctx, timeout=30) as srv:
            if cfg.user and cfg.password:
                srv.login(cfg.user, cfg.password)
            srv.send_message(msg)
        return

    with smtplib.SMTP(cfg.host, cfg.port, timeout=30) as srv:
        srv.ehlo()
        if cfg.use_tls:
            srv.starttls(context=ctx)
            srv.ehlo()
        if cfg.user and cfg.password:
            srv.login(cfg.user, cfg.password)
        srv.send_message(msg)


def send_email(to: Sequence[str],
               subject: str,
               body_text: str,
               body_html: Optional[str] = None,
               cfg: Optional[SmtpConfig] = None) -> bool:
    """Send a mail synchronously. Returns True on delivery."""
    if not to:
        return False
    cfg = cfg or get_smtp_config()
    if cfg is None:
        logger.info('SMTP not configured — dropping mail to %s', to)
        return False
    msg = _build_message(cfg, to, subject, body_text, body_html)
    _send_via_smtp(cfg, msg)
    return True


def _description_text(value: Any, title: str = '') -> str:
    """Turn the limited HTML produced by integrations into readable plain text.

    We intentionally do not mark source HTML as safe: event data is untrusted.
    HTMLParser keeps structural line breaks and discards every tag/attribute.
    """
    raw = _text(value)
    if not raw:
        return ''
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []

        def _break(self):
            self.parts.append('\n')

        def handle_starttag(self, tag, attrs):
            if tag in ('br', 'p', 'div', 'tr', 'table', 'td', 'th', 'li',
                       'h1', 'h2', 'h3', 'h4', 'pre'):
                self._break()

        def handle_endtag(self, tag):
            if tag in ('p', 'div', 'tr', 'table', 'li',
                       'h1', 'h2', 'h3', 'h4', 'pre'):
                self._break()

        def handle_data(self, data):
            self.parts.append(data)

    parser = TextExtractor()
    try:
        parser.feed(raw)
        parser.close()
        extracted = ''.join(parser.parts)
    except Exception:
        # Malformed integration HTML must not prevent the notification.
        extracted = re.sub(r'<[^>]*>', '\n', raw)

    lines: list[str] = []
    for source_line in extracted.replace('\r', '').split('\n'):
        line = re.sub(r'[ \t\xa0]+', ' ', source_line).strip()
        if not line:
            if lines and lines[-1] != '':
                lines.append('')
            continue
        if title and not lines and line.strip() == title.strip():
            continue
        if re.match(r'^Время:\s*\d{4}-\d{2}-\d{2}T', line):
            continue
        if re.fullmatch(r'Приоритет:\s*[123]', line):
            continue
        if 'Разбор в HomeWiki' in line:
            continue
        if line.lower() == 'event':
            line = 'Событие:'
        lines.append(line)
    while lines and lines[-1] == '':
        lines.pop()
    return '\n'.join(lines)


def _without_sensitive(value: Any) -> Any:
    """Recursively remove secret-looking keys before JSON reaches an email."""
    if isinstance(value, dict):
        return {
            key: _without_sensitive(item)
            for key, item in value.items()
            if not _SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [_without_sensitive(item) for item in value]
    return value


def _text(value: Any, default: str = '') -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return 'да' if value else 'нет'
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(_without_sensitive(value), ensure_ascii=False, indent=2, default=str)
    result = str(value).strip()
    return result or default


def _clip(value: Any, limit: int = 3000) -> str:
    result = _text(value, '—')
    if len(result) > limit:
        return result[:limit - 1].rstrip() + '…'
    return result


def _safe_url(value: Any, base_url: str = '', relative: bool = False) -> Optional[str]:
    """Allow only HTTP(S) URLs and, optionally, local absolute paths."""
    candidate = _text(value)
    if not candidate or any(ord(char) < 32 for char in candidate):
        return None
    if relative and candidate.startswith('/') and not candidate.startswith('//'):
        if '\\' in candidate or not base_url:
            return None
        return base_url.rstrip('/') + candidate
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    return candidate


def _public_base_url() -> str:
    # IRIS_ALLOW_ORIGIN is a CORS setting and may intentionally differ from
    # the public address. Custom environment keys are not automatically
    # copied into Flask config, so read the process environment first.
    from os import environ
    configured = environ.get('IRIS_PUBLIC_URL') or app.config.get('IRIS_PUBLIC_URL')
    return _safe_url(configured) or ''


def _format_time(value: Any) -> str:
    if not isinstance(value, datetime):
        return _text(value, '—')
    moment = value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    try:
        moment = moment.astimezone(ZoneInfo('Asia/Yekaterinburg'))
        offset = moment.strftime('%z')
        offset = f'{offset[:3]}:{offset[3:]}'
        return moment.strftime('%d.%m.%Y %H:%M:%S') + f' · Екатеринбург (UTC{offset})'
    except (ValueError, OSError):
        return moment.strftime('%d.%m.%Y %H:%M:%S %Z (UTC%z)')


def _object_name(obj: Any, attributes: Sequence[str]) -> str:
    if obj is None:
        return ''
    for attribute in attributes:
        value = _text(getattr(obj, attribute, None))
        if value:
            return value
    return ''


def _severity(value: Any) -> dict[str, str]:
    original = _text(value, 'INFO')
    code, russian, colour = _SEVERITIES.get(
        original.lower(),
        (original.upper(), original, '#89b4fa'),
    )
    return {
        'code': code,
        'label': f'{code} · {russian}',
        'colour': colour,
    }


def _status(value: Any) -> str:
    original = _text(value, '—')
    return _STATUSES.get(original.lower(), original)


def _alert_host(alert: Any) -> str:
    """Resolve the originating host before falling back to Graylog's source."""
    source_content = getattr(alert, 'alert_source_content', None) or {}
    if not isinstance(source_content, dict):
        return ''
    mappings = [
        source_content.get('group_by_fields'),
        source_content.get('fields'),
        getattr(alert, 'alert_context', None),
    ]
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        for key in ('source', 'host', 'hostname', 'agent_hostname', 'computer'):
            value = _text(mapping.get(key))
            if value:
                return value
    return _text(source_content.get('source'))


def _homewiki_url(alert: Any) -> Optional[str]:
    source_content = getattr(alert, 'alert_source_content', None) or {}
    reference = source_content.get('event_definition_id') if isinstance(source_content, dict) else None
    reference = reference or getattr(alert, 'alert_source_ref', None)
    reference = _text(reference)
    if not re.fullmatch(r'[0-9a-fA-F]{24}', reference):
        return None
    return f'https://homewiki.apps.monitoring.test/rules/{reference}'


def _technical_fields(alert: Any) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    source_content = getattr(alert, 'alert_source_content', None) or {}
    if isinstance(source_content, dict):
        for key, label in _SOURCE_FIELD_LABELS.items():
            if key not in source_content or _SENSITIVE_KEY.search(key):
                continue
            value = source_content.get(key)
            if value in (None, '', [], {}):
                continue
            fields.append({'label': label, 'value': _clip(value), 'pre': True})

    context = getattr(alert, 'alert_context', None) or {}
    if isinstance(context, dict):
        for key, value in context.items():
            key_text = _text(key)
            if not key_text or _SENSITIVE_KEY.search(key_text) or value in (None, '', [], {}):
                continue
            if len(fields) >= 20:
                break
            fields.append({'label': f'Контекст · {key_text}', 'value': _clip(value), 'pre': True})
    return fields


def _load_alert(notification: Any) -> Any:
    if notification.source_type != 'alert' or notification.source_id is None:
        return None
    try:
        from app.db import db
        from app.models.alerts import Alert
        return db.session.get(Alert, int(notification.source_id))
    except Exception:
        # A missing/deleted alert must not suppress the original notification.
        logger.exception('Could not enrich notification %s from alert %s',
                         notification.id, notification.source_id)
        return None


def _notification_content(notification: Any) -> dict[str, Any]:
    event_label = _EVENT_LABELS.get(notification.event_type, notification.event_type)
    base_url = _public_base_url()
    iris_url = _safe_url(notification.link, base_url=base_url, relative=True)
    iris_url = iris_url or _safe_url(notification.link)
    alert = _load_alert(notification)
    severity = _severity(getattr(getattr(alert, 'severity', None), 'severity_name', None))

    fields: list[dict[str, Any]] = []
    technical_fields: list[dict[str, Any]] = []
    source_url = None
    homewiki_url = None
    if alert is not None:
        title = _text(alert.alert_title, notification.body or notification.title)
        description = _clip(_description_text(alert.alert_description, title), 6000)
        candidates = [
            ('Хост', _alert_host(alert)),
            ('Критичность', severity['label']),
            ('Статус', _status(_object_name(alert.status, ('status_name',)))),
            ('Источник', _text(alert.alert_source)),
            ('Время уведомления', _format_time(notification.created_at)),
            ('Время исходного события', _format_time(alert.alert_source_event_time)),
            ('Зарегистрирован в IRIS', _format_time(alert.alert_creation_time)),
            ('Ответственный', _object_name(
                alert.owner, ('name', 'user_name', 'username', 'login', 'user_login', 'email'))),
            ('Клиент', _object_name(alert.customer, ('name', 'client_name', 'customer_name'))),
            ('Теги', _text(alert.alert_tags)),
        ]
        fields = [
            {'label': label, 'value': _clip(value, 1500), 'pre': False}
            for label, value in candidates if _text(value)
        ]
        technical_fields = _technical_fields(alert)
        source_url = _safe_url(alert.alert_source_link)
        homewiki_url = _homewiki_url(alert)
        alert_id = alert.alert_id
    else:
        title = _text(notification.title, event_label)
        description = _clip(notification.body, 6000) if notification.body else ''
        fields = [
            {'label': 'Тип события', 'value': event_label, 'pre': False},
            {'label': 'Время уведомления', 'value': _format_time(notification.created_at), 'pre': False},
        ]
        if notification.source_type:
            fields.append({
                'label': 'Источник',
                'value': _text(notification.source_type),
                'pre': False,
            })
        alert_id = None

    return {
        'event_label': event_label,
        'title': title,
        'description': description,
        'severity': severity,
        'fields': fields,
        'technical_fields': technical_fields,
        'iris_url': iris_url,
        'source_url': source_url,
        'homewiki_url': homewiki_url,
        'notification_id': notification.id,
        'alert_id': alert_id,
        'notification_time': _format_time(notification.created_at),
    }


def _plain_text(content: dict[str, Any]) -> str:
    lines = [
        f"IRIS Homelab — {content['event_label']}",
        content['title'],
        '',
    ]
    if content['description']:
        lines.extend([content['description'], ''])
    for field in content['fields']:
        lines.append(f"{field['label']}: {field['value']}")
    if content['technical_fields']:
        lines.extend(['', '--- Технические данные ---'])
        for field in content['technical_fields']:
            lines.append(f"{field['label']}:\n{field['value']}")
    lines.append('')
    if content['iris_url']:
        lines.append(f"Открыть в IRIS: {content['iris_url']}")
    if content['source_url']:
        lines.append(f"Источник в Graylog: {content['source_url']}")
    if content['homewiki_url']:
        lines.append(f"Разбор в HomeWiki: {content['homewiki_url']}")
    lines.extend([
        '',
        f"Уведомление № {content['notification_id']} · {content['notification_time']}",
    ])
    return '\n'.join(lines) + '\n'


# ---- Celery task -----------------------------------------------------
_RETRY_BACKOFF_MAX = 600
_RETRY_MAX_ATTEMPTS = 5


@celery.task(
    bind=True,
    autoretry_for=(smtplib.SMTPException, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=_RETRY_BACKOFF_MAX,
    retry_jitter=True,
    max_retries=_RETRY_MAX_ATTEMPTS,
)
def send_notification_email(self, notification_id: int) -> bool:
    """Render and deliver a persisted notification, then stamp emailed_at."""
    from app.db import db
    from app.models.notifications import Notification

    cfg = get_smtp_config()
    if cfg is None:
        logger.debug('send_notification_email(%s): SMTP disabled, skipping',
                     notification_id)
        return False

    n = Notification.query.filter(Notification.id == notification_id).first()
    if n is None:
        logger.warning('send_notification_email(%s): row not found', notification_id)
        return False

    user = getattr(n, 'user', None)
    to_addr = getattr(user, 'email', None) if user is not None else None
    if not to_addr:
        logger.info('send_notification_email(%s): recipient has no email', notification_id)
        return False

    content = _notification_content(n)
    body_html = app.jinja_env.get_template('email/notification.html').render(**content)
    body_text = _plain_text(content)
    severity_code = content['severity']['code'] if content['alert_id'] is not None else 'NOTICE'
    subject_title = content['title'].replace('\r', ' ').replace('\n', ' ').strip()
    if len(subject_title) > 160:
        subject_title = subject_title[:159].rstrip() + '…'
    subject = f"[IRIS Homelab] {severity_code} · {content['event_label']}: {subject_title}"

    try:
        send_email([to_addr], subject, body_text, body_html=body_html, cfg=cfg)
    except Exception:
        logger.exception('send_notification_email(%s) failed permanently', notification_id)
        return False

    n.emailed_at = datetime.utcnow()
    db.session.commit()
    return True


def mail_send_system(to: Sequence[str], subject: str, body: str) -> bool:
    """One-off system mail (SMTP test, admin alerts, …)."""
    return send_email(to, subject, body)
