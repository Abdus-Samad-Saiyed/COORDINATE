"""
Local development secrets template.
Copy this file to campus/settings/secrets_local.py for local development.
This file is excluded from Git and Docker and must NEVER be used in production.
"""

# Django Secret Key for local development
DJANGO_SECRET_KEY = 'local-dev-insecure-secret-key-change-if-needed'

# Email Credentials for development SMTP testing
EMAIL_HOST_USER = 'noreply.campus.nexus@gmail.com'
EMAIL_HOST_PASSWORD = 'your-google-app-password-here'

# Superaccount dev password override for development seeding
PERSONAL_SUPERACCOUNT_PASSWORD = 'dev-superaccount-password-placeholder'
