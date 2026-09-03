from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("connectors", views.ConnectorViewSet)

# Endpoints do agente (token) — montados em /api/coletor/
coletor_urls = [
    path("plan/", views.coletor_plan),
    path("ingest/", views.coletor_ingest),
    path("heartbeat/", views.coletor_heartbeat),
    path("error/", views.coletor_error),
    path("queries/", views.coletor_queries),
    path("commands/", views.coletor_commands),
    path("commands/<int:pk>/result/", views.coletor_command_result),
    path("agente.py", views.coletor_agent_code),
    # Instalador pronto (chave embutida): /api/coletor/instalar/<chave>.sh | .ps1
    path("instalar/<str:token>.<str:ext>", views.coletor_prefilled_script),
    path("<str:script>", views.coletor_install_script),
]

# Endpoints da tela (JWT) — montados em /api/erp/
urlpatterns = [
    path("instalador/", views.InstaladorView.as_view()),
    path("painel/", views.PainelErpView.as_view()),
    path("metrics/", views.MetricCatalogView.as_view()),
    path("targets/", views.TargetCatalogView.as_view()),
    path("metrics/preview/", views.MetricPreviewView.as_view()),
    path("", include(router.urls)),
]
