
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from bloodbank_requests.models import BloodRequest


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
