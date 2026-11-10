from django.contrib import admin
from .models import Donation, BloodUnit, DonationBooking, DonationSlot

admin.site.register(Donation)


@admin.register(DonationSlot)
class DonationSlotAdmin(admin.ModelAdmin):
    list_display = ("starts_at", "location", "capacity")
    list_filter = ("location",)
    ordering = ("starts_at",)


@admin.register(DonationBooking)
class DonationBookingAdmin(admin.ModelAdmin):
    list_display = ("reference", "donor", "slot", "status", "created_by")
    list_filter = ("status", "slot__location")
    search_fields = ("reference", "donor__user__first_name", "donor__user__last_name", "donor__phone")
    readonly_fields = ("reference", "created_at", "updated_at")


@admin.register(BloodUnit)
class BloodUnitAdmin(admin.ModelAdmin):
    list_display = ("unit_code", "donation", "status", "processing_status", "expiry_date", "location")
    list_filter = ("status", "processing_status", "location")
    search_fields = ("unit_code",)
