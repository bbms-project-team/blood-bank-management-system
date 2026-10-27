from .models import AuditLog


def record_audit(actor, action, object_type, object_id, details=None):
    """Persist a small, non-sensitive audit event for a critical action."""
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        details=details or {},
    )
