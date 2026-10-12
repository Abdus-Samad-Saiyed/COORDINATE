"""Forms for the coordinate app."""

from django import forms

from .models import RideMessage, RideRequest, RideReview


class RideRequestForm(forms.ModelForm):
    """Form for creating a new ride."""

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
            'route': forms.Select(attrs={'class': 'form-select', 'id': 'id_route'}),
            'custom_from_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'From location',
            }),
            'custom_to_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'To location',
            }),
            'visibility': forms.Select(attrs={'class': 'form-select'}),
            'departure_time': forms.DateTimeInput(
                attrs={'class': 'form-control', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
            'total_spots': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 2,
                'max': 6,
                'placeholder': '2–6',
            }),
        }

    def clean_total_spots(self):
        spots = self.cleaned_data.get('total_spots')
        if spots is not None and (spots < 2 or spots > 6):
            raise forms.ValidationError('Total spots must be between 2 and 6.')
        return spots

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('route') == 'CUSTOM':
            if not cleaned.get('custom_from_location'):
                self.add_error('custom_from_location', 'Required for custom routes.')
            if not cleaned.get('custom_to_location'):
                self.add_error('custom_to_location', 'Required for custom routes.')
        return cleaned


class RideMessageForm(forms.ModelForm):
    """Inline form for sending a chat message (fallback for non-WebSocket)."""

    class Meta:
        model = RideMessage
        fields = ['content']
        widgets = {
            'content': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Type a message…',
                'autocomplete': 'off',
            }),
        }


class RideReviewForm(forms.ModelForm):
    """Post-ride review form."""

    class Meta:
        model = RideReview
        fields = ['rating', 'complaint']
        widgets = {
            'rating': forms.RadioSelect(),
            'complaint': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional: describe any issue with this participant.',
            }),
        }
