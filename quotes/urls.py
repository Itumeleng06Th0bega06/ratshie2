from django.urls import path
from . import views

app_name = "quotes"

urlpatterns = [
    path("get-a-quote/", views.quote_form, name="form"),
    path("service/<slug:service_slug>/", views.quote_form, name="form_for_service"),
    path("submit/", views.quote_submit, name="submit"),
]
