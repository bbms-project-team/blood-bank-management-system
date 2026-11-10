
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch, sentinel

from django.db import close_old_connections
from django.db.utils import OperationalError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from bloodbank_requests.models import BloodRequest
from bloodbank_requests.models import AuditLog, RequestNotification
from bloodbank_requests.services import WorkflowError, reserve_request, issue_request
from bloodbank_requests.compatibility import is_blood_compatible
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
            {**self.request_data, "requester": self.staff.pk},
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

    def test_compatibility_helper_covers_invalid_inputs_and_exact_match_policy(self):
        self.assertTrue(is_blood_compatible("A+", "A+", "WHOLE_BLOOD"))
        self.assertFalse(is_blood_compatible("A+", "B+", "WHOLE_BLOOD"))
        self.assertFalse(is_blood_compatible("BAD", "A+", "WHOLE_BLOOD"))
        self.assertFalse(is_blood_compatible("A+", "BAD", "WHOLE_BLOOD"))
        self.assertFalse(is_blood_compatible("A+", "A+", "INVALID"))

    def test_reservation_retries_transient_database_lock_and_stops_after_limit(self):
        transient = OperationalError("database is locked")
        with patch("bloodbank_requests.services.time.sleep") as sleep, patch(
            "bloodbank_requests.services._reserve_request_once",
            side_effect=[transient, sentinel.reserved],
        ) as attempt:
            self.assertIs(reserve_request("unused", self.staff), sentinel.reserved)
            self.assertEqual(attempt.call_count, 2)
            sleep.assert_called_once()
        with patch("bloodbank_requests.services.time.sleep"), patch(
            "bloodbank_requests.services._reserve_request_once",
            side_effect=OperationalError("database is locked"),
        ) as attempt:
            with self.assertRaises(WorkflowError):
                reserve_request("unused", self.staff)
            self.assertEqual(attempt.call_count, 3)

    def test_issue_retries_transient_database_lock_and_stops_after_limit(self):
        transient = OperationalError("database is locked")
        with patch("bloodbank_requests.services.time.sleep") as sleep, patch(
            "bloodbank_requests.services._issue_request_once",
            side_effect=[transient, sentinel.issued],
        ) as attempt:
            self.assertIs(issue_request("unused", self.staff), sentinel.issued)
            self.assertEqual(attempt.call_count, 2)
            sleep.assert_called_once()
        with patch("bloodbank_requests.services.time.sleep"), patch(
            "bloodbank_requests.services._issue_request_once",
            side_effect=OperationalError("database is locked"),
        ) as attempt:
            with self.assertRaises(WorkflowError):
                issue_request("unused", self.staff)
            self.assertEqual(attempt.call_count, 3)

    def test_malformed_request_fields_are_rejected(self):
        self.client.force_login(self.requester)
        invalid_data = self.request_data.copy()
        invalid_data.update({
            "blood_group": "INVALID",
            "component": "INVALID",
            "units_required": "-1",
        })

        response = self.client.post(reverse("submit_request"), invalid_data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BloodRequest.objects.count(), 0)

    def test_request_form_rejects_missing_names_and_zero_units(self):
        from bloodbank_requests.forms import BloodRequestForm
        data = self.request_data.copy()
        data.update({"patient_name": " ", "hospital_name": " ", "units_required": "0"})
        form = BloodRequestForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn("patient_name", form.errors)
        self.assertIn("hospital_name", form.errors)
        self.assertIn("units_required", form.errors)

    def test_staff_request_actions_reject_get_methods(self):
        request = self.create_blood_request()
        self.client.force_login(self.staff)
        for name in ("decide_request", "reserve_request", "issue_request"):
            response = self.client.get(
                reverse(name, kwargs={"request_id": request.request_id}),
                HTTP_ACCEPT="text/html",
            )
            self.assertRedirects(response, reverse("my_requests"))

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
        notification = RequestNotification.objects.get(request=blood_request)
        self.assertEqual(notification.recipient, self.requester)
        self.assertIn("approved", notification.message)

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
        notification = RequestNotification.objects.get(request=blood_request)
        self.assertEqual(notification.recipient, self.requester)
        self.assertIn("rejected", notification.message)

    def test_invalid_decision_returns_standard_json_error(self):
        request = self.create_blood_request()
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("decide_request", kwargs={"request_id": request.request_id}),
            {"decision": "INVALID"},
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"error": {"code": "invalid_decision", "message": "Invalid decision."}},
        )

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

        response = self.client.post(
            reverse("submit_request"),
            self.request_data,
        )

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
            status="AVAILABLE",
            processing_status="TESTED",
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
        notification = RequestNotification.objects.get(request=request)
        self.assertEqual(notification.recipient, self.requester)
        self.assertIn("reserved", notification.message)

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

    def test_reservation_api_error_is_consistent_and_logged(self):
        request = self.approved_request()
        self.client.force_login(self.staff)

        with self.assertLogs("bloodbank_requests.views", level="WARNING") as logs:
            response = self.client.post(
                reverse("reserve_request", kwargs={"request_id": request.request_id}),
                HTTP_ACCEPT="application/json",
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "reservation_failed",
                    "message": "There are not enough matching, unexpired units.",
                }
            },
        )
        self.assertIn(str(request.request_id), logs.output[0])
        self.assertNotIn("password", logs.output[0].lower())

    def test_reservation_rejects_expired_and_nonmatching_units(self):
        request = self.approved_request()
        expired = self.create_unit(expiry=timezone.localdate() - timedelta(days=1))
        self.create_unit(blood_group="B+")
        with self.assertRaises(WorkflowError):
            reserve_request(request.request_id, self.staff)
        expired.refresh_from_db()
        self.assertEqual(expired.status, "AVAILABLE")

    def test_incompatible_blood_group_is_not_reserved(self):
        request = self.approved_request()
        unit = self.create_unit(blood_group="B+")

        with self.assertRaises(WorkflowError):
            reserve_request(request.request_id, self.staff)

        request.refresh_from_db()
        unit.refresh_from_db()
        self.assertEqual(request.status, BloodRequest.Status.APPROVED)
        self.assertEqual(unit.status, "AVAILABLE")
        self.assertFalse(
            AuditLog.objects.filter(action="REQUEST_RESERVED").exists()
        )

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
        dispatch_log = AuditLog.objects.get(action="REQUEST_ISSUED")
        self.assertEqual(
            set(dispatch_log.details["unit_codes"]),
            {str(unit.unit_code) for unit in units},
        )
        self.assertEqual(
            RequestNotification.objects.filter(request=request).count(), 2
        )
        self.assertTrue(
            RequestNotification.objects.filter(
                request=request,
                recipient=self.requester,
                message__icontains="issued",
            ).exists()
        )

    def test_approved_request_cannot_be_issued_before_units_are_reserved(self):
        request = self.approved_request()
        unit = self.create_unit()

        with self.assertRaises(WorkflowError):
            issue_request(request.request_id, self.staff)

        request.refresh_from_db()
        unit.refresh_from_db()
        self.assertEqual(request.status, BloodRequest.Status.APPROVED)
        self.assertEqual(unit.status, "AVAILABLE")
        self.assertFalse(AuditLog.objects.filter(action="REQUEST_ISSUED").exists())

    def test_requester_cannot_dispatch_reserved_units(self):
        request = self.approved_request()
        unit = self.create_unit()
        reserve_request(request.request_id, self.staff)
        self.client.force_login(self.requester)

        response = self.client.post(
            reverse("issue_request", kwargs={"request_id": request.request_id})
        )

        self.assertEqual(response.status_code, 403)
        request.refresh_from_db()
        unit.refresh_from_db()
        self.assertEqual(request.status, BloodRequest.Status.RESERVED)
        self.assertEqual(unit.status, "RESERVED")

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
        other_request_data = self.request_data.copy()
        other_request_data["patient_name"] = "Private Patient"
        other_request = BloodRequest.objects.create(
            requester=other,
            **other_request_data,
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
        self.assertNotContains(response, "Private Patient")

    def test_requester_can_mark_only_their_own_notification_as_read(self):
        request = self.create_blood_request()
        notification = RequestNotification.objects.create(
            request=request,
            recipient=self.requester,
            message="Your request was approved.",
        )
        self.client.force_login(self.requester)

        response = self.client.post(
            reverse(
                "mark_notification_read",
                kwargs={"notification_id": notification.pk},
            )
        )

        self.assertRedirects(response, reverse("my_requests"))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)

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
            status="AVAILABLE",
            processing_status="TESTED",
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
