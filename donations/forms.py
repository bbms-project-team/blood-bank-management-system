
from django import forms
from django.db.models import Count, F, Q
from django.utils import timezone
from datetime import datetime
from .models import Donation, DonationBooking, DonationSlot
from donors.models import DonorProfile


class DonationForm(forms.ModelForm):
    booking = forms.ModelChoiceField(
        queryset=DonationBooking.objects.none(), label="Eligible appointment",
        empty_label="Choose an in-progress donation",
    )

    class Meta:
        model = Donation
        fields = [
            "booking",
            "donation_date",
            "component",
            "volume_ml",
        ]
        widgets = {
            "donation_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_volume_ml(self):
        volume = self.cleaned_data["volume_ml"]
        if volume <= 0:
            raise forms.ValidationError("Volume must be greater than zero.")
        return volume

    def clean_donation_date(self):
        donation_date = self.cleaned_data["donation_date"]
        if donation_date > timezone.localdate():
            raise forms.ValidationError("Donation date cannot be in the future.")
        return donation_date

    def clean(self):
        cleaned_data = super().clean()
        booking = cleaned_data.get("booking")
        if booking and booking.status != DonationBooking.Status.IN_PROGRESS:
            self.add_error("booking", "The appointment must be screened as eligible and marked in progress.")
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["booking"].queryset = DonationBooking.objects.filter(
            status=DonationBooking.Status.IN_PROGRESS
        ).select_related("donor__user", "slot").order_by("slot__starts_at")


class DonationBookingForm(forms.Form):
    donor = forms.ModelChoiceField(
        queryset=DonorProfile.objects.select_related("user").order_by("user__last_name", "user__first_name"),
        required=False,
        label="Donor",
    )
    slot = forms.ModelChoiceField(
        queryset=DonationSlot.objects.none(),
        label="Available donation time",
        empty_label="Choose a time",
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slot"].queryset = DonationSlot.objects.filter(
            starts_at__gt=timezone.now(),
        ).annotate(
            active_bookings=Count("booking", filter=~Q(booking__status__in=["CANCELLED", "NO_SHOW", "COMPLETED", "DEFERRED"]))
        ).filter(active_bookings__lt=F("capacity"))


class DonationSlotForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    location = forms.CharField(max_length=150, initial="Main Blood Bank")
    capacity = forms.IntegerField(min_value=1, max_value=100, initial=1)

    def clean(self):
        cleaned = super().clean()
        date_value, time_value, location = cleaned.get("date"), cleaned.get("time"), cleaned.get("location")
        if date_value and time_value and location:
            starts_at = timezone.make_aware(datetime.combine(date_value, time_value), timezone.get_current_timezone())
            if starts_at <= timezone.now():
                self.add_error("time", "Choose a future date and time.")
            elif DonationSlot.objects.filter(starts_at=starts_at, location__iexact=location.strip()).exists():
                self.add_error("time", "A slot already exists at this centre and time.")
            cleaned["starts_at"] = starts_at
            cleaned["location"] = location.strip()
        return cleaned
