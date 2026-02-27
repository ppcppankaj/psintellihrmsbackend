from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User
from apps.core.models import Organization

class CustomUserCreationForm(UserCreationForm):
    """
    Custom user creation form for User model.
    Uses email as the primary identifier instead of username.
    Explicitly uses forms.CharField to avoid TypeError in UsernameField.
    """
    email = forms.EmailField(required=True)
    username = forms.CharField(required=False, help_text="Legacy username (optional)")
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
        required=False,
        label="Organization",
        help_text="Optional: Assign user to an organization"
    )

    class Meta:
        model = User
        fields = ('email', 'username', 'first_name', 'last_name', 'is_org_admin', 'is_staff', 'is_verified')
        field_classes = {
            'email': forms.EmailField,
            'username': forms.CharField,
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        organization = self.cleaned_data.get('organization')
        if organization:
            user.organization = organization
        if commit:
            user.save()
        return user

class CustomUserChangeForm(UserChangeForm):
    """
    Custom user change form for User model.
    """
    username = forms.CharField(required=False, help_text="Legacy username (optional)")

    class Meta:
        model = User
        fields = '__all__'
        field_classes = {
            'username': forms.CharField,
        }
