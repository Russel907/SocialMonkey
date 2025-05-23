# Generated by Django 5.1.7 on 2025-03-27 05:29

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restaurant', '0007_table_booking_status_table_created_at_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('min_advance_amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('upi_id', models.CharField(max_length=255)),
                ('upi_qr_code', models.ImageField(blank=True, null=True, upload_to='media/upi_qr_codes/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('restaurant', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='restaurant.restaurant')),
            ],
        ),
    ]
