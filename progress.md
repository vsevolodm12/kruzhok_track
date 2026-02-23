# Прогресс разработки — Кружок TMA

## Архитектура

```
ZenClass (LMS) → webhooks → Django Backend → PostgreSQL
Google Sheets  → импорт студентов → PostgreSQL
Django         → отдаёт index.html (SPA) + REST API
React SPA      → Telegram Mini App (один VPS, один домен)
```

**Стек:** Django 5 + PostgreSQL 16 + React 18 (CDN, без сборки) + Tailwind CDN + Recharts + Docker + Nginx + Certbot

---

## Готово

### Данные в БД
- 6 924 студента, 96 курсов, 14 049 зачислений — импортированы из Google Sheets
- Суперюзер Django Admin: `seva / 1712`

### Backend — Модели (`core/models.py`)
- `Student` — email, telegram_id, name
- `Course` — name, zenclass_id
- `Enrollment` — студент↔курс (active/expired)
- `Task` — задание (тип HW/MOCK/ESSAY/PROJECT, max_score)
- `Grade` — оценка (score, teacher_comment, status)
- `ScheduleEvent` — расписание (title, scheduled_at, duration_minutes)
- `Deadline` — дедлайны (title, due_date, submitted)
- `CourseWebhookSecret` — секрет вебхука per-course (хранится в БД, управляется через Admin)
- `WebhookLog` — лог для идемпотентности по webhook_id
- Миграции: `0001_initial`, `0002_scheduleevent_duration_minutes_deadline_submitted`

### Backend — API endpoints (`core/urls.py`)
| Endpoint | Метод | Описание |
|---|---|---|
| `/` | GET | Отдаёт React SPA (`index.html`) |
| `/auth/email/` | POST | Авторизация по email |
| `/auth/telegram/` | POST | Авторизация через TMA initData |
| `/auth/logout/` | GET | Выход (flush сессии → редирект на `/`) |
| `/api/me/` | GET | Текущий студент (email, name) |
| `/api/courses/` | GET | Курсы студента |
| `/api/grades/` | GET | Все оценки студента |
| `/api/schedule/` | GET | Расписание по всем курсам |
| `/api/deadlines/` | GET | Дедлайны по всем курсам |
| `/api/update-name/` | POST | Смена отображаемого имени |
| `/webhook/zenclass/` | POST | Вебхук от ZenClass |

### Backend — Вебхуки ZenClass (`webhooks/`)
- Верификация подписи: `SHA1(secret + '&' + webhook_id + '&' + timestamp)` — амперсанды обязательны
- Идемпотентность по `webhook_id` через `WebhookLog`
- `lesson_task_accepted` → сохраняет оценку, шлёт Telegram-уведомление
- `lesson_task_submitted_for_review` → статус «На проверке»
- `product_user_subscribed`, `payment_accepted` → зачисление на курс
- `access_to_course_expired` → пометка enrollment как expired

### Backend — Авторизация
- Email-first: студент вводит email → сессия → загружаются данные
- TG fallback: если открыто через Telegram — пробует initData HMAC-SHA256
- Сессия живёт 30 дней, `SESSION_COOKIE_SAMESITE='None'` для работы в iframe Telegram

### Frontend — React SPA (`backend/index.html`)
- Подаётся Django на `/`, никакого отдельного деплоя
- React 18 + Babel standalone (без npm/webpack), Tailwind CDN, Recharts CDN
- Auth state machine: `loading → need_email / authorized`
- **Home**: активность (кол-во работ, средний балл), расписание курса (4 ближайших занятия), дедлайны 7 дней
- **Stats**: табы HW/MOCK/ESSAY/PROJECT, Line/Bar chart, список работ с diff-индикаторами
- **History**: все проверенные работы с фильтром по типу
- **Schedule**: полное расписание с табами по месяцам, статус (сегодня/прошедшее)
- **Deadlines**: все дедлайны сгруппированы по срочности
- Тёмная/светлая тема, инлайн-редактирование имени, смена курса
- Email в шапке → попап с кнопкой «Выйти из аккаунта» (закрывается по клику вне)

### Инфраструктура
- `Dockerfile` — Python 3.12-slim, gunicorn
- `docker-compose.yml` — прод (PostgreSQL + Django/gunicorn + Nginx + Certbot)
- `docker-compose.dev.yml` — локальная разработка (Django dev server, порт 8000 открыт)
- `nginx.conf` — HTTP→HTTPS редирект, SSL TLS 1.2/1.3, proxy к Django, `/static/` → файловая система
- `.env` — все секреты (SECRET_KEY, POSTGRES_PASSWORD, TELEGRAM_BOT_TOKEN, etc.)

### Домен
- `kruzhoktrack.ru` — куплен, прописан в `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `nginx.conf`

---

## В работе

_(пусто)_

---

## Следующий этап — Деплой на VPS

### Что нужно

1. **VPS с публичным IP** (минимум 1 CPU / 1 GB RAM)
   - Hetzner CX11 ~4€/мес, DigitalOcean Droplet ~6$/мес, Timeweb ~300₽/мес
   - ОС: Ubuntu 22.04

2. **DNS — A-запись домена**
   - У регистратора: `kruzhoktrack.ru → IP_сервера` и `www.kruzhoktrack.ru → IP_сервера`
   - Propagation до 24ч, обычно 5–15 минут

3. **На сервере установить:** `docker`, `docker-compose`, `git`

4. **Скопировать проект:** `git clone` или `scp`

5. **Настроить `.env` для прода:**
   ```
   DEBUG=False
   SECRET_KEY=<сгенерировать новый>
   ALLOWED_HOSTS=kruzhoktrack.ru,www.kruzhoktrack.ru
   POSTGRES_PASSWORD=<надёжный пароль>
   TELEGRAM_BOT_TOKEN=<токен>
   ```

6. **Получить SSL-сертификат** (см. проблемное место ниже)

7. **Запустить:** `docker-compose up -d`

---

### Проблемные места

#### ⚠️ SSL — курица и яйцо
**Проблема:** `nginx.conf` требует SSL-сертификат при старте. Но certbot не может получить сертификат через `/.well-known/acme-challenge/`, пока nginx не запущен. Круговая зависимость.

**Решение — bootstrap-процедура:**

Шаг 1: временно подменить nginx.conf на HTTP-only (без 443-блока):
```nginx
server {
    listen 80;
    server_name kruzhoktrack.ru www.kruzhoktrack.ru;
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    location / {
        proxy_pass http://web:8000;
    }
}
```

Шаг 2: запустить только db + web + nginx:
```bash
docker-compose up -d db web nginx
```

Шаг 3: получить сертификат:
```bash
docker-compose run --rm certbot certonly --webroot \
  -w /var/www/certbot \
  -d kruzhoktrack.ru -d www.kruzhoktrack.ru \
  --email your@email.com --agree-tos --no-eff-email
```

Шаг 4: вернуть оригинальный `nginx.conf` и перезапустить:
```bash
docker-compose restart nginx
docker-compose up -d certbot   # автообновление сертификата каждые 12ч
```

---

#### ⚠️ DEBUG=False — нужна collectstatic
При `DEBUG=False` Django не отдаёт static-файлы сам — это делает Nginx.
В `docker-compose.yml` команда уже включает `collectstatic --noinput`, всё должно работать автоматически.

---

#### ⚠️ Дедлайны — нужно заполнить вручную
Дедлайны не приходят из ZenClass через вебхуки — их нужно добавлять через Django Admin:
`/admin/` → **Core → Deadlines → Add deadline**

---

#### ⚠️ Секреты вебхуков ZenClass
Для каждого активного курса нужно добавить секрет в Admin:
`/admin/` → **Core → Courses → [курс] → Webhook Secret**
Секрет берётся из настроек автоматизации ZenClass.

---

## TODO после деплоя

- [ ] Протестировать вебхуки ZenClass в проде
- [ ] Проверить авторизацию через Telegram Mini App
- [ ] Заполнить расписание занятий для активных курсов (через Admin)
- [ ] Заполнить дедлайны для активных курсов (через Admin)
- [ ] Добавить секреты вебхуков для активных курсов (через Admin)
- [ ] Настроить BotFather: Web App URL → `https://kruzhoktrack.ru`
