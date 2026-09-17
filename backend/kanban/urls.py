from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BoardViewSet, TaskMessageViewSet, TaskViewSet

router = DefaultRouter()
router.register("kanban-boards", BoardViewSet)
router.register("kanban-tasks", TaskViewSet)
router.register("kanban-mensagens", TaskMessageViewSet)

urlpatterns = [path("", include(router.urls))]
