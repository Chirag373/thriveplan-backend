from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.mail import MailDeliveryError, send_password_reset_email

from .authentication import FirebaseAuthentication, FirebaseProvider
from .serializers import (
    ForgotPasswordSerializer,
    NotificationPreferencesSerializer,
    NotificationPreferencesUpdateSerializer,
    PreferencesSerializer,
    PreferencesUpdateSerializer,
    ProfileUpdateSerializer,
    SignInSerializer,
    SignUpSerializer,
    UserSerializer,
)
from .services import (
    get_notification_preferences,
    login_user,
    signup_user,
    update_notification_preferences,
    update_preferences,
    update_profile,
)


class SignUpAuthEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    parser_classes = (JSONParser,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "signup"

    def get_authenticate_header(self, request):
        return "Bearer"

    def post(self, request):
        identity = FirebaseProvider(request=request).authenticate()
        serializer = SignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, created = signup_user(identity=identity, **serializer.validated_data)
        return Response(
            {
                "user": UserSerializer(user).data,
                "created": created,
                "next_step": "home" if user.preferences.onboarding_completed else "preferences",
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SignInAuthEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    parser_classes = (JSONParser,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "login"

    def get_authenticate_header(self, request):
        return "Bearer"

    def post(self, request):
        identity = FirebaseProvider(request=request).authenticate()
        serializer = SignInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = login_user(identity=identity)
        return Response(
            {
                "user": UserSerializer(user).data,
                "next_step": "home" if user.preferences.onboarding_completed else "preferences",
            }
        )


class ForgotPasswordAuthEndpoint(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    parser_classes = (JSONParser,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "forgot_password"

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            send_password_reset_email(**serializer.validated_data)
        except MailDeliveryError:
            raise EmailUnavailable() from None
        return Response(
            {"detail": "If an eligible account exists, you will receive a password reset email."}
        )


class MeEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "patch", "head", "options")
    parser_classes = (JSONParser,)

    def get(self, request):
        user_data = UserSerializer(request.user).data
        response = Response(
            {
                "user": user_data,
                "next_step": "home" if user_data["onboarding_completed"] else "preferences",
            }
        )
        response["Cache-Control"] = "private, no-store"
        return response

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = update_profile(user=request.user, changes=serializer.validated_data)
        user_data = UserSerializer(user).data
        response = Response(
            {
                "user": user_data,
                "next_step": "home" if user_data["onboarding_completed"] else "preferences",
            }
        )
        response["Cache-Control"] = "private, no-store"
        return response


class PreferencesEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)
    http_method_names = ("patch", "options")

    def patch(self, request):
        serializer = PreferencesUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preferences = update_preferences(user=request.user, changes=serializer.validated_data)
        response = Response(
            {
                "preferences": PreferencesSerializer(preferences).data,
                "next_step": "home" if preferences.onboarding_completed else "preferences",
            }
        )
        response["Cache-Control"] = "private, no-store"
        return response


class EmailUnavailable(APIException):
    status_code = 503
    default_detail = "Email service is temporarily unavailable."
    default_code = "email_unavailable"


class NotificationPreferencesEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)
    http_method_names = ("get", "patch", "head", "options")

    def get(self, request):
        preferences = get_notification_preferences(user=request.user)
        return Response(NotificationPreferencesSerializer(preferences).data)

    def patch(self, request):
        serializer = NotificationPreferencesUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preferences = update_notification_preferences(
            user=request.user, changes=serializer.validated_data
        )
        return Response(NotificationPreferencesSerializer(preferences).data)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response
