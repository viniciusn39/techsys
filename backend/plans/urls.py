from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ActionItemViewSet, ActionPlanViewSet, DeviationViewSet

router = DefaultRouter()
router.register("deviations", DeviationViewSet)
router.register("action-plans", ActionPlanViewSet)
router.register("action-items", ActionItemViewSet)

urlpatterns = [path("", include(router.urls))]
