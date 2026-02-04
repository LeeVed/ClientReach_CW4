from django.urls import path

from . import views
from .apps import NewsletterConfig

app_name = NewsletterConfig.name

urlpatterns = [
    path("", views.home_view, name="home"),
    path("statistics/", views.UserStatisticsView.as_view(), name="user_statistics"),
    # для отправки рассылки
    path("dispatches/<int:pk>/send/", views.dispatch_send_view, name="dispatch_send"),
    path("dispatches/", views.DispatchListView.as_view(), name="dispatch_list"),
    path("dispatches/create/", views.DispatchCreateView.as_view(), name="dispatch_create"),
    path("dispatches/<int:pk>/", views.DispatchDetailView.as_view(), name="dispatch_detail"),
    path("dispatches/<int:pk>/update/", views.DispatchUpdateView.as_view(), name="dispatch_update"),
    path("dispatches/<int:pk>/delete/", views.DispatchDeleteView.as_view(), name="dispatch_delete"),
    path("dispatches/<int:pk>/toggle-status/", views.dispatch_toggle_status_view, name="dispatch_toggle_status"),
    # URLs для получателей
    path("subscribers/", views.SubscriberListView.as_view(), name="subscriber_list"),
    path("subscribers/create/", views.SubscriberCreateView.as_view(), name="subscriber_create"),
    path("subscribers/<int:pk>/", views.SubscriberDetailView.as_view(), name="subscriber_detail"),
    path("subscribers/<int:pk>/update/", views.SubscriberUpdateView.as_view(), name="subscriber_update"),
    path("subscribers/<int:pk>/delete/", views.SubscriberDeleteView.as_view(), name="subscriber_delete"),
    # URLs для сообщений
    path("messages/", views.MessageListView.as_view(), name="message_list"),
    path("messages/create/", views.MessageCreateView.as_view(), name="message_create"),
    path("messages/<int:pk>/", views.MessageDetailView.as_view(), name="message_detail"),
    path("messages/<int:pk>/update/", views.MessageUpdateView.as_view(), name="message_update"),
    path("messages/<int:pk>/delete/", views.MessageDeleteView.as_view(), name="message_delete"),
    # URLs для пользователей
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/<int:pk>/toggle-block/", views.user_toggle_block_view, name="user_toggle_block"),
]
