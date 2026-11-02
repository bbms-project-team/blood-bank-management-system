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
- User registration and authentication
- Role-based access
- Donor and donation management
- Blood inventory and blood requests

## Running Automated Tests

Activate the project's virtual environment before running these commands.

- Check Django configuration: `python manage.py check`
- Run automated tests: `python manage.py test`

The system check validates the Django configuration, while the test command runs the project's automated test suite.

Run these checks before submitting changes for review.

