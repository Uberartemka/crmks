# Cloud-init деплой frontcrm

`cloud-init.yml` поднимает CRM на свежем Ubuntu-сервере одной командой — без ручного SSH.

## Как использовать

### 1. Отредактируй параметры

В `deploy/cloud-init.yml` найди блок `write_files:` → `path: /etc/crmks-bootstrap.env` и поправь значения:

```yaml
CRMKS_DOMAIN="crm.example.ru"        # домен или IP сервера
CRMKS_GIT_REPO="https://github.com/Uberartemka/crmks.git"
CRMKS_GIT_BRANCH="main"
CRMKS_INSTALL_PLAYWRIGHT="true"       # Chromium для PDF/КП (~400 МБ)
CRMKS_REQUEST_SSL="false"             # true только если DNS уже указывает на сервер
CRMKS_KIMI_API_KEY="sk-..."           # или REPLACE_ME, заполни .env после
CRMKS_CF_ACCOUNT_ID="..."
CRMKS_CF_API_TOKEN="..."
CRMKS_CF_EMAIL="..."
CRMKS_SERPAPI_KEY="..."
```

### 2. Создай сервер и вставь cloud-config

У большинства провайдеров (Hetzner, DigitalOcean, AWS Lightsail, Яндекс.Облако, Selectel, Timeweb) при создании VPS есть поле **«cloud-init» / «user-data» / «Custom script»**. Вставь туда **полное содержимое** `cloud-init.yml` целиком (включая `#cloud-config` первой строкой).

### 3. Подожди 5–10 минут

Сервер сам:
- поставит пакеты (Python, Node, PostgreSQL, Redis, nginx, certbot)
- создаст БД `hhb_b2b`, пользователя `crmks`, Redis с паролем
- склонирует репозиторий и соберёт фронт
- накатит миграции БД
- запустит сервисы `crmks-api` и `crmks-watchdog` под systemd
- настроит nginx (если указан домен)

### 4. Проверь

```bash
ssh root@<IP>
sudo systemctl status crmks-api crmks-watchdog
sudo cat /var/log/cloud-init-output.log | tail -50
curl http://127.0.0.1:8000/docs | head -1
```

Если что-то упало — смотри `/var/log/cloud-init-output.log` и `/var/log/crmks-install.log`.

### 5. SSL (если не запросил автоматически)

```bash
sudo certbot --nginx -d crm.example.ru
```

## Пароли

После установки пароли сохранены в:
- `/root/crmks_db_password.txt`
- `/root/crmks_redis_password.txt`

## Обновление кода

Cloud-init — для первичной установки. Для обновления используй:
```bash
sudo bash /var/www/crmks/deploy/update.sh
```

## Замечания

- **Секреты в metadata:** некоторые провайдеры логируют user-data. Если боишься — оставь API-ключи как `REPLACE_ME` и заполни `/var/www/crmks/backend/.env` вручную после поднятия сервера.
- **Приватный репозиторий:** если сделаешь репо приватным, поменяй `CRMKS_GIT_REPO` на SSH-URL и добавь deploy key.
- **Тестирование:** cloud-config проверен по синтаксису, но не прогнан на реальном VPS. Первый запуск может потребовать точечной правки под версию дистрибутива.
