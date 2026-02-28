from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from django.core.mail import send_mail

from .models import CustomUser


class CustomUserCreationForm(UserCreationForm):
    """Форма для создания и валидации нового пользователя"""

    email = forms.EmailField(
        label="Email", widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Введите ваш email"})
    )
    password1 = forms.CharField(
        label="Пароль", widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Введите пароль"})
    )

    password2 = forms.CharField(
        label="Подтверждение пароля",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Повторите пароль"}),
    )
    phone_number = forms.CharField(
        max_length=15,
        required=False,
        label="Номер телефона",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Введите номер вашего телефона"}),
    )
    country = forms.CharField(
        max_length=50,
        required=False,
        label="Страна",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Укажите название вашей страны"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "username" in self.fields:
            del self.fields["username"]

    class Meta:
        model = CustomUser
        fields = ("email", "phone_number", "country", "password1", "password2")

    def clean_email(self):
        """Проверка уникальности email"""

        email = self.cleaned_data.get("email")
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже существует")
        return email

    def send_welcome_email(self, user):
        """Отправляет приветственное письмо пользователю"""

        subject = "Добро пожаловать в ClientReach!"
        message = f"""Здравствуйте, {user.email}!

    Спасибо за регистрацию в нашем сервисе рассылок ClientReach!
    Желаем вам успешной коммуникации!

    С уважением,
    Команда ClientReach"""

        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [user.email]

        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=recipient_list,
            )
            print(f"Приветственное письмо отправлено на {user.email}")
        except Exception as e:
            print(f"Не удалось отправить письмо: {e}")

    def save(self, commit=True):
        """Сохраняет пользователя и отправляет приветственное письмо"""

        user = super().save(commit=False)

        if commit:
            user.save()
            self.send_welcome_email(user)

        return user


class CustomAuthenticationForm(AuthenticationForm):
    """Форма для существующего в БД пользователя для входа в систему по email"""

    username = forms.EmailField(
        label="Email", widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Введите ваш email"})
    )

    password = forms.CharField(
        label="Пароль", widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Введите пароль"})
    )

    error_messages = {
        "invalid_login": "Пожалуйста, введите правильные email и пароль.",
        "inactive": "Этот аккаунт неактивен.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"
