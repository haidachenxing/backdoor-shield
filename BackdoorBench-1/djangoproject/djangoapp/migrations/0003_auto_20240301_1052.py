# Generated by Django 3.1 on 2024-03-01 02:52

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('djangoapp', '0002_remove_user_username'),
    ]

    operations = [
        migrations.RenameField(
            model_name='user',
            old_name='email',
            new_name='username',
        ),
    ]
