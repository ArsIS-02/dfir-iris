import importlib.util
import sys
import types
import unittest
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment
from jinja2 import FileSystemLoader
from jinja2 import select_autoescape


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / 'custom' / 'templates'


def _load_outbound():
    flask_app = SimpleNamespace(
        config={'IRIS_PUBLIC_URL': 'https://iris.apps.monitoring.test'},
        jinja_env=Environment(
            loader=FileSystemLoader(str(TEMPLATE_ROOT)),
            autoescape=select_autoescape(['html', 'xml']),
        ),
    )

    class Celery:
        @staticmethod
        def task(*args, **kwargs):
            return lambda function: function

    app_module = types.ModuleType('app')
    app_module.app = flask_app
    app_module.celery = Celery()
    config_module = types.ModuleType('app.iris_engine.mail.config')
    config_module.SmtpConfig = object
    config_module.get_smtp_config = lambda: None

    saved = {name: sys.modules.get(name) for name in (
        'app', 'app.iris_engine', 'app.iris_engine.mail',
        'app.iris_engine.mail.config',
    )}
    sys.modules['app'] = app_module
    sys.modules['app.iris_engine'] = types.ModuleType('app.iris_engine')
    sys.modules['app.iris_engine.mail'] = types.ModuleType('app.iris_engine.mail')
    sys.modules['app.iris_engine.mail.config'] = config_module

    spec = importlib.util.spec_from_file_location(
        'iris_test_outbound', ROOT / 'custom' / 'mail' / 'outbound.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._test_saved_modules = saved
    return module


class NotificationMailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mail = _load_outbound()
        cls.original_load_alert = staticmethod(cls.mail._load_alert)

    def setUp(self):
        self.mail._load_alert = self.original_load_alert

    def _notification(self):
        return SimpleNamespace(
            id=987,
            event_type='alert_assigned',
            title='An alert was assigned to you',
            body='Тестовый алерт',
            link='/alerts/14',
            source_type='alert',
            source_id=14,
            created_at=datetime(2026, 11, 11, 6, 0, 0),
        )

    def _alert(self):
        return SimpleNamespace(
            alert_id=14,
            alert_title='AUDIT - Изменение файлов учётных записей',
            alert_description='Проверка <b>оформления</b> и переноса текста.',
            alert_source='Graylog',
            alert_source_ref='6af0c56861b983feab6a56cc',
            alert_source_link='https://graylog.apps.monitoring.test/alerts/EVENT/replay-search',
            alert_source_event_time=datetime(2026, 11, 11, 5, 59, 0),
            alert_creation_time=datetime(2026, 11, 11, 6, 0, 0),
            alert_tags='audit,linux',
            alert_severity_id=4,
            severity=SimpleNamespace(severity_name='High'),
            status=SimpleNamespace(status_name='New'),
            owner=None,
            customer=SimpleNamespace(name='IrisInitialClient'),
            alert_context={'password': 'не должно попасть в письмо', 'hostname': 'redos-server'},
            alert_source_content={
                'id': 'EVENT',
                'event_definition_id': '6af0c56861b983feab6a56cc',
                'message': 'Событие <script>alert(1)</script>',
                'fields': {
                    'source': 'redos-server',
                    'access_token': 'не должно попасть в письмо',
                },
            },
        )

    def test_safe_urls(self):
        self.assertEqual(
            self.mail._safe_url('/alerts/14', 'https://iris.example', relative=True),
            'https://iris.example/alerts/14')
        self.assertIsNone(self.mail._safe_url('javascript:alert(1)'))
        self.assertIsNone(self.mail._safe_url('//evil.example/path', 'https://iris.example', True))
        self.assertIsNone(self.mail._safe_url('https://user:secret@example.com'))

    def test_alert_content_and_html(self):
        self.mail._load_alert = lambda notification: self._alert()
        content = self.mail._notification_content(self._notification())
        self.assertEqual(content['event_label'], 'Вам назначен алерт')
        self.assertEqual(content['severity']['code'], 'HIGH')
        self.assertEqual(content['fields'][1]['value'], 'Новый')
        self.assertEqual(content['iris_url'], 'https://iris.apps.monitoring.test/alerts/14')
        self.assertIn('homewiki.apps.monitoring.test/rules/', content['homewiki_url'])
        self.assertFalse(any('password' in field['label'] for field in content['technical_fields']))

        html = self.mail.app.jinja_env.get_template('email/notification.html').render(**content)
        self.assertIn('IRIS HOMELAB', html)
        self.assertIn('Открыть в IRIS', html)
        self.assertIn('Источник в Graylog', html)
        self.assertIn('Разбор в HomeWiki', html)
        self.assertIn('&lt;b&gt;оформления&lt;/b&gt;', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertNotIn('не должно попасть в письмо', html)

        plain = self.mail._plain_text(content)
        self.assertIn('Критичность: HIGH · высокая', plain)
        self.assertIn('Статус: Новый', plain)
        self.assertIn('Открыть в IRIS:', plain)

    def test_generic_notification_without_source_object(self):
        notification = self._notification()
        notification.source_type = 'case'
        notification.event_type = 'case_assigned'
        notification.title = 'You were made the owner of a case'
        notification.body = 'Кейс <b>тест</b>'
        content = self.mail._notification_content(notification)
        html = self.mail.app.jinja_env.get_template('email/notification.html').render(**content)
        self.assertEqual(content['event_label'], 'Вам назначен кейс')
        self.assertIsNone(content['source_url'])
        self.assertIn('Кейс &lt;b&gt;тест&lt;/b&gt;', html)

    def test_multipart_message(self):
        config = SimpleNamespace(
            from_name='IRIS Homelab', from_address='iris@example.com')
        message = self.mail._build_message(
            config, ['analyst@example.com'], 'Тест', 'Текст', '<b>HTML</b>')
        self.assertIsInstance(message, EmailMessage)
        self.assertEqual(message.get_content_type(), 'multipart/alternative')
        payloads = message.get_payload()
        self.assertEqual(payloads[0].get_content_type(), 'text/plain')
        self.assertEqual(payloads[1].get_content_type(), 'text/html')


if __name__ == '__main__':
    unittest.main()
