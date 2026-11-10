
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.forms import AuthenticationForm
from .models import User


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email already exists."
            )
        return email


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(
                "An account with this email already exists."
            )
        return email


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Email address (or username)",
        widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "you@example.com"}),
    )

    def clean(self):
        login_id = self.cleaned_data.get("username", "").strip()
        if "@" in login_id:
            match = User.objects.filter(email__iexact=login_id).only("username").first()
            if match:
                self.cleaned_data["username"] = match.get_username()
        return super().clean()
