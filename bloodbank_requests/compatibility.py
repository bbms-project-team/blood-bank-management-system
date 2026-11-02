
"""
Blood-group compatibility checks for BBMS.

Temporary conservative policy:
Only exact blood-group matches are accepted.
Broader component-specific ABO/Rh compatibility
requires an approved project compatibility matrix.
"""

from config.domain import BLOOD_GROUPS, COMPONENTS


VALID_BLOOD_GROUPS = {
    value for value, label in BLOOD_GROUPS
}

VALID_COMPONENTS = {
    value for value, label in COMPONENTS
}


def is_blood_compatible(donor_group, recipient_group, component):
    """
    Return True only when the donor and recipient blood
    groups match exactly and the component is supported.
    """

    if donor_group not in VALID_BLOOD_GROUPS:
        return False

    if recipient_group not in VALID_BLOOD_GROUPS:
        return False

    if component not in VALID_COMPONENTS:
        return False

    # Conservative fallback until the approved
    # component-specific compatibility matrix is available.
    return donor_group == recipient_group
