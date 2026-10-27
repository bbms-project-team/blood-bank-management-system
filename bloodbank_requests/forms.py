
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
            "blood_group": forms.Select(
                choices=[
                    ("A+", "A+"), ("A-", "A-"),
                    ("B+", "B+"), ("B-", "B-"),
                    ("AB+", "AB+"), ("AB-", "AB-"),
                    ("O+", "O+"), ("O-", "O-"),
                ]
            ),
            "component": forms.Select(
                choices=[
                    ("WHOLE_BLOOD", "Whole Blood"),
                    ("RED_CELLS", "Red Blood Cells"),
                    ("PLASMA", "Plasma"),
                    ("PLATELETS", "Platelets"),
                ]
            ),
            "reason": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_units_required(self):
        units = self.cleaned_data["units_required"]
        if units <= 0:
            raise forms.ValidationError(
                "Units required must be greater than zero."
            )
        return units
