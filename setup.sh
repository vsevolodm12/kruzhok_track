#!/bin/bash
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
info() { echo -e "${CYAN}→${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
step() { echo -e "\n${BOLD}── $1${NC}"; }

[ "$EUID" -ne 0 ] && fail "Запусти от root: sudo bash setup.sh"

BACKEND="/opt/kruzhok/backend"

# ─────────────────────────────────────────────────────────────────────────────
step "1. Обновление кода"
# ─────────────────────────────────────────────────────────────────────────────
[ ! -d /opt/kruzhok ] && fail "/opt/kruzhok не найден. Сначала: git clone https://github.com/vsevolodm12/kruzhok_track.git /opt/kruzhok"
git -C /opt/kruzhok pull --ff-only
ok "Код обновлён"

# ─────────────────────────────────────────────────────────────────────────────
step "2. Проверка .env"
# ─────────────────────────────────────────────────────────────────────────────
[ ! -f "$BACKEND/.env" ] && fail ".env не найден в $BACKEND"
grep -q "ЗАМЕНИ_НА" "$BACKEND/.env" && fail "В .env остались незаполненные поля"
ok ".env в порядке"

# ─────────────────────────────────────────────────────────────────────────────
step "3. Остановка старых контейнеров"
# ─────────────────────────────────────────────────────────────────────────────
cd "$BACKEND"
docker compose down 2>/dev/null || true
ok "Остановлено"

# ─────────────────────────────────────────────────────────────────────────────
step "4. Получение SSL-сертификата (Let's Encrypt)"
# ─────────────────────────────────────────────────────────────────────────────
read -p "  Email для Let's Encrypt: " CERT_EMAIL
[ -z "$CERT_EMAIL" ] && fail "Email не может быть пустым"

mkdir -p certbot/conf certbot/www

# Временно ставим HTTP-only nginx — без него certbot не запустится
cp nginx.conf nginx.conf.ssl
cp nginx.conf.bootstrap nginx.conf
info "nginx → HTTP-only режим"

docker compose up -d db web nginx
info "Жду 20 сек (миграции Django)..."
sleep 20

info "Запрашиваю сертификат..."
docker compose run --rm certbot certonly --webroot \
  -w /var/www/certbot \
  -d kruzhoktrack.ru -d www.kruzhoktrack.ru \
  --email "$CERT_EMAIL" --agree-tos --no-eff-email \
  || { cp nginx.conf.ssl nginx.conf; fail "Certbot не смог получить сертификат. Проверь что порты 80/443 проброшены на малинку."; }

ok "Сертификат получен"

# ─────────────────────────────────────────────────────────────────────────────
step "5. Запуск с SSL"
# ─────────────────────────────────────────────────────────────────────────────
cp nginx.conf.ssl nginx.conf
info "nginx → SSL режим"

docker compose restart nginx
docker compose up -d certbot
ok "Все сервисы запущены"

sleep 5
echo ""
docker compose ps

# ─────────────────────────────────────────────────────────────────────────────
step "6. Создание суперюзера Django Admin"
# ─────────────────────────────────────────────────────────────────────────────
docker compose exec web python manage.py createsuperuser

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}Готово!${NC}"
echo -e "  Сайт:         ${CYAN}https://kruzhoktrack.ru${NC}"
echo -e "  Django Admin: ${CYAN}https://kruzhoktrack.ru/admin/${NC}"
echo ""
echo -e "  Логи:   docker compose -C $BACKEND logs -f"
echo -e "  Статус: docker compose -C $BACKEND ps"
