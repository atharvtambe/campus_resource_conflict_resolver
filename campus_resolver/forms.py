from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .permissions import ROLE_STUDENT, ROLE_FACULTY, ensure_default_groups

User = get_user_model()


class UserRegistrationForm(forms.ModelForm):
    """
    Registration form with server-side duplicate checking, role selection,
    and Django password hasher integration.
    """
    ROLE_CHOICES = [
        (ROLE_STUDENT, 'Student'),
        (ROLE_FACULTY, 'Faculty Member'),
    ]

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        initial=ROLE_STUDENT,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select your campus role for access permissions."
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter strong password'}),
        help_text="Must contain at least 8 characters and not be too common."
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Re-enter your password'})
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. jdoe'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'e.g. jdoe@campus.edu'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            raise ValidationError("Username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("A user with that username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise ValidationError("Email address is required.")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email address already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', "Passwords do not match.")
            else:
                # Validate password with Django password validators
                temp_user = User(
                    username=cleaned_data.get('username'),
                    email=cleaned_data.get('email'),
                    first_name=cleaned_data.get('first_name'),
                    last_name=cleaned_data.get('last_name')
                )
                try:
                    validate_password(password, user=temp_user)
                except ValidationError as e:
                    self.add_error('password', e)

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
            ensure_default_groups()
            selected_role = self.cleaned_data.get('role', ROLE_STUDENT)
            group, _ = Group.objects.get_or_create(name=selected_role)
            user.groups.add(group)
        return user


class BootstrapLoginForm(AuthenticationForm):
    """
    Login form styled with Bootstrap 5 input classes and error handling.
    """
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your username',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
        })
    )
