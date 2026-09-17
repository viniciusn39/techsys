from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AccessProfileViewSet, EmpresasView, EmpresaView, MeView, OrgUnitViewSet, TenantViewSet, UserViewSet

router = DefaultRouter()
router.register("tenants", TenantViewSet)
router.register("users", UserViewSet)
router.register("org-units", OrgUnitViewSet)
router.register("access-profiles", AccessProfileViewSet)

urlpatterns = [
    path("auth/me/", MeView.as_view()),
    path("empresa/", EmpresaView.as_view()),
    path("empresas/", EmpresasView.as_view()),
    path("", include(router.urls)),
]
