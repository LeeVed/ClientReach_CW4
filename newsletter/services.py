import logging
from django.db.models import Count, Q
from django.utils import timezone
from django.core.mail import send_mail, BadHeaderError
from django.conf import settings

from .models import DispatchLog, Dispatch

logger = logging.getLogger(__name__)


def send_dispatch(dispatch, trigger_type="auto"):
    """
    Отправка рассылки через Django mail backend
    """
    now = timezone.now()

    # Проверяем можно ли отправлять через метод модели
    can_send, error_message = dispatch.can_send_now()
    if not can_send:
        if trigger_type == "manual":
            return False, error_message
        return False, None

    success_count = 0
    failed_count = 0
    total_count = dispatch.recipients.count()

    logger.info(f"[{trigger_type.upper()}] Начинаем отправку рассылки {dispatch.id} для {total_count} получателей")

    # Отправляем письмо каждому получателю
    for recipient in dispatch.recipients.all():
        try:
            # отправка через Django mail backend
            send_mail(
                subject=dispatch.message.subject,
                message=dispatch.message.text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
                fail_silently=False,
            )

            # Логируем успех
            DispatchLog.objects.create(
                dispatch=dispatch,
                recipient=recipient,
                status="success",
                trigger_type=trigger_type,
                server_response="Email successfully sent"
            )
            success_count += 1

        except BadHeaderError as e:
            # Ошибка в заголовках письма(защита от аттак)
            error_msg = f"BadHeaderError: {str(e)}"
            logger.error(f"[{trigger_type.upper()}] {error_msg} для {recipient.email}")

            DispatchLog.objects.create(
                dispatch=dispatch,
                recipient=recipient,
                status="failed",
                trigger_type=trigger_type,
                server_response=error_msg
            )
            failed_count += 1

        except Exception as e:
            # Другие ошибки отправки
            error_msg = f"Error: {str(e)}"
            logger.error(f"[{trigger_type.upper()}] Ошибка отправки для {recipient.email}: {error_msg}")

            DispatchLog.objects.create(
                dispatch=dispatch,
                recipient=recipient,
                status="failed",
                trigger_type=trigger_type,
                server_response=error_msg
            )
            failed_count += 1

    dispatch.last_sent_at = now
    dispatch.save(update_fields=["last_sent_at"])

    if dispatch.periodicity == "once":
        dispatch.status = "completed"
        dispatch.save(update_fields=["status"])
    else:
        dispatch.schedule_next_send()

    # Если были успешные отправки и рассылка была в статусе "created"
    if success_count > 0 and dispatch.status == "created":
        dispatch.status = "started"
        dispatch.save(update_fields=["status"])

    message = f"Отправлено {success_count}/{total_count} писем (успешно: {success_count}, ошибок: {failed_count})"
    logger.info(f"[{trigger_type.upper()}] Рассылка {dispatch.id} завершена: {message}")

    return True, message

def check_and_process_dispatches():
    """
    Функция для планировщика
    Проверяет и отправляет все запланированные рассылки
    """
    try:
        now = timezone.now()
        logger.info(f"Запуск планировщика рассылок в {now}")

        # Обновляем статусы всех активных рассылок
        updated_count = 0
        for dispatch in Dispatch.objects.filter(is_active=True):
            try:
                if dispatch.update_status():
                    updated_count += 1
            except Exception as e:
                logger.error(f"Ошибка при обновлении статуса рассылки {dispatch.pk}: {e}")

        # Находим рассылки для отправки (у которых наступило время next_sent_at)
        dispatches_to_send = Dispatch.objects.filter(
            is_active=True,
            status="started",
            next_sent_at__lte=now,
            first_sent_at__lte=now,
            end_sent_at__gte=now,
        ).select_related("message")

        results = []
        for dispatch in dispatches_to_send:
            try:
                success, message = send_dispatch(dispatch, trigger_type="auto")
                results.append({
                    "dispatch_pk": dispatch.pk,
                    "subject": dispatch.message.subject if dispatch.message else "Без темы",
                    "success": success,
                    "message": message
                })
            except Exception as e:
                logger.error(f"Ошибка при отправке рассылки {dispatch.pk}: {e}")
                results.append({
                    "dispatch_pk": dispatch.pk,  # Используем pk вместо id
                    "subject": dispatch.message.subject if dispatch.message else "Без темы",
                    "success": False,
                    "message": str(e)
                })

        # Логируем результаты
        successful_sends = sum(1 for r in results if r["success"])
        total_attempted = len(results)

        logger.info(
            f"Планировщик: обновлено статусов {updated_count}, "
            f"обработано рассылок {total_attempted}, "
            f"успешно: {successful_sends}"
        )

        return {
            "timestamp": now.isoformat(),
            "status_updated": updated_count,
            "processed": total_attempted,
            "successful": successful_sends,
            "failed": total_attempted - successful_sends,
            "details": results
        }

    except Exception as e:
        logger.error(f"Критическая ошибка в планировщике: {e}", exc_info=True)
        return {
            "timestamp": timezone.now().isoformat(),
            "error": str(e),
            "processed": 0,
            "successful": 0,
            "failed": 0
        }

def manual_start_dispatch(dispatch_id, user):
    """
    Ручной запуск рассылки пользователем
    """
    try:
        # Проверяем права доступа
        dispatch = Dispatch.objects.get(id=dispatch_id, owner=user)

        # Проверяем доступность через метод модели
        can_send, error_message = dispatch.can_send_now()
        if not can_send:
            return False, error_message

        # Запускаем отправку
        success, message = send_dispatch(dispatch, trigger_type='manual')

        return success, message

    except Dispatch.DoesNotExist:
        return False, "Рассылка не найдена или у вас нет прав доступа"
    except Exception as e:
        logger.error(f"Ошибка при ручном запуске рассылки {dispatch_id}: {e}")
        return False, f"Внутренняя ошибка: {str(e)}"


def pause_dispatch(dispatch_id, user):
    """
    Приостановка рассылки
    """
    try:
        dispatch = Dispatch.objects.get(id=dispatch_id, owner=user)

        if dispatch.status == "completed":
            return False, "Невозможно приостановить завершенную рассылку"

        dispatch.is_active = False
        dispatch.status = "paused"
        dispatch.save(update_fields=["is_active", "status"])

        logger.info(f"Рассылка {dispatch_id} приостановлена пользователем {user.id}")
        return True, "Рассылка приостановлена"

    except Dispatch.DoesNotExist:
        return False, "Рассылка не найдена"
    except Exception as e:
        logger.error(f"Ошибка при приостановке рассылки: {e}")
        return False, f"Ошибка: {str(e)}"


def resume_dispatch(dispatch_id, user):
    """
    Возобновление приостановленной рассылки
    """
    try:
        dispatch = Dispatch.objects.get(id=dispatch_id, owner=user)

        if dispatch.status != "paused":
            return False, "Можно возобновить только приостановленные рассылки"

        now = timezone.now()

        # Проверяем, не истекла ли рассылка
        if dispatch.end_sent_at < now:
            dispatch.status = "completed"
            dispatch.is_active = False
            message = "Время рассылки истекло, она переведена в статус завершенной"
        else:
            dispatch.is_active = True
            dispatch.status = "started" if dispatch.first_sent_at <= now else "created"
            message = "Рассылка возобновлена"

        dispatch.save()
        return True, message

    except Dispatch.DoesNotExist:
        return False, "Рассылка не найдена"
    except Exception as e:
        logger.error(f"Ошибка при возобновлении рассылки: {e}")
        return False, f"Ошибка: {str(e)}"


def get_user_mailing_statistics(user):
    """
    Собирает статистику по рассылкам пользователя:
    1. Количество успешных попыток
    2. Количество неуспешных попыток
    3. Количество отправленных сообщений
    """
    try:
        dispatches = user.dispatches.all().annotate(
            success_count=Count("logs", filter=Q(logs__status="success")),
            failed_count=Count("logs", filter=Q(logs__status="failed")),
            recipients_count=Count("recipients"),
        )

        total_success = sum(d.success_count or 0 for d in dispatches)
        total_failed = sum(d.failed_count or 0 for d in dispatches)

        return {
            "total_success_attempts": total_success,
            "total_failed_attempts": total_failed,
            "total_messages_sent": total_success,
            "total_attempts": total_success + total_failed,
            "total_dispatches": dispatches.count(),
            "dispatches_with_counts": dispatches,
        }
    except Exception as e:
        logger.error(f"Ошибка при сборе статистики для пользователя {user.id}: {e}")
        return {
            "total_success_attempts": 0,
            "total_failed_attempts": 0,
            "total_messages_sent": 0,
            "total_attempts": 0,
            "total_dispatches": 0,
            "dispatches_with_counts": [],
        }

def get_upcoming_dispatches(user, hours=24):
    """
    Возвращает ближайшие запланированные рассылки пользователя
    """
    now = timezone.now()
    later = now + timezone.timedelta(hours=hours)

    upcoming = user.dispatches.filter(
        is_active=True,
        status__in=["created", "started"],
        next_sent_at__gte=now,
        next_sent_at__lte=later,
    ).order_by('next_sent_at')

    return upcoming
