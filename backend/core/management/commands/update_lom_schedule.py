"""
Команда для обновления расписания курса Ломоносов 25/26.

Заменяет все события с 02.03.2026 по 20.03.2026:
  python manage.py update_lom_schedule
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware

from core.models import Course, ScheduleEvent

NEW_SCHEDULE = [
    (2,  3, 'Особенности подготовки в Ломоносову и эссе'),
    (4,  3, 'Практика по IX-XVI веку (блок А)'),
    (6,  3, 'Практика по XVI-XVII веку (блок А)'),
    (8,  3, 'Практика по блоку Б'),
    (9,  3, 'Эссе'),
    (10, 3, 'ПРОБНИК'),
    (12, 3, 'Практика по XVIII веку (блок А)'),
    (14, 3, 'Практика по XIX веку (блок А)'),
    (15, 3, 'Практика по блоку Б'),
    (16, 3, 'ПРОБНИК'),
    (18, 3, 'Практика по ХХ веку (блок А)'),
    (20, 3, 'Практика по ВОВ (блок А)'),
]


class Command(BaseCommand):
    help = 'Обновляет расписание курса Ломоносов 25/26 (март 2026)'

    def handle(self, *args, **options):
        try:
            course = Course.objects.get(name__icontains='Ломоносов')
        except Course.MultipleObjectsReturned:
            self.stdout.write(self.style.ERROR(
                'Найдено несколько курсов с "Ломоносов". Уточните фильтр.'
            ))
            return
        except Course.DoesNotExist:
            self.stdout.write(self.style.ERROR('Курс Ломоносов не найден.'))
            return

        self.stdout.write(f'Курс: {course.name} (id={course.id})')

        # Удаляем события начиная с 02.03.2026
        cutoff = make_aware(datetime(2026, 3, 2, 0, 0))
        deleted, _ = ScheduleEvent.objects.filter(
            course=course,
            scheduled_at__gte=cutoff,
        ).delete()
        self.stdout.write(f'Удалено старых событий: {deleted}')

        # Создаём новые события
        created = 0
        for day, month, title in NEW_SCHEDULE:
            aware_dt = make_aware(datetime(2026, month, day, 18, 0, 0))
            ScheduleEvent.objects.create(
                course=course,
                title=title,
                scheduled_at=aware_dt,
            )
            created += 1
            self.stdout.write(f'  + {day:02d}.{month:02d} {title}')

        self.stdout.write(self.style.SUCCESS(f'Готово! Создано событий: {created}'))
