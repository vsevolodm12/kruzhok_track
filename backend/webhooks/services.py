import hashlib
import logging
from datetime import datetime, timezone as dt_timezone
from django.db import IntegrityError
from core.models import Student, Course, Enrollment, Task, Grade, WebhookLog
from core.services.telegram import TelegramNotificationService

logger = logging.getLogger(__name__)


TASK_EVENTS = {'lesson_task_accepted', 'lesson_task_submitted_for_review', 'access_to_course_expired'}
ENROLLMENT_EVENTS = {'product_user_subscribed', 'payment_accepted'}


def _get_secret_for_event(event_name: str, payload: dict) -> str | None:
    """
    Возвращает секрет для верификации подписи вебхука.

    - Enrollment-события (product_user_subscribed, payment_accepted):
      глобальный WEBHOOK_SECRET_ENROLLMENT из .env — одна автоматизация на все курсы.
    - Task-события (lesson_task_accepted, lesson_task_submitted_for_review, access_to_course_expired):
      per-course секрет из CourseWebhookSecret в БД — каждый курс настраивается отдельно.
    """
    from django.conf import settings
    from core.models import CourseWebhookSecret

    if event_name in ENROLLMENT_EVENTS:
        return settings.WEBHOOK_SECRET_ENROLLMENT or None

    if event_name in TASK_EVENTS:
        course_id = payload.get('course_id')
        if not course_id:
            logger.warning(f"course_id отсутствует в payload для события '{event_name}'")
            return None
        try:
            secret_obj = CourseWebhookSecret.objects.get(course__zenclass_id=course_id)
            return secret_obj.secret_key
        except CourseWebhookSecret.DoesNotExist:
            logger.warning(
                f"Секрет не настроен для курса {course_id} — добавьте через Admin → Core → Секреты вебхуков курсов"
            )
            return None

    return None


def verify_webhook_signature(webhook_id: str, timestamp: int, received_hash: str, event_name: str, payload: dict | None = None) -> bool:
    """
    Проверяет подпись вебхука ZenClass.
    Алгоритм: sha1(secret & webhook_id & timestamp) == hash

    Для task-событий: секрет берётся из CourseWebhookSecret в БД по course_id из payload.
    Для enrollment-событий: глобальный WEBHOOK_SECRET_ENROLLMENT из .env.
    """
    secret = _get_secret_for_event(event_name, payload or {})

    if not secret:
        logger.warning(f"Секрет не настроен для события '{event_name}' — проверьте .env")
        return False

    concatenated = f"{secret}&{webhook_id}&{timestamp}"
    calculated_hash = hashlib.sha1(concatenated.encode()).hexdigest()

    if calculated_hash != received_hash:
        logger.warning(f"Невалидная подпись: expected={calculated_hash}, got={received_hash}")
        return False

    return True


def claim_webhook(webhook_id: str, event_name: str, payload: dict) -> WebhookLog | None:
    """
    Атомарно проверяет идемпотентность и логирует вебхук.
    Возвращает WebhookLog если вебхук новый, None если уже обработан.
    Использует get_or_create + IntegrityError вместо exists() + create()
    для защиты от race condition при конкурентных запросах.
    """
    try:
        log, created = WebhookLog.objects.get_or_create(
            webhook_id=webhook_id,
            defaults={
                'event_name': event_name,
                'payload': payload,
            }
        )
    except IntegrityError:
        # Конкурентная вставка — другой поток уже обработал
        return None

    return log if created else None


def get_or_create_student(user_email: str, user_id: str = None) -> Student:
    """Получает или создаёт ученика по email."""
    email = user_email.lower().strip()

    student, created = Student.objects.get_or_create(
        email=email,
        defaults={
            'name': email.split('@')[0].title(),
            'zenclass_id': user_id,
        }
    )

    if not created and user_id and not student.zenclass_id:
        student.zenclass_id = user_id
        student.save(update_fields=['zenclass_id'])

    if created:
        logger.info(f"Создан новый студент: {email}")

    return student


def get_or_create_course(course_id: str, course_name: str) -> Course:
    """
    Получает или создаёт курс.

    Сначала ищет по zenclass_id (реальный ID из вебхука).
    Если не найден — ищет по имени (мог быть создан импортом с синтетическим UUID)
    и обновляет zenclass_id на реальный.
    """
    try:
        return Course.objects.get(zenclass_id=course_id)
    except Course.DoesNotExist:
        pass

    # Курс мог быть создан импортом с синтетическим zenclass_id — ищем по имени
    try:
        course = Course.objects.get(name=course_name)
        course.zenclass_id = course_id
        course.save(update_fields=['zenclass_id'])
        logger.info(f"Обновлён zenclass_id курса '{course_name}': {course_id}")
        return course
    except Course.DoesNotExist:
        pass

    course = Course.objects.create(zenclass_id=course_id, name=course_name)
    logger.info(f"Создан новый курс: {course_name}")
    return course


def get_or_create_task(task_id: str, task_name: str, course: Course) -> Task:
    """Получает или создаёт задание."""
    task_type = Task.detect_task_type(task_name)

    task, created = Task.objects.get_or_create(
        zenclass_id=task_id,
        defaults={
            'name': task_name,
            'course': course,
            'task_type': task_type,
        }
    )

    if created:
        logger.info(f"Создано новое задание: {task_name} (тип: {task_type})")

    return task


def process_task_accepted(payload: dict, timestamp: int) -> Grade | None:
    """
    Обрабатывает событие lesson_task_accepted.
    Парсит оценку из комментария и сохраняет результат.
    Отправляет уведомление в Telegram.
    """
    user_email = payload.get('user_email')
    user_id = payload.get('user_id')
    course_id = payload.get('course_id')
    course_name = payload.get('course_name', 'Неизвестный курс')
    task_id = payload.get('task_id')
    task_name = payload.get('task_name', 'Задание')
    comment = payload.get('comment', '')
    task_result = payload.get('task_result', 'ok')
    report_link = payload.get('report_link', '')
    tariff_id = payload.get('tarif_id')
    tariff_name = payload.get('tarif_name', '')

    if not all([user_email, course_id, task_id]):
        logger.warning(f"Неполные данные вебхука: email={user_email}, course={course_id}, task={task_id}")
        return None

    student = get_or_create_student(user_email, user_id)
    course = get_or_create_course(course_id, course_name)
    task = get_or_create_task(task_id, task_name, course)

    # Создаём или обновляем связь ученик-курс
    Enrollment.objects.get_or_create(
        student=student,
        course=course,
        defaults={
            'tariff_id': tariff_id,
            'tariff_name': tariff_name,
        }
    )

    # Парсим оценку
    score = None
    max_score = task.max_score

    # Для тестов с автопроверкой: "5/7"
    if task_result and '/' in str(task_result):
        parts = str(task_result).split('/')
        try:
            score = int(parts[0])
            max_score = int(parts[1])
            task.max_score = max_score
            task.save(update_fields=['max_score'])
        except (ValueError, IndexError):
            pass
    elif comment:
        score = Grade.parse_score_from_comment(comment)

    # Создаём или обновляем оценку
    checked_at = datetime.fromtimestamp(timestamp, tz=dt_timezone.utc)

    grade, created = Grade.objects.update_or_create(
        student=student,
        task=task,
        defaults={
            'value': score,
            'teacher_comment': comment,
            'status': Grade.Status.ACCEPTED,
            'report_link': report_link,
            'checked_at': checked_at,
        }
    )

    logger.info(f"{'Создана' if created else 'Обновлена'} оценка: {student.email} - {task_name} = {score}")

    # Отправляем уведомление в Telegram
    if student.telegram_id:
        notification_service = TelegramNotificationService()
        notification_service.notify_grade(
            telegram_id=student.telegram_id,
            course_name=course_name,
            task_name=task_name,
            score=score,
            max_score=max_score
        )
        logger.info(f"Отправлено уведомление: {student.telegram_id}")

    return grade


def process_task_submitted(payload: dict, timestamp: int) -> Grade | None:
    """
    Обрабатывает событие lesson_task_submitted_for_review.
    Создаёт оценку со статусом 'На проверке'.
    """
    user_email = payload.get('user_email')
    user_id = payload.get('user_id')
    course_id = payload.get('course_id')
    course_name = payload.get('course_name', 'Неизвестный курс')
    task_id = payload.get('task_id')
    task_name = payload.get('task_name', 'Задание')
    tariff_id = payload.get('tarif_id')
    tariff_name = payload.get('tarif_name', '')

    if not all([user_email, course_id, task_id]):
        return None

    student = get_or_create_student(user_email, user_id)
    course = get_or_create_course(course_id, course_name)
    task = get_or_create_task(task_id, task_name, course)

    Enrollment.objects.get_or_create(
        student=student,
        course=course,
        defaults={
            'tariff_id': tariff_id,
            'tariff_name': tariff_name,
        }
    )

    grade, created = Grade.objects.get_or_create(
        student=student,
        task=task,
        defaults={
            'status': Grade.Status.SUBMITTED,
        }
    )

    if created:
        logger.info(f"Задание отправлено на проверку: {student.email} - {task_name}")

    return grade


def process_user_subscribed(payload: dict) -> Enrollment | None:
    """Обрабатывает подписку на курс."""
    user_email = payload.get('user_email')
    user_id = payload.get('user_id')
    product_id = payload.get('product_id')
    product_name = payload.get('product_name', 'Курс')
    tariff_id = payload.get('tarif_id')
    tariff_name = payload.get('tarif_name', '')

    if not all([user_email, product_id]):
        return None

    student = get_or_create_student(user_email, user_id)
    course = get_or_create_course(product_id, product_name)

    enrollment, created = Enrollment.objects.update_or_create(
        student=student,
        course=course,
        defaults={
            'tariff_id': tariff_id,
            'tariff_name': tariff_name,
            'status': Enrollment.Status.ACTIVE,
        }
    )

    if created:
        logger.info(f"Новая подписка: {student.email} на {course.name}")

    return enrollment


def process_payment_accepted(payload: dict) -> Enrollment | None:
    """Обрабатывает успешную оплату."""
    user_email = payload.get('user_email')
    user_id = payload.get('user_id')
    product_id = payload.get('product_id')
    product_name = payload.get('product_name', 'Курс')
    tariff_id = payload.get('tarif_id')
    tariff_name = payload.get('tarif_name', '')

    if not all([user_email, product_id]):
        return None

    student = get_or_create_student(user_email, user_id)
    course = get_or_create_course(product_id, product_name)

    enrollment, created = Enrollment.objects.update_or_create(
        student=student,
        course=course,
        defaults={
            'tariff_id': tariff_id,
            'tariff_name': tariff_name,
            'status': Enrollment.Status.ACTIVE,
        }
    )

    logger.info(f"Оплата подтверждена: {student.email} - {course.name}")

    return enrollment


def process_access_expired(payload: dict) -> Enrollment | None:
    """Обрабатывает окончание доступа к курсу."""
    user_email = payload.get('user_email')
    course_id = payload.get('course_id')

    if not all([user_email, course_id]):
        return None

    try:
        student = Student.objects.get(email=user_email.lower())
        course = Course.objects.get(zenclass_id=course_id)
        enrollment = Enrollment.objects.get(student=student, course=course)
        enrollment.status = Enrollment.Status.EXPIRED
        enrollment.save(update_fields=['status'])

        logger.info(f"Доступ истёк: {student.email} - {course.name}")

        return enrollment
    except (Student.DoesNotExist, Course.DoesNotExist, Enrollment.DoesNotExist):
        return None
