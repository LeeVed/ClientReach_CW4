from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import logging


logger = logging.getLogger(__name__)


class Subscriber(models.Model):
    """
    Получатель рассылки
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Владелец",
        related_name="subscribers",
        null=True,
        blank=True,
    )
    email = models.EmailField(unique=True, verbose_name="Email адрес")
    full_name = models.CharField(max_length=150, verbose_name="Ф.И.О.", blank=True, help_text="Фамилия Имя Отчество")
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    # для статистики
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Получатель рассылки"
        verbose_name_plural = "Получатели рассылки"
        ordering = ["email"]
        permissions = [
            ("can_view_all_subscribers", "Может просматривать всех получателей"),
        ]

    def __str__(self):
        return self.email


class Message(models.Model):
    """
    Модель Сообщение
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Владелец",
        related_name="messages",
        null=True,  # для существующих записей
        blank=True,
    )
    subject = models.CharField(
        max_length=200,
        verbose_name="Тема письма",
    )
    text = models.TextField(verbose_name="Тело письма", help_text="Содержимое письма")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        ordering = ["-created_at"]
        permissions = [
            ("can_view_all_messages", "Может просматривать все сообщения"),
        ]

    def __str__(self):
        date_str = self.created_at.strftime("%d.%m.%Y")
        # Если тема слишком длинная, обрезаем
        if len(self.subject) > 50:
            return f"{self.subject[:47]}... ({date_str})"
        return f"{self.subject} ({date_str})"


class Dispatch(models.Model):
    """Модель рассылки"""

    STATUS_CHOICES = [
        ("created", "Создана"),
        ("started", "Запущена"),
        ("completed", "Завершена"),
        ("paused", "Приостановлена"),
    ]

    PERIODICITY_CHOICES = [
        ("once", "Однократно"),
        ("daily", "Ежедневно"),
        ("weekly", "Еженедельно"),
        ("monthly", "Ежемесячно"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Владелец",
        related_name="dispatches",
        null=False,
        blank=False,
    )

    first_sent_at = models.DateTimeField(verbose_name="Дата и время первой отправки")
    end_sent_at = models.DateTimeField(verbose_name="Дата и время окончания отправки")
    periodicity = models.CharField(
        max_length=20,
        choices=PERIODICITY_CHOICES,
        default="once",
        verbose_name="Периодичность"
    )
    last_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата последней отправки"
    )
    next_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата следующей отправки"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="created",
        verbose_name="Статус"
    )
    message = models.ForeignKey(
        "Message",
        on_delete=models.CASCADE,
        verbose_name="Сообщение",
        related_name="dispatches"
    )
    recipients = models.ManyToManyField(
        "Subscriber",
        verbose_name="Получатели",
        related_name="dispatches"
    )

    class Meta:
        verbose_name = "Рассылка"
        verbose_name_plural = "Рассылки"
        ordering = ["-first_sent_at"]
        permissions = [
            ("can_view_all_dispatches", "Может просматривать все рассылки"),
            ("can_pause_dispatch", "Может приостанавливать рассылки"),
            ("can_resume_dispatch", "Может возобновлять рассылки"),
        ]

    def __str__(self):
        if self.message:
            return f"{self.message.subject} ({self.get_status_display()})"
        return f"Рассылка #{self.pk} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        """
        Автоматическая валидация и расчет next_sent_at
        """
        skip_validation = kwargs.pop('skip_validation', False)

        # При создании новой рассылки устанавливаем next_sent_at
        if not self.pk and self.status == "created":
            self.next_sent_at = self.first_sent_at

            # Если время уже наступило - сразу запускаем
            now = timezone.now()
            if self.first_sent_at <= now <= self.end_sent_at:
                self.status = "started"
                # Сразу отправляем через services
                from .services import send_dispatch
                send_dispatch(self, trigger_type="auto")

        if not skip_validation:
            self.clean()

        super().save(*args, **kwargs)

    def clean(self):
        """Валидация данных перед сохранением"""

        errors = {}
        now = timezone.now()

        if self.status == "created" and self.first_sent_at and self.first_sent_at < now:
            errors["first_sent_at"] = "Дата начала не может быть в прошлом для новой рассылки"

        if self.first_sent_at and self.end_sent_at:
            if self.first_sent_at >= self.end_sent_at:
                errors["end_sent_at"] = "Дата окончания должна быть позже даты начала"
            # Для периодических рассылок минимальный интервал - 1 день
            if self.periodicity != "once":
                days_diff = (self.end_sent_at - self.first_sent_at).days
                if days_diff < 1:
                    errors["end_sent_at"] = "Для периодических рассылок минимальный период - 1 день"

        # если статус completed, даты должны быть в прошлом
        if self.status == "completed":
            if self.first_sent_at and self.first_sent_at > now:
                errors["first_sent_at"] = "Завершённая рассылка не может начинаться в будущем"
            if self.end_sent_at and self.end_sent_at > now:
                errors["end_sent_at"] = "Завершённая рассылка не может заканчиваться в будущем"

        if errors:
            raise ValidationError(errors)

    def update_status(self):
        """
        Автоматическое обновление статуса рассылки на основе текущего времени
        """
        now = timezone.now()

        if self.status == "paused":
            return False

        if now < self.first_sent_at:
            new_status = "created"
        elif self.first_sent_at <= now <= self.end_sent_at:
            new_status = "started"
        else:
            new_status = "completed"

        if self.status != new_status:
            self.status = new_status
            self.save(update_fields=["status"])

            if new_status == "started":
                self.schedule_next_send()

            return True

        return False

    def schedule_next_send(self):
        """Рассчитывает следующее время отправки на основе периодичности"""

        if self.status != "started" or not self.is_active:
            return None

        if not self.last_sent_at:
            self.next_sent_at = self.first_sent_at
            self.save(update_fields=["next_sent_at"])
            return self.next_sent_at

        if self.periodicity == "once":
            self.next_sent_at = None

        elif self.periodicity == "daily":
            self.next_sent_at = self.last_sent_at + timedelta(days=1)

        elif self.periodicity == "weekly":
            self.next_sent_at = self.last_sent_at + timedelta(weeks=1)

        elif self.periodicity == "monthly":
            self.next_sent_at = self.last_sent_at + timedelta(days=30)

        # Проверяем, что следующая отправка не позже окончания рассылки
        if self.next_sent_at and self.next_sent_at > self.end_sent_at:
            self.next_sent_at = None
            self.status = "completed"
            self.save(update_fields=["status", "next_sent_at"])
        else:
            self.save(update_fields=["next_sent_at"])

        return self.next_sent_at

    def can_send_now(self):
        """Проверяет, можно ли отправить рассылку сейчас"""

        now = timezone.now()

        if not self.is_active:
            return False, "Рассылка неактивна"

        if self.status not in ["started", "created"]:
            return False, f"Невозможно отправить в статусе {self.get_status_display()}"

        if now < self.first_sent_at:
            return False, "Время рассылки еще не наступило"

        if now > self.end_sent_at:
            return False, "Время рассылки истекло"

        # Для периодических рассылок проверяем next_sent_at
        if self.periodicity != "once" and self.next_sent_at:
            # Разрешаем отправку ±5 минут от запланированного времени
            time_diff = abs((self.next_sent_at - now).total_seconds())
            if time_diff > 300:  # 5 минут в секундах
                return False, "Не время для отправки по расписанию"

        return True, ""

    def send(self, trigger_type='auto'):
        """
        Отправляет рассылку всем получателям через сервисный слой
        Возвращает (успех, сообщение)
        """
        from .services import send_dispatch
        return send_dispatch(self, trigger_type)

    def manual_start(self):
        """
        Ручной запуск рассылки через сервисный слой
        """
        from .services import manual_start_dispatch
        return manual_start_dispatch(self.pk, self.owner)

    def pause(self):
        """
        Приостановка рассылки через сервисный слой
        """
        from .services import pause_dispatch
        return pause_dispatch(self.pk, self.owner)

    def resume(self):
        """
        Возобновление рассылки через сервисный слой
        """
        from .services import resume_dispatch
        return resume_dispatch(self.pk, self.owner)

    @classmethod
    def get_mailings_to_process(cls):
        """
        Возвращает все рассылки, которые нужно обработать
        """

        now = timezone.now()

        return cls.objects.filter(
            is_active=True,
            status__in=["created", "started"],
            first_sent_at__lte=now,
            end_sent_at__gte=now
        ).exclude(status="paused")

    @classmethod
    def check_and_send_scheduled(cls):
        """
        Проверяет и отправляет все запланированные рассылки
        Используется планировщиком
        """
        now = timezone.now()

        mailings_to_send = cls.objects.filter(
            is_active=True,
            status="started",
            next_sent_at__lte=now,
            first_sent_at__lte=now,
            end_sent_at__gte=now,
        ).select_related('message')

        results = []
        for dispatch in mailings_to_send:
            try:
                success, message = dispatch.send(trigger_type="auto")
                results.append({
                    "dispatch_pk": dispatch.pk,
                    "subject": dispatch.message.subject if dispatch.message else "Без темы",
                    "success": success,
                    "message": message
                })
            except Exception as e:
                logger.error(f"Ошибка при отправке рассылки {dispatch.pk}: {e}")
                results.append({
                    "dispatch_pk": dispatch.pk,
                    "subject": dispatch.message.subject if dispatch.message else "Без темы",
                    "success": False,
                    "message": str(e)
                })

        return results


class DispatchLog(models.Model):
    """Модель попытки рассылки"""

    STATUS_CHOICES = [
        ("success", "Успешно"),
        ("failed", "Не успешно"),
    ]

    TRIGGER_CHOICES = [
        ("auto", "Автоматически"),
        ("manual", "Вручную"),
    ]

    attempt_time = models.DateTimeField(auto_now_add=True, verbose_name="Дата и время попытки")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name="Статус")
    server_response = models.TextField(verbose_name="Ответ почтового сервера", blank=True)
    dispatch = models.ForeignKey(
        "Dispatch",
        on_delete=models.CASCADE,
        verbose_name="Рассылка",
        related_name="logs"
    )
    recipient = models.ForeignKey(
        "Subscriber",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Получатель",
        related_name="logs"
    )
    trigger_type = models.CharField(
        max_length=20,
        choices=TRIGGER_CHOICES,
        default="auto",
        verbose_name="Тип запуска"
    )

    class Meta:
        verbose_name = "Попытка рассылки"
        verbose_name_plural = "Попытки рассылок"
        ordering = ["-attempt_time"]
        indexes = [
            models.Index(fields=['dispatch', 'status']),
            models.Index(fields=['attempt_time']),
        ]

    def __str__(self):
        status_display = self.get_status_display()
        time_str = self.attempt_time.strftime("%d.%m.%Y %H:%M")
        recipient_str = f" для {self.recipient.email}" if self.recipient else ""
        trigger_str = f" [{self.get_trigger_type_display()}]"
        return f"Попытка #{self.pk}{trigger_str} - {status_display}{recipient_str} - {time_str}"
