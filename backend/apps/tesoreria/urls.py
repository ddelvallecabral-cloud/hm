from django.urls import path

from . import views

app_name = "tesoreria"
urlpatterns = [path("dashboard/", views.dashboard, name="dashboard")]
