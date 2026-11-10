from django.urls import path
from . import reception

urlpatterns = [
    path("", reception.dashboard, name="reception_dashboard"),
    path("donors/", reception.donor_search, name="reception_donors"),
    path("donors/new/", reception.donor_create, name="reception_donor_create"),
    path("donors/<int:donor_id>/", reception.donor_detail, name="reception_donor_detail"),
    path("donors/<int:donor_id>/edit/", reception.donor_edit, name="reception_donor_edit"),
    path("donors/<int:donor_id>/schedule/", reception.schedule_appointment, name="schedule_appointment_for_donor"),
    path("appointments/", reception.appointment_list, name="appointment_list"),
    path("appointments/new/", reception.schedule_appointment, name="schedule_appointment"),
    path("slots/", reception.slot_management, name="manage_donation_slots"),
    path("appointments/<int:booking_id>/action/", reception.appointment_action, name="appointment_action"),
    path("inventory/<int:unit_id>/process/", reception.process_blood_unit, name="process_blood_unit"),
    path("my/", reception.donor_dashboard, name="donor_dashboard"),
]
