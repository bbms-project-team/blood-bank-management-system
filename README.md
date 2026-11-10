# Blood Bank Management System

A Django-based Blood Bank Management System developed as a Software Engineering project.

## Requirements
- Python 3.13
- pip
- Git

## Run locally
1. Clone the repository and open its directory.
2. Create and activate a virtual environment.
3. Install the dependencies listed in requirements.txt.
4. Apply migrations:
   python manage.py migrate
5. Start the development server:
   python manage.py runserver

Open http://127.0.0.1:8000/ in your browser.

## Main features
- Role-based donor, receptionist, medical, inventory and administrator access
- Central login accepts email and password (and keeps username login compatibility); inactive accounts are rejected by Django authentication
- Reception dashboard with today's queue, donor totals, donations and tested stock by blood group
- Walk-in donor registration with duplicate email and phone checks and password setup email
- Searchable donor directory and donor profiles with appointment and donation history
- Reception staff can edit donor contact/profile details with audit logging
- Receptionist appointment scheduling with unique references, location and capacity-limited slots
- Appointment check-in, medical screening and eligibility decisions, donation processing and audit events
- Donor dashboard showing receptionist-created appointments, donation history and notifications
- Blood units quarantined after donation until processing and testing are cleared
- Blood requests, inventory and existing audit functionality

## Blood request and dispatch workflow

Hospital requester accounts submit requests with a generated request ID and pending status. Blood bank staff review, approve or reject requests; the request list shows currently available units matching the exact blood group and component. Reservation and issue operations recheck stock, compatibility and expiry inside atomic transactions. Reserved units are unavailable to other requests. Dispatch records the issuing user and time on each unit, changes the request to issued, writes an audit event with the unit codes, and notifies the requester. Insufficient compatible stock and expired reservations fail without partially changing the inventory.

## Reception workflow

Create a receptionist account by assigning the `RECEPTIONIST` role to a user (or use the Django admin). In `/reception/slots/`, create future donation times with a centre and capacity. The receptionist then searches for an existing donor or registers a walk-in donor, and schedules an appointment. New donors receive a password setup link by email. In development the email is printed to the runserver console; configure Django's email settings for deployment.

Staff confirm and check in appointments. Medical staff record screening and eligibility, then mark the donation in progress. A donation can only be recorded against an in-progress appointment. The resulting unit stays quarantined until an authorized user records the processing and testing result. A cleared unit then appears as available inventory. Donors use `/reception/my/` to view appointments scheduled by staff, their references, status, notifications and donation history.

For the local database, existing available units are treated as already tested by the migration. New donation records enter quarantine. Apply new migrations with:

```powershell
python manage.py migrate
```

## Running Automated Tests

Activate the project's virtual environment before running these commands.

- Check Django configuration: `python manage.py check`
- Run automated tests: `python manage.py test`

The system check validates the Django configuration, while the test command runs the project's automated test suite.

Run these checks before submitting changes for review.

