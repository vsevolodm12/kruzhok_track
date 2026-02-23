#!/bin/bash
set -e

# ─── Цвета ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${CYAN}→${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
fail() { echo -e "${RED}✗ ОШИБКА:${NC} $1"; exit 1; }
step() { echo -e "\n${BOLD}── $1 ──────────────────────────────────────────${NC}"; }

# ─── Проверка прав ────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
  fail "Запусти скрипт от root: sudo bash deploy.sh"
fi

# ─── Переменные ───────────────────────────────────────────────────────────────
REPO_URL="https://github.com/vsevolodm12/kruzhok_track.git"
DEPLOY_DIR="/opt/kruzhok"
BACKEND_DIR="$DEPLOY_DIR/backend"

# ─────────────────────────────────────────────────────────────────────────────
step "1/7  Проверка зависимостей"
# ─────────────────────────────────────────────────────────────────────────────

command -v docker  >/dev/null 2>&1 || fail "docker не установлен"
command -v git     >/dev/null 2>&1 || fail "git не установлен"
docker compose version >/dev/null 2>&1 || fail "docker compose (v2) не установлен"
ok "docker, git, docker compose — есть"

# ─────────────────────────────────────────────────────────────────────────────
step "2/7  Клонирование репозитория"
# ─────────────────────────────────────────────────────────────────────────────

if [ -d "$DEPLOY_DIR/.git" ]; then
  info "Репозиторий уже есть — обновляю (git pull)"
  git -C "$DEPLOY_DIR" pull --ff-only
else
  info "Клонирую в $DEPLOY_DIR"
  git clone "$REPO_URL" "$DEPLOY_DIR"
fi
ok "Код получен: $DEPLOY_DIR"

# ─────────────────────────────────────────────────────────────────────────────
step "3/7  Настройка .env (секреты)"
# ─────────────────────────────────────────────────────────────────────────────

cd "$BACKEND_DIR"

if [ ! -f .env ]; then
  # Генерируем SECRET_KEY прямо здесь
  SECRET=$(python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits+'!@#\$%^&*') for _ in range(50)))")

  cat > .env << EOF
SECRET_KEY=$SECRET
DEBUG=False
ALLOWED_HOSTS=kruzhoktrack.ru,www.kruzhoktrack.ru
POSTGRES_PASSWORD=ЗАМЕНИ_НА_НАДЁЖНЫЙ_ПАРОЛЬ
TELEGRAM_BOT_TOKEN=ЗАМЕНИ_НА_ТОКЕН_ОТ_BOTFATHER
GOOGLE_SHEETS_SPREADSHEET_ID=
GOOGLE_SERVICE_ACCOUNT_FILE=credentials/service-account.json
EOF
  ok "Файл .env создан (SECRET_KEY уже заполнен)"
else
  warn ".env уже существует — не трогаю"
fi

echo ""
warn "Сейчас откроется редактор. Заполни:"
warn "  POSTGRES_PASSWORD  — придумай пароль"
warn "  TELEGRAM_BOT_TOKEN — токен от @BotFather"
warn "Нажми Ctrl+X → Y → Enter чтобы сохранить и выйти."
echo ""
read -p "  Нажми Enter чтобы открыть .env..." _
nano .env

# Проверяем что обязательные поля заполнены
if grep -q "ЗАМЕНИ_НА" .env; then
  fail "В .env остались незаполненные поля (ЗАМЕНИ_НА_...). Запусти скрипт снова."
fi
ok ".env заполнен"

# ─────────────────────────────────────────────────────────────────────────────
step "4/7  Запрос email для SSL-сертификата"
# ─────────────────────────────────────────────────────────────────────────────

read -p "  Email для Let's Encrypt (уведомления об истечении): " CERT_EMAIL
[ -z "$CERT_EMAIL" ] && fail "Email не может быть пустым"
ok "Email: $CERT_EMAIL"

# ─────────────────────────────────────────────────────────────────────────────
step "5/7  Bootstrap SSL (получение сертификата)"
# ─────────────────────────────────────────────────────────────────────────────

mkdir -p certbot/conf certbot/www

# Временно ставим HTTP-only nginx (без SSL — иначе он не стартует без сертификата)
cp nginx.conf nginx.conf.ssl
cp nginx.conf.bootstrap nginx.conf
info "nginx.conf → HTTP-only (bootstrap режим)"

info "Поднимаю db + web + nginx..."
docker compose up -d db web nginx

info "Жду 20 секунд пока Django выполнит миграции..."
sleep 20

info "Запрашиваю SSL-сертификат у Let's Encrypt..."
docker compose run --rm certbot certonly --webroot \
  -w /var/www/certbot \
  -d kruzhoktrack.ru -d www.kruzhoktrack.ru \
  --email "$CERT_EMAIL" --agree-tos --no-eff-email \
  || fail "Certbot не смог получить сертификат. Проверь что DNS kruzhoktrack.ru → этот сервер."

ok "SSL-сертификат получен"

# Возвращаем рабочий nginx с SSL
cp nginx.conf.ssl nginx.conf
info "nginx.conf → восстановлен (SSL режим)"

docker compose restart nginx
ok "nginx перезапущен с SSL"

# ─────────────────────────────────────────────────────────────────────────────
step "6/7  Финальный запуск всех сервисов"
# ─────────────────────────────────────────────────────────────────────────────

docker compose up -d
ok "Все контейнеры запущены"

info "Жду 10 секунд..."
sleep 10

echo ""
docker compose ps
echo ""

# ─────────────────────────────────────────────────────────────────────────────
step "7/7  Создание суперюзера Django Admin"
# ─────────────────────────────────────────────────────────────────────────────

info "Создаём суперюзера для /admin/ ..."
docker compose exec web python manage.py createsuperuser

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║         Деплой завершён успешно!         ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Сайт:        ${CYAN}https://kruzhoktrack.ru${NC}"
echo -e "  Django Admin: ${CYAN}https://kruzhoktrack.ru/admin/${NC}"
echo ""
echo -e "  Следующие шаги:"
echo -e "  ${YELLOW}1.${NC} /admin/ → Core → Courses → добавь webhook secret для каждого курса"
echo -e "  ${YELLOW}2.${NC} /admin/ → Core → Deadlines → добавь дедлайны вручную"
echo -e "  ${YELLOW}3.${NC} BotFather → Web App URL → https://kruzhoktrack.ru"
echo ""
