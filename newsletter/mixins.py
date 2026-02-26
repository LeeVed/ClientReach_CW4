from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class OwnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Проверка прав доступа к объекту:
    - Владелец может всё со своими объектами
    - Менеджеры могут только просматривать (НЕ редактировать/удалять)
    - Суперпользователи могут всё
    """

    def test_func(self):
        obj = self.get_object()

        if self.request.user.is_superuser:
            return True

        if self.request.user.groups.filter(name="managers").exists():
            if self.request.method not in ["GET", "HEAD", "OPTIONS"]:
                return False
            return True

        return obj.owner == self.request.user


class ManagerCanViewMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Миксин для менеджеров: могут просматривать, но не изменять
    для ListView и DetailView
    """

    def test_func(self):
        if self.request.user.is_superuser:
            return True

        if self.request.user.groups.filter(name="managers").exists():
            return True

        # Для DetailView - проверяем владельца
        if hasattr(self, "get_object") and self.get_object:
            try:
                obj = self.get_object()
                return obj.owner == self.request.user
            except (AttributeError, TypeError):
                return True

        return True


class ManagerRestrictedMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Миксин для операций изменения (CreateView, UpdateView, DeleteView)
    Менеджеры не имеют доступа к этим операциям
    """

    def test_func(self):

        if self.request.user.groups.filter(name="managers").exists():
            return False

        if self.request.user.is_superuser:
            return True

        if hasattr(self, "get_object") and self.get_object:
            try:
                obj = self.get_object()
                return obj.owner == self.request.user
            except (AttributeError, TypeError):
                # Для CreateView (нет объекта) - разрешаем
                return True

        return True
