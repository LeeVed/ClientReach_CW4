from django.contrib import admin

from .models import Dispatch
from .models import DispatchLog
from .models import Message
from .models import Subscriber


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "full_name", "comment_preview", "created_at")
    list_filter = ("created_at",)
    search_fields = ("email", "full_name", "comment")
    readonly_fields = ("created_at",)

    def comment_preview(self, obj):
        """Краткий просмотр комментария"""

        if obj.comment and obj.comment.strip():
            clean_comment = " ".join(obj.comment.strip().split())
            if len(clean_comment) > 50:
                return f"{clean_comment[:47]}..."
            return clean_comment
        return "—"

    # человекочитаемый заголовок в колонке вместо comment_preview
    comment_preview.short_description = "Комментарий"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("subject_preview", "created_at", "text_preview")
    list_filter = ("created_at",)
    search_fields = ("subject", "text")
    readonly_fields = ("created_at",)

    def subject_preview(self, obj):
        """Превью темы сообщения"""

        if obj.subject and obj.subject.strip():
            clean_subject = " ".join(obj.subject.strip().split())
            if len(clean_subject) > 50:
                return f"{clean_subject[:47]}..."
            return clean_subject
        return "—"

    # человекочитаемый заголовок в колонке вместо subject_preview
    subject_preview.short_description = "Тема"

    def text_preview(self, obj):
        """Превью текста сообщения"""

        if obj.text and obj.text.strip():
            clean_text = " ".join(obj.text.strip().split())
            if len(clean_text) > 100:
                return f"{clean_text[:97]}..."
            return clean_text
        return "—"

    # человекочитаемый заголовок в колонке вместо text_preview
    text_preview.short_description = "Текст"


@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin):
    actions = ["send_dispatches_action"]
    list_display = ("id", "status", "first_sent_at", "end_sent_at", "message_preview")
    list_filter = ("status", "first_sent_at")
    # для демонстрации (обзор всех вариантов с малочисленными элементами)
    filter_horizontal = ["recipients"]

    def message_preview(self, obj):
        """Превью сообщения в рассылке"""

        if obj.message and obj.message.subject:
            subject = obj.message.subject.strip()
            if len(subject) > 30:
                return f"{subject[:27]}..."
            return subject
        return "—"

    # человекочитаемый заголовок в колонке вместо message_preview
    message_preview.short_description = "Сообщение"

    def send_dispatches_action(self, request, queryset):
        """Действие для отправки выбранных рассылок (симуляция)"""

        for dispatch in queryset:
            dispatch.status = "started"
            dispatch.save()

            DispatchLog.objects.create(
                dispatch=dispatch, status="success", server_response=f"Отправлено через админку"
            )
        self.message_user(request, f"Рассылки отправлены")

    # человекочитаемый заголовок в колонке вместо send_dispatches_action
    send_dispatches_action.short_description = "Отправить выбранные рассылки"


@admin.register(DispatchLog)
class DispatchLogAdmin(admin.ModelAdmin):
    list_display = ("id", "dispatch_preview", "status", "attempt_time", "response_preview")
    list_filter = ("status", "attempt_time")
    readonly_fields = ("attempt_time",)
    search_fields = ("dispatch__id", "server_response")

    def dispatch_preview(self, obj):
        """Превью рассылки в логах"""

        if obj.dispatch and obj.dispatch.message:
            return f"Рассылка #{obj.dispatch.id} - {obj.dispatch.message.subject[:30]}..."
        return f"Рассылка #{obj.dispatch.id}"

    # человекочитаемый заголовок в колонке вместо dispatch_preview
    dispatch_preview.short_description = "Рассылка"

    def response_preview(self, obj):
        """Превью ответа сервера"""

        if obj.server_response:
            text = obj.server_response.strip()
            if len(text) > 50:
                return f"{text[:47]}..."
            return text
        return "—"

    # человекочитаемый заголовок в колонке вместо response_preview
    response_preview.short_description = "Ответ сервера"
