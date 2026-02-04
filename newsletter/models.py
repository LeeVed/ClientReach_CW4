from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Владелец",
        related_name="dispatches",
        null=False,
        blank=False,
    )
    # устанавливается вручную
    first_sent_at = models.DateTimeField(verbose_name="Дата и время первой отправки")
    end_sent_at = models.DateTimeField(verbose_name="Дата и время окончания отправки")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="created", verbose_name="Статус")
    message = models.ForeignKey(Message, on_delete=models.CASCADE, verbose_name="Сообщение", related_name="dispatches")
    recipients = models.ManyToManyField(Subscriber, verbose_name="Получатели", related_name="dispatches")

    class Meta:
        verbose_name = "Рассылка"
        verbose_name_plural = "Рассылки"
        ordering = ["-first_sent_at"]

    def __str__(self):
        if self.message:
            return f"{self.message.subject} ({self.get_status_display()})"
        return f"Рассылка #{self.pk} ({self.get_status_display()})"

    def update_status(self):
        """
        Автоматическое обновление статуса рассылки на основе текущего времени
        """
        now = timezone.now()
        # Определяем новый статус
        if now < self.first_sent_at:
            new_status = "created"
        elif self.first_sent_at <= now <= self.end_sent_at:
            new_status = "started"
        else:
            new_status = "completed"
        # Обновляем, если статус изменился
        if self.status != new_status:
            self.status = new_status
            self.save(update_fields=["status"])
            return True

        return False  # Статус не изменился

    def clean(self):
        """Валидация данных перед сохранением"""
        errors = {}
        now = timezone.now()

        # first_sent_at не может быть в прошлом (если статус created)
        if self.status == "created" and self.first_sent_at and self.first_sent_at < now:
            errors["first_sent_at"] = "Дата начала не может быть в прошлом для новой рассылки"

        # first_sent_at должен быть раньше end_sent_at
        if self.first_sent_at and self.end_sent_at:
            if self.first_sent_at >= self.end_sent_at:
                errors["end_sent_at"] = "Дата окончания должна быть позже даты начала"

        # если статус completed, даты должны быть в прошлом
        if self.status == "completed":
            if self.first_sent_at and self.first_sent_at > now:
                errors["first_sent_at"] = "Завершённая рассылка не может начинаться в будущем"
            if self.end_sent_at and self.end_sent_at > now:
                errors["end_sent_at"] = "Завершённая рассылка не может заканчиваться в будущем"

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Переопределяем save для автоматической валидации"""

        self.clean()
        super().save(*args, **kwargs)


class DispatchLog(models.Model):
    """Модель попытки рассылки"""

    STATUS_CHOICES = [
        ("success", "Успешно"),
        ("failed", "Не успешно"),
    ]
    # Дата и время попытки (datetime)
    attempt_time = models.DateTimeField(auto_now_add=True, verbose_name="Дата и время попытки")
    # Статус (Успешно/Не успешно)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name="Статус")
    # Ответ почтового сервера
    server_response = models.TextField(verbose_name="Ответ почтового сервера", blank=True)
    # Рассылка (внешний ключ на модель «Рассылка»)
    dispatch = models.ForeignKey("Dispatch", on_delete=models.CASCADE, verbose_name="Рассылка", related_name="logs")

    class Meta:
        verbose_name = "Попытка рассылки"
        verbose_name_plural = "Попытки рассылок"
        ordering = ["-attempt_time"]

    def __str__(self):
        status_display = self.get_status_display()
        time_str = self.attempt_time.strftime("%d.%m.%Y %H:%M")
        return f"Попытка #{self.pk} - {status_display} - {time_str}"
