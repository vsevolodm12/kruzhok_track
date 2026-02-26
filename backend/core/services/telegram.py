import hmac
import hashlib
import json
import logging
from urllib.parse import parse_qsl, unquote
from django.conf import settings
import httpx

logger = logging.getLogger(__name__)


class TelegramAuthService:
    """
    Сервис авторизации через Telegram Mini App.

    Проверяет initData от Telegram Web App по алгоритму:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """

    @staticmethod
    def validate_init_data(init_data: str) -> dict | None:
        """
        Валидирует initData от Telegram.

        Возвращает распарсенные данные пользователя или None если невалидно.
        """
        if not init_data:
            return None

        bot_token = settings.TELEGRAM_BOT_TOKEN
        if not bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN не настроен")
            return None

        try:
            # Парсим query string
            parsed = dict(parse_qsl(init_data, keep_blank_values=True))

            received_hash = parsed.pop('hash', None)
            if not received_hash:
                return None

            # Создаём строку для проверки (отсортированная по ключам)
            data_check_string = '\n'.join(
                f"{k}={v}" for k, v in sorted(parsed.items())
            )

            # Вычисляем secret_key = HMAC-SHA256(bot_token, "WebAppData")
            secret_key = hmac.new(
                b"WebAppData",
                bot_token.encode(),
                hashlib.sha256
            ).digest()

            # Вычисляем хеш данных
            calculated_hash = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256
            ).hexdigest()

            if calculated_hash != received_hash:
                logger.warning("Невалидная подпись initData")
                return None

            # Парсим user из JSON
            user_json = parsed.get('user')
            if user_json:
                parsed['user'] = json.loads(unquote(user_json))

            return parsed

        except Exception as e:
            logger.error(f"Ошибка валидации initData: {e}")
            return None

    @staticmethod
    def extract_user_data(validated_data: dict) -> dict | None:
        """Извлекает данные пользователя из валидированных данных."""
        user = validated_data.get('user')
        if not user:
            return None

        return {
            'telegram_id': user.get('id'),
            'first_name': user.get('first_name', ''),
            'last_name': user.get('last_name', ''),
            'username': user.get('username', ''),
            'language_code': user.get('language_code', 'ru'),
        }


class TelegramNotificationService:
    """Сервис отправки уведомлений через Telegram Bot API."""

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
        """Отправляет сообщение пользователю."""
        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN не настроен, уведомление не отправлено")
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в Telegram: {e}")
            return False

    def send_message_sync(self, chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
        """Синхронная отправка сообщения (для использования в Django views)."""
        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN не настроен, уведомление не отправлено")
            return False

        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в Telegram: {e}")
            return False

    def notify_grade(self, telegram_id: int, course_name: str, task_name: str, score: int | None, max_score: int) -> bool:
        """Отправляет уведомление о проверенном задании."""
        if score is not None:
            text = (
                f"✅ <b>Работа проверена!</b>\n\n"
                f"📚 Курс: {course_name}\n"
                f"📝 Задание: {task_name}\n"
                f"🎯 Оценка: <b>{score}/{max_score}</b>"
            )
        else:
            text = (
                f"✅ <b>Работа принята!</b>\n\n"
                f"📚 Курс: {course_name}\n"
                f"📝 Задание: {task_name}"
            )

        return self.send_message_sync(telegram_id, text)
