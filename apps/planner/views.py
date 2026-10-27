from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import FirebaseAuthentication

from .serializers import (
    SubtaskSerializer,
    SubtaskWriteSerializer,
    TaskListQuerySerializer,
    TaskSerializer,
    TaskWriteSerializer,
)
from .services import (
    create_subtask,
    create_task,
    delete_subtask,
    delete_task,
    list_tasks,
    update_subtask,
    update_task,
)


class TaskPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class TaskListEndpoint(ListAPIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = TaskSerializer
    pagination_class = TaskPagination
    http_method_names = ("get", "post", "head", "options")
    parser_classes = (JSONParser,)

    def get_queryset(self):
        query = TaskListQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return list_tasks(user=self.request.user, filters=query.validated_data)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def post(self, request):
        serializer = TaskWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = create_task(user=request.user, data=serializer.validated_data)
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)


class TaskDetailEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)
    http_method_names = ("patch", "delete", "options")

    def patch(self, request, task_id):
        serializer = TaskWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        task = update_task(user=request.user, task_id=task_id, data=serializer.validated_data)
        return Response(TaskSerializer(task).data)

    def delete(self, request, task_id):
        delete_task(user=request.user, task_id=task_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class SubtaskCreateEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)
    http_method_names = ("post", "options")

    def post(self, request, task_id):
        serializer = SubtaskWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subtask = create_subtask(user=request.user, task_id=task_id, data=serializer.validated_data)
        return Response(SubtaskSerializer(subtask).data, status=status.HTTP_201_CREATED)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class SubtaskDetailEndpoint(APIView):
    authentication_classes = (FirebaseAuthentication,)
    permission_classes = (IsAuthenticated,)
    parser_classes = (JSONParser,)
    http_method_names = ("patch", "delete", "options")

    def patch(self, request, task_id, subtask_id):
        serializer = SubtaskWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        subtask = update_subtask(
            user=request.user,
            task_id=task_id,
            subtask_id=subtask_id,
            data=serializer.validated_data,
        )
        return Response(SubtaskSerializer(subtask).data)

    def delete(self, request, task_id, subtask_id):
        delete_subtask(user=request.user, task_id=task_id, subtask_id=subtask_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response
