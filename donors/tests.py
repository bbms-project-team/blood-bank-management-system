
from datetime import date
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from donors.models import DonorProfile


class DonorProfileTests(TestCase):
    def setUp(self):
        self.donor_user = User.objects.create_user(
            username="test_donor",
            email="donor@example.com",
            password="TestPass123!",
            role=User.Role.DONOR,
        )

        self.staff = User.objects.create_user(
            username="bloodbank_staff",
            email="staff@example.com",
            password="TestPass123!",
            role=User.Role.STAFF,
        )

        self.other_donor_user = User.objects.create_user(
            username="other_donor",
            email="other@example.com",
            password="TestPass123!",
            role=User.Role.DONOR,
        )

        self.profile_data = {
            "phone": "9876543210",
            "date_of_birth": "1995-05-15",
            "address": "Bengaluru",
            "blood_group": "A+",
            "last_donation_date": "",
            "eligibility_notes": "No known issues",
        }

    def test_donor_can_create_profile(self):
        self.client.force_login(self.donor_user)

        response = self.client.post(
            reverse("my_profile"),
            self.profile_data,
        )

        self.assertRedirects(response, reverse("my_profile"))

        profile = DonorProfile.objects.get(user=self.donor_user)
        self.assertEqual(profile.phone, "9876543210")
        self.assertEqual(profile.blood_group, "A+")
        self.assertEqual(profile.address, "Bengaluru")

    def test_donor_can_update_existing_profile(self):
        profile = DonorProfile.objects.create(
            user=self.donor_user,
            phone="9000000000",
            date_of_birth=date(1995, 5, 15),
            address="Old address",
            blood_group="A+",
        )

        self.client.force_login(self.donor_user)

        updated_data = self.profile_data.copy()
        updated_data["phone"] = "9123456780"
        updated_data["address"] = "Updated Bengaluru address"

        response = self.client.post(
            reverse("my_profile"),
            updated_data,
        )

        self.assertRedirects(response, reverse("my_profile"))

        profile.refresh_from_db()
        self.assertEqual(profile.phone, "9123456780")
        self.assertEqual(profile.address, "Updated Bengaluru address")
        self.assertEqual(
            DonorProfile.objects.filter(user=self.donor_user).count(),
            1,
        )

    def test_donor_cannot_create_profile_with_invalid_blood_group(self):
        self.client.force_login(self.donor_user)

        invalid_data = self.profile_data.copy()
        invalid_data["blood_group"] = "INVALID"

        response = self.client.post(
            reverse("my_profile"),
            invalid_data,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            DonorProfile.objects.filter(user=self.donor_user).exists()
        )

    def test_donor_profile_rejects_future_dates(self):
        self.client.force_login(self.donor_user)
        invalid_data = self.profile_data.copy()
        invalid_data["date_of_birth"] = (timezone.localdate() + timedelta(days=1)).isoformat()
        invalid_data["last_donation_date"] = (timezone.localdate() + timedelta(days=1)).isoformat()
        response = self.client.post(reverse("my_profile"), invalid_data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DonorProfile.objects.filter(user=self.donor_user).exists())

    def test_non_donor_cannot_access_donor_profile(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("my_profile"))

        self.assertEqual(response.status_code, 403)

    def test_staff_can_view_donor_list(self):
        DonorProfile.objects.create(
            user=self.donor_user,
            phone="9876543210",
            date_of_birth=date(1995, 5, 15),
            address="Bengaluru",
            blood_group="A+",
        )

        self.client.force_login(self.staff)

        response = self.client.get(reverse("donor_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "test_donor")
        self.assertContains(response, "A+")

    def test_donor_cannot_view_staff_donor_list(self):
        self.client.force_login(self.donor_user)

        response = self.client.get(reverse("donor_list"))

        self.assertEqual(response.status_code, 403)
