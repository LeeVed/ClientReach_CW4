from django import forms

from .models import Dispatch
from .models import Message
from .models import Subscriber


class SubscriberForm(forms.ModelForm):
    class Meta:
        model = Subscriber
        fields = ["email", "full_name", "comment"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Добавляем Bootstrap классы всем полям
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ["subject", "text"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Добавляем Bootstrap классы всем полям
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"


class DispatchForm(forms.ModelForm):
    class Meta:
        model = Dispatch
        fields = ["first_sent_at", "end_sent_at", "status", "message", "recipients"]
        widgets = {
            "first_sent_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "end_sent_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "recipients": forms.SelectMultiple(attrs={"size": 10}),
        }

    def __init__(self, *args, **kwargs):
        # Получаем пользователя из kwargs
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Добавляем Bootstrap классы всем полям
        for field_name, field in self.fields.items():
            field.widget.attrs["class"] = "form-control"

        # Ограничиваем выбор для обычных пользователей
        if self.user and not self.user.groups.filter(name="managers").exists():
            # Ограничиваем получателей только своими подписчиками
            self.fields["recipients"].queryset = Subscriber.objects.filter(owner=self.user)

            # Ограничиваем сообщения только своими
            self.fields["message"].queryset = Message.objects.filter(owner=self.user)
