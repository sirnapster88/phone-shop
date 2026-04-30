import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Создает или обновляет демо-администратора из env переменных.'

    def handle(self, *args, **options):
        username = os.getenv('DEMO_ADMIN_USERNAME', '').strip()
        password = os.getenv('DEMO_ADMIN_PASSWORD', '').strip()
        email = os.getenv('DEMO_ADMIN_EMAIL', '').strip()

        if not username or not password:
            self.stdout.write('DEMO_ADMIN_USERNAME / DEMO_ADMIN_PASSWORD не заданы, bootstrap admin пропущен.')
            return

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'is_staff': True,
                'is_superuser': True,
            },
        )

        updated_fields = []

        if email and user.email != email:
            user.email = email
            updated_fields.append('email')

        if not user.is_staff:
            user.is_staff = True
            updated_fields.append('is_staff')

        if not user.is_superuser:
            user.is_superuser = True
            updated_fields.append('is_superuser')

        if created or not user.check_password(password):
            user.set_password(password)
            updated_fields.append('password')

        if updated_fields:
            user.save(update_fields=updated_fields)

        if created:
            self.stdout.write(self.style.SUCCESS(f'Создан демо-администратор: {username}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Демо-администратор обновлен: {username}'))
