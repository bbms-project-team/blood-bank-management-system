
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

    def clean_patient_name(self):
        patient_name = self.cleaned_data.get("patient_name", "").strip()

        if not patient_name:
            raise forms.ValidationError(
                "Patient name is required."
            )

        return patient_name

    def clean_hospital_name(self):
        hospital_name = self.cleaned_data.get("hospital_name", "").strip()

        if not hospital_name:
            raise forms.ValidationError(
                "Hospital name is required."
            )

        return hospital_name

    def clean_units_required(self):
        units = self.cleaned_data["units_required"]

        if units <= 0:
            raise forms.ValidationError(
                "Units required must be greater than zero."
            )

        return units

    def clean_reason(self):
        reason = self.cleaned_data.get("reason", "")

        return reason.strip() if reason else reason
