from django.urls import path
from . import views

app_name = "orders"

urlpatterns = [
    path("cart/", views.cart_view, name="cart"),
    path("cart/partial/", views.cart_partial, name="cart_partial"),
    path("cart/add/<slug:slug>/", views.cart_add, name="cart_add"),
    path("cart/set-qty/<int:pk>/", views.cart_set_qty, name="cart_set_qty"),
    path("cart/remove/<int:pk>/", views.cart_remove, name="cart_remove"),
    path("cart/clear/", views.cart_clear, name="cart_clear"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/submit/", views.checkout_submit, name="checkout_submit"),
    path("management/order/<int:pk>/status/", views.order_status_update, name="order_status_update"),
]
