from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduleevent',
            name='duration_minutes',
            field=models.PositiveIntegerField(default=90, verbose_name='Длительность (мин)'),
        ),
        migrations.AddField(
            model_name='deadline',
            name='submitted',
            field=models.BooleanField(default=False, verbose_name='Сдано'),
        ),
    ]
