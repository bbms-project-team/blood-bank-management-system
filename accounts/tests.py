
from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class AccountsTests(TestCase):
    def setUp(self):
        self.user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        }
        self.user = User.objects.create_user(
            username="existinguser",
            email="existing@example.com",
            password="StrongPass123!",
            role=User.Role.DONOR,
        )

    def test_home_page_loads(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

    def test_registration_page_loads(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)

    def test_user_can_register_successfully(self):
        response = self.client.post(
            reverse("register"),
            self.user_data,
        )

        self.assertRedirects(response, reverse("home"))

        registered_user = User.objects.get(username="testuser")
        self.assertEqual(registered_user.email, "test@example.com")
        self.assertEqual(registered_user.role, User.Role.DONOR)
        self.assertTrue(registered_user.check_password("StrongPass123!"))
        self.assertTrue(
            response.wsgi_request.user.is_authenticated
        )

    def test_registration_rejects_duplicate_email(self):
        duplicate_email_data = self.user_data.copy()
        duplicate_email_data["email"] = "EXISTING@example.com"

        response = self.client.post(
            reverse("register"),
            duplicate_email_data,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(
            email__iexact="existing@example.com"
        ).count(), 1)
        self.assertFalse(
            User.objects.filter(username="testuser").exists()
        )

    def test_registration_rejects_mismatched_passwords(self):
        invalid_data = self.user_data.copy()
        invalid_data["password2"] = "DifferentPass456!"

        response = self.client.post(
            reverse("register"),
            invalid_data,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(username="testuser").exists()
        )

    def test_login_page_loads(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_user_can_log_in(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "existinguser",
                "password": "StrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertTrue(
            response.wsgi_request.user.is_authenticated
        )

    def test_login_rejects_incorrect_password(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "existinguser",
                "password": "WrongPassword123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            response.wsgi_request.user.is_authenticated
        )

    def test_logout_requires_login(self):
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_logged_in_user_can_log_out(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)
