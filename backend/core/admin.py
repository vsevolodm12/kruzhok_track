from django.contrib import admin
from .models import Student, Course, Enrollment, Task, Grade, ScheduleEvent, Deadline, CourseWebhookSecret, WebhookLog


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'telegram_id', 'created_at']
    search_fields = ['name', 'email']
    list_filter = ['created_at']


class WebhookSecretInline(admin.StackedInline):
    model = CourseWebhookSecret
    extra = 1
    max_num = 1
    fields = ['secret_key']
    verbose_name = 'Секретный ключ вебхука'
    verbose_name_plural = 'Секретный ключ вебхука'


class ScheduleEventInline(admin.TabularInline):
    model = ScheduleEvent
    extra = 0
    fields = ['title', 'scheduled_at', 'duration_minutes']
    ordering = ['scheduled_at']


class DeadlineInline(admin.TabularInline):
    model = Deadline
    extra = 0
    fields = ['title', 'due_date', 'submitted']
    ordering = ['due_date']


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['name', 'zenclass_id', 'has_secret', 'schedule_count', 'deadline_count', 'created_at']
    search_fields = ['name', 'zenclass_id']
    inlines = [WebhookSecretInline, ScheduleEventInline, DeadlineInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'zenclass_id'),
            'description': (
                'ZenClass ID — UUID курса из ZenClass. '
                'Найти: Настройки курса → Встраивание → ID из прямой ссылки.'
            ),
        }),
    )

    @admin.display(boolean=True, description='Секрет')
    def has_secret(self, obj):
        return hasattr(obj, 'webhook_secret')

    @admin.display(description='Занятий')
    def schedule_count(self, obj):
        return obj.schedule.count()

    @admin.display(description='Дедлайнов')
    def deadline_count(self, obj):
        return obj.deadlines.count()


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'status', 'subscribed_at']
    list_filter = ['status', 'course']
    search_fields = ['student__name', 'student__email', 'course__name']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'course', 'task_type', 'max_score']
    list_filter = ['task_type', 'course']
    search_fields = ['name']


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ['student', 'task', 'value', 'status', 'checked_at']
    list_filter = ['status', 'task__course']
    search_fields = ['student__name', 'task__name']


@admin.register(ScheduleEvent)
class ScheduleEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'scheduled_at']
    list_filter = ['course', 'scheduled_at']
    search_fields = ['title']


@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'due_date', 'submitted']
    list_filter = ['course', 'due_date', 'submitted']
    search_fields = ['title']


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ['webhook_id', 'event_name', 'processed_at']
    list_filter = ['event_name']
    search_fields = ['webhook_id']
    readonly_fields = ['webhook_id', 'event_name', 'payload', 'processed_at']
