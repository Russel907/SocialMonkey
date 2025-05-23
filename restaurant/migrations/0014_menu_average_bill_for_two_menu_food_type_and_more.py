# Generated by Django 5.1.7 on 2025-04-09 05:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restaurant', '0013_remove_seats_booking_available'),
    ]

    operations = [
        migrations.AddField(
            model_name='menu',
            name='average_bill_for_two',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='menu',
            name='food_type',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='restaurant',
            name='food_type',
            field=models.CharField(choices=[('veg', 'Veg'), ('non_veg', 'Non-Veg'), ('both', 'Both')], default='both', max_length=255),
        ),
    ]
