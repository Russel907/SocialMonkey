# Generated by Django 5.1.7 on 2025-04-09 10:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restaurant', '0019_offer'),
    ]

    operations = [
        migrations.AddField(
            model_name='offer',
            name='end_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='offer',
            name='start_time',
            field=models.TimeField(blank=True, null=True),
        ),
    ]
