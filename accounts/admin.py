from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("BBMS Role", {"fields": ("role",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("BBMS Details", {"fields": ("email", "role")}),
    )
    list_display = ("username", "email", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff")

    @staticmethod
    def _is_authorized_admin(request):
        user = request.user
        return user.is_superuser or (
            user.is_staff and user.role == User.Role.ADMIN
        )

    def has_module_permission(self, request):
        return (
            self._is_authorized_admin(request)
            and super().has_module_permission(request)
        )

    def has_view_permission(self, request, obj=None):
        return (
            self._is_authorized_admin(request)
            and super().has_view_permission(request, obj)
        )

    def has_add_permission(self, request):
        return (
            self._is_authorized_admin(request)
            and super().has_add_permission(request)
        )

    def has_change_permission(self, request, obj=None):
        return (
            self._is_authorized_admin(request)
            and super().has_change_permission(request, obj)
        )

    def has_delete_permission(self, request, obj=None):
        return (
            self._is_authorized_admin(request)
            and super().has_delete_permission(request, obj)
        )
