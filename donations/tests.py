
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from donors.models import DonorProfile
from donations.models import Donation, BloodUnit, DonationBooking, DonationSlot
from bloodbank_requests.models import BloodRequest


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
        self.requester = User.objects.create_user(
            username="hospital_user",
            email="hospital@example.com",
            password="TestPass123!",
            role=User.Role.REQUESTER,
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

        request = None
        issued_at = None
        issued_by = None
        if status in {"RESERVED", "ISSUED"}:
            request = BloodRequest.objects.create(
                requester=self.requester,
                patient_name="Test Patient",
                hospital_name="Test Hospital",
                blood_group=blood_group,
                component=component,
                units_required=1,
                reason="Test fixture",
                status=BloodRequest.Status.RESERVED,
            )
        if status == "ISSUED":
            issued_at = timezone.now()
            issued_by = self.staff
            request.status = BloodRequest.Status.ISSUED
            request.save(update_fields=["status"])

        unit = BloodUnit.objects.create(
            donation=donation,
            expiry_date=expiry_date,
            location=location,
            status=status,
            reserved_for=request,
            reserved_at=timezone.now() if request else None,
            issued_at=issued_at,
            issued_by=issued_by,
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

    def test_future_donation_date_is_rejected(self):
        self.client.force_login(self.staff)
        invalid_data = self.donation_data.copy()
        invalid_data["donation_date"] = (
            timezone.localdate() + timedelta(days=1)
        ).isoformat()

        response = self.client.post(reverse("record_donation"), invalid_data)

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

    def test_requester_can_search_availability(self):
        self.create_inventory_unit()
        self.client.force_login(self.requester)
        response = self.client.get(reverse("inventory"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["units"]), 1)


class DonationBookingTests(TestCase):
    def setUp(self):
        self.donor_user = User.objects.create_user(
            username="booking_donor",
            email="booking-donor@example.com",
            password="StrongPass123!",
            role=User.Role.DONOR,
        )
        self.donor = DonorProfile.objects.create(
            user=self.donor_user,
            phone="9876543210",
            date_of_birth=date(1995, 5, 15),
            address="Bengaluru",
            blood_group="A+",
        )
        self.slot = DonationSlot.objects.create(
            starts_at=timezone.now() + timedelta(days=1),
        )

    def test_donor_can_book_an_available_future_slot(self):
        self.client.force_login(self.donor_user)

        response = self.client.get(reverse("book_donation"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Available donation time")
        self.assertContains(response, str(self.slot.starts_at.year))

        response = self.client.post(
            reverse("book_donation"),
            {"slot": self.slot.pk},
        )

        self.assertRedirects(response, reverse("book_donation"))
        self.assertTrue(
            DonationBooking.objects.filter(donor=self.donor, slot=self.slot).exists()
        )

    def test_booked_or_past_slots_are_not_form_choices(self):
        booked_slot = DonationSlot.objects.create(
            starts_at=timezone.now() + timedelta(days=2),
        )
        DonationBooking.objects.create(donor=self.donor, slot=booked_slot)
        old_slot = DonationSlot.objects.create(
            starts_at=timezone.now() - timedelta(minutes=1),
        )

        self.client.force_login(self.donor_user)
        response = self.client.get(reverse("book_donation"))

        self.assertEqual(response.status_code, 200)
        available_ids = set(
            response.context["form"].fields["slot"].queryset.values_list("pk", flat=True)
        )
        self.assertEqual(available_ids, {self.slot.pk})
        self.assertNotIn(booked_slot.pk, available_ids)
        self.assertNotIn(old_slot.pk, available_ids)

