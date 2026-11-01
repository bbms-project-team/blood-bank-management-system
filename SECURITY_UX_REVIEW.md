# Issue 13: security, usability, and responsive UI review

## Security checks

- Passwords are stored through Django's password hasher (`create_user` / form save); authentication tests verify passwords without storing them as plain text.
- Role protected views reject users outside their allowed roles. Account, donor, donation, and request tests cover sign-in and role restrictions.
- Sessions expire after 15 minutes without activity and when the browser closes. Logout is POST-only and clears the authenticated session.
- With `DJANGO_DEBUG=false`, Django redirects HTTP to HTTPS, uses secure session and CSRF cookies, and sends HSTS for one year. SameSite is `Lax`; content type sniffing is disabled and the referrer policy is `same-origin`.
- The local Django development server does not provide production TLS. The deployment web server or trusted proxy must provide a valid HTTPS certificate and terminate TLS. For a trusted TLS-terminating proxy, set `DJANGO_TRUST_X_FORWARDED_PROTO=true` only when it strips client-supplied forwarded headers and sets `X-Forwarded-Proto` itself. Production settings must include the correct `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`.

## Usability and accessibility review

- The shared layout uses semantic header, navigation, main, and footer landmarks, with a keyboard-visible skip link and visible focus outlines.
- Django form fields render labels and validation errors; status messages are announced through a polite live region.
- Layout breakpoints at 820px and 560px stack navigation and content grids for smaller screens. Tables remain available in horizontal scroll containers; the base layout sets a 320px minimum viewport width.
- Reduced-motion preferences are respected. No automated screen-reader or physical-device evaluation was performed.

## Verification

- Django tests: `python manage.py test` — 50 passed.
- Configuration: `python manage.py check` and `python manage.py makemigrations --check --dry-run`.
- HTTPS redirect and HSTS response behavior are covered by focused account tests.
