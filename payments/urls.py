from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path("details/<str:reference>/", views.payment_details, name="details"),
    path("return/<str:reference>/", views.payment_return, name="return"),
    path("cancel/<str:reference>/", views.payment_cancel, name="cancel"),
    path("itn/", views.payment_itn, name="itn"),
]
