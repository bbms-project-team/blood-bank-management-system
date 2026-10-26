
from django.urls import path
from . import views

urlpatterns = [
    path("record/", views.record_donation, name="record_donation"),
    path("inventory/", views.inventory, name="inventory"),
]
