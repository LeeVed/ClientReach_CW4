from django.core.management.base import BaseCommand

from newsletter.models import Dispatch
from newsletter.models import DispatchLog


class Command(BaseCommand):
    help = "Симуляция отправки запланированных рассылок"

    def handle(self, *args, **options):
        # ищет все рассылки со статусом "created"
        dispatches = Dispatch.objects.filter(status="created")
        # если не находит, выводит сообщение и останавливается
        if not dispatches.exists():
            self.stdout.write("Нет рассылок для отправки")
            return
        for dispatch in dispatches:
            # если находит меняет статус на "started" и сохраняет
            dispatch.status = "started"
            dispatch.save()

            # создаёт логи в DispatchLog (отчет)
            DispatchLog.objects.create(
                dispatch=dispatch, status="success", server_response=f"Отправлено через командную строку."
            )

            self.stdout.write(f"Рассылка #{dispatch.pk} отправлена")
        # выводит отчет в консоль
        self.stdout.write(f"Готово! Отправлено {dispatches.count()} рассылок")
