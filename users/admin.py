from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Персональная информация"), {"fields": ("first_name", "last_name", "phone_number", "country", "avatar")}),
        (
            _("Права и разрешения"),
            {
                "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
            },
        ),
        (_("Важные даты"), {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )

    list_display = ("email", "first_name", "last_name", "phone_number", "country", "is_staff")
    list_filter = ("is_staff", "is_superuser", "is_active", "country")
    search_fields = ("email", "first_name", "last_name", "phone_number", "country")
    ordering = ("email",)
