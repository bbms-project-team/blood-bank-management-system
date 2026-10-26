
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*allowed_roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                raise PermissionDenied(
                    "You do not have permission to access this page."
                )
            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator
