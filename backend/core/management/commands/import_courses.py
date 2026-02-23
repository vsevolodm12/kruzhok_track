"""
Импорт зачислений из таблицы Курсы (ZenClass Google Sheets).

Каждый лист = один курс. Название листа: "Название курса (uuid)".
Содержит всех студентов курса включая бесплатных.

Использование:
    python manage.py import_courses
    python manage.py import_courses --dry-run
"""

import re
import uuid
import logging
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from core.models import Student, Course, Enrollment
from core.services.google_sheets import GoogleSheetsService

logger = logging.getLogger(__name__)

COURSES_SPREADSHEET_ID = '12khQ9s3xUNH4iE7NQl3B-qGTmce9ghvwE7sSPYqkink'

# Листы которые не являются курсами
SKIP_SHEETS = {'Untitled course', 'Обучение кураторов', 'Тестовый курс', 'Корпоративное обучение'}


class Command(BaseCommand):
    help = 'Импорт зачислений из таблицы Курсы (ZenClass)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] Данные не будут сохранены\n'))

        svc = GoogleSheetsService()
        svc.spreadsheet_id = COURSES_SPREADSHEET_ID
        service = svc._get_service()

        # Получаем список листов
        meta = service.spreadsheets().get(spreadsheetId=COURSES_SPREADSHEET_ID).execute()
        sheets = meta.get('sheets', [])
        self.stdout.write(f'Листов (курсов): {len(sheets)}\n')

        total_enrollments = 0
        total_students_created = 0
        total_courses_created = 0
        skipped_sheets = 0

        for sheet_info in sheets:
            sheet_title = sheet_info['properties']['title']

            # Извлекаем UUID из названия листа: "Название курса (uuid)"
            match = re.search(r'\(([0-9a-f-]{36})\)\s*$', sheet_title)
            if not match:
                self.stdout.write(f'  Пропускаю (нет UUID): {sheet_title}')
                skipped_sheets += 1
                continue

            zenclass_id = uuid.UUID(match.group(1))
            course_name = sheet_title[:match.start()].strip()

            if any(skip in course_name for skip in SKIP_SHEETS):
                skipped_sheets += 1
                continue

            # Читаем данные листа
            range_name = f"'{sheet_title}'!A1:L2000"
            result = service.spreadsheets().values().get(
                spreadsheetId=COURSES_SPREADSHEET_ID,
                range=range_name
            ).execute()
            rows = result.get('values', [])

            if not rows or len(rows) < 2:
                continue

            headers = [h.lower().strip() for h in rows[0]]
            email_idx = self._find_col(headers, ['email', 'e-mail', 'почта'])
            name_idx = self._find_col(headers, ['имя'])
            surname_idx = self._find_col(headers, ['фамилия'])

            if email_idx is None:
                self.stdout.write(f'  Нет Email в: {course_name}')
                continue

            # Создаём/находим курс
            if not dry_run:
                course, course_created = Course.objects.get_or_create(
                    zenclass_id=zenclass_id,
                    defaults={'name': course_name}
                )
                if course_created:
                    total_courses_created += 1
            else:
                course_created = False

            enrolled_count = 0
            for row in rows[1:]:
                if not row or len(row) <= email_idx:
                    continue
                email = row[email_idx].strip().lower()
                if not email or '@' not in email:
                    continue

                # Имя
                parts = []
                if surname_idx is not None and len(row) > surname_idx:
                    parts.append(row[surname_idx].strip())
                if name_idx is not None and len(row) > name_idx:
                    parts.append(row[name_idx].strip())
                full_name = ' '.join(filter(None, parts)) or email.split('@')[0]

                if dry_run:
                    enrolled_count += 1
                    continue

                # Студент
                try:
                    student, s_created = Student.objects.get_or_create(
                        email=email,
                        defaults={'name': full_name}
                    )
                    if s_created:
                        total_students_created += 1
                except IntegrityError:
                    student = Student.objects.get(email=email)

                # Зачисление
                _, e_created = Enrollment.objects.get_or_create(
                    student=student,
                    course=course
                )
                if e_created:
                    enrolled_count += 1
                    total_enrollments += 1

            self.stdout.write(
                f'  {"[DRY]" if dry_run else "OK"} {course_name}: '
                f'{len(rows) - 1} студентов{f", +{enrolled_count} новых" if not dry_run else ""}'
            )

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'\nГотово:\n'
                f'  Создано курсов: {total_courses_created}\n'
                f'  Создано студентов: {total_students_created}\n'
                f'  Добавлено зачислений: {total_enrollments}\n'
                f'  Пропущено листов: {skipped_sheets}'
            ))

    def _find_col(self, headers, variants):
        for i, h in enumerate(headers):
            for v in variants:
                if v in h:
                    return i
        return None
