from django.urls import path
from django.views.generic import RedirectView

from . import views

# The shop is the site's landing page.
#
# This is one permanent redirect to the existing named Shop route
# (products:shop -> /shop/), not a second copy of the shop view or template.
# Targeting the name rather than the literal "/shop/" means the destination
# follows the route if the shop's URL ever changes.
#
# The "home" name is deliberately kept so reverse("home") and any existing
# bookmark to "/" keep resolving; only the destination is the shop.
shop_landing = RedirectView.as_view(pattern_name="products:shop", permanent=True)

urlpatterns = [
    path("", shop_landing, name="home"),
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
