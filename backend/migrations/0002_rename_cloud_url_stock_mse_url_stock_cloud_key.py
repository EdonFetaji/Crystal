# Generated by Django 5.0.1 on 2024-12-04 14:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backend', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='stock',
            old_name='cloud_url',
            new_name='mse_url',
        ),
        migrations.AddField(
            model_name='stock',
            name='cloud_key',
            field=models.CharField(default='FfERF', max_length=255),
            preserve_default=False,
        ),
    ]
