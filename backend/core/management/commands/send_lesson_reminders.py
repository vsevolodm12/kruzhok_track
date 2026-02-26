"""
Команда для отправки напоминаний о предстоящих занятиях.

Запускать каждые 5 минут через cron:
  */5 * * * * docker exec kruzhok-web-1 python manage.py send_lesson_reminders >> /var/log/lesson_reminders.log 2>&1

Или через systemd timer (см. ADMIN.md).
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import ScheduleEvent, Enrollment
from core.services.telegram import TelegramNotificationService

logger = logging.getLogger(__name__)

# Окно: уведомляем, если занятие начнётся через 5–15 минут
REMIND_BEFORE_MIN = 5
REMIND_WINDOW_MIN = 10


class Command(BaseCommand):
    help = 'Отправляет Telegram-напоминания о занятиях, которые начинаются через ~10 минут'

    def handle(self, *args, **options):
        now = timezone.now()
        window_start = now + timedelta(minutes=REMIND_BEFORE_MIN)
        window_end = now + timedelta(minutes=REMIND_BEFORE_MIN + REMIND_WINDOW_MIN)

        upcoming = ScheduleEvent.objects.filter(
            scheduled_at__gte=window_start,
            scheduled_at__lt=window_end,
        ).select_related('course')

        if not upcoming.exists():
            self.stdout.write('Нет предстоящих занятий в окне уведомлений.')
            return

        service = TelegramNotificationService()
        sent = 0
        skipped = 0

        for event in upcoming:
            course = event.course
            enrollments = Enrollment.objects.filter(
                course=course,
                status=Enrollment.Status.ACTIVE,
            ).select_related('student')

            for enrollment in enrollments:
                student = enrollment.student
                if not student.telegram_id:
                    skipped += 1
                    continue

                ok = service.notify_lesson_reminder(
                    telegram_id=student.telegram_id,
                    course_name=course.name,
                    lesson_title=event.title,
                    zoom_url=course.zoom_url,
                    zoom_meeting_id=course.zoom_meeting_id,
                    zoom_passcode=course.zoom_passcode,
                    zoom_login=course.zoom_login,
                    zoom_password=course.zoom_password,
                )
                if ok:
                    sent += 1
                    logger.info(
                        f'Напоминание отправлено: {student.email} → '
                        f'"{event.title}" ({course.name})'
                    )
                else:
                    logger.warning(
                        f'Не удалось отправить: {student.email} '
                        f'(tg_id={student.telegram_id})'
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'Готово: отправлено {sent}, пропущено (нет TG) {skipped}.'
            )
        )
