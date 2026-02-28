from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.generic import CreateView
from django.views.generic import DeleteView
from django.views.generic import DetailView
from django.views.generic import ListView
from django.views.generic import TemplateView
from django.views.generic import UpdateView

from .forms import DispatchForm
from .forms import MessageForm
from .forms import SubscriberForm
from .models import Dispatch, DispatchLog
from .models import Message
from .models import Subscriber
from .services import get_user_mailing_statistics
from .services import manual_start_dispatch
from .services import pause_dispatch
from .services import resume_dispatch
from .mixins import ManagerCanViewMixin, ManagerRestrictedMixin


@cache_page(60 * 5)
def home_view(request):
    """
    Главная страница с статистикой рассылок
    """
    now = timezone.now()

    # Общее количество рассылок
    total_dispatches = Dispatch.objects.count()

    # Активные рассылки
    active_dispatches = Dispatch.objects.filter(
        first_sent_at__lte=now,
        end_sent_at__gte=now,
        status="started"
    ).count()

    # Уникальные получатели
    unique_recipients = Subscriber.objects.count()

    context = {
        "total_dispatches": total_dispatches,
        "active_dispatches": active_dispatches,
        "unique_recipients": unique_recipients,
    }

    # Если пользователь авторизован, добавляем его статистику
    if request.user.is_authenticated:
        # Количество рассылок текущего пользователя
        user_dispatches = Dispatch.objects.filter(owner=request.user)
        context["user_total_dispatches"] = user_dispatches.count()

        # Активные рассылки пользователя
        context["user_active_dispatches"] = user_dispatches.filter(
            first_sent_at__lte=now,
            end_sent_at__gte=now,
            status="started"
        ).count()

    return render(request, "newsletter/home.html", context)


@login_required
def dispatch_send_view(request, pk):
    """Ручной запуск рассылки"""

    # Проверяем права доступа
    is_manager_or_superuser = request.user.groups.filter(name="managers").exists() or request.user.is_superuser

    if is_manager_or_superuser:
        dispatch = get_object_or_404(Dispatch, pk=pk)
    else:
        dispatch = get_object_or_404(Dispatch, pk=pk, owner=request.user)

    # Проверяем что есть получатели
    if dispatch.recipients.count() == 0:
        messages.error(request, "Нет получателей для отправки.")
        return redirect("newsletter:dispatch_detail", pk=pk)

    # Запускаем рассылку через сервисную функцию
    success, result_message = manual_start_dispatch(dispatch.pk, request.user)

    if success:
        messages.success(request, f"Рассылка отправлена! {result_message}")
    else:
        messages.error(request, f"Ошибка при отправке: {result_message}")

    return redirect("newsletter:dispatch_detail", pk=pk)


@login_required
def dispatch_pause_view(request, pk):
    """Приостановка рассылки"""

    is_manager_or_superuser = request.user.groups.filter(name="managers").exists() or request.user.is_superuser

    if not is_manager_or_superuser:
        raise Http404("Доступ запрещен")

    success, message = pause_dispatch(pk, request.user)

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect("newsletter:dispatch_detail", pk=pk)


@login_required
def dispatch_resume_view(request, pk):
    """Возобновление рассылки"""
    is_manager_or_superuser = request.user.groups.filter(name="managers").exists() or request.user.is_superuser

    if not is_manager_or_superuser:
        raise Http404("Доступ запрещен")

    success, message = resume_dispatch(pk, request.user)

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect("newsletter:dispatch_detail", pk=pk)


class UserListView(LoginRequiredMixin, ListView):
    template_name = "newsletter/user_list.html"
    context_object_name = "users"

    def dispatch(self, request, *args, **kwargs):
        # Проверка прав доступа к этому view
        is_manager_or_superuser = (
            request.user.groups.filter(name="managers").exists() or request.user.is_superuser
        )
        if not is_manager_or_superuser:
            raise Http404("Доступ запрещен")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        User = get_user_model()

        if self.request.user.is_superuser:
            # Суперпользователь видит всех, кроме себя
            return User.objects.exclude(id=self.request.user.id).order_by("email")
        else:
            # Менеджер видит только НЕ суперпользователей
            return User.objects.filter(
                is_superuser=False
            ).exclude(
                id=self.request.user.id
            ).order_by("email")


class UserStatisticsView(LoginRequiredMixin, TemplateView):
    """Страница со статистикой пользователя"""

    template_name = "newsletter/user_statistics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statistics"] = get_user_mailing_statistics(self.request.user)
        return context


class SubscriberListView(ManagerCanViewMixin, ListView):
    """CBV для списка подписчиков"""

    model = Subscriber
    template_name = "newsletter/subscriber_list.html"
    context_object_name = "subscribers"

    def get_queryset(self):
        if self.request.user.is_superuser:
            # Суперпользователь видит всех
            return Subscriber.objects.all().select_related("owner")

        if self.request.user.groups.filter(name="managers").exists():
            # Менеджеры видят только подписчиков обычных пользователей
            return Subscriber.objects.filter(
                owner__is_superuser=False,
                owner__groups__name="users"
            ).select_related("owner")

        # Обычный пользователь видит только своих подписчиков
        return Subscriber.objects.filter(owner=self.request.user).select_related("owner")


class SubscriberCreateView(ManagerRestrictedMixin, CreateView):
    """CBV для создания подписчика"""

    model = Subscriber
    form_class = SubscriberForm
    template_name = "newsletter/subscriber_form.html"
    success_url = reverse_lazy("newsletter:subscriber_list")

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class SubscriberUpdateView(ManagerRestrictedMixin, UpdateView):
    """CBV для редактирования существующего подписчика"""

    model = Subscriber
    form_class = SubscriberForm
    template_name = "newsletter/subscriber_form.html"
    success_url = reverse_lazy("newsletter:subscriber_list")


class SubscriberDetailView(ManagerCanViewMixin, DetailView):
    """CBV для отображения детальной информации о подписчике"""

    model = Subscriber
    template_name = "newsletter/subscriber_detail.html"


class SubscriberDeleteView(ManagerRestrictedMixin, DeleteView):
    """CBV для удаления подписчика"""

    model = Subscriber
    template_name = "newsletter/subscriber_confirm_delete.html"
    success_url = reverse_lazy("newsletter:subscriber_list")


class MessageListView(ManagerCanViewMixin, ListView):
    """CBV для списка сообщений"""

    model = Message
    template_name = "newsletter/message_list.html"
    context_object_name = "message_list"

    def get_queryset(self):
        if self.request.user.is_superuser or self.request.user.groups.filter(name="managers").exists():
            # Суперпользователь и менеджер видят всех
            return Message.objects.all().select_related("owner")
        else:
            # Обычный пользователь видит только свои сообщения
            return Message.objects.filter(owner=self.request.user)


class MessageCreateView(ManagerRestrictedMixin, CreateView):
    """CBV для создания сообщения"""

    model = Message
    form_class = MessageForm
    template_name = "newsletter/message_form.html"
    success_url = reverse_lazy("newsletter:message_list")

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class MessageUpdateView(ManagerRestrictedMixin, UpdateView):
    """CBV для редактирования существующего сообщения"""

    model = Message
    form_class = MessageForm
    template_name = "newsletter/message_form.html"
    success_url = reverse_lazy("newsletter:message_list")


class MessageDetailView(ManagerCanViewMixin, DetailView):
    """CBV для отображения детальной информации о сообщении"""

    model = Message
    template_name = "newsletter/message_detail.html"


class MessageDeleteView(ManagerRestrictedMixin, DeleteView):
    """CBV для удаления сообщения"""

    model = Message
    template_name = "newsletter/message_confirm_delete.html"
    success_url = reverse_lazy("newsletter:message_list")


class DispatchListView(ManagerCanViewMixin, ListView):
    """CBV для списка рассылок"""

    @method_decorator(cache_page(60 * 3))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    model = Dispatch
    template_name = "newsletter/dispatch_list.html"
    context_object_name = "dispatch_list"

    def get_queryset(self):
        if self.request.user.is_superuser or self.request.user.groups.filter(name="managers").exists():
            # Суперпользователь и менеджер видят всех
            return Dispatch.objects.all().select_related("owner", "message")
        else:
            # Обычный пользователь видит только свои рассылки
            return Dispatch.objects.filter(owner=self.request.user).select_related("message")


class DispatchCreateView(ManagerRestrictedMixin, CreateView):
    """CBV для создания рассылки"""

    model = Dispatch
    form_class = DispatchForm
    template_name = "newsletter/dispatch_form.html"
    success_url = reverse_lazy("newsletter:dispatch_list")

    def get_form_kwargs(self):
        """Передаем пользователя в форму"""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class DispatchUpdateView(ManagerRestrictedMixin, UpdateView):
    """CBV для редактирования рассылки"""

    model = Dispatch
    form_class = DispatchForm
    template_name = "newsletter/dispatch_form.html"
    success_url = reverse_lazy("newsletter:dispatch_list")

    def get_form_kwargs(self):
        """Передаем пользователя в форму"""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class DispatchDetailView(ManagerCanViewMixin, DetailView):
    """CBV для отображения детальной информации о рассылке"""

    model = Dispatch
    template_name = "newsletter/dispatch_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dispatch = self.object
        user = self.request.user

        # Определяем специальные права
        is_manager = user.groups.filter(name="managers").exists()
        is_superuser = user.is_superuser
        is_special_user = is_manager or is_superuser
        is_owner = dispatch.owner == user

        context["is_manager"] = is_manager
        context["is_superuser"] = is_superuser
        context["is_special_user"] = is_special_user

        # Редактировать/удалять: только Суперпользователь и владелец
        context["can_edit"] = is_superuser or (not is_manager and is_owner)
        context["can_delete"] = is_superuser or (not is_manager and is_owner)

        # Отправлять: владелец или менеджер/суперпользователь
        context["can_send"] = (is_special_user or is_owner) and dispatch.status == "started"

        # Отключать/включать: только Суперпользователь и Менеджер
        context["can_toggle"] = is_special_user and dispatch.status != "completed"

        # Приостанавливать/возобновлять: только Суперпользователь и Менеджер
        context["can_pause"] = is_special_user and dispatch.status == "started"
        context["can_resume"] = is_special_user and dispatch.status == "paused"

        context["success_logs_count"] = dispatch.logs.filter(status="success").count()
        context["failed_logs_count"] = dispatch.logs.filter(status="failed").count()

        return context


class DispatchDeleteView(ManagerRestrictedMixin, DeleteView):
    """CBV для удаления рассылки"""

    model = Dispatch
    template_name = "newsletter/dispatch_confirm_delete.html"
    success_url = reverse_lazy("newsletter:dispatch_list")


class UserListView(LoginRequiredMixin, ListView):
    """Список пользователей сервиса только для менеджеров и суперпользователя"""

    template_name = "newsletter/user_list.html"
    context_object_name = "users"

    @method_decorator(cache_page(60 * 5))
    def dispatch(self, request, *args, **kwargs):
        # Проверка прав доступа к этому view
        is_manager_or_superuser = (
            request.user.groups.filter(name="managers").exists() or request.user.is_superuser
        )
        if not is_manager_or_superuser:
            raise Http404("Доступ запрещен")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        User = get_user_model()

        # Суперпользователь видит ВСЕХ (кроме себя)
        if self.request.user.is_superuser:
            return User.objects.exclude(id=self.request.user.id).distinct().order_by("email")
        else:
            # Менеджер видит только обычных пользователей (группа "users")
            return (
                User.objects.filter(groups__name="users")
                .exclude(id=self.request.user.id)
                .distinct()
                .order_by("email")
            )


@login_required
def user_toggle_block_view(request, pk):
    """Блокировка/разблокировка пользователя для менеджеров и суперпользователя"""

    is_manager_or_superuser = request.user.groups.filter(name="managers").exists() or request.user.is_superuser

    if not is_manager_or_superuser:
        raise Http404("Доступ запрещен")

    User = get_user_model()

    # Суперпользователь может блокировать кого угодно (кроме себя)
    if request.user.is_superuser:
        user_to_block = get_object_or_404(User.objects.exclude(id=request.user.id), pk=pk)
    else:
        # Менеджер может блокировать только обычных пользователей
        user_to_block = get_object_or_404(
            User.objects.filter(groups__name="users").exclude(id=request.user.id),
            pk=pk
        )

    # Дополнительная проверка на самого себя
    if user_to_block == request.user:
        messages.error(request, "Вы не можете заблокировать самого себя")
        return redirect("newsletter:user_list")

    user_to_block.is_active = not user_to_block.is_active
    user_to_block.save()

    action = "заблокирован" if not user_to_block.is_active else "разблокирован"

    # информацию о роли пользователя
    user_role = ""
    if user_to_block.is_superuser:
        user_role = " (суперпользователь)"
    elif user_to_block.groups.filter(name="managers").exists():
        user_role = " (менеджер)"
    elif user_to_block.groups.filter(name="users").exists():
        user_role = " (пользователь)"

    messages.success(request, f"Пользователь {user_to_block.email}{user_role} {action}")

    return redirect("newsletter:user_list")


@login_required
def dispatch_toggle_status_view(request, pk):
    """Отключение/включение рассылки менеджером и суперпользователем"""

    is_manager_or_superuser = request.user.groups.filter(name="managers").exists() or request.user.is_superuser

    if not is_manager_or_superuser:
        raise Http404("Доступ запрещен")

    dispatch = get_object_or_404(Dispatch, pk=pk)
    now = timezone.now()

    # проверка на возможность статус
    if dispatch.status == "completed":
        messages.error(request, f"Нельзя изменить статус завершенной рассылки")
        return redirect("newsletter:dispatch_detail", pk=pk)

    if dispatch.status == "started":
        # Отключаем рассылку (ставим "created")
        Dispatch.objects.filter(pk=pk).update(status="created")
        action = "отключена"
        message_type = messages.WARNING
    else:
        # Включаем рассылку (ставим "started")
        if now > dispatch.end_sent_at:
            messages.error(
                request,
                f"Нельзя запустить рассылку, так как время окончания ({dispatch.end_sent_at.strftime('%d.%m.%Y %H:%M')}) уже прошло",
            )
            return redirect("newsletter:dispatch_detail", pk=pk)


        Dispatch.objects.filter(pk=pk).update(status="started")
        action = "запущена"
        message_type = messages.SUCCESS

    dispatch_name = dispatch.message.subject if dispatch.message else f"Рассылка #{dispatch.pk}"
    messages.add_message(request, message_type, f"Рассылка '{dispatch_name}' {action}")

    return redirect("newsletter:dispatch_detail", pk=pk)


class DispatchLogListView(ManagerCanViewMixin, ListView):
    """
    Список попыток рассылок:
    - Менеджеры и суперпользователи видят ВСЕ логи
    - Обычные пользователи видят только логи своих рассылок
    """
    model = DispatchLog
    template_name = "newsletter/dispatch_log_list.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        """
        Фильтрация логов в зависимости от прав пользователя
        """

        queryset = DispatchLog.objects.select_related(
            "dispatch",
            "dispatch__message",
            "recipient"
        )
        # Фильтрация по правам
        if not (self.request.user.is_superuser or self.request.user.groups.filter(name="managers").exists()):
            queryset = queryset.filter(dispatch__owner=self.request.user)
        # Фильтрация по GET-параметрам
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)
        trigger = self.request.GET.get("trigger_type")
        if trigger:
            queryset = queryset.filter(trigger_type=trigger)

        return queryset

    def get_context_data(self, **kwargs):
        """
        Добавляем дополнительные данные в контекст
        """
        context = super().get_context_data(**kwargs)
        context["status_choices"] = DispatchLog.STATUS_CHOICES
        context["trigger_choices"] = DispatchLog.TRIGGER_CHOICES
        return context

    def get_ordering(self):
        """Сортировка - сначала новые"""

        return ["-attempt_time"]
