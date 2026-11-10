
from datetime import date, timedelta

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from donors.models import DonorProfile
from donations.models import Donation, BloodUnit, DonationBooking, DonationSlot
from bloodbank_requests.models import AuditLog, BloodRequest


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

        self.booking = DonationBooking.objects.create(
            donor=self.donor,
            slot=DonationSlot.objects.create(starts_at=timezone.now() + timedelta(days=1)),
            status=DonationBooking.Status.IN_PROGRESS,
        )
        self.donation_data = {
            "booking": self.booking.pk,
            "donation_date": self.donation_date.isoformat(),
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
            processing_status="TESTED",
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
        self.assertEqual(unit.status, "QUARANTINED")
        self.assertEqual(unit.processing_status, "PENDING")

        self.donor.refresh_from_db()
        self.assertEqual(
            self.donor.last_donation_date,
            self.donation_date,
        )

    def test_blood_unit_validation_accepts_valid_expiry_and_rejects_expiry_before_collection(self):
        valid = BloodUnit.objects.create(
            donation=Donation.objects.create(
                donor=self.donor, donation_date=self.donation_date, blood_group="A+",
                component="WHOLE_BLOOD", volume_ml=450,
            ),
            expiry_date=timezone.localdate() + timedelta(days=20),
        )
        valid.full_clean()
        invalid = BloodUnit(
            donation=Donation.objects.create(
                donor=self.donor, donation_date=self.donation_date, blood_group="A+",
                component="WHOLE_BLOOD", volume_ml=450,
            ),
            expiry_date=self.donation_date - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_donation_cannot_be_recorded_before_screening_and_in_progress(self):
        self.client.force_login(self.staff)
        self.booking.status = DonationBooking.Status.SCHEDULED
        self.booking.save(update_fields=["status"])

        response = self.client.post(
            reverse("record_donation"),
            self.donation_data,
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


class ReceptionWorkflowTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="reception", email="reception@example.com", password="TestPass123!",
            role=User.Role.STAFF,
        )
        self.donor_user = User.objects.create_user(
            username="workflowdonor", email="workflow@example.com", password="TestPass123!",
            role=User.Role.DONOR, first_name="Jamie", last_name="Donor",
        )
        self.donor = DonorProfile.objects.create(
            user=self.donor_user, phone="9000012345", date_of_birth=date(1990, 4, 1),
            address="Bengaluru", blood_group="O+",
        )
        self.slot = DonationSlot.objects.create(
            starts_at=timezone.now() + timedelta(days=1), location="Central Centre", capacity=1,
        )

    def test_reception_pages_render_for_staff(self):
        self.client.force_login(self.staff)
        for url in ("reception_dashboard", "reception_donors", "appointment_list"):
            response = self.client.get(reverse(url))
            self.assertEqual(response.status_code, 200, url)
        response = self.client.get(reverse("reception_donor_detail", args=[self.donor.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("reception_donors"), {"q": "Jamie"}).status_code, 200)
        self.assertEqual(self.client.get(reverse("reception_donors"), {"q": "not-a-donor"}).status_code, 200)

    def test_receptionist_can_update_donor_and_audit_the_change(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("reception_donor_edit", args=[self.donor.pk]), {
            "first_name": "Jamie", "last_name": "Updated", "email": self.donor_user.email,
            "phone": "9000012345", "gender": "", "date_of_birth": "1990-04-01",
            "address": "Updated address", "blood_group": "O+", "emergency_contact": "9000000000",
        })
        self.assertRedirects(response, reverse("reception_donor_detail", args=[self.donor.pk]))
        self.donor.refresh_from_db()
        self.assertEqual(self.donor.address, "Updated address")
        self.assertEqual(self.donor.emergency_contact, "9000000000")
        self.assertTrue(AuditLog.objects.filter(action="DONOR_PROFILE_UPDATED", object_id=str(self.donor.pk)).exists())

    def test_receptionist_can_create_a_slot_and_choose_it_for_scheduling(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("manage_donation_slots"), {
            "date": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "time": "10:30", "location": "Central Centre", "capacity": 4,
        })
        self.assertRedirects(response, reverse("manage_donation_slots"))
        slot = DonationSlot.objects.get(
            location="Central Centre", starts_at__date=timezone.localdate() + timedelta(days=2),
        )
        response = self.client.get(reverse("schedule_appointment_for_donor", args=[self.donor.pk]))
        self.assertEqual(response.status_code, 200)
        choices = response.context["form"].fields["slot"].queryset
        self.assertTrue(choices.filter(pk=slot.pk).exists())

        duplicate = self.client.post(reverse("manage_donation_slots"), {
            "date": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "time": "10:30", "location": "central centre", "capacity": 2,
        })
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.context["form"].has_error("time"))
        past = self.client.post(reverse("manage_donation_slots"), {
            "date": (timezone.localdate() - timedelta(days=1)).isoformat(),
            "time": "10:30", "location": "South Centre", "capacity": 1,
        })
        self.assertEqual(past.status_code, 200)
        self.assertTrue(past.context["form"].has_error("time"))

    def test_schedule_requires_a_donor_and_blocks_second_active_booking(self):
        self.client.force_login(self.staff)
        url = reverse("schedule_appointment")
        response = self.client.post(url, {"slot": self.slot.pk, "notes": "Walk-in"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].has_error("donor"))
        DonationBooking.objects.create(donor=self.donor, slot=self.slot)
        other_slot = DonationSlot.objects.create(
            starts_at=timezone.now() + timedelta(days=3), location="North Centre",
        )
        response = self.client.post(url, {"donor": self.donor.pk, "slot": other_slot.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has an upcoming appointment")

    def test_receptionist_cannot_make_medical_screening_decision(self):
        receptionist = User.objects.create_user(
            username="restricted_reception", email="restricted-reception@example.com",
            password="TestPass123!", role=User.Role.RECEPTIONIST,
        )
        booking = DonationBooking.objects.create(donor=self.donor, slot=self.slot)
        self.client.force_login(receptionist)
        response = self.client.post(reverse("appointment_action", args=[booking.pk]), {"action": "start_screening"})
        self.assertRedirects(response, reverse("appointment_list"))
        booking.refresh_from_db()
        self.assertEqual(booking.status, DonationBooking.Status.SCHEDULED)

    def test_invalid_appointment_transition_is_rejected(self):
        booking = DonationBooking.objects.create(donor=self.donor, slot=self.slot)
        self.client.force_login(self.staff)
        response = self.client.post(reverse("appointment_action", args=[booking.pk]), {"action": "eligible"})
        self.assertRedirects(response, reverse("appointment_list"))
        booking.refresh_from_db()
        self.assertEqual(booking.status, DonationBooking.Status.SCHEDULED)

    def test_appointment_list_filters_by_date_status_and_donor_search(self):
        booking = DonationBooking.objects.create(donor=self.donor, slot=self.slot)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("appointment_list"), {
            "date": timezone.localtime(self.slot.starts_at).date().isoformat(), "status": "SCHEDULED", "q": "Jamie",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(booking.reference)[:8])
        response = self.client.get(reverse("appointment_list"), {"status": "INVALID"})
        self.assertEqual(response.status_code, 200)

    def test_processing_marks_failed_units_unavailable_and_rejects_repeat_action(self):
        donation = Donation.objects.create(
            donor=self.donor, donation_date=timezone.localdate() - timedelta(days=1),
            blood_group="A+", component="WHOLE_BLOOD", volume_ml=450,
        )
        unit = BloodUnit.objects.create(
            donation=donation, expiry_date=timezone.localdate() + timedelta(days=30),
        )
        inventory_manager = User.objects.create_user(
            username="inventory_manager", email="inventory-manager@example.com",
            password="TestPass123!", role=User.Role.INVENTORY,
        )
        self.client.force_login(inventory_manager)
        response = self.client.post(reverse("process_blood_unit", args=[unit.pk]), {"result": "FAILED"})
        self.assertRedirects(response, reverse("inventory"))
        unit.refresh_from_db()
        self.assertEqual(unit.status, "QUARANTINED")
        self.assertEqual(unit.processing_status, "FAILED")
        response = self.client.post(reverse("process_blood_unit", args=[unit.pk]), {"result": "TESTED"})
        self.assertRedirects(response, reverse("inventory"))
        unit.refresh_from_db()
        self.assertEqual(unit.status, "AVAILABLE")
        response = self.client.post(reverse("process_blood_unit", args=[unit.pk]), {"result": "TESTED"})
        self.assertRedirects(response, reverse("inventory"))
        unit.refresh_from_db()
        self.assertEqual(unit.status, "AVAILABLE")

    def test_receptionist_can_schedule_and_donor_sees_the_appointment(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("schedule_appointment_for_donor", args=[self.donor.pk]), {
            "slot": self.slot.pk, "notes": "First visit",
        })
        self.assertRedirects(response, reverse("appointment_list"))
        booking = DonationBooking.objects.get()
        self.assertEqual(booking.created_by, self.staff)
        self.assertEqual(booking.donor, self.donor)
        self.assertEqual(booking.notes, "First visit")
        self.assertTrue(booking.reference)
        self.assertTrue(booking.notifications.exists())

        self.client.force_login(self.donor_user)
        response = self.client.get(reverse("donor_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(booking.reference))
        self.assertContains(response, "Central Centre")

    def test_walk_in_registration_prevents_duplicate_email_and_phone(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("reception_donor_create"), {
            "first_name": "Jamie", "last_name": "Another", "email": "new@example.com",
            "phone": "9000099999", "date_of_birth": "1994-03-02", "address": "Mysuru",
            "blood_group": "A+", "emergency_contact": "9999999999",
        })
        self.assertEqual(response.status_code, 302)
        account = User.objects.get(email="new@example.com")
        self.assertEqual(account.role, User.Role.DONOR)
        self.assertTrue(account.has_usable_password())
        self.assertTrue(DonorProfile.objects.filter(user=account, emergency_contact="9999999999").exists())

        duplicate = self.client.post(reverse("reception_donor_create"), {
            "first_name": "Duplicate", "email": "WORKFLOW@example.com", "phone": "9000011111",
            "date_of_birth": "1994-03-02", "address": "Mysuru", "blood_group": "A+",
        })
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(DonorProfile.objects.count(), 2)

    def test_screening_and_donation_are_separate_before_inventory_availability(self):
        booking = DonationBooking.objects.create(donor=self.donor, slot=self.slot, created_by=self.staff)
        self.client.force_login(self.staff)
        for action in ("confirm", "check_in", "start_screening", "eligible", "start_donation"):
            response = self.client.post(reverse("appointment_action", args=[booking.pk]), {
                "action": action, "screening_notes": "Screened by authorized staff",
            })
            self.assertEqual(response.status_code, 302)
            booking.refresh_from_db()
        self.assertEqual(booking.status, DonationBooking.Status.IN_PROGRESS)
        response = self.client.post(reverse("record_donation"), {
            "booking": booking.pk, "donation_date": timezone.localdate().isoformat(),
            "component": "WHOLE_BLOOD", "volume_ml": 450,
        })
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        unit = BloodUnit.objects.get()
        self.assertEqual(booking.status, DonationBooking.Status.COMPLETED)
        self.assertEqual(unit.status, "QUARANTINED")
        self.assertEqual(unit.processing_status, "PENDING")

        self.client.post(reverse("process_blood_unit", args=[unit.pk]), {"result": "TESTED"})
        unit.refresh_from_db()
        self.assertEqual(unit.status, "AVAILABLE")
        self.assertEqual(unit.processing_status, "TESTED")

