from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordChangeDoneView
from django.contrib import messages
from django.urls import reverse_lazy
from .forms import UserRegistrationForm, BootstrapLoginForm


def register_view(request):
    """
    User registration view with role selection and password hashing.
    Redirects to dashboard immediately after auto-login.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Log in automatically upon registration
            login(request, user)
            messages.success(
                request,
                f"Welcome to Campus Resource Conflict Resolver, {user.username}! Your account has been created."
            )
            return redirect('dashboard')
        else:
            messages.error(request, "Please correct the errors in the registration form below.")
    else:
        form = UserRegistrationForm()

    return render(request, 'registration/register.html', {'form': form})


class CampusLoginView(LoginView):
    """
    Login view using styled Bootstrap form and session authentication.
    """
    form_class = BootstrapLoginForm
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        remember_user = form.get_user()
        messages.success(self.request, f"Welcome back, {remember_user.username}!")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Invalid username or password. Please try again.")
        return super().form_invalid(form)


def logout_view(request):
    """
    Logout view that safely terminates the session and redirects to login.
    """
    if request.user.is_authenticated:
        username = request.user.username
        logout(request)
        messages.info(request, f"Goodbye, {username}. You have been securely logged out.")
    return redirect('login')


class CampusPasswordChangeView(PasswordChangeView):
    """
    Allows authenticated users to change their password securely.
    """
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('password_change_done')

    def form_valid(self, form):
        messages.success(self.request, "Your password was successfully updated!")
        return super().form_valid(form)


class CampusPasswordChangeDoneView(PasswordChangeDoneView):
    """
    Confirmation view after password change.
    """
    template_name = 'registration/password_change_done.html'
