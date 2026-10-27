from django.urls import path

from .views import (
    ForgotPasswordAuthEndpoint,
    MeEndpoint,
    PreferencesEndpoint,
    SignInAuthEndpoint,
    SignUpAuthEndpoint,
)

urlpatterns = [
    path("me/preferences/", PreferencesEndpoint.as_view(), name="preferences"),
    path("me/", MeEndpoint.as_view(), name="me"),
    path("forgot-password/", ForgotPasswordAuthEndpoint.as_view(), name="forgot-password"),
    path("signup/", SignUpAuthEndpoint.as_view(), name="signup"),
    path("login/", SignInAuthEndpoint.as_view(), name="login"),
]
