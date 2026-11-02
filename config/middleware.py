
import logging

from django.core.exceptions import (
    PermissionDenied,
    SuspiciousOperation,
)
from django.http import Http404

from .api_errors import (
    api_bad_request,
    api_forbidden,
    api_not_found,
    api_server_error,
)

logger = logging.getLogger(__name__)


class APIExceptionMiddleware:
    """
    Handle exceptions for API requests using standardized JSON responses.

    Normal Django website requests continue using Django's default
    HTML error handling.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        # Only handle API requests.
        if not request.path.startswith("/api/"):
            return None

        if isinstance(exception, Http404):
            logger.warning("API resource not found.")
            return api_not_found()

        if isinstance(exception, PermissionDenied):
            logger.warning("API permission denied.")
            return api_forbidden()

        if isinstance(exception, SuspiciousOperation):
            logger.warning("Invalid API request received.")
            return api_bad_request()

        # Log only the exception class, not its message or traceback.
        logger.error(
            "Unexpected API exception occurred. Exception type: %s",
            type(exception).__name__,
        )

        return api_server_error()
