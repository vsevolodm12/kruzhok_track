import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .services import (
    verify_webhook_signature,
    claim_webhook,
    process_task_accepted,
    process_task_submitted,
    process_user_subscribed,
    process_payment_accepted,
    process_access_expired,
)

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def zenclass_webhook(request):
    """
    Обработчик вебхуков от ZenClass.

    Поддерживаемые события:
    - lesson_task_accepted: задание принято
    - lesson_task_submitted_for_review: задание отправлено на проверку
    - product_user_subscribed: подписка на курс
    - payment_accepted: оплата подтверждена
    - access_to_course_expired: доступ к курсу истёк
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        logger.warning("Получен невалидный JSON")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    webhook_id = data.get('id')
    event_name = data.get('event_name')
    timestamp = data.get('timestamp')
    received_hash = data.get('hash')
    payload = data.get('payload', {})

    logger.info(f"Получен вебхук: {event_name} (id={webhook_id})")

    # Валидация обязательных полей
    if not all([webhook_id, event_name, timestamp]):
        logger.warning("Отсутствуют обязательные поля")
        return JsonResponse({'error': 'Missing required fields'}, status=400)

    # Проверка подписи: task-события — per-course секрет из БД, enrollment — глобальный из .env
    if received_hash and not verify_webhook_signature(webhook_id, timestamp, received_hash, event_name, payload):
        return JsonResponse({'error': 'Invalid signature'}, status=403)

    # Атомарная проверка идемпотентности + логирование
    webhook_log = claim_webhook(webhook_id, event_name, payload)
    if webhook_log is None:
        logger.info(f"Вебхук уже обработан: {webhook_id}")
        return JsonResponse({'status': 'already_processed'}, status=200)

    # Обработка события
    result = None
    processed = True

    if event_name == 'lesson_task_accepted':
        result = process_task_accepted(payload, timestamp)

    elif event_name == 'lesson_task_submitted_for_review':
        result = process_task_submitted(payload, timestamp)

    elif event_name == 'product_user_subscribed':
        result = process_user_subscribed(payload)

    elif event_name == 'payment_accepted':
        result = process_payment_accepted(payload)

    elif event_name == 'access_to_course_expired':
        result = process_access_expired(payload)

    else:
        logger.info(f"Неизвестное событие: {event_name}")
        processed = False

    return JsonResponse({
        'status': 'ok',
        'event': event_name,
        'processed': processed and result is not None
    })
