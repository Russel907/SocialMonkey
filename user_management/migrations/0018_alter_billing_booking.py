# Generated by Django 5.1.7 on 2025-04-21 11:02

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user_management', '0017_specialrequestforseat'),
    ]

    operations = [
        migrations.AlterField(
            model_name='billing',
            name='booking',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='billing', to='user_management.seatbooking'),
        ),
    ]
