"""End-to-end tests for workflows that cross BBMS apps and roles."""

from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from bloodbank_requests.models import AuditLog, BloodRequest, RequestNotification
from donations.models import BloodUnit, Donation, DonationBooking, DonationSlot
from donors.models import DonorProfile


class DonorOnboardingWorkflowTests(TestCase):
    def test_donor_registers_completes_profile_and_books_a_slot(self):
        donor_client = Client()
        registration = donor_client.post(
            reverse("register"),
            {
                "username": "workflow_donor",
                "email": "workflow-donor@example.com",
                "first_name": "Workflow",
                "last_name": "Donor",
                "password1": "Good!DonorPassword2026",
                "password2": "Good!DonorPassword2026",
            },
        )

        self.assertRedirects(registration, reverse("home"))
        donor = User.objects.get(username="workflow_donor")
        self.assertEqual(donor.role, User.Role.DONOR)
        self.assertTrue(donor_client.session.get("_auth_user_id"))

        profile_response = donor_client.post(
            reverse("my_profile"),
            {
                "phone": "9876543210",
                "date_of_birth": (timezone.localdate() - timedelta(days=30 * 365)).isoformat(),
                "address": "Bengaluru",
                "blood_group": "A+",
                "last_donation_date": "",
                "eligibility_notes": "",
            },
        )
        self.assertRedirects(profile_response, reverse("my_profile"))
        profile = DonorProfile.objects.get(user=donor)

        slot = DonationSlot.objects.create(
            starts_at=timezone.now() + timedelta(days=2),
        )
        booking_response = donor_client.post(
            reverse("book_donation"),
            {"slot": slot.pk},
        )

        self.assertRedirects(booking_response, reverse("book_donation"))
        self.assertTrue(
            DonationBooking.objects.filter(donor=profile, slot=slot).exists()
        )
        appointment_page = donor_client.get(reverse("book_donation"))
        self.assertEqual(appointment_page.status_code, 200)
        self.assertContains(appointment_page, "Your upcoming appointment")
        dashboard = donor_client.get(reverse("home"))
        self.assertContains(dashboard, "Donor dashboard")
        self.assertEqual(dashboard.context["donor_donation_count"], 0)
        self.assertEqual(dashboard.context["upcoming_booking"], DonationBooking.objects.get(slot=slot))


class BloodRequestToDispatchWorkflowTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="workflow_staff",
            email="workflow-staff@example.com",
            password="Good!StaffPassword2026",
            role=User.Role.STAFF,
        )
        self.requester = User.objects.create_user(
            username="workflow_requester",
            email="workflow-requester@example.com",
            password="Good!RequesterPassword2026",
            role=User.Role.REQUESTER,
        )
        donor_user = User.objects.create_user(
            username="inventory_donor",
            email="inventory-donor@example.com",
            password="Good!DonorPassword2026",
            role=User.Role.DONOR,
        )
        self.donor = DonorProfile.objects.create(
            user=donor_user,
            phone="9876543210",
            date_of_birth=timezone.localdate() - timedelta(days=30 * 365),
            address="Bengaluru",
            blood_group="A+",
        )
        self.staff_client = Client()
        self.staff_client.force_login(self.staff)
        self.requester_client = Client()
        self.requester_client.force_login(self.requester)

    def test_donation_is_reviewed_reserved_dispatched_and_notified(self):
        donation_date = timezone.localdate() - timedelta(days=1)
        record_response = self.staff_client.post(
            reverse("record_donation"),
            {
                "donor": self.donor.pk,
                "donation_date": donation_date.isoformat(),
                "blood_group": "A+",
                "component": "WHOLE_BLOOD",
                "volume_ml": 450,
            },
        )
        self.assertRedirects(record_response, reverse("inventory"))
        unit = BloodUnit.objects.get()
        self.assertEqual(unit.status, "AVAILABLE")

        submit_response = self.requester_client.post(
            reverse("submit_request"),
            {
                "patient_name": "Integration Patient",
                "hospital_name": "Integration Hospital",
                "blood_group": "A+",
                "component": "WHOLE_BLOOD",
                "units_required": 1,
                "reason": "Urgent blood requirement",
            },
        )
        self.assertRedirects(submit_response, reverse("my_requests"))
        request = BloodRequest.objects.get(requester=self.requester)
        self.assertEqual(request.status, BloodRequest.Status.PENDING)

        requester_dashboard = self.requester_client.get(reverse("home"))
        self.assertEqual(requester_dashboard.context["request_total"], 1)
        self.assertEqual(requester_dashboard.context["active_request_total"], 1)
        self.assertEqual(requester_dashboard.context["unread_notification_total"], 0)
        staff_dashboard = self.staff_client.get(reverse("home"))
        self.assertEqual(staff_dashboard.context["staff_pending_requests"], 1)
        self.assertEqual(staff_dashboard.context["staff_available_units"], 1)

        request_url = reverse(
            "decide_request",
            kwargs={"request_id": request.request_id},
        )
        decide_response = self.staff_client.post(
            request_url,
            {"decision": BloodRequest.Status.APPROVED},
        )
        self.assertRedirects(decide_response, reverse("my_requests"))
        request.refresh_from_db()
        self.assertEqual(request.status, BloodRequest.Status.APPROVED)

        reserve_url = reverse(
            "reserve_request",
            kwargs={"request_id": request.request_id},
        )
        unauthorized_reservation = self.requester_client.post(reserve_url)
        self.assertEqual(unauthorized_reservation.status_code, 403)

        reserve_response = self.staff_client.post(reserve_url)
        self.assertRedirects(reserve_response, reverse("my_requests"))
        request.refresh_from_db()
        unit.refresh_from_db()
        self.assertEqual(request.status, BloodRequest.Status.RESERVED)
        self.assertEqual(unit.status, "RESERVED")
        self.assertEqual(unit.reserved_for, request)

        issue_response = self.staff_client.post(
            reverse("issue_request", kwargs={"request_id": request.request_id})
        )
        self.assertRedirects(issue_response, reverse("my_requests"))
        request.refresh_from_db()
        unit.refresh_from_db()
        self.assertEqual(request.status, BloodRequest.Status.ISSUED)
        self.assertEqual(unit.status, "ISSUED")
        self.assertEqual(unit.issued_by, self.staff)
        self.assertIsNotNone(unit.issued_at)

        requester_page = self.requester_client.get(reverse("my_requests"))
        self.assertEqual(requester_page.status_code, 200)
        self.assertContains(requester_page, "issued / dispatched")
        notifications = RequestNotification.objects.filter(
            request=request,
            recipient=self.requester,
        )
        self.assertEqual(notifications.count(), 3)
        requester_dashboard = self.requester_client.get(reverse("home"))
        self.assertEqual(requester_dashboard.context["request_total"], 1)
        self.assertEqual(requester_dashboard.context["active_request_total"], 0)
        self.assertEqual(requester_dashboard.context["unread_notification_total"], 3)
        self.assertTrue(
            AuditLog.objects.filter(
                action="REQUEST_ISSUED",
                object_id=str(request.request_id),
            ).exists()
        )

        notification = notifications.first()
        read_response = self.requester_client.post(
            reverse(
                "mark_notification_read",
                kwargs={"notification_id": notification.pk},
            )
        )
        self.assertRedirects(read_response, reverse("my_requests"))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
