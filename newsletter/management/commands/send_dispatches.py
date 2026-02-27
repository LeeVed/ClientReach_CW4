from django.core.management.base import BaseCommand
from newsletter.services import check_and_process_dispatches


class Command(BaseCommand):
    help = "Запуск планировщика рассылок"

    def handle(self, *args, **options):
        self.stdout.write("Запуск планировщика рассылок...")
        result = check_and_process_dispatches()

        self.stdout.write(self.style.SUCCESS(
            f"Обработано рассылок: {result['processed']}, "
            f"успешно: {result['successful']}"
        ))
