from django import forms

from .models import AccountApplication, User


class AccountApplicationForm(forms.ModelForm):

    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control'
            }
        )
    )

    class Meta:

        model = AccountApplication

        fields = [
            'enrollment_number',
            'full_name',
            'phone_number',
            'gender',
            'password',
        ]

        widgets = {

            'enrollment_number':
                forms.TextInput(
                    attrs={
                        'class': 'form-control'
                    }
                ),

            'full_name':
                forms.TextInput(
                    attrs={
                        'class': 'form-control'
                    }
                ),

            'phone_number':
                forms.TextInput(
                    attrs={
                        'class': 'form-control'
                    }
                ),

            'gender':
                forms.Select(
                    attrs={
                        'class': 'form-select'
                    }
                ),
        }

    def clean_enrollment_number(self):

        enrollment_number = (
            self.cleaned_data['enrollment_number']
            .strip()
            .upper()
        )

        validator = User._meta.get_field(
            'enrollment_number'
        ).validators[0]

        validator(enrollment_number)

        if User.objects.filter(
            enrollment_number=enrollment_number
        ).exists():

            raise forms.ValidationError(
                'Account already exists.'
            )

        if AccountApplication.objects.filter(
            enrollment_number=enrollment_number,
            approved=False
        ).exists():

            raise forms.ValidationError(
                'An application is already pending for this enrollment number.'
            )

        return enrollment_number

    def clean_phone_number(self):

        phone_number = self.cleaned_data['phone_number'].strip()

        if not phone_number.replace('+', '', 1).isdigit():

            raise forms.ValidationError(
                'Enter a valid phone number.'
            )

        if len(phone_number) < 10:

            raise forms.ValidationError(
                'Phone number is too short.'
            )

        return phone_number
