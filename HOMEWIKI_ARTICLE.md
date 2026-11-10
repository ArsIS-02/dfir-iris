# DFIR-IRIS — управление инцидентами ИБ

<h1 align="center">DFIR-IRIS</h1>

**Платформа регистрации и расследования инцидентов ИБ. Алерты Graylog попадают в очередь IRIS автоматически — остаётся триажить и эскалировать в кейсы.**

Адрес: **https://iris.apps.monitoring.test/** (плитка «DFIR-IRIS» в Atrium, группа Security)
Вход: **administrator / AdminHomelab2026** (пароль можно сменить: профиль → Change password)

![Дашборд IRIS](/static/articles/iris/dashboard.png)

---

## 1. Что это и зачем

DFIR-IRIS (LGPL-3.0, полностью open source) — система ведения расследований: очередь алертов, кейсы инцидентов, IOC, ассеты, задачи, заметки, таймлайн, доказательства с SHA-256, PDF-отчёты.

В нашей лаборатории цепочка такая:

```
Graylog High-алерт → TicketBridge → GLPI (тикет на работу)
                                 └→ IRIS (алерт на расследование)
```

GLPI отвечает за учёт работ, IRIS — за расследование инцидента. Ручной ввод не нужен: каждый High-алерт Graylog автоматически появляется в IRIS → Alerts.

## 2. Ежедневная работа: от алерта до закрытия инцидента

### Шаг 1. Очередь алертов
Меню слева → **Alerts**. Здесь все алерты Graylog со статусом New. Видны название, severity (High/Medium/Low по приоритету Graylog), источник, время.

![Очередь алертов: три тестовых алерта из Graylog](/static/articles/iris/alerts.png)

### Шаг 2. Триаж
Кликни по цветному кругу severity слева в карточке алерта — раскроются детали: описание со ссылками (разбор в HomeWiki, отчёт TrafficLens, кнопка блокировки IOC в BlockBoard) и сырой JSON события Graylog.

![Детали алерта: описание, источник Graylog, время события](/static/articles/iris/alert-detail.png)

- Ложное срабатывание → **Close** (статус Closed).
- Настоящий инцидент → **Escalate to case**.

### Шаг 3. Кейс (инцидент)
После эскалации открывается кейс. Заполняй по мере расследования:

![Кейс инцидента: сводка, управление, отчёты](/static/articles/iris/case.png)
- **IOCs** — индикаторы (IP, домены, хэши). Можно обогащать через модули.
- **Assets** — затронутые хосты/учётки.
- **Notes** — ход расследования (что проверил, что нашёл).
- **Timeline** — хронология событий и действий.
- **Tasks** — чек-лист действий (шаги можно брать из runbook HomeWiki).
- **Evidence** — файлы-доказательства (дампы, скриншоты), хэшируются автоматически.

### Шаг 4. Закрытие и отчёт
Когда инцидент решён — статус кейса Closed, кнопка отчёта сгенерирует PDF. Тикет в GLPI закроется автоматически при восстановлении хоста или по TTL (сутки тишины) — это делает TicketBridge.

## 3. Типовые сценарии

**IoC-алерт (TrafficLens/BlockBoard):** алерт в IRIS → в описании ссылка «Заблокировать» → блокировка в BlockBoard → в кейсе зафиксировать IOC, хост, время → закрыть после проверки.

**Агент молчит (HomeRepo):** алерт «устройство молчит больше суток» → проверить хост → при возвращении агента TicketBridge сам закроет тикет GLPI, в IRIS алерт закрой вручную.

**Расследование pcap:** алерт → ссылка на отчёт TrafficLens → граф соединений, файлы, сигнатуры → выводы в Notes кейса, IOC — в IOCs.

## 4. API (для своих интеграций)

Ключ: профиль (правый верхний угол) → **API Key** → Renew (после Renew старый ключ перестаёт работать!).

```bash
curl -sk -X POST 'https://iris.apps.monitoring.test/alerts/add' \
  -H 'Authorization: Bearer <API_KEY>' -H 'Content-Type: application/json' \
  -d '{
    "alert_title": "Тестовый алерт",
    "alert_description": "Описание",
    "alert_source": "Graylog",
    "alert_source_ref": "test-001",
    "alert_severity_id": 5,
    "alert_status_id": 2,
    "alert_source_event_time": "2026-11-10T08:00:00",
    "alert_customer_id": 1,
    "alert_source_content": {}
  }'
```

Справочник severity: 6 Critical, 5 High, 1 Medium, 4 Low, 3 Informational. Статус 2 = New. Маппинг в TicketBridge: Graylog priority 3→High, 2→Medium, 1→Low.

## 5. Администрирование (redos-server)

| Что | Где |
|---|---|
| Код развёртывания | `~/dfir-iris/` (docker-compose.yml, .env, certificates/) |
| Стек | iriswebapp_db (PostgreSQL), iriswebapp_app, iriswebapp_worker, iriswebapp_rabbitmq, iriswebapp_nginx — v2.4.29 |
| Порт | 8101 (HTTPS, self-signed), снаружи — Caddy `iris.apps.monitoring.test` |
| Автозапуск | `systemctl --user status dfir-iris` |
| Логи | `podman logs iriswebapp_app` |
| Данные | named volumes: db_data, iris-downloads, user_templates, server_data |

```bash
# Перезапуск / остановка / поднятие
systemctl --user restart dfir-iris     # осторожно: down+up всего стека
podman restart iriswebapp_app          # только приложение

# Обновление версии: правим теги в docker-compose.yml, затем
cd ~/dfir-iris && podman-compose pull && podman-compose up -d

# Бэкап БД
podman exec iriswebapp_db pg_dump -U postgres iris_db > iris_db_$(date +%F).sql
```

Особенности нашей установки (что чинили): SELinux — `chcon -R -t container_file_t ~/dfir-iris/certificates/`; права на ключ nginx — 644; `IRIS_WORKER` в `.env` не задавать (иначе приложение падает с «A secret key is required to use CSRF»).

## 6. Глоссарий: интерфейс IRIS на русском

Штатной русской локализации в IRIS нет. Быстрый вариант — автоперевод браузера (правый клик → «Перевести на русский»), а эта таблица поможет с терминами.

### Главное меню (слева)

| Английский | Русский / что делает |
|---|---|
| Home | Домашняя страница |
| Statistics | Статистика |
| Dashboards | Дашборды |
| Overview | Обзор текущего кейса |
| Case | Текущий кейс (инцидент) |
| Alerts | Очередь алертов — сюда падают алерты Graylog |
| Search | Поиск по всем объектам |
| Activities | Журнал действий |
| DIM Tasks | Задачи из модулей |
| Manage cases | Управление всеми кейсами |
| Advanced | Администрирование (пользователи, модули, справочники) |
| Help | Справка |

### Работа с алертами

| Английский | Русский |
|---|---|
| Alert | Алерт — ещё не инцидент, сигнал на проверку |
| Triage | Триаж — разбор: ложный или настоящий |
| Escalate to case | Эскалировать в кейс — создать инцидент из алерта |
| Merge | Объединить алерты (дубли) |
| Close | Закрыть (ложное срабатывание / обработано) |
| Assign | Назначить ответственного |
| New / Assigned / In progress / Pending / Closed / Merged / Escalated | Новый / Назначен / В работе / Отложен / Закрыт / Объединён / Эскалирован |

### Внутри кейса

| Английский | Русский |
|---|---|
| Case | Кейс = инцидент |
| IOCs | Индикаторы компрометации (IP, домены, хэши) |
| Assets | Затронутые активы (хосты, учётки) |
| Notes | Заметки — ход расследования |
| Timeline | Таймлайн — хронология событий и действий |
| Tasks | Задачи / чек-лист реагирования |
| Evidence | Доказательства (файлы, хэшируются SHA-256) |
| Datastore | Хранилище файлов кейса |
| Report | Отчёт по инциденту (PDF) |
| Summary | Сводка |
| Comments | Комментарии |
| Activity | История изменений |

### Прочее

| Английский | Русский |
|---|---|
| Observable | Наблюдаемый объект (IP, домен, хэш и т.п.) |
| Customer | «Клиент» — в нашей лаборатории один: IrisInitialClient |
| Severity | Критичность: Critical / High / Medium / Low / Informational |
| Renew (API Key) | Перевыпустить API-ключ (старый перестаёт работать!) |
| Prompt before deleting | Подтверждение перед удалением |
| Refresh access | Обновить права/сессию |
| War Room (v3) | «Комната» совместной работы в реальном времени |
