from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Синхронизирует группы пользователей: добавляет новых пользователей в группу 'users'"

    def add_arguments(self, parser):
        parser.add_argument("--verbose", action="store_true", help="Подробный вывод")

    def handle(self, *args, **options):
        User = get_user_model()
        verbose = options["verbose"]

        users_group, created = Group.objects.get_or_create(name="users")
        if created:
            self.stdout.write(self.style.SUCCESS("Создана группа 'users'"))

        managers_group, created = Group.objects.get_or_create(name="managers")
        if created:
            self.stdout.write(self.style.SUCCESS("Создана группа 'managers'"))

        users_to_update = []
        for user in User.objects.all():
            user_groups = list(user.groups.values_list("name", flat=True))

            if "managers" not in user_groups and "users" not in user_groups:
                user.groups.add(users_group)
                users_to_update.append(user.email)
                if verbose:
                    self.stdout.write(f"Добавлен в группу 'users': {user.email}")

            elif "users" in user_groups:
                if verbose:
                    self.stdout.write(f"Уже в группе 'users': {user.email}")

            elif "managers" in user_groups:
                if verbose:
                    self.stdout.write(f"Менеджер (пропуск): {user.email}")

        if users_to_update:
            self.stdout.write(self.style.SUCCESS(f"Обновлено {len(users_to_update)} пользователей"))
            if verbose:
                for email in users_to_update:
                    self.stdout.write(f"   • {email}")
        else:
            self.stdout.write(self.style.WARNING("Нет пользователей для обновления"))

        total_users = User.objects.count()
        users_in_users_group = User.objects.filter(groups__name="users").distinct().count()
        users_in_managers_group = User.objects.filter(groups__name="managers").distinct().count()

        self.stdout.write("\nСтатистика:")
        self.stdout.write(f"   Всего пользователей: {total_users}")
        self.stdout.write(f"   В группе 'users': {users_in_users_group}")
        self.stdout.write(f"   В группе 'managers': {users_in_managers_group}")
