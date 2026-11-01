from django.contrib import admin
from .models import Donation, BloodUnit, DonationBooking, DonationSlot

admin.site.register(Donation)
admin.site.register(BloodUnit)
admin.site.register(DonationSlot)
admin.site.register(DonationBooking)
