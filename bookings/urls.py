from django.urls import path
from . import views

app_name = "bookings"

urlpatterns = [
    path("book-a-service/", views.booking_form, name="form"),
    path("service/<slug:service_slug>/", views.booking_form, name="form_for_service"),
    path("submit/", views.booking_submit, name="submit"),
]
