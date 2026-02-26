from django.db import models
from django.utils import timezone
from datetime import timedelta
import re


class Student(models.Model):
    """Ученик онлайн-школы."""

    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=255)
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True, db_index=True)
    zenclass_id = models.UUIDField(null=True, blank=True, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ученик'
        verbose_name_plural = 'Ученики'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.email})"

    def get_streak(self) -> int:
        """
        Рассчитывает текущий streak — количество последовательных дней
        с принятыми заданиями (начиная с сегодня или вчера).
        """
        grades = self.grades.filter(
            status=Grade.Status.ACCEPTED,
            checked_at__isnull=False
        ).order_by('-checked_at')

        if not grades.exists():
            return 0

        today = timezone.now().date()
        streak = 0
        expected_date = today

        # Группируем по датам
        dates_with_grades = set()
        for grade in grades:
            dates_with_grades.add(grade.checked_at.date())

        # Если сегодня нет оценки, начинаем со вчера
        if today not in dates_with_grades:
            expected_date = today - timedelta(days=1)

        while expected_date in dates_with_grades:
            streak += 1
            expected_date -= timedelta(days=1)

        return streak

    def get_total_stats(self) -> dict:
        """Возвращает общую статистику по всем курсам."""
        grades = self.grades.filter(status=Grade.Status.ACCEPTED)
        total = grades.count()

        if total == 0:
            return {'total': 0, 'average_percent': 0}

        # Средний процент
        grades_with_score = grades.filter(value__isnull=False)
        if grades_with_score.exists():
            total_percent = 0
            count = 0
            for grade in grades_with_score:
                if grade.task.max_score > 0:
                    total_percent += (grade.value / grade.task.max_score) * 100
                    count += 1
            avg = round(total_percent / count) if count > 0 else 0
        else:
            avg = 0

        return {
            'total': total,
            'average_percent': avg,
        }


class Course(models.Model):
    """Курс в ZenClass."""

    name = models.CharField(max_length=500)
    zenclass_id = models.UUIDField(unique=True, db_index=True)
    students = models.ManyToManyField(
        Student,
        through='Enrollment',
        related_name='enrolled_courses'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    zoom_url = models.URLField(blank=True, default='', verbose_name='Ссылка Zoom')
    zoom_passcode = models.CharField(max_length=50, blank=True, default='', verbose_name='Код доступа Zoom')

    class Meta:
        verbose_name = 'Курс'
        verbose_name_plural = 'Курсы'
        ordering = ['name']

    def __str__(self):
        return self.name


class Enrollment(models.Model):
    """Связь ученик-курс (подписка)."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Активен'
        EXPIRED = 'expired', 'Доступ закончился'

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    tariff_id = models.UUIDField(null=True, blank=True)
    tariff_name = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    subscribed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Подписка на курс'
        verbose_name_plural = 'Подписки на курсы'
        unique_together = ['student', 'course']

    def __str__(self):
        return f"{self.student.name} - {self.course.name}"


class Task(models.Model):
    """Задание в курсе."""

    class TaskType(models.TextChoices):
        HOMEWORK = 'homework', 'Домашнее задание'
        MOCK = 'mock', 'Пробник'
        ESSAY = 'essay', 'Эссе'
        PROJECT = 'project', 'Проект'
        OTHER = 'other', 'Другое'

    name = models.CharField(max_length=500)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='tasks')
    zenclass_id = models.UUIDField(unique=True, db_index=True)
    task_type = models.CharField(
        max_length=20,
        choices=TaskType.choices,
        default=TaskType.HOMEWORK
    )
    max_score = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Задание'
        verbose_name_plural = 'Задания'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.course.name})"

    @classmethod
    def detect_task_type(cls, task_name: str) -> str:
        """Определяет тип задания по названию."""
        name_lower = task_name.lower()

        if any(word in name_lower for word in ['пробник', 'пробный', 'mock', 'тест']):
            return cls.TaskType.MOCK
        elif any(word in name_lower for word in ['эссе', 'essay', 'сочинение']):
            return cls.TaskType.ESSAY
        elif any(word in name_lower for word in ['проект', 'project', 'исследование']):
            return cls.TaskType.PROJECT
        else:
            return cls.TaskType.HOMEWORK


class Grade(models.Model):
    """Оценка за задание."""

    class Status(models.TextChoices):
        SUBMITTED = 'submitted', 'На проверке'
        ACCEPTED = 'accepted', 'Принято'
        REJECTED = 'rejected', 'Отклонено'

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='grades')
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='grades')
    value = models.PositiveIntegerField(null=True, blank=True)
    teacher_comment = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUBMITTED
    )
    report_link = models.URLField(max_length=500, blank=True, default='')
    checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Оценка'
        verbose_name_plural = 'Оценки'
        unique_together = ['student', 'task']
        ordering = ['-checked_at']
        indexes = [
            models.Index(fields=['student', 'checked_at']),
            models.Index(fields=['student', 'status']),
        ]

    def __str__(self):
        score = self.value if self.value is not None else 'зачёт'
        return f"{self.student.name} - {self.task.name}: {score}"

    @property
    def percent(self) -> int | None:
        """Возвращает процент выполнения."""
        if self.value is None or self.task.max_score == 0:
            return None
        return round((self.value / self.task.max_score) * 100)

    @staticmethod
    def parse_score_from_comment(comment: str) -> int | None:
        """
        Извлекает оценку из комментария учителя.
        Ищет первую цифру или паттерн вида "5/5", "Оценка: 5".
        """
        if not comment:
            return None

        comment = comment.strip()

        # Паттерн "X/Y" — берём X
        match = re.search(r'(\d+)\s*/\s*\d+', comment)
        if match:
            return int(match.group(1))

        # Паттерн "Оценка: X" или просто цифра в начале
        match = re.search(r'(\d+)', comment)
        if match:
            return int(match.group(1))

        return None


class ScheduleEvent(models.Model):
    """Событие в расписании курса (занятие)."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='schedule')
    title = models.CharField(max_length=500)
    scheduled_at = models.DateTimeField(db_index=True)
    duration_minutes = models.PositiveIntegerField(default=90, verbose_name='Длительность (мин)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Занятие в расписании'
        verbose_name_plural = 'Расписание занятий'
        ordering = ['scheduled_at']

    def __str__(self):
        return f"{self.title} - {self.scheduled_at.strftime('%d.%m.%Y')}"

    @property
    def is_past(self) -> bool:
        return self.scheduled_at < timezone.now()

    @property
    def is_today(self) -> bool:
        return self.scheduled_at.date() == timezone.now().date()


class Deadline(models.Model):
    """Дедлайн домашнего задания."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='deadlines')
    title = models.CharField(max_length=500)
    due_date = models.DateTimeField(db_index=True)
    submitted = models.BooleanField(default=False, verbose_name='Сдано')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Дедлайн'
        verbose_name_plural = 'Дедлайны'
        ordering = ['due_date']

    def __str__(self):
        return f"{self.title} - {self.due_date.strftime('%d.%m.%Y %H:%M')}"

    @property
    def days_left(self) -> int:
        """Количество дней до дедлайна."""
        delta = self.due_date.date() - timezone.now().date()
        return delta.days

    @property
    def is_overdue(self) -> bool:
        return self.due_date < timezone.now()


class CourseWebhookSecret(models.Model):
    """Секретный ключ вебхука ZenClass для конкретного курса."""

    course = models.OneToOneField(
        Course,
        on_delete=models.CASCADE,
        related_name='webhook_secret',
        verbose_name='Курс'
    )
    secret_key = models.CharField(
        max_length=500,
        verbose_name='Секретный ключ',
        help_text='Секретный ключ из настроек автоматизации в ZenClass (поле "Секретный ключ")'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Секрет вебхука курса'
        verbose_name_plural = 'Секреты вебхуков курсов'

    def __str__(self):
        return f"Секрет для: {self.course.name}"


class WebhookLog(models.Model):
    """Лог обработанных вебхуков (для идемпотентности)."""

    webhook_id = models.CharField(max_length=64, unique=True, db_index=True)
    event_name = models.CharField(max_length=100)
    payload = models.JSONField()
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Лог вебхука'
        verbose_name_plural = 'Логи вебхуков'
        ordering = ['-processed_at']

    def __str__(self):
        return f"{self.event_name} - {self.webhook_id}"
