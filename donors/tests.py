
from datetime import date
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from donations.models import Donation
from donors.eligibility import booking_eligibility_error
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


class BookingEligibilityTests(TestCase):
    def make_donor(self, age, last_donation_date=None, recorded_date=None):
        today = timezone.localdate()
        birth_date = today.replace(year=today.year - age)
        index = User.objects.count()
        user = User.objects.create_user(
            username=f"eligibility_{index}", email=f"eligibility_{index}@example.com",
            password="TestPass123!", role=User.Role.DONOR,
        )
        donor = DonorProfile.objects.create(
            user=user, phone=f"9{index:09d}"[-10:], date_of_birth=birth_date,
            address="Bengaluru", blood_group="A+", last_donation_date=last_donation_date,
        )
        if recorded_date:
            Donation.objects.create(
                donor=donor, donation_date=recorded_date, blood_group="A+",
                component="WHOLE_BLOOD", volume_ml=450, accepted=True,
            )
        return donor

    def test_age_minimum_and_first_time_maximum(self):
        minor = self.make_donor(17)
        self.assertIn("18 years old", booking_eligibility_error(minor))
        first_time_over_limit = self.make_donor(61)
        self.assertIn("First-time donors over 60", booking_eligibility_error(first_time_over_limit))

    def test_repeat_donor_maximum_age_and_recent_donation_interval(self):
        today = timezone.localdate()
        older_repeat = self.make_donor(66, last_donation_date=today - timedelta(days=180))
        self.assertIn("Repeat donors over 65", booking_eligibility_error(older_repeat))
        recent_repeat = self.make_donor(40, recorded_date=today - timedelta(days=30))
        self.assertIn("wait 90 more day", booking_eligibility_error(recent_repeat))

    def test_first_time_and_repeat_donors_inside_limits_are_allowed(self):
        today = timezone.localdate()
        first_time = self.make_donor(25)
        repeat = self.make_donor(64, last_donation_date=today - timedelta(days=130))
        self.assertIsNone(booking_eligibility_error(first_time))
        self.assertIsNone(booking_eligibility_error(repeat))

