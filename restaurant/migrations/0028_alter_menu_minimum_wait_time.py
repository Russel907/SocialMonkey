# Generated by Django 5.0.2 on 2025-06-03 14:00

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("restaurant", "0027_alter_restaurantstaffprofile_user"),
    ]

    operations = [
        migrations.AlterField(
            model_name="menu",
            name="minimum_wait_time",
            field=models.PositiveIntegerField(default="In minutes"),
        ),
    ]
