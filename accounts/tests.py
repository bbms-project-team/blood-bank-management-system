
from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from accounts.models import User
from accounts.views import role_home


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

    def test_home_routes_authenticated_roles_to_their_dashboards(self):
        cases = [
            (User.Role.DONOR, "donor_dashboard"),
            (User.Role.STAFF, "reception_dashboard"),
            (User.Role.ADMIN, "reception_dashboard"),
            (User.Role.RECEPTIONIST, "reception_dashboard"),
            (User.Role.MEDICAL, "appointment_list"),
        ]
        for index, (role, destination) in enumerate(cases):
            user = User.objects.create_user(
                username=f"role_home_{index}", email=f"role{index}@example.com",
                password="StrongPass123!", role=role,
            )
            response = role_home(user)
            self.assertEqual(response.url, reverse(destination))
        inventory_user = User.objects.create_user(
            username="role_home_inventory", email="roleinventory@example.com",
            password="StrongPass123!", role=User.Role.INVENTORY,
        )
        requester = User.objects.create_user(
            username="role_home_requester", email="rolerequester@example.com",
            password="StrongPass123!", role=User.Role.REQUESTER,
        )
        self.assertEqual(role_home(inventory_user).url, reverse("inventory"))
        self.assertEqual(role_home(requester).url, reverse("home"))

    def test_home_page_role_redirects_and_fallback(self):
        for role, expected in (
            (User.Role.DONOR, "donor_dashboard"),
            (User.Role.RECEPTIONIST, "reception_dashboard"),
            (User.Role.MEDICAL, "appointment_list"),
        ):
            self.user.role = role
            self.user.save(update_fields=["role"])
            self.client.force_login(self.user)
            response = self.client.get(reverse("home"))
            self.assertRedirects(response, reverse(expected))
        self.user.role = User.Role.REQUESTER
        self.user.save(update_fields=["role"])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)

    def test_account_profile_get_update_and_duplicate_email_validation(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("account_profile")).status_code, 200)
        response = self.client.post(reverse("account_profile"), {
            "first_name": "Updated", "last_name": "Name", "email": "existing@example.com",
        })
        self.assertRedirects(response, reverse("account_profile"))
        other = User.objects.create_user(
            username="profile_other", email="other-profile@example.com", password="StrongPass123!",
        )
        response = self.client.post(reverse("account_profile"), {
            "first_name": "Updated", "last_name": "Name", "email": other.email,
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "existing@example.com")

    def test_health_check_returns_unavailable_on_database_error(self):
        with patch("accounts.views.connection.cursor", side_effect=DatabaseError("offline")):
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

        self.assertRedirects(response, reverse("donor_dashboard"))

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

        self.assertRedirects(response, reverse("donor_dashboard"))
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
        unknown_email = self.client.post(reverse("login"), {
            "username": "missing@example.com", "password": "StrongPass123!",
        })
        self.assertEqual(unknown_email.status_code, 200)

    def test_user_can_log_in_with_email_address(self):
        response = self.client.post(
            reverse("login"),
            {"username": "EXISTING@example.com", "password": "StrongPass123!"},
        )
        self.assertRedirects(response, reverse("donor_dashboard"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_inactive_account_cannot_log_in(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("login"),
            {"username": self.user.email, "password": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_requires_login(self):
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_logged_in_user_can_log_out(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_authenticated_get_logout_keeps_session_and_redirects_home(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_session_timeout_is_configured(self):
        from django.conf import settings
        self.assertEqual(settings.SESSION_COOKIE_AGE, 15 * 60)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)

    def test_admin_can_add_users_and_the_action_is_logged(self):
        admin_user = User.objects.create_superuser(
            username="bbms_admin",
            email="admin@example.com",
            password="StrongPass123!",
            role=User.Role.ADMIN,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "username": "manageduser",
                "password1": "ManagedPass123!",
                "password2": "ManagedPass123!",
                "email": "managed@example.com",
                "role": User.Role.DONOR,
            },
        )
        self.assertEqual(response.status_code, 302)
        managed_user = User.objects.get(username="manageduser")
        self.assertTrue(
            LogEntry.objects.filter(
                user=admin_user,
                object_id=str(managed_user.pk),
                action_flag=ADDITION,
            ).exists()
        )

    def test_regular_user_cannot_access_admin_user_management(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)

    def test_staff_role_cannot_manage_users_even_with_django_permissions(self):
        staff_user = User.objects.create_user(
            username="staff_admin_attempt",
            email="staff-admin@example.com",
            password="StrongPass123!",
            role=User.Role.STAFF,
            is_staff=True,
        )
        user_content_type = ContentType.objects.get_for_model(User)
        staff_user.user_permissions.set(
            Permission.objects.filter(content_type=user_content_type)
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse("admin:accounts_user_changelist"))

        self.assertEqual(response.status_code, 403)
