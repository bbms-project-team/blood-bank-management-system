
from django import forms
from .models import BloodRequest


class BloodRequestForm(forms.ModelForm):
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
