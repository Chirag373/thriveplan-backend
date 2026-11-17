from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import FirebaseAuthentication

from .game_validation import public_games
from .serializers import (
    ActivityCompletionSerializer,
    ActivitySessionSerializer,
    RewardsSummaryQuerySerializer,
)
from .services import (
    complete_activity_session,
    get_rewards_summary,
    session_data,
    start_activity_session,
)


class RewardsEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class RewardsSummaryEndpoint(RewardsEndpoint):
    http_method_names = ("get", "head", "options")

    def get(self, request):
        query = RewardsSummaryQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(get_rewards_summary(user=request.user, filters=query.validated_data))


class ActivitySessionEndpoint(RewardsEndpoint):
    http_method_names = ("post", "options")

    def post(self, request, activity):
        body = ActivitySessionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        session, created = start_activity_session(
            user=request.user,
            activity=activity,
            data=body.validated_data,
        )
        return Response(session_data(session), status=201 if created else 200)


class ActivityCompletionEndpoint(RewardsEndpoint):
    http_method_names = ("post", "options")

    def post(self, request, activity, session_id):
        body = ActivityCompletionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        return Response(
            complete_activity_session(
                user=request.user,
                activity=activity,
                session_id=session_id,
                data=body.validated_data,
            )
        )


class GameCatalogEndpoint(RewardsEndpoint):
    http_method_names = ("get", "head", "options")

    def get(self, request, activity):
        return Response({"results": public_games(activity)})
