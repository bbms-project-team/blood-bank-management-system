from django.utils import timezone


MIN_DONOR_AGE = 18
MAX_FIRST_TIME_DONOR_AGE = 60
MAX_REPEAT_DONOR_AGE = 65
MIN_DAYS_BETWEEN_DONATIONS = 120


def booking_eligibility_error(donor):
    """Return a preliminary deferral reason, or None when booking is allowed.

    Use the stricter 120-day interval because the profile does not record sex.
    Staff still perform the required medical screening at the donation centre.
    """
    today = timezone.localdate()
    age = today.year - donor.date_of_birth.year - (
        (today.month, today.day) < (donor.date_of_birth.month, donor.date_of_birth.day)
    )
    last_recorded = donor.donations.filter(accepted=True).order_by(
        "-donation_date"
    ).values_list("donation_date", flat=True).first()
    last_donation = max(
        (date for date in (donor.last_donation_date, last_recorded) if date),
        default=None,
    )
    is_repeat_donor = last_donation is not None

    if age < MIN_DONOR_AGE:
        return "Donors must be at least 18 years old to book."
    max_age = MAX_REPEAT_DONOR_AGE if is_repeat_donor else MAX_FIRST_TIME_DONOR_AGE
    if age > max_age:
        if is_repeat_donor:
            return "Repeat donors over 65 cannot book online."
        return "First-time donors over 60 cannot book online."
    if last_donation:
        days_since = (today - last_donation).days
        if days_since < MIN_DAYS_BETWEEN_DONATIONS:
            remaining = MIN_DAYS_BETWEEN_DONATIONS - days_since
            return f"Please wait {remaining} more day(s) after your last recorded donation."
    return None
