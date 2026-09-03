from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from erp.urls import coletor_urls


def health(_request):
    return JsonResponse({"status": "ok", "app": "techsys-gestao"})


urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/health/", health),
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/", include("accounts.urls")),
    path("api/", include("strategy.urls")),
    path("api/", include("indicators.urls")),
    path("api/", include("plans.urls")),
    path("api/ai/", include("ai.urls")),
    path("api/erp/", include("erp.urls")),
    path("api/coletor/", include(coletor_urls)),
]
