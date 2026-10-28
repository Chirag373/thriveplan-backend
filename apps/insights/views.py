from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import FirebaseAuthentication

from .serializers import ProductivityQuerySerializer, SummaryQuerySerializer
from .services import get_productivity, get_summary


class InsightsSummaryEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "head", "options")

    def get(self, request):
        query = SummaryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(get_summary(user=request.user, filters=query.validated_data))

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class ProductivityEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "head", "options")

    def get(self, request):
        query = ProductivityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(get_productivity(user=request.user, filters=query.validated_data))

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response
