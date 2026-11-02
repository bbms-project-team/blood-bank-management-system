
import json

from django.core.exceptions import (
    PermissionDenied,
    SuspiciousOperation,
)
from django.http import Http404
from django.test import (
    Client,
    RequestFactory,
    SimpleTestCase,
    override_settings,
)
from django.urls import path

from config.middleware import APIExceptionMiddleware


def api_test_404_view(request):
    """Temporary view used to test API middleware through HTTP."""
    raise Http404()


urlpatterns = [
    path("api/test-404/", api_test_404_view),
]


class APIExceptionMiddlewareTests(SimpleTestCase):
    """Tests for standardized API error handling and security."""

    def setUp(self):
        self.factory = RequestFactory()

        self.middleware = APIExceptionMiddleware(
            lambda request: None
        )

        self.request = self.factory.get("/api/test/")

    def get_json(self, response):
        """Convert JsonResponse content into a Python dictionary."""
        return json.loads(response.content.decode("utf-8"))

    def test_api_not_found_returns_standard_json(self):
        response = self.middleware.process_exception(
            self.request,
            Http404(),
        )

        self.assertEqual(response.status_code, 404)

        self.assertEqual(
            self.get_json(response),
            {
                "success": False,
                "error": {
                    "code": "RESOURCE_NOT_FOUND",
                    "message": "The requested resource was not found.",
                },
            },
        )

    def test_api_forbidden_returns_standard_json(self):
        response = self.middleware.process_exception(
            self.request,
            PermissionDenied(),
        )

        self.assertEqual(response.status_code, 403)

        data = self.get_json(response)

        self.assertEqual(
            data["error"]["code"],
            "PERMISSION_DENIED",
        )

        self.assertFalse(data["success"])

    def test_api_bad_request_returns_standard_json(self):
        response = self.middleware.process_exception(
            self.request,
            SuspiciousOperation(),
        )

        self.assertEqual(response.status_code, 400)

        data = self.get_json(response)

        self.assertEqual(
            data["error"]["code"],
            "INVALID_REQUEST",
        )

        self.assertFalse(data["success"])

    def test_api_server_error_returns_standard_json(self):
        exception = Exception("Sensitive database details")

        with self.assertLogs(
            "config.middleware",
            level="ERROR",
        ) as captured:
            response = self.middleware.process_exception(
                self.request,
                exception,
            )

        self.assertEqual(response.status_code, 500)

        data = self.get_json(response)

        self.assertEqual(
            data["error"]["code"],
            "INTERNAL_SERVER_ERROR",
        )

        self.assertFalse(data["success"])

        log_output = "\n".join(captured.output)

        self.assertNotIn(
            "Sensitive database details",
            log_output,
        )

    def test_non_api_request_is_not_modified(self):
        request = self.factory.get("/accounts/login/")

        response = self.middleware.process_exception(
            request,
            Http404(),
        )

        self.assertIsNone(response)

    def test_server_error_does_not_expose_password_or_token(self):
        sensitive_values = [
            "MySecretPassword123",
            "secret-access-token-456",
        ]

        exception = Exception(" ".join(sensitive_values))

        with self.assertLogs(
            "config.middleware",
            level="ERROR",
        ) as captured:
            response = self.middleware.process_exception(
                self.request,
                exception,
            )

        response_text = response.content.decode("utf-8")
        log_output = "\n".join(captured.output)

        for secret in sensitive_values:
            self.assertNotIn(secret, response_text)
            self.assertNotIn(secret, log_output)

    def test_error_response_never_contains_exception_details(self):
        secret = "DATABASE_PASSWORD=super-secret-value"

        with self.assertLogs(
            "config.middleware",
            level="ERROR",
        ):
            response = self.middleware.process_exception(
                self.request,
                Exception(secret),
            )

        response_text = response.content.decode("utf-8")

        self.assertNotIn(secret, response_text)

        self.assertIn(
            "INTERNAL_SERVER_ERROR",
            response_text,
        )

        self.assertIn(
            "An unexpected error occurred.",
            response_text,
        )

    @override_settings(
        ROOT_URLCONF="config.tests",
        ALLOWED_HOSTS=["testserver"],
        DEBUG=False,
    )
    def test_api_404_through_real_http_request(self):
        client = Client(raise_request_exception=False)

        response = client.get("/api/test-404/")

        self.assertEqual(response.status_code, 404)

        data = self.get_json(response)

        self.assertFalse(data["success"])

        self.assertEqual(
            data["error"]["code"],
            "RESOURCE_NOT_FOUND",
        )
