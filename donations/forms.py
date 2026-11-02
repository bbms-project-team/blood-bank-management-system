
from django import forms
from django.utils import timezone
from .models import Donation, DonationSlot


class DonationForm(forms.ModelForm):
    class Meta:
        model = Donation
        fields = [
            "donor",
            "donation_date",
            "blood_group",
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
        donor = cleaned_data.get("donor")
        blood_group = cleaned_data.get("blood_group")

        if donor and blood_group and donor.blood_group != blood_group:
            self.add_error(
                "blood_group",
                "The donation blood group must match the donor profile.",
            )

        return cleaned_data


class DonationBookingForm(forms.Form):
    slot = forms.ModelChoiceField(
        queryset=DonationSlot.objects.none(),
        label="Available donation time",
        empty_label="Choose a time",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slot"].queryset = DonationSlot.objects.filter(
            starts_at__gt=timezone.now(),
            booking__isnull=True,
        )
