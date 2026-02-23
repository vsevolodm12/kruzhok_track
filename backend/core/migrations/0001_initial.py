import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Student',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(db_index=True, max_length=254, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('telegram_id', models.BigIntegerField(blank=True, db_index=True, null=True, unique=True)),
                ('zenclass_id', models.UUIDField(blank=True, db_index=True, null=True, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Ученик',
                'verbose_name_plural': 'Ученики',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Course',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=500)),
                ('zenclass_id', models.UUIDField(db_index=True, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Курс',
                'verbose_name_plural': 'Курсы',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Enrollment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tariff_id', models.UUIDField(blank=True, null=True)),
                ('tariff_name', models.CharField(blank=True, default='', max_length=255)),
                ('status', models.CharField(
                    choices=[('active', 'Активен'), ('expired', 'Доступ закончился')],
                    default='active',
                    max_length=20,
                )),
                ('subscribed_at', models.DateTimeField(auto_now_add=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='enrollments', to='core.student')),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='enrollments', to='core.course')),
            ],
            options={
                'verbose_name': 'Подписка на курс',
                'verbose_name_plural': 'Подписки на курсы',
                'unique_together': {('student', 'course')},
            },
        ),
        migrations.AddField(
            model_name='course',
            name='students',
            field=models.ManyToManyField(related_name='enrolled_courses', through='core.Enrollment', to='core.student'),
        ),
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=500)),
                ('zenclass_id', models.UUIDField(db_index=True, unique=True)),
                ('task_type', models.CharField(
                    choices=[('homework', 'Домашнее задание'), ('mock', 'Пробник'), ('essay', 'Эссе'), ('project', 'Проект'), ('other', 'Другое')],
                    default='homework',
                    max_length=20,
                )),
                ('max_score', models.PositiveIntegerField(default=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tasks', to='core.course')),
            ],
            options={
                'verbose_name': 'Задание',
                'verbose_name_plural': 'Задания',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Grade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.PositiveIntegerField(blank=True, null=True)),
                ('teacher_comment', models.TextField(blank=True, default='')),
                ('status', models.CharField(
                    choices=[('submitted', 'На проверке'), ('accepted', 'Принято'), ('rejected', 'Отклонено')],
                    default='submitted',
                    max_length=20,
                )),
                ('report_link', models.URLField(blank=True, default='', max_length=500)),
                ('checked_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='grades', to='core.student')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='grades', to='core.task')),
            ],
            options={
                'verbose_name': 'Оценка',
                'verbose_name_plural': 'Оценки',
                'ordering': ['-checked_at'],
                'unique_together': {('student', 'task')},
            },
        ),
        migrations.AddIndex(
            model_name='grade',
            index=models.Index(fields=['student', 'checked_at'], name='core_grade_student_checked_idx'),
        ),
        migrations.AddIndex(
            model_name='grade',
            index=models.Index(fields=['student', 'status'], name='core_grade_student_status_idx'),
        ),
        migrations.CreateModel(
            name='ScheduleEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=500)),
                ('scheduled_at', models.DateTimeField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule', to='core.course')),
            ],
            options={
                'verbose_name': 'Занятие в расписании',
                'verbose_name_plural': 'Расписание занятий',
                'ordering': ['scheduled_at'],
            },
        ),
        migrations.CreateModel(
            name='Deadline',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=500)),
                ('due_date', models.DateTimeField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deadlines', to='core.course')),
            ],
            options={
                'verbose_name': 'Дедлайн',
                'verbose_name_plural': 'Дедлайны',
                'ordering': ['due_date'],
            },
        ),
        migrations.CreateModel(
            name='CourseWebhookSecret',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('secret_key', models.CharField(
                    help_text='Секретный ключ из настроек автоматизации в ZenClass (поле "Секретный ключ")',
                    max_length=500,
                    verbose_name='Секретный ключ',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('course', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='webhook_secret',
                    to='core.course',
                    verbose_name='Курс',
                )),
            ],
            options={
                'verbose_name': 'Секрет вебхука курса',
                'verbose_name_plural': 'Секреты вебхуков курсов',
            },
        ),
        migrations.CreateModel(
            name='WebhookLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('webhook_id', models.CharField(db_index=True, max_length=64, unique=True)),
                ('event_name', models.CharField(max_length=100)),
                ('payload', models.JSONField()),
                ('processed_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Лог вебхука',
                'verbose_name_plural': 'Логи вебхуков',
                'ordering': ['-processed_at'],
            },
        ),
    ]
