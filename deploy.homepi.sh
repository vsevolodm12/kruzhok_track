#!/bin/bash
set -e

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

[ "$EUID" -ne 0 ] && fail "Запусти от root: sudo bash deploy.homepi.sh"

REPO_URL="https://github.com/vsevolodm12/kruzhok_track.git"
DEPLOY_DIR="/opt/kruzhok"
BACKEND_DIR="$DEPLOY_DIR/backend"

# ─────────────────────────────────────────────────────────────────────────────
step "1/5  Проверка зависимостей"
# ─────────────────────────────────────────────────────────────────────────────

command -v docker  >/dev/null 2>&1 || fail "docker не установлен"
command -v git     >/dev/null 2>&1 || fail "git не установлен"
docker compose version >/dev/null 2>&1 || fail "docker compose (v2) не установлен"
ok "docker, git, docker compose — есть"

# ─────────────────────────────────────────────────────────────────────────────
step "2/5  Клонирование / обновление репозитория"
# ─────────────────────────────────────────────────────────────────────────────

if [ -d "$DEPLOY_DIR/.git" ]; then
  info "Репозиторий уже есть — обновляю"
  git -C "$DEPLOY_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$DEPLOY_DIR"
fi
ok "Код в $DEPLOY_DIR"

# ─────────────────────────────────────────────────────────────────────────────
step "3/5  Настройка .env"
# ─────────────────────────────────────────────────────────────────────────────

cd "$BACKEND_DIR"

if [ ! -f .env ]; then
  SECRET=$(python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits+'!@#%^&*') for _ in range(50)))")
  printf 'SECRET_KEY=%s\nDEBUG=False\nALLOWED_HOSTS=kruzhoktrack.ru,www.kruzhoktrack.ru\nPOSTGRES_PASSWORD=ЗАМЕНИ_НА_НАДЁЖНЫЙ_ПАРОЛЬ\nTELEGRAM_BOT_TOKEN=ЗАМЕНИ_НА_ТОКЕН_ОТ_BOTFATHER\nCLOUDFLARE_TUNNEL_TOKEN=ЗАМЕНИ_НА_TUNNEL_TOKEN\n' "$SECRET" > .env
  ok "Файл .env создан"
else
  warn ".env уже существует — не трогаю"
fi

echo ""
warn "Сейчас откроется редактор. Заполни три поля:"
warn "  POSTGRES_PASSWORD       — придумай пароль"
warn "  TELEGRAM_BOT_TOKEN      — токен от @BotFather"
warn "  CLOUDFLARE_TUNNEL_TOKEN — токен из Cloudflare (см. инструкцию ниже)"
echo ""
echo -e "  ${BOLD}Как получить CLOUDFLARE_TUNNEL_TOKEN:${NC}"
echo "  1. Зайди на dash.cloudflare.com → Zero Trust"
echo "  2. Networks → Tunnels → Create a tunnel"
echo "  3. Выбери Cloudflared → имя: kruzhok → Next"
echo "  4. Скопируй токен из команды (длинная строка после --token)"
echo "  5. На вкладке Public Hostnames добавь:"
echo "     Domain: kruzhoktrack.ru  →  Service: http://nginx:80"
echo ""
read -p "  Нажми Enter чтобы открыть .env..." _
nano .env

grep -q "ЗАМЕНИ_НА" .env && fail "В .env остались незаполненные поля. Запусти скрипт снова."
ok ".env заполнен"

# ─────────────────────────────────────────────────────────────────────────────
step "4/5  Запуск контейнеров"
# ─────────────────────────────────────────────────────────────────────────────

info "Собираю и запускаю..."
docker compose -f docker-compose.homepi.yml up -d --build

info "Жду 20 секунд (миграции Django)..."
sleep 20

echo ""
docker compose -f docker-compose.homepi.yml ps
echo ""

# Проверяем что cloudflared живой
if docker compose -f docker-compose.homepi.yml ps cloudflared | grep -q "Up\|running"; then
  ok "Cloudflare Tunnel запущен"
else
  warn "cloudflared не поднялся — проверь токен:"
  docker compose -f docker-compose.homepi.yml logs cloudflared --tail=20
fi

# ─────────────────────────────────────────────────────────────────────────────
step "5/5  Создание суперюзера Django Admin"
# ─────────────────────────────────────────────────────────────────────────────

docker compose -f docker-compose.homepi.yml exec web python manage.py createsuperuser

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║         Деплой завершён успешно!         ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Сайт:         ${CYAN}https://kruzhoktrack.ru${NC}"
echo -e "  Django Admin: ${CYAN}https://kruzhoktrack.ru/admin/${NC}"
echo ""
echo -e "  ${YELLOW}Следующие шаги:${NC}"
echo "  1. /admin/ → Core → Courses → webhook secret для каждого курса"
echo "  2. /admin/ → Core → Deadlines → добавь дедлайны"
echo "  3. BotFather → Web App URL → https://kruzhoktrack.ru"
echo ""
echo -e "  ${YELLOW}Полезные команды:${NC}"
echo "  Логи:    docker compose -f /opt/kruzhok/backend/docker-compose.homepi.yml logs -f"
echo "  Статус:  docker compose -f /opt/kruzhok/backend/docker-compose.homepi.yml ps"
echo "  Стоп:    docker compose -f /opt/kruzhok/backend/docker-compose.homepi.yml down"
echo ""
