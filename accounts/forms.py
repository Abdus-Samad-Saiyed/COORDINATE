"""Forms for the accounts app."""

from django import forms

from .models import AccountApplication, User


class AccountApplicationForm(forms.ModelForm):
    """Public form for prospective students to apply for a verified account."""

    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Choose a password'}),
    )
    confirm_password = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repeat your password'}),
    )

    class Meta:
        model = AccountApplication
        fields = ['enrollment_number', 'full_name', 'phone_number', 'gender']
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

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get('password')
        cpw = cleaned.get('confirm_password')
        if pw and cpw and pw != cpw:
            self.add_error('confirm_password', 'Passwords do not match.')
        return cleaned
