from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DashboardSummaryView,
    DataSourceViewSet,
    IndicatorValueBulkView,
    IndicatorViewSet,
)

router = DefaultRouter()
router.register("data-sources", DataSourceViewSet)
router.register("indicators", IndicatorViewSet)

urlpatterns = [
    path("indicator-values/bulk/", IndicatorValueBulkView.as_view()),
    path("dashboard/summary/", DashboardSummaryView.as_view()),
    path("", include(router.urls)),
]
