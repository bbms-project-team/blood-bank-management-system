
from django.http import JsonResponse


def api_error(code, message, status_code):
    """
    Return a standardized JSON error response.

    Sensitive information such as passwords, tokens,
    database details and internal exceptions must not
    be included in the message.
    """

    return JsonResponse(
        {
            "success": False,
            "error": {
                "code": code,
                "message": message,
            },
        },
        status=status_code,
    )


def api_not_found():
    """Return a standardized resource-not-found response."""

    return api_error(
        code="RESOURCE_NOT_FOUND",
        message="The requested resource was not found.",
        status_code=404,
    )


def api_forbidden():
    """Return a standardized permission-denied response."""

    return api_error(
        code="PERMISSION_DENIED",
        message="You do not have permission to perform this action.",
        status_code=403,
    )


def api_bad_request():
    """Return a standardized invalid-request response."""

    return api_error(
        code="INVALID_REQUEST",
        message="The request could not be processed.",
        status_code=400,
    )


def api_server_error():
    """Return a standardized internal-server-error response."""

    return api_error(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred. Please try again later.",
        status_code=500,
    )
