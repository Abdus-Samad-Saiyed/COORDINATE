# COORDINATE

COORDINATE is a Django-based platform for helping students coordinate shared cab rides.

The project was built around a simple problem: ride-sharing requests posted in student WhatsApp groups can quickly get buried among other messages.

COORDINATE provides a dedicated platform where verified students can create, discover and join shared rides.

## Features

### Student Accounts

- Custom Django user model
- Enrollment-number based login
- Student application workflow
- Unique application numbers
- Superuser-controlled verification
- Student profiles
- Phone number and gender information

Students do not directly create verified accounts through normal registration.

The intended flow is:

```text
Student
   |
   v
Application
   |
   v
Physical Verification
   |
   v
Admin Approval
   |
   v
Verified Account
