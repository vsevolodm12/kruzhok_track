"""
Команда для настройки курса МГИМО:
- Создаёт расписание занятий 05-13.03.2026
- Создаёт дедлайны с теми же датами
- Устанавливает секрет вебхука

  python manage.py setup_mgimo_course
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware

from core.models import Course, ScheduleEvent, Deadline, CourseWebhookSecret

WEBHOOK_SECRET = 'f68tgGovErvASZMHKdxw3PLe98fCTKXT'

LESSONS = [
    (5,  3, 'Особенности олимпиады МГИМО'),
    (6,  3, 'Исторические задания'),
    (7,  3, 'Социально-экономические задания'),
    (8,  3, 'Эссе'),
    (9,  3, 'Пробник №1'),
    (10, 3, 'Исторические задания'),
    (11, 3, 'Социально-экономические задания'),
    (12, 3, 'Пробник №2'),
    (13, 3, 'Эссе'),
]


class Command(BaseCommand):
    help = 'Настраивает расписание, дедлайны и вебхук-секрет для курса МГИМО'

    def handle(self, *args, **options):
        # Ищем курс МГИМО по названию
        courses = Course.objects.filter(name__icontains='мгимо')
        if not courses.exists():
            self.stdout.write(self.style.ERROR('Курс с "мгимо" в названии не найден.'))
            return
        if courses.count() > 1:
            self.stdout.write(self.style.WARNING(f'Найдено несколько курсов: {list(courses.values_list("name", "id"))}'))
            self.stdout.write(self.style.ERROR('Уточни команду.'))
            return

        course = courses.first()
        self.stdout.write(f'Курс: {course.name} (id={course.id})')

        # Удаляем старое расписание и дедлайны начиная с 05.03.2026
        cutoff = make_aware(datetime(2026, 3, 5, 0, 0))

        deleted_s, _ = ScheduleEvent.objects.filter(
            course=course,
            scheduled_at__gte=cutoff,
        ).delete()
        self.stdout.write(f'Удалено старых занятий: {deleted_s}')

        deleted_d, _ = Deadline.objects.filter(
            course=course,
            due_date__gte=cutoff,
        ).delete()
        self.stdout.write(f'Удалено старых дедлайнов: {deleted_d}')

        # Создаём расписание (18:00) и дедлайны (23:59)
        for day, month, title in LESSONS:
            schedule_dt = make_aware(datetime(2026, month, day, 18, 0, 0))
            ScheduleEvent.objects.create(course=course, title=title, scheduled_at=schedule_dt)

            deadline_dt = make_aware(datetime(2026, month, day, 23, 59, 0))
            Deadline.objects.create(course=course, title=title, due_date=deadline_dt)

            self.stdout.write(f'  + {day:02d}.{month:02d} {title}')

        self.stdout.write(f'Создано занятий и дедлайнов: {len(LESSONS)}')

        # Устанавливаем секрет вебхука
        secret, created = CourseWebhookSecret.objects.update_or_create(
            course=course,
            defaults={'secret_key': WEBHOOK_SECRET},
        )
        action = 'Создан' if created else 'Обновлён'
        self.stdout.write(f'{action} секрет вебхука: {WEBHOOK_SECRET[:8]}...')

        self.stdout.write(self.style.SUCCESS('Готово!'))
