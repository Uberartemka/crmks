#!/bin/bash
#==============================================================================
# Обновление frontcrm на сервере (повторный деплой).
# Запускать: sudo bash deploy/update.sh
#
# Что делает:
#   1. git pull
#   2. pip install -r requirements.txt
#   3. npm ci && npm run build  (фронт)
#   4. apply_all() миграции БД
#   5. systemctl restart crmks-api crmks-watchdog
#==============================================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
info()  { echo -e "${GREEN}✓${NC} $1"; }
step()  { echo -e "\n${YELLOW}=== $1 ===${NC}"; }

SITE_DIR="/var/www/crmks"
VENV_DIR="$SITE_DIR/backend/venv"
APP_USER="crmks"

# Подгрузить DATABASE_URL для миграций
set -a; [ -f "$SITE_DIR/backend/.env" ] && source "$SITE_DIR/backend/.env"; set +a

step "1/5. git pull"
cd "$SITE_DIR"
sudo -u "$APP_USER" git pull --ff-only
info "Код обновлён"

step "2/5. Python-зависимости"
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -r "$SITE_DIR/backend/requirements.txt" --quiet
info "Зависимости обновлены"

step "3/5. Сборка фронта"
if [ -f "$SITE_DIR/package.json" ]; then
    sudo -u "$APP_USER" bash -c "cd $SITE_DIR && npm ci --silent && npm run build"
    info "Фронт пересобран"
else
    warn "package.json не найден — пропускаем"
fi

step "4/5. Миграции БД"
sudo -u "$APP_USER" bash -c "cd $SITE_DIR/backend && $VENV_DIR/bin/python -c 'from migrations.runner import apply_all; apply_all(\"$DATABASE_URL\")'" \
    || echo -e "${YELLOW}⚠${NC} Миграция завершилась с ошибкой — проверьте логи"
info "Миграции применены"

step "5/5. Перезапуск сервисов"
systemctl restart crmks-api crmks-watchdog
sleep 2
if systemctl is-active --quiet crmks-api && systemctl is-active --quiet crmks-watchdog; then
    info "Сервисы перезапущены и активны"
else
    echo "✗ Один из сервисов не поднялся. Проверь:"
    echo "  sudo systemctl status crmks-api crmks-watchdog"
    echo "  sudo journalctl -u crmks-api -n 30"
    exit 1
fi

echo ""
info "Деплой завершён. Проверь: curl -s http://127.0.0.1:8000/ | head -1"
