from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AttachmentViewSet

router = DefaultRouter()
router.register("anexos", AttachmentViewSet)

urlpatterns = [path("", include(router.urls))]
