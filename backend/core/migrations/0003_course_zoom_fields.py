from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_scheduleevent_duration_minutes_deadline_submitted'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='zoom_url',
            field=models.URLField(blank=True, default='', verbose_name='Ссылка Zoom'),
        ),
        migrations.AddField(
            model_name='course',
            name='zoom_meeting_id',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='ID конференции'),
        ),
        migrations.AddField(
            model_name='course',
            name='zoom_passcode',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='Код доступа'),
        ),
        migrations.AddField(
            model_name='course',
            name='zoom_login',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Логин Zoom'),
        ),
        migrations.AddField(
            model_name='course',
            name='zoom_password',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Пароль Zoom'),
        ),
    ]
