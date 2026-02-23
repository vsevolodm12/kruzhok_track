import logging
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)


class GoogleSheetsService:
    """
    Сервис для работы с Google Sheets API.

    Используется для одноразовой миграции данных студентов.
    """

    def __init__(self):
        self.spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID
        self.credentials_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE
        self._service = None

    def _get_service(self):
        """Инициализирует и возвращает Google Sheets API сервис."""
        if self._service:
            return self._service

        if not self.credentials_file or not Path(self.credentials_file).exists():
            raise FileNotFoundError(
                f"Файл учётных данных Google не найден: {self.credentials_file}"
            )

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )

            self._service = build('sheets', 'v4', credentials=credentials)
            return self._service

        except Exception as e:
            logger.error(f"Ошибка инициализации Google Sheets API: {e}")
            raise

    def get_sheet_data(self, range_name: str) -> list[list[str]]:
        """
        Получает данные из указанного диапазона таблицы.

        Args:
            range_name: Диапазон в формате "Лист1!A1:D100" или "Лист1"

        Returns:
            Список строк, каждая строка — список значений ячеек.
        """
        service = self._get_service()

        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()

            return result.get('values', [])

        except Exception as e:
            logger.error(f"Ошибка получения данных из Google Sheets: {e}")
            raise

    def get_students_data(self, sheet_name: str = "Студенты") -> list[dict]:
        """
        Получает список студентов из таблицы.

        Ожидаемый формат таблицы:
        | Email | Имя | Курсы (через запятую) |

        Returns:
            Список словарей с данными студентов.
        """
        try:
            rows = self.get_sheet_data(sheet_name)

            if not rows:
                return []

            # Первая строка — заголовки
            headers = [h.lower().strip() for h in rows[0]]
            students = []

            for row in rows[1:]:
                if not row or not row[0].strip():
                    continue

                student = {}
                for i, header in enumerate(headers):
                    value = row[i] if i < len(row) else ''

                    if 'email' in header:
                        student['email'] = value.strip().lower()
                    elif 'имя' in header or 'name' in header:
                        student['name'] = value.strip()
                    elif 'курс' in header or 'покупки' in header:
                        # Курсы через запятую
                        courses = [c.strip() for c in value.split(',') if c.strip()]
                        student['courses'] = courses

                if student.get('email'):
                    students.append(student)

            return students

        except Exception as e:
            logger.error(f"Ошибка парсинга студентов: {e}")
            raise

    def get_course_students(self, course_sheet_name: str) -> list[str]:
        """
        Получает список email студентов курса из отдельного листа.

        Ожидаемый формат: столбец с email студентов.
        """
        try:
            rows = self.get_sheet_data(course_sheet_name)

            if not rows:
                return []

            emails = []
            for row in rows[1:]:  # Пропускаем заголовок
                if row and row[0].strip() and '@' in row[0]:
                    emails.append(row[0].strip().lower())

            return emails

        except Exception as e:
            logger.error(f"Ошибка получения студентов курса: {e}")
            raise

    def get_schedule_data(self, sheet_name: str) -> list[dict]:
        """
        Получает расписание курса.

        Ожидаемый формат:
        | Дата | Название занятия |

        Формат даты: ДД.ММ.ГГГГ или ДД.ММ.ГГГГ ЧЧ:ММ
        """
        try:
            rows = self.get_sheet_data(sheet_name)

            if not rows:
                return []

            schedule = []
            for row in rows[1:]:  # Пропускаем заголовок
                if len(row) < 2 or not row[0].strip():
                    continue

                schedule.append({
                    'date': row[0].strip(),
                    'title': row[1].strip() if len(row) > 1 else '',
                })

            return schedule

        except Exception as e:
            logger.error(f"Ошибка получения расписания: {e}")
            raise
