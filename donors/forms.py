
from django import forms
from accounts.models import User
from django.utils import timezone
from .models import DonorProfile


class DonorProfileForm(forms.ModelForm):
    class Meta:
        model = DonorProfile
        fields = [
            "phone",
            "emergency_contact",
            "gender",
            "date_of_birth",
            "address",
            "blood_group",
            "last_donation_date",
            "eligibility_notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "last_donation_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_date_of_birth(self):
        value = self.cleaned_data["date_of_birth"]
        if value > timezone.localdate():
            raise forms.ValidationError("Date of birth cannot be in the future.")
        return value
    def clean_last_donation_date(self):
        value = self.cleaned_data.get("last_donation_date")
        if value and value > timezone.localdate():
            raise forms.ValidationError("Last donation date cannot be in the future.")
        return value


class ReceptionDonorForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField()
    phone = forms.CharField(max_length=15)
    gender = forms.ChoiceField(choices=[("", "Not provided")] + DonorProfile.GENDER_CHOICES, required=False)
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    blood_group = forms.ChoiceField(choices=DonorProfile.BLOOD_GROUPS)
    emergency_contact = forms.CharField(max_length=150, required=False)

    def __init__(self, *args, donor=None, **kwargs):
        self.donor = donor
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        users = User.objects.filter(email__iexact=email)
        if self.donor:
            users = users.exclude(pk=self.donor.user_id)
        if users.exists():
            raise forms.ValidationError("An account with this email already exists. Search for the donor instead.")
        return email

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        profiles = DonorProfile.objects.filter(phone=phone)
        if self.donor:
            profiles = profiles.exclude(pk=self.donor.pk)
        if profiles.exists():
            raise forms.ValidationError("A donor profile with this phone number already exists. Search for the donor instead.")
        return phone

    def clean_date_of_birth(self):
        value = self.cleaned_data["date_of_birth"]
        if value > timezone.localdate():
            raise forms.ValidationError("Date of birth cannot be in the future.")
        return value
