# Generated by Django 5.0.1 on 2024-12-17 17:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('backend', '0004_alter_stock_last_modified_alter_stock_mse_url_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stock',
            name='last_modified',
            field=models.DateField(blank=True, null=True),
        ),
    ]