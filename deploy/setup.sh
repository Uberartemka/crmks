#==============================================================================
# Первичная установка frontcrm (CRM) на свежий Ubuntu/Debian сервер.
#
# Запускать ОДИН РАЗ при первичном деплое:
#
#   sudo bash deploy/setup.sh
#
# Скрипт интерактивный: спросит домен и git-URL.
#==============================================================================
set -e

# ---- Цвета ----
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
step()  { echo -e "\n${YELLOW}=== $1 ===${NC}"; }
die()   { echo -e "${RED}✗ $1${NC}"; exit 1; }

# Проверка root
if [ "$EUID" -ne 0 ]; then
    echo "Запустите с sudo: sudo bash deploy/setup.sh"
    exit 1
fi

# ---- Константы ----
APP_NAME="crmks"
APP_USER="crmks"
SITE_DIR="/var/www/$APP_NAME"
LOG_DIR="/var/log/$APP_NAME"
DB_NAME="hhb_b2b"
DB_USER="crmks"
VENV_DIR="$SITE_DIR/backend/venv"

# Определяем версию Python (предпочитаем 3.11/3.12)
PY_BIN=$(command -v python3.12 || command -v python3.11 || command -v python3)
[ -z "$PY_BIN" ] && die "Python 3.11+ не найден. Установите: apt install python3"
info "Используется Python: $PY_BIN ($($PY_BIN --version))"

#==============================================================================
# Шаг 0. Опрос параметров
#==============================================================================
step "0/10. Параметры установки"

read -rp "Домен для CRM (например crm.example.ru, или Enter чтобы пропустить nginx+SSL): " DOMAIN
read -rp "URL git-репозитория (HTTPS с токеном или SSH, или Enter чтобы пропустить клонирование): " REPO_URL
read -rp "Установить Playwright + Chromium для генерации PDF? [y/N]: " INSTALL_PW
INSTALL_PW=${INSTALL_PW:-N}

#==============================================================================
# Шаг 1. Системные пакеты
#==============================================================================
step "1/10. Установка системных пакетов"
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip \
    nodejs npm \
    nginx postgresql postgresql-contrib \
    redis-server \
    certbot python3-certbot-nginx \
    git ufw curl wget \
    >/dev/null
info "Системные пакеты установлены"

#==============================================================================
# Шаг 2. Пользователь и директории
#==============================================================================
step "2/10. Пользователь и директории"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    useradd -r -m -d "/home/$APP_USER" -s /bin/bash "$APP_USER"
    info "Пользователь $APP_USER создан"
else
    info "Пользователь $APP_USER уже существует"
fi
mkdir -p "$SITE_DIR" "$LOG_DIR"
chown -R "$APP_USER:$APP_USER" "$SITE_DIR" "$LOG_DIR"
info "Директории готовы: $SITE_DIR, $LOG_DIR"

#==============================================================================
# Шаг 3. PostgreSQL — БД hhb_b2b + юзер crmks
#==============================================================================
step "3/10. Настройка PostgreSQL"
DB_PASS=$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9' | head -c 24)
echo "${APP_NAME} db password: $DB_PASS" > "/root/${APP_NAME}_db_password.txt"
chmod 600 "/root/${APP_NAME}_db_password.txt"

sudo -u postgres psql <<EOF
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = '$DB_USER') THEN
        CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';
    END IF;
END\$\$;
EOF

# БД создаём только если её нет
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER ENCODING 'UTF8' LC_COLLATE 'ru_RU.UTF-8' LC_CTYPE 'ru_RU.UTF-8' TEMPLATE template0;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" >/dev/null
info "БД '$DB_NAME' и пользователь '$DB_USER' готовы"
info "Пароль БД сохранён в /root/${APP_NAME}_db_password.txt"

#==============================================================================
# Шаг 4. Redis — с паролем
#==============================================================================
step "4/10. Настройка Redis"
REDIS_PASS=$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9' | head -c 24)
echo "${APP_NAME} redis password: $REDIS_PASS" > "/root/${APP_NAME}_redis_password.txt"
chmod 600 "/root/${APP_NAME}_redis_password.txt"

# Конфигурируем requirepass если ещё не задан
if ! grep -q "^requirepass" /etc/redis/redis.conf; then
    echo "requirepass $REDIS_PASS" >> /etc/redis/redis.conf
    systemctl restart redis-server
    info "Redis защищён паролем"
else
    warn "Redis уже имеет requirepass — используем существующий (см. /etc/redis/redis.conf)"
    REDIS_PASS=$(grep "^requirepass" /etc/redis/redis.conf | awk '{print $2}')
fi
info "Пароль Redis сохранён в /root/${APP_NAME}_redis_password.txt"

#==============================================================================
# Шаг 5. Клонирование репозитория
#==============================================================================
step "5/10. Клонирование проекта"
if [ -d "$SITE_DIR/.git" ]; then
    warn "Git-репозиторий уже существует — пропускаем клонирование"
else
    if [ -z "$REPO_URL" ]; then
        warn "URL не указан. Склонируйте вручную: git clone <repo> $SITE_DIR"
    else
        git clone "$REPO_URL" "$SITE_DIR"
        info "Проект склонирован в $SITE_DIR"
    fi
fi
chown -R "$APP_USER:$APP_USER" "$SITE_DIR"

#==============================================================================
# Шаг 6. Backend: venv + зависимости
#==============================================================================
step "6/10. Backend: виртуальное окружение и зависимости"
if [ ! -d "$VENV_DIR" ]; then
    sudo -u "$APP_USER" bash -c "cd $SITE_DIR/backend && $PY_BIN -m venv venv && \
        ./venv/bin/pip install --upgrade pip --quiet && \
        ./venv/bin/pip install -r requirements.txt --quiet"
    info "venv создан, Python-зависимости установлены"
else
    warn "venv уже существует — обновляем зависимости"
    sudo -u "$APP_USER" bash -c "$VENV_DIR/bin/pip install -r $SITE_DIR/backend/requirements.txt --quiet"
fi

# Playwright + Chromium (опционально, для PDF/КП)
if [[ "$INSTALL_PW" =~ ^[Yy]$ ]]; then
    step "6b. Установка Playwright + Chromium (для генерации PDF)"
    sudo -u "$APP_USER" bash -c "$VENV_DIR/bin/playwright install chromium --with-deps" || \
        warn "Playwright install завершился с предупреждениями — проверьте логи"
    info "Chromium установлен"
else
    warn "Playwright пропущен. PDF/КП генерация будет недоступна. Установить позже: $VENV_DIR/bin/playwright install chromium --with-deps"
fi

#==============================================================================
# Шаг 7. Frontend: npm install + build
#==============================================================================
step "7/10. Frontend: установка и сборка"
if [ -f "$SITE_DIR/package.json" ]; then
    sudo -u "$APP_USER" bash -c "cd $SITE_DIR && npm ci --silent && npm run build"
    if [ -d "$SITE_DIR/dist" ]; then
        info "Фронт собран в $SITE_DIR/dist"
    else
        warn "Сборка завершена, но dist/ не найден — проверьте package.json scripts"
    fi
else
    warn "package.json не найден — пропускаем сборку фронта"
fi

#==============================================================================
# Шаг 8. Файлы окружения (.env)
#==============================================================================
step "8/10. Конфигурация окружения (.env)"

# Backend .env — основная конфигурация
BACKEND_ENV="$SITE_DIR/backend/.env"
if [ ! -f "$BACKEND_ENV" ]; then
    cat > "$BACKEND_ENV" <<EOF
# === База данных ===
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME

# === Redis ===
REDIS_URL=redis://:$REDIS_PASS@127.0.0.1:6379/0
TOKEN_TTL_SECONDS=86400
REDIS_FAIL_FAST=0

# === AI / External APIs (ЗАПОЛНИ ВРУЧНУЮ) ===
KIMI_API_KEY=sk-REPLACE_ME
KIMI_TIMEOUT_SEC=25
KIMI_MAX_WORKERS=8
AI_CALL_TIMEOUT_SEC=30
CF_ACCOUNT_ID=REPLACE_ME
CF_API_TOKEN=REPLACE_ME
CF_MODEL=@cf/moonshotai/kimi-k2.5
CF_EMAIL=REPLACE_ME
SERPAPI_KEY=REPLACE_ME
EOF
    chown "$APP_USER:$APP_USER" "$BACKEND_ENV"
    chmod 600 "$BACKEND_ENV"
    info "backend/.env создан (ЗАПОЛНИ API-ключи вручную!)"
else
    warn "backend/.env уже существует — не перезаписываю"
fi

# Корневой .env — для фронтенд-сборки (VITE_ переменные)
ROOT_ENV="$SITE_DIR/.env"
if [ ! -f "$ROOT_ENV" ]; then
    if [ -n "$DOMAIN" ]; then
        API_BASE="https://$DOMAIN/api"
    else
        API_BASE="/api"
    fi
    cat > "$ROOT_ENV" <<EOF
VITE_API_BASE_URL=$API_BASE
VITE_USE_MOCKS=false
EOF
    chown "$APP_USER:$APP_USER" "$ROOT_ENV"
    info "Корневой .env создан (VITE_API_BASE_URL=$API_BASE)"
else
    warn "Корневой .env уже существует — не перезаписываю"
fi

#==============================================================================
# Шаг 9. Применение миграций БД
#==============================================================================
step "9/10. Применение миграций БД"
sudo -u "$APP_USER" bash -c "cd $SITE_DIR/backend && \
    DATABASE_URL='postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME' \
    $VENV_DIR/bin/python -c 'from migrations.runner import apply_all; apply_all(\"postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME\")'" \
    || warn "Миграция завершилась с ошибкой — проверьте подключение к БД"
info "Миграции применены (job_queue watchdog-колонки)"

#==============================================================================
# Шаг 10. systemd + nginx + файрвол
#==============================================================================
step "10/10. systemd-сервисы и Nginx"

# Подставляем пароль в api-юнит (на случай если бэк читает .env из CWD)
cp "$SITE_DIR/deploy/crmks-api.service" /etc/systemd/system/
cp "$SITE_DIR/deploy/crmks-watchdog.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable crmks-api crmks-watchdog
systemctl restart crmks-api crmks-watchdog
info "Сервисы crmks-api и crmks-watchdog установлены и запущены"

# Nginx (только если указан домен)
if [ -n "$DOMAIN" ]; then
    # Подставляем домен в конфиг
    sed "s/__DOMAIN__/$DOMAIN/g" "$SITE_DIR/deploy/nginx-crmks.conf" > /etc/nginx/sites-available/$APP_NAME
    ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx
    info "Nginx настроен для $DOMAIN"
    warn "SSL-сертификат НЕ получен. После настройки DNS выполните:"
    warn "  sudo certbot --nginx -d $DOMAIN"
else
    warn "Домен не указан — Nginx не настроен. API доступен на http://localhost:8000"
fi

# Файрвол
ufw allow 'Nginx Full' >/dev/null 2>&1 || true
ufw allow OpenSSH >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true
info "Файрвол настроен"

#==============================================================================
# Итог
#==============================================================================
echo ""
echo "=============================================="
echo -e "${GREEN}✓ УСТАНОВКА ЗАВЕРШЕНА${NC}"
echo "=============================================="
echo ""
echo "СЛЕДУЮЩИЕ ШАГИ:"
echo ""
echo "1. Заполни API-ключи в $BACKEND_ENV:"
echo "   KIMI_API_KEY, CF_*, SERPAPI_KEY"
echo "   Затем: sudo systemctl restart crmks-api"
echo ""
echo "2. Проверь сервисы:"
echo "   sudo systemctl status crmks-api crmks-watchdog"
echo "   sudo journalctl -u crmks-api -f"
echo "   sudo journalctl -u crmks-watchdog -f"
echo ""
if [ -n "$DOMAIN" ]; then
echo "3. Получи SSL-сертификат (после настройки DNS):"
echo "   sudo certbot --nginx -d $DOMAIN"
echo ""
echo "4. Открой: https://$DOMAIN"
else
echo "3. API доступен на http://localhost:8000/docs"
fi
echo ""
echo "Пароли сохранены в:"
echo "  /root/${APP_NAME}_db_password.txt"
echo "  /root/${APP_NAME}_redis_password.txt"
echo ""
echo "Для обновления кода в будущем: sudo bash $SITE_DIR/deploy/update.sh"
