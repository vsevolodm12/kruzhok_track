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
- 6 928 студентов, 98 курсов, 14 051 зачисление — импортированы из Google Sheets
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
- `.env` — все секреты (SECRET_KEY, POSTGRES_PASSWORD, TELEGRAM_BOT_TOKEN, GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SHEETS_SPREADSHEET_ID)
- `credentials/service-account.json` — Google Service Account для импорта из Sheets

### Домен
- `kruzhoktrack.ru` — куплен, прописан в `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `nginx.conf`

---

## Ошибки найденные и исправленные (2026-02-25)

### 1. Неверное имя поля тарифа при парсинге вебхуков
**Файл:** `webhooks/services.py`

**Проблема:** ZenClass передаёт поле тарифа как `tarif_id` / `tarif_name` (одна `f`), а в коде было `payload.get('tariff_id')` / `payload.get('tariff_name')` (две `f`). В результате тариф никогда не сохранялся в `Enrollment`.

**Исправлено:** во всех четырёх функциях (`process_task_accepted`, `process_task_submitted`, `process_user_subscribed`, `process_payment_accepted`) заменено на `tarif_id` / `tarif_name`.

### 2. Вебхуки о покупке/зачислении не приходили вовсе
**Проблема:** В ZenClass была настроена отправка только события `lesson_task_accepted`. События `product_user_subscribed` и `payment_accepted` не были добавлены в автоматизацию.

**Исправлено:** Настроить в ZenClass (Автоматизации → HTTP-уведомление):
- `product_user_subscribed` → `https://kruzhoktrack.ru/webhook/zenclass/`
- `payment_accepted` → `https://kruzhoktrack.ru/webhook/zenclass/`

Один URL принимает **все типы событий** — ZenClass различает их по полю `event_name` в теле запроса.

### 3. Google Sheets credentials не были на сервере
**Проблема:** Файл сервисного аккаунта Google (`service-account.json`) и переменные окружения не были скопированы на продовый сервер — команды импорта падали с `FileNotFoundError`.

**Исправлено:** Файл загружен в `/opt/kruzhok/backend/credentials/`, в `.env` добавлены:
```
GOOGLE_SERVICE_ACCOUNT_FILE=/app/credentials/service-account.json
GOOGLE_SHEETS_SPREADSHEET_ID=12khQ9s3xUNH4iE7NQl3B-qGTmce9ghvwE7sSPYqkink
```

### 4. Дубликаты курсов в БД
**Проблема:** `import_students` создаёт курсы по **названию** (синтетический UUID5), а `import_courses` — по **UUID из заголовка листа** (реальный ZenClass ID). Если оба импорта запускались для одного курса — создавались два `Course` с одним именем. Дополнительно: в ZenClass несколько продуктов с одинаковым названием (разные потоки) — это нормально, они хранятся как отдельные записи с разными zenclass_id.

**Статус:** Дубликаты присутствуют в БД, критичных проблем не вызывают. При дальнейших вебхуках `get_or_create_course` ищет сначала по `zenclass_id`, поэтому новые зачисления будут попадать в правильный курс.

### 5. Новые курсы не попали в интеграцию Google Sheets
**Проблема:** Листы новых курсов (например "Интенсив к Ломоносов по истории 25/26") в Google Sheets были пустыми — интеграция ZenClass→Sheets не распространяется на новые курсы автоматически. Требует переподключения интеграции.

**Решение:** Для свежих зачислений использовать вебхуки (теперь настроены). Либо переподключить интеграцию Google Sheets в ZenClass (удалить и создать заново).

---

## Изменения и ошибки (2026-02-26)

### 1. Секреты вебхуков переделаны на per-course

**Контекст:** ZenClass ограничивает количество HTTP-автоматизаций в одном окне, поэтому каждый курс настраивается отдельно. Для зачисления студентов (global automation) один секрет остаётся.

**Изменена архитектура:**
- **Раньше:** два глобальных секрета из `.env`: `WEBHOOK_SECRET_TASKS` и `WEBHOOK_SECRET_ENROLLMENT`
- **Теперь:** `WEBHOOK_SECRET_TASKS` удалён. Для task-событий (`lesson_task_*`, `access_to_course_expired`) — секрет берётся из `CourseWebhookSecret` в БД по `course_id` из payload. Для enrollment-событий (`product_user_subscribed`, `payment_accepted`) — по-прежнему глобальный `WEBHOOK_SECRET_ENROLLMENT`.

**Файлы:** `webhooks/services.py`, `webhooks/views.py`, `config/settings.py`

**Как настраивать:** Admin → Core → Секреты вебхуков курсов → выбрать курс → вставить секрет из ZenClass (Автоматизации → HTTP-уведомление → поле «Секретный ключ»). Если секрет не добавлен — вебхук отклоняется с 403.

---

### 2. CourseWebhookSecret не отображался в Django Admin

**Проблема:** Модель была зарегистрирована только как inline внутри CourseAdmin, но не как отдельный раздел. В главном меню Admin раздел «Секреты вебхуков курсов» отсутствовал.

**Исправлено:** добавлен `@admin.register(CourseWebhookSecret)` в `core/admin.py` — теперь доступен как отдельный раздел Core.

**Файл:** `core/admin.py`

---

### 3. Новые курсы (25/26) не создавались при enrollment-вебхуках

**Проблема:** ZenClass присылал `product_user_subscribed` с `"user_email": null`. Функция `process_user_subscribed` делала `if not all([user_email, product_id]): return None` — и выходила не создав курс. В итоге "Интенсив к МОШ по истории 25/26" никогда не попал в БД, хотя вебхук был принят и залогирован.

Это подтверждено запросом к WebhookLog: payload содержал `"user_email": null` и нормальный `product_id`.

**Исправлено:** в `process_user_subscribed` и `process_payment_accepted` курс теперь создаётся всегда при наличии `product_id`. Студент и зачисление создаются только если есть email, иначе пишется warning в лог.

**Файл:** `webhooks/services.py`

**Доп. действие:** курс "Интенсив к МОШ по истории 25/26" создан вручную в БД командой `get_or_create`:
```
zenclass_id: 7dc97b81-9d45-4d95-9972-71a8c3d1da42
```

---

## Состояние сервера (2026-02-26)

- **URL:** `https://kruzhoktrack.ru`
- **VPS:** `root@45.10.245.122`
- **Проект на сервере:** `/opt/kruzhok/backend/`

### Вход на сервер (с ноутбука Севы)

```bash
ssh -i ~/.ssh/id_ed25519_seva root@45.10.245.122
```

> SSH-ключ: `~/.ssh/id_ed25519_seva` (файл `id_ed25519_seva` в папке `.ssh`)

### Команды управления (выполнять на сервере)

```bash
cd /opt/kruzhok/backend

docker compose up -d --build   # пересборка и перезапуск
docker compose logs web        # логи Django (последние записи)
docker compose logs web -f     # логи в реальном времени
docker compose down            # остановка всех контейнеров
docker compose ps              # статус контейнеров
```

### Деплой новой версии (с ноутбука)

```bash
# 1. На ноутбуке: закоммитить и запушить изменения
git add -p && git commit -m "..." && git push origin main

# 2. На сервере: обновить и пересобрать
ssh -i ~/.ssh/id_ed25519_seva root@45.10.245.122 \
  "cd /opt/kruzhok/backend && git pull origin main && docker compose up -d --build"
```

### Импорт студентов из Google Sheets

```bash
docker exec backend-web-1 python manage.py import_courses --dry-run
docker exec backend-web-1 python manage.py import_courses
```

---

## Настройка ZenClass — чеклист

- [x] Вебхук `lesson_task_accepted` настроен и работает (49 событий получено)
- [x] Вебхук `product_user_subscribed` добавлен в автоматизацию
- [ ] Проверить что `product_user_subscribed` реально приходит (ждём новую покупку)
- [ ] Для каждого активного курса добавить секрет в Admin → Core → Секреты вебхуков курсов

---

## Проблемные места

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

#### ⚠️ Секреты вебхуков ZenClass (per-course)

**Архитектура секретов:**
- **Зачисление** (`product_user_subscribed`, `payment_accepted`) — один глобальный секрет `WEBHOOK_SECRET_ENROLLMENT` в `.env`. Одна автоматизация в ZenClass на все курсы.
- **Оценки** (`lesson_task_accepted`, `lesson_task_submitted_for_review`) — отдельный секрет для каждого курса в БД. ZenClass ограничивает количество HTTP-уведомлений в одном окне, поэтому каждый курс — своя автоматизация.

**Добавить секрет для курса:**
`/admin/` → **Core → Секреты вебхуков курсов → Добавить**
- Выбрать курс
- Вставить секретный ключ из ZenClass (Автоматизации → HTTP-уведомление → поле «Секретный ключ»)

Если секрет не настроен — вебхук будет отклонён с ошибкой 403 и предупреждением в логах.

---

## TODO

- [ ] Дождаться первой реальной покупки и убедиться что `product_user_subscribed` пришёл и студент создался
- [ ] Проверить авторизацию через Telegram Mini App
- [ ] Заполнить расписание занятий для активных курсов (через Admin)
- [ ] Заполнить дедлайны для активных курсов (через Admin)
- [ ] Добавить per-course секреты для активных курсов (Admin → Core → Секреты вебхуков курсов)
- [ ] Настроить BotFather: Web App URL → `https://kruzhoktrack.ru`
- [ ] Переподключить интеграцию Google Sheets в ZenClass чтобы новые курсы попали в таблицу
