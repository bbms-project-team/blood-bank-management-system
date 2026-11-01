
from django.urls import path
from . import views

urlpatterns = [
    path("book/", views.book_donation, name="book_donation"),
    path("record/", views.record_donation, name="record_donation"),
    path("inventory/", views.inventory, name="inventory"),
]
