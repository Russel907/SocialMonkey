# Generated by Django 5.1.7 on 2025-04-10 08:00

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('user_management', '0008_seatbooking'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='seatbooking',
            name='advance_payment_per_guest',
        ),
    ]
