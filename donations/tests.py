
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from donors.models import DonorProfile
from donations.models import Donation, BloodUnit


class DonationAndInventoryTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="bloodbank_staff",
            email="staff@example.com",
            password="TestPass123!",
            role=User.Role.STAFF,
        )

        self.donor_user = User.objects.create_user(
            username="test_donor",
            email="donor@example.com",
            password="TestPass123!",
            role=User.Role.DONOR,
        )

        self.donor = DonorProfile.objects.create(
            user=self.donor_user,
            phone="9876543210",
            date_of_birth=date(1995, 5, 15),
            address="Bengaluru",
            blood_group="A+",
        )

        self.donation_date = timezone.localdate() - timedelta(days=1)

        self.donation_data = {
            "donor": self.donor.pk,
            "donation_date": self.donation_date.isoformat(),
            "blood_group": "A+",
            "component": "WHOLE_BLOOD",
            "volume_ml": 450,
        }

    def create_inventory_unit(
        self,
        blood_group="A+",
        component="WHOLE_BLOOD",
        location="Main Blood Bank",
        status="AVAILABLE",
        expiry_date=None,
    ):
        donation = Donation.objects.create(
            donor=self.donor,
            donation_date=self.donation_date,
            blood_group=blood_group,
            component=component,
            volume_ml=450,
            accepted=True,
        )

        if expiry_date is None:
            expiry_date = timezone.localdate() + timedelta(days=20)

        unit = BloodUnit.objects.create(
            donation=donation,
            expiry_date=expiry_date,
            location=location,
            status=status,
        )

        return unit

    def test_staff_can_record_donation_and_create_inventory(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("record_donation"),
            self.donation_data,
        )

        self.assertRedirects(response, reverse("inventory"))
        self.assertEqual(Donation.objects.count(), 1)
        self.assertEqual(BloodUnit.objects.count(), 1)

        donation = Donation.objects.get()
        unit = BloodUnit.objects.get()

        self.assertTrue(donation.accepted)
        self.assertEqual(donation.donor, self.donor)
        self.assertEqual(donation.blood_group, "A+")
        self.assertEqual(donation.component, "WHOLE_BLOOD")
        self.assertEqual(donation.volume_ml, 450)

        self.assertEqual(unit.donation, donation)
        self.assertEqual(
            unit.expiry_date,
            self.donation_date + timedelta(days=35),
        )
        self.assertEqual(unit.status, "AVAILABLE")

        self.donor.refresh_from_db()
        self.assertEqual(
            self.donor.last_donation_date,
            self.donation_date,
        )

    def test_donation_with_mismatched_blood_group_is_rejected(self):
        self.client.force_login(self.staff)

        invalid_data = self.donation_data.copy()
        invalid_data["blood_group"] = "B+"

        response = self.client.post(
            reverse("record_donation"),
            invalid_data,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)

    def test_donor_cannot_record_donation(self):
        self.client.force_login(self.donor_user)

        response = self.client.get(reverse("record_donation"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Donation.objects.count(), 0)

    def test_inventory_search_filters_by_blood_group(self):
        matching_unit = self.create_inventory_unit(blood_group="A+")
        self.create_inventory_unit(blood_group="B+")

        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("inventory"),
            {"blood_group": "A+"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(matching_unit.unit_code))
        self.assertEqual(
            list(response.context["units"]),
            [matching_unit],
        )

    def test_inventory_search_filters_by_component_and_location(self):
        matching_unit = self.create_inventory_unit(
            component="PLASMA",
            location="North Branch",
        )

        self.create_inventory_unit(
            component="WHOLE_BLOOD",
            location="North Branch",
        )

        self.create_inventory_unit(
            component="PLASMA",
            location="South Branch",
        )

        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("inventory"),
            {
                "component": "PLASMA",
                "location": "North",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["units"]),
            [matching_unit],
        )

    def test_inventory_excludes_expired_and_unavailable_units(self):
        valid_unit = self.create_inventory_unit(
            status="AVAILABLE",
            expiry_date=timezone.localdate(),
        )

        self.create_inventory_unit(
            status="AVAILABLE",
            expiry_date=timezone.localdate() - timedelta(days=1),
        )

        self.create_inventory_unit(
            status="RESERVED",
            expiry_date=timezone.localdate() + timedelta(days=10),
        )

        self.create_inventory_unit(
            status="ISSUED",
            expiry_date=timezone.localdate() + timedelta(days=10),
        )

        self.client.force_login(self.staff)

        response = self.client.get(reverse("inventory"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["units"]),
            [valid_unit],
        )

    def test_inventory_requires_staff_or_admin_role(self):
        self.client.force_login(self.donor_user)

        response = self.client.get(reverse("inventory"))

        self.assertEqual(response.status_code, 403)

