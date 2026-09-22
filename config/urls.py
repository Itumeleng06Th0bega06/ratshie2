"""Root URL configuration for the Ratshie website."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from core import views as core_views

# Ratshie admin runs as a premium command centre with a curated sidebar
# (see templates/admin/nav_sidebar.html + static/admin_premium/admin.css).


urlpatterns = [
    path(
        "admin/notifications/",
        include(
            (core_views.admin_urlpatterns, "core_notifications"),
            namespace="core_notifications",
        ),
    ),
    path(
        "admin/password-reset/",
        include(
            [
                path("", core_views.RatShiePasswordResetView.as_view(), name="admin_password_reset"),
                path("done/", core_views.RatShiePasswordResetDoneView.as_view(), name="admin_password_reset_done"),
                path(
                    "confirm/<uidb64>/<token>/",
                    core_views.RatShiePasswordResetConfirmView.as_view(),
                    name="admin_password_reset_confirm",
                ),
                path(
                    "complete/",
                    core_views.RatShiePasswordResetCompleteView.as_view(),
                    name="admin_password_reset_complete",
                ),
            ]
        ),
    ),
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("account/", include("customers.urls")),
    path("shop/", include("products.urls")),
    path("quotes/", include("quotes.urls")),
    path("bookings/", include("bookings.urls")),
    path("payments/", include("payments.urls")),
    path("orders/", include("orders.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")

# Error pages
handler404 = "core.views.handler404"
handler500 = "core.views.handler500"
handler403 = "core.views.handler403"
