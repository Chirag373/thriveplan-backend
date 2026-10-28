from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import FirebaseAuthentication

from .serializers import (
    DailyQuerySerializer,
    FavoriteCreateSerializer,
    FavoriteQuerySerializer,
    FavoriteSerializer,
    WellnessContentSerializer,
)
from .services import delete_favorite, get_daily_content, list_favorites, save_favorite


class DailyWellnessEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "head", "options")

    def get(self, request):
        query = DailyQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        date = params.get("date") or timezone.localdate(timezone=ZoneInfo(params["timezone"]))
        content = get_daily_content(date=date)
        payload = {"date": date.isoformat(), "timezone": params["timezone"]}
        for kind, item in content.items():
            if kind == "books":
                payload[kind] = WellnessContentSerializer(item, many=True).data
            else:
                payload[kind] = WellnessContentSerializer(item).data if item else None
        return Response(payload)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class FavoritePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class FavoriteListEndpoint(ListAPIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)
    serializer_class = FavoriteSerializer
    pagination_class = FavoritePagination
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        query = FavoriteQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return list_favorites(user=self.request.user, filters=query.validated_data)

    def post(self, request):
        serializer = FavoriteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        favorite, created = save_favorite(user=request.user, **serializer.validated_data)
        return Response(
            FavoriteSerializer(favorite).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class FavoriteDetailEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    http_method_names = ("delete", "options")

    def delete(self, request, favorite_id):
        delete_favorite(user=request.user, favorite_id=favorite_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response
