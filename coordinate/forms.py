from django import forms
from django.utils import timezone

from .models import (
    RideRequest,
    RideReview,
    RideMessage
)


class RideRequestForm(forms.ModelForm):

    departure_time = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={
                'type': 'datetime-local',
                'class': 'form-control'
            }
        )
    )

    class Meta:

        model = RideRequest

        fields = [

            'route',

            'custom_from_location',

            'custom_to_location',

            'visibility',

            'departure_time',

            'total_spots',
        ]

        widgets = {

            'route':
                forms.Select(
                    attrs={
                        'class': 'form-select'
                    }
                ),

            'custom_from_location':
                forms.TextInput(
                    attrs={
                        'class': 'form-control'
                    }
                ),

            'custom_to_location':
                forms.TextInput(
                    attrs={
                        'class': 'form-control'
                    }
                ),

            'visibility':
                forms.Select(
                    attrs={
                        'class': 'form-select'
                    }
                ),

            'total_spots':
                forms.NumberInput(
                    attrs={
                        'class': 'form-control'
                    }
                ),
        }

    def clean_total_spots(self):

        total_spots = self.cleaned_data['total_spots']

        if total_spots < 1:

            raise forms.ValidationError(
                'Total spots must be at least 1.'
            )

        return total_spots

    def clean_departure_time(self):

        departure_time = self.cleaned_data['departure_time']

        if departure_time <= timezone.now():

            raise forms.ValidationError(
                'Departure time must be in the future.'
            )

        return departure_time

    def clean(self):

        cleaned_data = super().clean()

        route = cleaned_data.get('route')
        custom_from = cleaned_data.get('custom_from_location', '').strip()
        custom_to = cleaned_data.get('custom_to_location', '').strip()

        if route == 'CUSTOM':

            if not custom_from:

                self.add_error(
                    'custom_from_location',
                    'Custom origin is required.'
                )

            if not custom_to:

                self.add_error(
                    'custom_to_location',
                    'Custom destination is required.'
                )

        else:

            cleaned_data['custom_from_location'] = ''
            cleaned_data['custom_to_location'] = ''

        return cleaned_data


class RideReviewForm(forms.ModelForm):

    class Meta:

        model = RideReview

        fields = [
            'rating',
            'complaint'
        ]

        widgets = {

            'rating':
                forms.Select(
                    attrs={
                        'class': 'form-select'
                    }
                ),

            'complaint':
                forms.Textarea(
                    attrs={
                        'class': 'form-control',
                        'rows': 4
                    }
                ),
        }


class RideMessageForm(forms.ModelForm):

    class Meta:

        model = RideMessage

        fields = [
            'content'
        ]

        widgets = {
            'content':
                forms.Textarea(
                    attrs={
                        'class': 'form-control',
                        'rows': 3,
                        'maxlength': 1000,
                        'placeholder': 'Message your ride group'
                    }
                ),
        }
