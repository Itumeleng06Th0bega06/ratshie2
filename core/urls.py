from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("contact/submit/", views.contact_submit, name="contact_submit"),
    path("faq/", views.faq, name="faq"),
    path("privacy/", views.privacy_policy, name="privacy"),
    path("terms/", views.terms_of_service, name="terms"),
    path("refunds/", views.refunds_policy, name="refunds"),
    path("shipping/", views.shipping_policy, name="shipping"),
    path("health/", views.health, name="health"),
]

admin_patterns = [
    path("notification/<int:pk>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("notification/read-all/", views.notification_mark_all_read, name="notification_mark_all_read"),
]
