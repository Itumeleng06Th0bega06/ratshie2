from django.urls import path
from . import views

app_name = "products"

urlpatterns = [
    path("", views.shop_index, name="shop"),
    path("enquiry/", views.product_enquiry, name="enquiry"),
    path("enquiry/submit/", views.product_enquiry_submit, name="enquiry_submit"),
    path("add-to-cart/<slug:slug>/", views.cart_add, name="cart_add"),
    path("add-to-cart-partial/<slug:slug>/", views.cart_add_partial, name="cart_add_partial"),
    path("buy-now/<slug:slug>/", views.buy_now, name="buy_now"),
    path("<slug:slug>/enquiry/", views.product_enquiry, name="product_enquiry"),
    path("<slug:slug>/", views.product_detail, name="detail"),
]
