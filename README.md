# DFIR-IRIS — развёртывание в домашней лаборатории

Платформа регистрации и расследования инцидентов ИБ [DFIR-IRIS](https://www.dfir-iris.org/)
(LGPL-3.0) на RED OS 8 + podman + Caddy. Алерты Graylog попадают в IRIS
автоматически через [TicketBridge](https://github.com/ArsIS-02/ticketbridge).

## Скриншоты

![Дашборд DFIR-IRIS](docs/screenshots/dashboard.png)

| Очередь алертов | Детали алерта |
|---|---|
| ![Очередь алертов](docs/screenshots/alerts.png) | ![Детали алерта](docs/screenshots/alert-detail.png) |

![Сводка кейса расследования](docs/screenshots/case.png)

## Стек

- iriswebapp_db (PostgreSQL), iriswebapp_app, iriswebapp_worker,
  iriswebapp_rabbitmq, iriswebapp_nginx — всё **v2.4.29**;
- `docker-compose.yml` — самодостаточный (без `extends`), работает с podman-compose;
- порт **8101** (HTTPS, self-signed), снаружи Caddy `iris.apps.monitoring.test`;
- автозапуск — `systemctl --user dfir-iris` (oneshot + `podman-compose up -d`).

## Установка

```bash
mkdir -p ~/dfir-iris/certificates/{rootCA,web_certificates,ldap}
cp docker-compose.yml .env.example ~/dfir-iris/
cd ~/dfir-iris && mv .env.example .env   # заполнить секреты

# Сертификаты
cd certificates
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout web_certificates/iris_key.pem -out web_certificates/iris_cert.pem \
  -days 825 -subj "/CN=iris.apps.monitoring.test" \
  -addext "subjectAltName=DNS:iris.apps.monitoring.test"
cp web_certificates/iris_cert.pem rootCA/irisRootCACert.pem
chmod 644 web_certificates/iris_*.pem
chcon -R -t container_file_t ~/dfir-iris/certificates/   # SELinux

cd ~/dfir-iris && podman-compose up -d
```

## Caddy

```
iris.apps.monitoring.test {
    tls internal
    reverse_proxy https://host.containers.internal:8101 {
        transport http {
            tls
            tls_insecure_skip_verify
        }
    }
}
```

## systemd (`~/.config/systemd/user/dfir-iris.service`)

```
[Unit]
Description=DFIR-IRIS — управление инцидентами ИБ
After=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=%h/dfir-iris
ExecStart=/usr/bin/podman-compose up -d
ExecStop=/usr/bin/podman-compose down

[Install]
WantedBy=default.target
```

## Первый вход и API

- Пароль администратора генерируется при первом запуске: смотреть
  `podman logs iriswebapp_app | grep -A2 "Administrator password"`.
  Логин — `administrator`.
- Смена пароля: профиль → Change password (политика: >12 символов, заглавная, цифра).
- API-ключ: профиль → API Key. Приём алертов: `POST /alerts/add`,
  заголовок `Authorization: Bearer <key>`.
- Интеграция Graylog: TicketBridge (`TB_IRIS_URL`, `TB_IRIS_KEY`) дублирует
  каждый High-алерт в IRIS; severity: Graylog 3→High(5), 2→Medium(1), 1→Low(4).

## Грабли, которые уже встречались

1. `IRIS_WORKER=1` в `.env` → приложение не стартует CSRF («A secret key is required»).
   Переменная должна быть только у worker, в `.env` её не пишем.
2. SELinux: без `chcon -R -t container_file_t certificates/` nginx не читает сертификаты.
3. Ключ `iris_key.pem` должен быть читаемым (644) — nginx работает не от root.
4. `:ro:z` в mounts podman-compose не парсит — используем `:ro` + `chcon`.
5. Короткие имена образов (`rabbitmq:...`) требуют полного пути `docker.io/library/...`.

## Бэкап

```bash
podman exec iriswebapp_db pg_dump -U postgres iris_db > iris_db_$(date +%F).sql
```

Инструкция для пользователей — `HOMEWIKI_ARTICLE.md` (опубликована в HomeWiki,
статья `art-iris`).
