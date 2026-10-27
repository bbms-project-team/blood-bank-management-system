
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from bloodbank_requests.models import BloodRequest
from bloodbank_requests.models import AuditLog, RequestNotification
from bloodbank_requests.services import WorkflowError, reserve_request, issue_request
from donations.models import Donation, BloodUnit
from donors.models import DonorProfile


class BloodRequestTests(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username="hospital_user",
            email="hospital@example.com",
            password="TestPass123!",
            role=User.Role.REQUESTER,
        )

        self.staff = User.objects.create_user(
            username="bloodbank_staff",
            email="staff@example.com",
            password="TestPass123!",
            role=User.Role.STAFF,
        )

        self.donor = User.objects.create_user(
            username="donor_user",
            email="donor@example.com",
            password="TestPass123!",
            role=User.Role.DONOR,
        )
        self.donor_profile = DonorProfile.objects.create(
            user=self.donor,
            phone="9876543210",
            date_of_birth=timezone.localdate() - timedelta(days=30 * 365),
            address="Bengaluru",
            blood_group="A+",
        )

        self.request_data = {
            "patient_name": "Test Patient",
            "hospital_name": "City Hospital",
            "blood_group": "A+",
            "component": "WHOLE_BLOOD",
            "units_required": 2,
            "reason": "Emergency requirement",
        }

    def create_blood_request(self):
        return BloodRequest.objects.create(
            requester=self.requester,
            **self.request_data,
        )

    def test_requester_can_submit_blood_request(self):
        self.client.force_login(self.requester)

        response = self.client.post(
            reverse("submit_request"),
            self.request_data,
        )

        self.assertRedirects(response, reverse("my_requests"))
        self.assertEqual(BloodRequest.objects.count(), 1)

        blood_request = BloodRequest.objects.get()
        self.assertEqual(blood_request.requester, self.requester)
        self.assertEqual(
            blood_request.status,
            BloodRequest.Status.PENDING,
        )
        self.assertIsNotNone(blood_request.request_id)

    def test_staff_can_approve_pending_request(self):
        blood_request = self.create_blood_request()
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse(
                "decide_request",
                kwargs={"request_id": blood_request.request_id},
            ),
            {"decision": "APPROVED"},
        )

        self.assertRedirects(response, reverse("my_requests"))

        blood_request.refresh_from_db()
        self.assertEqual(
            blood_request.status,
            BloodRequest.Status.APPROVED,
        )
        self.assertEqual(blood_request.decision_by, self.staff)
        self.assertIsNotNone(blood_request.decision_at)

    def test_staff_can_reject_pending_request(self):
        blood_request = self.create_blood_request()
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse(
                "decide_request",
                kwargs={"request_id": blood_request.request_id},
            ),
            {"decision": "REJECTED"},
        )

        self.assertRedirects(response, reverse("my_requests"))

        blood_request.refresh_from_db()
        self.assertEqual(
            blood_request.status,
            BloodRequest.Status.REJECTED,
        )
        self.assertEqual(blood_request.decision_by, self.staff)
        self.assertIsNotNone(blood_request.decision_at)

    def test_already_decided_request_cannot_be_changed(self):
        blood_request = self.create_blood_request()
        self.client.force_login(self.staff)

        decision_url = reverse(
            "decide_request",
            kwargs={"request_id": blood_request.request_id},
        )

        self.client.post(
            decision_url,
            {"decision": "APPROVED"},
        )

        blood_request.refresh_from_db()
        original_decision_time = blood_request.decision_at

        self.client.post(
            decision_url,
            {"decision": "REJECTED"},
        )

        blood_request.refresh_from_db()
        self.assertEqual(
            blood_request.status,
            BloodRequest.Status.APPROVED,
        )
        self.assertEqual(blood_request.decision_by, self.staff)
        self.assertEqual(
            blood_request.decision_at,
            original_decision_time,
        )

    def test_donor_cannot_submit_blood_request(self):
        self.client.force_login(self.donor)

        response = self.client.get(reverse("submit_request"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(BloodRequest.objects.count(), 0)

    def test_requester_cannot_decide_blood_request(self):
        blood_request = self.create_blood_request()
        self.client.force_login(self.requester)

        response = self.client.post(
            reverse(
                "decide_request",
                kwargs={"request_id": blood_request.request_id},
            ),
            {"decision": "APPROVED"},
        )

        self.assertEqual(response.status_code, 403)

        blood_request.refresh_from_db()
        self.assertEqual(
            blood_request.status,
            BloodRequest.Status.PENDING,
        )
        self.assertIsNone(blood_request.decision_by)
        self.assertIsNone(blood_request.decision_at)

    def create_unit(self, blood_group="A+", component="WHOLE_BLOOD", expiry=None):
        donation = Donation.objects.create(
            donor=self.donor_profile,
            donation_date=timezone.localdate() - timedelta(days=1),
            blood_group=blood_group,
            component=component,
            volume_ml=450,
            accepted=True,
        )
        return BloodUnit.objects.create(
            donation=donation,
            expiry_date=expiry or timezone.localdate() + timedelta(days=10),
        )

    def approved_request(self, units=1):
        request = self.create_blood_request()
        request.units_required = units
        request.status = BloodRequest.Status.APPROVED
        request.save(update_fields=["units_required", "status"])
        return request

    def test_reservation_updates_inventory_and_audit_atomically(self):
        request = self.approved_request(units=2)
        units = [self.create_unit(), self.create_unit()]
        reserve_request(request.request_id, self.staff)
        request.refresh_from_db()
        self.assertEqual(request.status, BloodRequest.Status.RESERVED)
        for unit in units:
            unit.refresh_from_db()
            self.assertEqual(unit.status, "RESERVED")
            self.assertEqual(unit.reserved_for, request)
        self.assertTrue(AuditLog.objects.filter(action="REQUEST_RESERVED").exists())
        self.assertEqual(RequestNotification.objects.filter(request=request).count(), 1)

    def test_reservation_rolls_back_when_matching_stock_is_insufficient(self):
        request = self.approved_request(units=2)
        unit = self.create_unit()
        with self.assertRaises(WorkflowError):
            reserve_request(request.request_id, self.staff)
        request.refresh_from_db()
        unit.refresh_from_db()
        self.assertEqual(request.status, BloodRequest.Status.APPROVED)
        self.assertEqual(unit.status, "AVAILABLE")
        self.assertFalse(AuditLog.objects.filter(action="REQUEST_RESERVED").exists())

    def test_reservation_rejects_expired_and_nonmatching_units(self):
        request = self.approved_request()
        expired = self.create_unit(expiry=timezone.localdate() - timedelta(days=1))
        self.create_unit(blood_group="B+")
        with self.assertRaises(WorkflowError):
            reserve_request(request.request_id, self.staff)
        expired.refresh_from_db()
        self.assertEqual(expired.status, "AVAILABLE")

    def test_request_cannot_be_reserved_twice(self):
        request = self.approved_request()
        self.create_unit()
        reserve_request(request.request_id, self.staff)
        with self.assertRaises(WorkflowError):
            reserve_request(request.request_id, self.staff)
        self.assertEqual(BloodUnit.objects.filter(reserved_for=request).count(), 1)

    def test_issue_is_atomic_traceable_and_cannot_repeat(self):
        request = self.approved_request(units=2)
        units = [self.create_unit(), self.create_unit()]
        reserve_request(request.request_id, self.staff)
        issue_request(request.request_id, self.staff)
        request.refresh_from_db()
        self.assertEqual(request.status, BloodRequest.Status.ISSUED)
        for unit in units:
            unit.refresh_from_db()
            self.assertEqual(unit.status, "ISSUED")
            self.assertEqual(unit.issued_by, self.staff)
            self.assertIsNotNone(unit.issued_at)
        with self.assertRaises(WorkflowError):
            issue_request(request.request_id, self.staff)
        self.assertEqual(AuditLog.objects.filter(action="REQUEST_ISSUED").count(), 1)

    def test_expired_reserved_unit_cannot_be_issued_and_stays_reserved(self):
        request = self.approved_request()
        unit = self.create_unit()
        reserve_request(request.request_id, self.staff)
        BloodUnit.objects.filter(pk=unit.pk).update(
            expiry_date=timezone.localdate() - timedelta(days=1)
        )
        with self.assertRaises(WorkflowError):
            issue_request(request.request_id, self.staff)
        unit.refresh_from_db()
        request.refresh_from_db()
        self.assertEqual(unit.status, "RESERVED")
        self.assertEqual(request.status, BloodRequest.Status.RESERVED)

    def test_requester_cannot_access_staff_reports_or_admin_audit(self):
        self.client.force_login(self.requester)
        self.assertEqual(self.client.get(reverse("reports")).status_code, 403)
        self.assertEqual(self.client.get(reverse("audit_log")).status_code, 403)

    def test_request_decision_creates_requester_notification_and_audit(self):
        request = self.create_blood_request()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("decide_request", kwargs={"request_id": request.request_id}),
            {"decision": "APPROVED"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(RequestNotification.objects.filter(request=request).exists())
        self.assertTrue(AuditLog.objects.filter(action="REQUEST_APPROVED").exists())

    def test_requester_sees_only_their_status_notifications(self):
        request = self.create_blood_request()
        RequestNotification.objects.create(
            request=request,
            recipient=self.requester,
            message="Your request was approved.",
        )
        other = User.objects.create_user(
            username="other_hospital",
            email="other-hospital@example.com",
            password="TestPass123!",
            role=User.Role.REQUESTER,
        )
        other_request = BloodRequest.objects.create(
            requester=other,
            **self.request_data,
        )
        RequestNotification.objects.create(
            request=other_request,
            recipient=other,
            message="Private other request update.",
        )
        self.client.force_login(self.requester)
        response = self.client.get(reverse("my_requests"))
        self.assertContains(response, "Your request was approved.")
        self.assertNotContains(response, "Private other request update.")

    def test_staff_alerts_show_low_stock_and_expiry(self):
        soon = self.create_unit(expiry=timezone.localdate() + timedelta(days=3))
        expired = self.create_unit(expiry=timezone.localdate() - timedelta(days=1))
        self.client.force_login(self.staff)
        response = self.client.get(reverse("alerts"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(
            item["donation__blood_group"] == "A+"
            and item["donation__component"] == "WHOLE_BLOOD"
            and item["units"] == 1
            for item in response.context["stock_alerts"]
        ))
        self.assertContains(response, str(soon.unit_code))
        self.assertContains(response, str(expired.unit_code))

    def test_staff_report_summarizes_real_inventory_and_requests(self):
        self.create_blood_request()
        self.create_unit()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["available_units"], 1)
        self.assertEqual(response.context["donation_count"], 1)


class ConcurrentReservationTests(TransactionTestCase):
    reset_sequences = True

    def test_competing_requests_cannot_reserve_the_same_unit(self):
        staff = User.objects.create_user(
            username="concurrent_staff",
            email="concurrent-staff@example.com",
            password="TestPass123!",
            role=User.Role.STAFF,
        )
        donor_user = User.objects.create_user(
            username="concurrent_donor",
            email="concurrent-donor@example.com",
            password="TestPass123!",
            role=User.Role.DONOR,
        )
        profile = DonorProfile.objects.create(
            user=donor_user,
            phone="9876543210",
            date_of_birth=timezone.localdate() - timedelta(days=30 * 365),
            address="Bengaluru",
            blood_group="A+",
        )
        requesters = [
            User.objects.create_user(
                username=f"concurrent_hospital_{index}",
                email=f"concurrent-hospital-{index}@example.com",
                password="TestPass123!",
                role=User.Role.REQUESTER,
            )
            for index in range(2)
        ]
        requests = [
            BloodRequest.objects.create(
                requester=requester,
                patient_name="Synthetic Patient",
                hospital_name="Synthetic Hospital",
                blood_group="A+",
                component="WHOLE_BLOOD",
                units_required=1,
                reason="Concurrent reservation test",
                status=BloodRequest.Status.APPROVED,
            )
            for requester in requesters
        ]
        donation = Donation.objects.create(
            donor=profile,
            donation_date=timezone.localdate() - timedelta(days=1),
            blood_group="A+",
            component="WHOLE_BLOOD",
            volume_ml=450,
            accepted=True,
        )
        unit = BloodUnit.objects.create(
            donation=donation,
            expiry_date=timezone.localdate() + timedelta(days=10),
        )
        barrier = Barrier(2)

        def attempt(request_id):
            close_old_connections()
            barrier.wait(timeout=10)
            try:
                reserve_request(request_id, staff)
                return "reserved"
            except WorkflowError:
                return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda item: attempt(item.request_id), requests))

        self.assertCountEqual(results, ["reserved", "rejected"])
        unit.refresh_from_db()
        self.assertEqual(unit.status, "RESERVED")
        self.assertEqual(
            BloodRequest.objects.filter(status=BloodRequest.Status.RESERVED).count(),
            1,
        )
