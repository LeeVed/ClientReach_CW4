from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from newsletter.models import Subscriber, Message, Dispatch


class Command(BaseCommand):
    help = "Синхронизирует группы пользователей и назначает права"

    def add_arguments(self, parser):
        parser.add_argument("--verbose", action="store_true", help="Подробный вывод")

    def handle(self, *args, **options):
        User = get_user_model()
        verbose = options["verbose"]

        # Создаем или получаем группы
        users_group, users_created = Group.objects.get_or_create(name="users")
        if users_created:
            self.stdout.write(self.style.SUCCESS("Создана группа 'users'"))

        managers_group, managers_created = Group.objects.get_or_create(name="managers")
        if managers_created:
            self.stdout.write(self.style.SUCCESS("Создана группа 'managers'"))

        # === НАЗНАЧАЕМ ПРАВА ДЛЯ МЕНЕДЖЕРОВ ===
        if verbose:
            self.stdout.write("\n" + "="*50)
            self.stdout.write("Назначение прав для группы 'managers'")
            self.stdout.write("="*50)

        # Получаем content types для моделей
        subscriber_ct = ContentType.objects.get_for_model(Subscriber)
        message_ct = ContentType.objects.get_for_model(Message)
        dispatch_ct = ContentType.objects.get_for_model(Dispatch)

        # Права для просмотра всех получателей
        view_subscribers_permission, _ = Permission.objects.get_or_create(
            codename="can_view_all_subscribers",
            name="Может просматривать всех получателей",
            content_type=subscriber_ct,
        )

        # Права для просмотра всех сообщений
        view_messages_permission, _ = Permission.objects.get_or_create(
            codename="can_view_all_messages",
            name="Может просматривать все сообщения",
            content_type=message_ct,
        )

        # Права для просмотра всех рассылок
        view_dispatches_permission, _ = Permission.objects.get_or_create(
            codename="can_view_all_dispatches",
            name="Может просматривать все рассылки",
            content_type=dispatch_ct,
        )

        # Права для приостановки рассылок
        pause_dispatch_permission, _ = Permission.objects.get_or_create(
            codename="can_pause_dispatch",
            name="Может приостанавливать рассылки",
            content_type=dispatch_ct,
        )

        # Права для возобновления рассылок
        resume_dispatch_permission, _ = Permission.objects.get_or_create(
            codename="can_resume_dispatch",
            name="Может возобновлять рассылки",
            content_type=dispatch_ct,
        )

        # Собираем все права для менеджеров
        managers_permissions = [
            view_subscribers_permission,
            view_messages_permission,
            view_dispatches_permission,
            pause_dispatch_permission,
            resume_dispatch_permission,
        ]

        # Назначаем права группе менеджеров
        for permission in managers_permissions:
            managers_group.permissions.add(permission)
            if verbose:
                self.stdout.write(f"  ✓ Добавлено право: {permission.name}")

        if verbose:
            self.stdout.write(self.style.SUCCESS(f"\nВсего прав назначено: {len(managers_permissions)}"))

        # === РАСПРЕДЕЛЕНИЕ ПОЛЬЗОВАТЕЛЕЙ ПО ГРУППАМ ===
        if verbose:
            self.stdout.write("\n" + "="*50)
            self.stdout.write("Распределение пользователей по группам")
            self.stdout.write("="*50)

        users_to_update = []
        for user in User.objects.all():
            user_groups = list(user.groups.values_list("name", flat=True))

            if "managers" not in user_groups and "users" not in user_groups:
                user.groups.add(users_group)
                users_to_update.append(user.email)
                if verbose:
                    self.stdout.write(f"  ➕ Добавлен в группу 'users': {user.email}")

            elif "users" in user_groups:
                if verbose:
                    self.stdout.write(f"  ✓ Уже в группе 'users': {user.email}")

            elif "managers" in user_groups:
                if verbose:
                    self.stdout.write(f"  👤 Менеджер: {user.email}")

        if users_to_update:
            self.stdout.write(self.style.SUCCESS(f"\nОбновлено {len(users_to_update)} пользователей"))
            if verbose:
                for email in users_to_update:
                    self.stdout.write(f"   • {email}")
        else:
            self.stdout.write(self.style.WARNING("\nНет пользователей для обновления"))

        # === СТАТИСТИКА ===
        total_users = User.objects.count()
        users_in_users_group = User.objects.filter(groups__name="users").distinct().count()
        users_in_managers_group = User.objects.filter(groups__name="managers").distinct().count()

        # Считаем количество прав у группы менеджеров
        managers_permissions_count = managers_group.permissions.count()

        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS("ИТОГОВАЯ СТАТИСТИКА"))
        self.stdout.write("="*50)
        self.stdout.write(f"   Всего пользователей: {total_users}")
        self.stdout.write(f"   В группе 'users': {users_in_users_group}")
        self.stdout.write(f"   В группе 'managers': {users_in_managers_group}")
        self.stdout.write(f"   Прав у группы 'managers': {managers_permissions_count}")

        if verbose and managers_permissions_count > 0:
            self.stdout.write("\n   Права группы 'managers':")
            for permission in managers_group.permissions.all().order_by("content_type__model"):
                self.stdout.write(f"      • {permission.name}")
