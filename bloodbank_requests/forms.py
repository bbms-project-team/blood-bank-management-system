
from django import forms
from .models import BloodRequest
from donations.models import Donation
from donors.models import DonorProfile


class BloodRequestForm(forms.ModelForm):
    blood_group = forms.ChoiceField(choices=DonorProfile.BLOOD_GROUPS)
    component = forms.ChoiceField(choices=Donation.COMPONENTS)

    class Meta:
        model = BloodRequest
        fields = [
            "patient_name",
            "hospital_name",
            "blood_group",
            "component",
            "units_required",
            "reason",
        ]
        widgets = {
            "reason": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_units_required(self):
        units = self.cleaned_data["units_required"]
        if units <= 0:
            raise forms.ValidationError(
                "Units required must be greater than zero."
            )
        return units
