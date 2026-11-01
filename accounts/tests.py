
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch
from django.db import OperationalError

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

    def test_health_check_returns_ok_when_database_is_available(self):
        response = self.client.get(reverse("health_check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
        self.assertIn("no-store", response["Cache-Control"])

    @patch("accounts.views.connection.cursor", side_effect=OperationalError("database unavailable"))
    def test_health_check_returns_unavailable_when_database_is_down(self, _mock_cursor):
        response = self.client.get(reverse("health_check"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content, b"unavailable")

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

    def test_registration_cannot_assign_privileged_role(self):
        data = self.user_data.copy()
        data["role"] = User.Role.ADMIN
        self.client.post(reverse("register"), data)
        registered_user = User.objects.get(username="testuser")
        self.assertEqual(registered_user.role, User.Role.DONOR)

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

    def test_authenticated_user_can_update_permitted_profile_fields(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("account_profile"),
            {
                "first_name": "Updated",
                "last_name": "Donor",
                "email": " UPDATED@example.com ",
            },
        )
        self.assertRedirects(response, reverse("account_profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.last_name, "Donor")
        self.assertEqual(self.user.email, "updated@example.com")

    def test_profile_update_rejects_duplicate_email(self):
        User.objects.create_user(
            username="anotheruser",
            email="test@example.com",
            password="StrongPass123!",
            role=User.Role.DONOR,
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("account_profile"),
            {
                "first_name": "Test",
                "last_name": "User",
                "email": "test@example.com",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "existing@example.com")

    def test_profile_update_cannot_change_role_or_password(self):
        original_password = self.user.password
        other_user = User.objects.create_user(
            username="otheraccount",
            email="other-account@example.com",
            password="StrongPass123!",
            role=User.Role.REQUESTER,
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("account_profile"),
            {
                "first_name": "Test",
                "last_name": "User",
                "email": "existing@example.com",
                "role": User.Role.ADMIN,
                "password": "CompromisedPassword123!",
                "user_id": other_user.pk,
            },
        )
        self.assertRedirects(response, reverse("account_profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.Role.DONOR)
        self.assertEqual(self.user.password, original_password)
        other_user.refresh_from_db()
        self.assertEqual(other_user.email, "other-account@example.com")
        self.assertEqual(other_user.role, User.Role.REQUESTER)

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

    def test_session_timeout_is_configured(self):
        from django.conf import settings
        self.assertEqual(settings.SESSION_COOKIE_AGE, 15 * 60)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_http_requests_redirect_to_https_when_enabled(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].startswith("https://"))

    @override_settings(SECURE_HSTS_SECONDS=31536000)
    def test_https_responses_include_hsts_when_enabled(self):
        response = self.client.get(reverse("home"), secure=True)
        self.assertEqual(
            response["Strict-Transport-Security"], "max-age=31536000"
        )
