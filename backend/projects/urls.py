from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ActivityFcaViewSet, ProjectActivityViewSet, ProjectViewSet

router = DefaultRouter()
router.register("projects", ProjectViewSet)
router.register("project-activities", ProjectActivityViewSet)
router.register("project-fcas", ActivityFcaViewSet)

urlpatterns = [path("", include(router.urls))]
