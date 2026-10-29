from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.authentication import FirebaseAuthentication

from .serializers import (
    DeviceRegistrationSerializer,
    DeviceSerializer,
    MarkReadSerializer,
    NotificationQuerySerializer,
    NotificationSerializer,
    ReadAllSerializer,
)
from .services import (
    list_notifications,
    mark_all_read,
    mark_read,
    register_device,
    unregister_device,
)


class PrivateNotificationMixin:
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class NotificationListEndpoint(PrivateNotificationMixin, ListAPIView):
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination
    http_method_names = ("get", "head", "options")

    def get_queryset(self):
        query = NotificationQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return list_notifications(user=self.request.user, filters=query.validated_data)


class NotificationReadEndpoint(PrivateNotificationMixin, APIView):
    http_method_names = ("patch", "options")

    def patch(self, request, notification_id):
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notification = mark_read(user=request.user, notification_id=notification_id)
        return Response(NotificationSerializer(notification).data)


class NotificationReadAllEndpoint(PrivateNotificationMixin, APIView):
    http_method_names = ("post", "options")

    def post(self, request):
        serializer = ReadAllSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"updated": mark_all_read(user=request.user)})


class DeviceRegistrationEndpoint(PrivateNotificationMixin, APIView):
    http_method_names = ("post", "options")
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "device_registration"

    def post(self, request):
        serializer = DeviceRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device, created = register_device(user=request.user, **serializer.validated_data)
        return Response(
            DeviceSerializer(device).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class DeviceUnregisterEndpoint(PrivateNotificationMixin, APIView):
    http_method_names = ("delete", "options")

    def delete(self, request, device_id):
        unregister_device(user=request.user, device_id=device_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
