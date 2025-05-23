# Generated by Django 5.1.7 on 2025-04-09 09:07

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restaurant', '0017_rename_album_gallery'),
    ]

    operations = [
        migrations.AddField(
            model_name='gallery',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='gallery',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.CreateModel(
            name='Performance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(blank=True, null=True, upload_to='media/performance/')),
                ('name', models.CharField(max_length=255)),
                ('entry', models.CharField(choices=[('free_entry', 'Free_entry'), ('paid_entry', 'Paid_entry')], default='free_entry', max_length=20)),
                ('start_time', models.TimeField()),
                ('date', models.DateField()),
                ('theme', models.CharField(blank=True, max_length=500, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('restaurant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='performance', to='restaurant.restaurant')),
            ],
        ),
    ]
