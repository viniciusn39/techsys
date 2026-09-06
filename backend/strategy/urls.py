from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CanvasItemViewSet, MeetingViewSet, StakeholderViewSet, SwotItemViewSet, SwotStrategyViewSet, GoalViewSet, PerspectiveViewSet, StrategicMapViewSet, StrategicObjectiveViewSet

router = DefaultRouter()
router.register("strategic-maps", StrategicMapViewSet)
router.register("perspectives", PerspectiveViewSet)
router.register("objectives", StrategicObjectiveViewSet)
router.register("goals", GoalViewSet)
router.register("swot", SwotItemViewSet)
router.register("swot-estrategias", SwotStrategyViewSet)
router.register("canvas", CanvasItemViewSet)
router.register("stakeholders", StakeholderViewSet)
router.register("meetings", MeetingViewSet)

urlpatterns = [path("", include(router.urls))]
