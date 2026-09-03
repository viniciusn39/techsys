from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AIChatSessionViewSet,
    AIInsightViewSet,
    AIIntegrationTestView,
    AIIntegrationView,
)

router = DefaultRouter()
router.register("insights", AIInsightViewSet)
router.register("chat/sessions", AIChatSessionViewSet)

urlpatterns = [
    path("integration/", AIIntegrationView.as_view()),
    path("integration/test/", AIIntegrationTestView.as_view()),
    path("", include(router.urls)),
]
