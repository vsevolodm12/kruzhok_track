# Кружок — Telegram Mini App для трекинга прогресса учеников

Веб-приложение для отслеживания прогресса учеников онлайн-школы по подготовке к олимпиадам. Работает как Telegram Mini App.

---

## Как это работает

### Общая схема

```
┌─────────────┐     webhook      ┌─────────────┐
│  ZenClass   │ ───────────────► │   Backend   │
│  (LMS)      │  оценки, оплаты  │  (Django)   │
└─────────────┘                  └──────┬──────┘
                                        │
┌─────────────┐     одноразово   ┌──────▼──────┐
│Google Sheets│ ───────────────► │ PostgreSQL  │
│(от ZenClass)│   импорт         │    (БД)     │
└─────────────┘   студентов      └──────┬──────┘
                                        │
                                 ┌──────▼──────┐
                                 │  Telegram   │
                                 │  Mini App   │
                                 │  (ученики)  │
                                 └─────────────┘
```

### Поток данных

1. **Импорт студентов (один раз):**
   - ZenClass автоматически синхронизирует данные в Google Sheets
   - Мы запускаем `python manage.py import_students`
   - В БД создаются записи: Student (email, имя) и Course (названия курсов)
   - После этого Google Sheets больше не нужен

2. **Вебхуки от ZenClass (постоянно):**
   - Учитель проверяет задание → ZenClass отправляет webhook → мы сохраняем оценку
   - Ученик покупает курс → webhook → создаём подписку
   - Доступ истёк → webhook → помечаем подписку как завершённую

3. **Авторизация ученика:**
   - Ученик открывает Mini App из Telegram
   - Telegram передаёт initData (id пользователя, имя)
   - Если telegram_id уже привязан к Student — сразу показываем dashboard
   - Если нет — просим ввести email, ищем в БД, привязываем

4. **Уведомления:**
   - При получении оценки бот отправляет сообщение ученику в Telegram

---

## Структура проекта

```
backend/
├── config/                 # Настройки Django
│   ├── settings.py         # Конфигурация
│   ├── urls.py             # Роутинг
│   └── wsgi.py
├── core/                   # Основное приложение
│   ├── models.py           # Модели данных
│   ├── views.py            # Страницы и API
│   ├── admin.py            # Админ-панель
│   ├── services/           # Сервисы
│   │   ├── telegram.py     # Авторизация и уведомления
│   │   └── google_sheets.py# Импорт данных
│   └── management/commands/
│       └── import_students.py  # Команда импорта
├── webhooks/               # Обработка вебхуков ZenClass
│   ├── views.py            # Endpoint /webhook/zenclass/
│   └── services.py         # Логика обработки
├── templates/              # HTML шаблоны
├── docker-compose.yml      # Продакшн
├── docker-compose.dev.yml  # Разработка
└── .env.example            # Пример переменных окружения
```

---

## Модели данных

### Student (Ученик)
| Поле | Тип | Описание |
|------|-----|----------|
| email | Email | Уникальный идентификатор (из ZenClass) |
| name | String | ФИО |
| telegram_id | BigInt | ID в Telegram (после привязки) |
| zenclass_id | UUID | ID в ZenClass |

### Course (Курс)
| Поле | Тип | Описание |
|------|-----|----------|
| name | String | Название курса |
| zenclass_id | UUID | ID в ZenClass |

### Enrollment (Подписка на курс)
| Поле | Тип | Описание |
|------|-----|----------|
| student | FK | Ученик |
| course | FK | Курс |
| status | Enum | active / expired |

### Task (Задание)
| Поле | Тип | Описание |
|------|-----|----------|
| name | String | Название |
| course | FK | Курс |
| task_type | Enum | homework / mock / essay / project |
| max_score | Int | Максимальный балл |
| zenclass_id | UUID | ID в ZenClass |

### Grade (Оценка)
| Поле | Тип | Описание |
|------|-----|----------|
| student | FK | Ученик |
| task | FK | Задание |
| value | Int | Балл (может быть null = зачёт) |
| teacher_comment | Text | Комментарий учителя |
| status | Enum | submitted / accepted |
| checked_at | DateTime | Дата проверки |

### ScheduleEvent (Расписание занятий)
| Поле | Тип | Описание |
|------|-----|----------|
| course | FK | Курс |
| title | String | Название занятия |
| scheduled_at | DateTime | Дата и время |

### Deadline (Дедлайны)
| Поле | Тип | Описание |
|------|-----|----------|
| course | FK | Курс |
| title | String | Название |
| due_date | DateTime | Срок сдачи |

---

## Вебхуки ZenClass

Сервер принимает POST-запросы на `/webhook/zenclass/`

### Поддерживаемые события

| Событие | event_name | Что происходит |
|---------|------------|----------------|
| Задание принято | `lesson_task_accepted` | Парсим оценку из комментария, сохраняем, отправляем уведомление |
| Задание на проверке | `lesson_task_submitted_for_review` | Создаём Grade со статусом "На проверке" |
| Подписка на курс | `product_user_subscribed` | Создаём Enrollment |
| Оплата | `payment_accepted` | Подтверждаем Enrollment |
| Доступ истёк | `access_to_course_expired` | Меняем статус Enrollment на expired |

### Парсинг оценок

ZenClass не передаёт оценку отдельным полем — она в комментарии учителя.

Алгоритм:
1. Берём `payload.comment`
2. Ищем число (например "4", "5/5", "Оценка: 4")
3. Если нашли — сохраняем как value
4. Если нет — считаем "зачёт"

### Проверка подписи

Каждый webhook содержит `hash` для проверки подлинности:
```
hash = sha1(SECRET_KEY + "&" + id + "&" + timestamp)
```

---

## Авторизация Telegram

1. При открытии Mini App Telegram передаёт `initData`
2. Бэкенд проверяет подпись (HMAC-SHA256 с токеном бота)
3. Извлекаем `telegram_id` пользователя
4. Если он привязан к Student — авторизуем
5. Если нет — показываем форму ввода email

После ввода email:
1. Ищем Student с таким email в БД
2. Если нашли — привязываем telegram_id
3. Создаём сессию Django

---

## Расписание и дедлайны

**Вносятся вручную через админ-панель Django.**

ZenClass не передаёт эти данные через webhook.

Путь: `/admin/` → Расписание занятий / Дедлайны

---

## Установка и запуск

### Подготовка

1. **Создать бота в Telegram:**
   - Написать @BotFather
   - `/newbot` → следовать инструкциям
   - Сохранить токен

2. **Настроить Google Sheets (для импорта):**
   - В ZenClass: Настройки → Интеграции → Google Sheets
   - Подключить аккаунт Google
   - Таблица "Студенты" создастся автоматически

3. **Создать сервисный аккаунт Google:**
   - Открыть [Google Cloud Console](https://console.cloud.google.com/)
   - Создать проект
   - APIs & Services → Enable APIs → включить "Google Sheets API"
   - Credentials → Create Credentials → Service Account
   - Создать ключ (JSON)
   - Дать этому аккаунту (его email) доступ к таблице ZenClass

### Запуск на VPS

```bash
# 1. Склонировать проект
git clone <repo> /opt/stankevich
cd /opt/stankevich/backend

# 2. Создать .env
cp .env.example .env
nano .env  # заполнить все переменные

# 3. Положить ключ Google (если нужен импорт)
mkdir -p credentials
# скопировать JSON-файл в credentials/service-account.json

# 4. Запустить
docker-compose up -d

# 5. Проверить логи
docker-compose logs -f web

# 6. Создать суперпользователя для админки
docker-compose exec web python manage.py createsuperuser

# 7. Импортировать студентов (один раз)
docker-compose exec web python manage.py import_students --dry-run  # проверить
docker-compose exec web python manage.py import_students             # выполнить
```

### Настройка ZenClass

1. ZenClass → Автоматизация → Создать процесс
2. Триггер: "Задание принято"
3. Действие: "Отправить HTTP-уведомление"
4. URL: `https://your-domain.com/webhook/zenclass/`
5. Сохранить как черновик → открыть снова → скопировать "Секретный ключ"
6. Вставить ключ в `.env` (ZENCLASS_SECRET_KEY)
7. Запустить процесс

Повторить для событий:
- "Студент подписался на продукт"
- "Продукт оплачен"
- "Закончился доступ к курсу"
- "Задание отправлено на проверку" (опционально)

### Настройка Mini App

1. @BotFather → `/newapp`
2. Выбрать бота
3. Web App URL: `https://your-domain.com/`
4. Готово!

---

## Проверка работы

### 1. Проверить что сервер работает
```bash
curl https://your-domain.com/health/
# Ответ: {"status": "ok", "timestamp": "..."}
```

### 2. Проверить вебхук (тестовый запрос)
```bash
curl -X POST https://your-domain.com/webhook/zenclass/ \
  -H "Content-Type: application/json" \
  -d '{"id":"test123","event_name":"test","timestamp":1234567890,"hash":"","payload":{}}'

# Ответ без ZENCLASS_SECRET_KEY: {"status": "ok", ...}
# Ответ с ключом но неверным hash: {"error": "Invalid signature"}
```

### 3. Проверить админку
- Открыть `https://your-domain.com/admin/`
- Войти под суперпользователем
- Проверить что есть модели: Ученики, Курсы, Оценки и т.д.

### 4. Проверить Mini App
- Открыть бота в Telegram
- Нажать кнопку Mini App
- Должна появиться страница авторизации

### 5. Полный тест вебхука
- В ZenClass принять тестовое задание ученика
- Проверить в админке что появилась оценка
- Если у ученика привязан Telegram — он получит уведомление

---

## Локальная разработка

```bash
cd backend
cp .env.example .env
# заполнить .env

# Запустить в dev-режиме
docker-compose -f docker-compose.dev.yml up

# Сервер доступен на http://localhost:8000

# Для тестирования вебхуков нужен публичный URL:
ngrok http 8000
# Использовать полученный URL в ZenClass
```

---

## SSL сертификат (Let's Encrypt)

```bash
# Получить сертификат
docker-compose run --rm certbot certonly --webroot \
  --webroot-path=/var/www/certbot \
  -d your-domain.com

# Раскомментировать HTTPS блок в nginx.conf
nano nginx.conf

# Перезапустить
docker-compose restart nginx
```

---

## Частые вопросы

### Как добавить расписание?
Через админку: `/admin/` → Расписание занятий → Добавить

### Как добавить дедлайн?
Через админку: `/admin/` → Дедлайны → Добавить

### Как обновить список студентов?
Запустить импорт снова:
```bash
docker-compose exec web python manage.py import_students
```
Существующие студенты обновятся, новые добавятся.

### Вебхук не приходит
1. Проверить что процесс автоматизации в ZenClass запущен (не черновик)
2. Проверить URL — должен быть с HTTPS
3. Посмотреть логи: `docker-compose logs -f web`

### Ученик не может привязать email
1. Проверить что студент импортирован (есть в админке)
2. Проверить регистр email (должен совпадать)

---

## Поддержка

Для вопросов и багов: создать Issue в репозитории.
