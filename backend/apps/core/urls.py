from django.urls import path

from .views import AuditLogListView, me

app_name = "core"
urlpatterns = [
    path("me/", me, name="me"),
    path("auditoria/", AuditLogListView.as_view(), name="auditoria"),
]
