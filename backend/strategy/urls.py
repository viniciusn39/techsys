from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import GoalViewSet, PerspectiveViewSet, StrategicMapViewSet, StrategicObjectiveViewSet

router = DefaultRouter()
router.register("strategic-maps", StrategicMapViewSet)
router.register("perspectives", PerspectiveViewSet)
router.register("objectives", StrategicObjectiveViewSet)
router.register("goals", GoalViewSet)

urlpatterns = [path("", include(router.urls))]
