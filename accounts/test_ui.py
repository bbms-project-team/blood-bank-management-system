from datetime import date
from html.parser import HTMLParser
from pathlib import Path

from django.contrib.staticfiles.finders import find
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from donors.models import DonorProfile


class PageMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.label_targets = []
        self.landmarks = set()
        self.meta_viewport = False
        self.stylesheet = False
        self.skip_link = False
        self.main_content = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "label":
            self.label_targets.append(attrs.get("for"))
        if tag in {"main", "nav", "header", "footer"}:
            self.landmarks.add(tag)
        if tag == "meta" and attrs.get("name") == "viewport":
            self.meta_viewport = True
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.stylesheet = True
        if tag == "a" and attrs.get("href") == "#main-content":
            self.skip_link = True
        if tag == "main" and attrs.get("id") == "main-content":
            self.main_content = True


class ResponsiveAccessibilityTests(TestCase):
    def setUp(self):
        self.donor_user = User.objects.create_user(
            username="ui_donor",
            email="ui-donor@example.com",
            password="StrongPass123!",
            role=User.Role.DONOR,
        )
        DonorProfile.objects.create(
            user=self.donor_user,
            phone="9876543210",
            date_of_birth=date(1995, 5, 15),
            address="Bengaluru",
            blood_group="A+",
        )
        self.staff_user = User.objects.create_user(
            username="ui_staff",
            email="ui-staff@example.com",
            password="StrongPass123!",
            role=User.Role.STAFF,
        )
        self.requester_user = User.objects.create_user(
            username="ui_requester",
            email="ui-requester@example.com",
            password="StrongPass123!",
            role=User.Role.REQUESTER,
        )
        self.admin_user = User.objects.create_user(
            username="ui_admin",
            email="ui-admin@example.com",
            password="StrongPass123!",
            role=User.Role.ADMIN,
        )

    def test_all_pages_share_responsive_accessible_landmarks(self):
        pages = [
            (None, "home"),
            (None, "login"),
            (None, "register"),
            (self.donor_user, "my_profile"),
            (self.staff_user, "donor_list"),
            (self.staff_user, "record_donation"),
            (self.staff_user, "inventory"),
            (self.requester_user, "submit_request"),
            (self.requester_user, "my_requests"),
            (self.staff_user, "alerts"),
            (self.staff_user, "reports"),
            (self.admin_user, "audit_log"),
        ]

        for user, route_name in pages:
            with self.subTest(page=route_name):
                if user is None:
                    self.client.logout()
                else:
                    self.client.force_login(user)
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)

                markup = PageMarkup()
                markup.feed(response.content.decode())
                self.assertEqual(markup.landmarks, {"main", "nav", "header", "footer"})
                self.assertTrue(markup.meta_viewport)
                self.assertTrue(markup.stylesheet)
                self.assertTrue(markup.skip_link)
                self.assertTrue(markup.main_content)
                self.assertTrue(
                    all(target and target in markup.ids for target in markup.label_targets),
                    f"Unassociated form label on {route_name}",
                )

    def test_styles_include_mobile_layout_keyboard_focus_and_reduced_motion(self):
        stylesheet = find("bbms/css/app.css")
        self.assertIsNotNone(stylesheet)
        css = Path(stylesheet).read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 720px)", css)
        self.assertIn("@media (max-width: 480px)", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("overflow-x: auto", css)
