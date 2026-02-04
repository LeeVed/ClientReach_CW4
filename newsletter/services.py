import random

from django.db.models import Count
from django.db.models import Q
from django.utils import timezone

from .models import DispatchLog


def send_dispatch_simulation(dispatch):
    """Симуляция отправки рассылки"""

    now = timezone.now()

    # проверяем время
    if not (dispatch.first_sent_at <= now <= dispatch.end_sent_at):
        return False, "Время отправки не наступило или уже прошло"

    success_count = 0
    total_count = dispatch.recipients.count()

    for recipient in dispatch.recipients.all():
        is_success = random.random() > 0.2

        DispatchLog.objects.create(
            dispatch=dispatch,
            status="success" if is_success else "failed",
            server_response=(
                f"Email sent to {recipient.email}"
                if is_success
                else f"Failed to send to {recipient.email}: simulated error"
            ),
        )

        if is_success:
            success_count += 1

    if success_count > 0:
        dispatch.status = "started"
        dispatch.save(update_fields=["status"])

    return True, f"Отправлено {success_count}/{total_count} писем"


def get_user_mailing_statistics(user):
    """Собирает статистику по рассылкам пользователя по заданию:
    1. Количество успешных попыток
    2. Количество неуспешных попыток
    3. Количество отправленных сообщений
    """
    # Получаем все рассылки пользователя с аннотациями
    dispatches = user.dispatches.all().annotate(
        success_count=Count("logs", filter=Q(logs__status="success")),
        failed_count=Count("logs", filter=Q(logs__status="failed")),
        recipients_count=Count("recipients"),
    )
    # Суммируем общую статистику
    total_success = sum(d.success_count or 0 for d in dispatches)
    total_failed = sum(d.failed_count or 0 for d in dispatches)

    return {
        "total_success_attempts": total_success,
        "total_failed_attempts": total_failed,
        "total_messages_sent": total_success,  # отправленные = успешные
        "total_attempts": total_success + total_failed,
        "total_dispatches": dispatches.count(),
        "dispatches_with_counts": dispatches,  # рассылки с аннотациями
    }
