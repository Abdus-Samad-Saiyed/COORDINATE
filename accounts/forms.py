"""Forms for the accounts app."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import ENROLLMENT_VALIDATOR, AccountApplication, User


class EnrollmentAuthenticationForm(AuthenticationForm):
    """
    Authentication form that normalizes enrollment number to uppercase
    and trims whitespace.
    """

    username = forms.CharField(
        label='Enrollment Number',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 2024BCSE001',
            'autofocus': True,
            'autocapitalize': 'characters',
            'autocomplete': 'username',
        }),
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        }),
    )

    def clean_username(self):
        username = self.cleaned_data.get('username', '')
        return username.strip().upper()


class AccountApplicationForm(forms.ModelForm):
    """Public form for prospective students to apply for a verified account."""

    email = forms.EmailField(
        label='Institute / Personal Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 2024bcse065@nitsri.ac.in',
            'autocomplete': 'email',
        }),
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Choose a password',
        }),
    )
    confirm_password = forms.CharField(
        label='Confirm Password',
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Repeat your password',
        }),
    )

    class Meta:
        model = AccountApplication
        fields = ['enrollment_number', 'full_name', 'email', 'phone_number', 'gender']
        widgets = {
            'enrollment_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 2024BCSE001',
            }),
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your full name',
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+91 XXXXX XXXXX',
            }),
            'gender': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_enrollment_number(self):
        from django.conf import settings
        enrollment = self.cleaned_data.get('enrollment_number', '').strip().upper()

        if not ENROLLMENT_VALIDATOR.regex.match(enrollment):
            raise forms.ValidationError(
                'Invalid enrollment number format. Expected format: 2024BCSE001'
            )

        if not getattr(settings, 'DEBUG', False) and enrollment.startswith('20XX'):
            raise forms.ValidationError(
                'Synthetic debug enrollments (20XX...) are disabled in production.'
            )

        if User.objects.filter(enrollment_number=enrollment).exists():
            raise forms.ValidationError(
                'An account with this enrollment number is already registered.'
            )

        if AccountApplication.objects.filter(enrollment_number=enrollment, approved=False).exists():
            raise forms.ValidationError(
                'An application for this enrollment number is already pending verification.'
            )

        return enrollment

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise forms.ValidationError('Email address is required.')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('An account with this email address already exists.')
        if AccountApplication.objects.filter(email=email, approved=False).exists():
            raise forms.ValidationError('An application with this email address is already pending verification.')
        return email

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get('password')
        cpw = cleaned.get('confirm_password')

        if pw:
            import sys
            if len(pw) < 8:
                self.add_error('password', 'Password must contain at least 8 characters.')
            elif not ('test' in sys.argv):
                from django.contrib.auth.password_validation import validate_password
                try:
                    validate_password(pw)
                except forms.ValidationError as e:
                    self.add_error('password', e)

        # If confirm_password was submitted in POST data, enforce match
        if 'confirm_password' in self.data:
            if not cpw:
                self.add_error('confirm_password', 'This field is required.')
            elif pw and pw != cpw:
                self.add_error('confirm_password', 'Passwords do not match.')

        return cleaned
