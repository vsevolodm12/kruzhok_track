"""
Одноразовый импорт студентов из Google Sheets (интеграция ZenClass).

Использует таблицу "Студенты" из ZenClass, которая содержит:
- Email
- Имя, Отчество, Фамилия
- Покупки (названия курсов через |)

Использование:
    python manage.py import_students
    python manage.py import_students --dry-run  # Только показать что будет импортировано
"""

from django.core.management.base import BaseCommand
from core.models import Student, Course, Enrollment
from core.services import GoogleSheetsService
import uuid


class Command(BaseCommand):
    help = 'Одноразовый импорт студентов из Google Sheets (интеграция ZenClass)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет импортировано без сохранения в БД'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write("Импорт студентов из Google Sheets...")
        self.stdout.write("Таблица должна быть создана через интеграцию ZenClass → Google Sheets\n")

        try:
            service = GoogleSheetsService()
            # Читаем лист "Студенты" (стандартное название от ZenClass)
            rows = service.get_sheet_data("Студенты")
        except FileNotFoundError as e:
            self.stderr.write(self.style.ERROR(str(e)))
            self.stderr.write(
                "\nПроверьте:\n"
                "1. Файл credentials/service-account.json существует\n"
                "2. GOOGLE_SERVICE_ACCOUNT_FILE указан в .env\n"
                "3. Сервисному аккаунту дан доступ к таблице"
            )
            return
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Ошибка: {e}"))
            return

        if not rows:
            self.stdout.write(self.style.WARNING("Таблица пустая"))
            return

        # Парсим заголовки (первая строка)
        headers = [h.lower().strip() for h in rows[0]]
        self.stdout.write(f"Найдены столбцы: {headers}\n")

        # Находим индексы нужных столбцов
        email_idx = self._find_column(headers, ['email', 'e-mail', 'почта'])
        name_idx = self._find_column(headers, ['имя'])
        surname_idx = self._find_column(headers, ['фамилия'])
        patronymic_idx = self._find_column(headers, ['отчество'])
        purchases_idx = self._find_column(headers, ['покупки', 'курсы'])

        if email_idx is None:
            self.stderr.write(self.style.ERROR("Не найден столбец Email"))
            return

        self.stdout.write(f"Найдено строк: {len(rows) - 1}\n")

        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] Данные не будут сохранены\n"))

        created_students = 0
        updated_students = 0
        created_courses = 0
        created_enrollments = 0

        for row in rows[1:]:
            if not row or len(row) <= email_idx:
                continue

            email = row[email_idx].strip().lower()
            if not email or '@' not in email:
                continue

            # Собираем имя
            name_parts = []
            if surname_idx is not None and len(row) > surname_idx:
                name_parts.append(row[surname_idx].strip())
            if name_idx is not None and len(row) > name_idx:
                name_parts.append(row[name_idx].strip())
            if patronymic_idx is not None and len(row) > patronymic_idx:
                name_parts.append(row[patronymic_idx].strip())

            full_name = ' '.join(filter(None, name_parts)) or email.split('@')[0]

            # Парсим курсы (через | или запятую)
            courses = []
            if purchases_idx is not None and len(row) > purchases_idx:
                purchases_str = row[purchases_idx].strip()
                if purchases_str:
                    # ZenClass использует | как разделитель
                    if '|' in purchases_str:
                        courses = [c.strip() for c in purchases_str.split('|') if c.strip()]
                    else:
                        courses = [c.strip() for c in purchases_str.split(',') if c.strip()]

            if dry_run:
                courses_str = ', '.join(courses) if courses else 'нет курсов'
                self.stdout.write(f"  {full_name} <{email}> → {courses_str}")
                continue

            # Создаём/обновляем студента
            student, created = Student.objects.update_or_create(
                email=email,
                defaults={'name': full_name}
            )

            if created:
                created_students += 1
            else:
                updated_students += 1

            # Создаём курсы и подписки
            for course_name in courses:
                # Генерируем zenclass_id из названия
                zenclass_id = uuid.uuid5(uuid.NAMESPACE_DNS, course_name)

                course, course_created = Course.objects.get_or_create(
                    name=course_name,
                    defaults={'zenclass_id': zenclass_id}
                )

                if course_created:
                    created_courses += 1

                enrollment, enroll_created = Enrollment.objects.get_or_create(
                    student=student,
                    course=course
                )

                if enroll_created:
                    created_enrollments += 1

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"\nИмпорт завершён:\n"
                f"  Создано студентов: {created_students}\n"
                f"  Обновлено студентов: {updated_students}\n"
                f"  Создано курсов: {created_courses}\n"
                f"  Создано подписок: {created_enrollments}"
            ))

    def _find_column(self, headers: list, variants: list) -> int | None:
        """Ищет столбец по возможным названиям."""
        for i, h in enumerate(headers):
            for v in variants:
                if v in h:
                    return i
        return None
