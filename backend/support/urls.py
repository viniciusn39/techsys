from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ServidorView, TicketViewSet

router = DefaultRouter()
router.register("tickets", TicketViewSet)

urlpatterns = [path("root/servidor/", ServidorView.as_view()), path("", include(router.urls))]
