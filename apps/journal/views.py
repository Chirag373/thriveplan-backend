from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import FirebaseAuthentication

from .serializers import (
    JournalEntrySerializer,
    JournalEntryWriteSerializer,
    JournalQuerySerializer,
    JournalTemplateSerializer,
)
from .services import create_entry, delete_entry, list_entries, list_templates, update_entry


class JournalPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class JournalEntryListEndpoint(ListAPIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)
    serializer_class = JournalEntrySerializer
    pagination_class = JournalPagination
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        query = JournalQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return list_entries(user=self.request.user, filters=query.validated_data)

    def post(self, request):
        serializer = JournalEntryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = create_entry(user=request.user, data=serializer.validated_data)
        return Response(JournalEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class JournalEntryDetailEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)
    http_method_names = ("patch", "delete", "options")

    def patch(self, request, entry_id):
        serializer = JournalEntryWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        entry = update_entry(user=request.user, entry_id=entry_id, data=serializer.validated_data)
        return Response(JournalEntrySerializer(entry).data)

    def delete(self, request, entry_id):
        delete_entry(user=request.user, entry_id=entry_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class JournalTemplateListEndpoint(ListAPIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = JournalTemplateSerializer
    pagination_class = None
    http_method_names = ("get", "head", "options")

    def get_queryset(self):
        return list_templates()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class JournalTemplateDetailEndpoint(RetrieveAPIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = JournalTemplateSerializer
    lookup_url_kwarg = "template_id"
    http_method_names = ("get", "head", "options")

    def get_queryset(self):
        return list_templates()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response
