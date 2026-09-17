from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from .models import Tenant, User


def get_request_tenant(request):
    """Resolve o tenant da requisição.

    Usuário comum: o próprio tenant ou, via header X-Tenant-Id, outra empresa a que
    ele esteja vinculado. Root: pode assumir um tenant via
    header X-Tenant-Id (seletor de empresa no frontend); sem header, None.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    if user.role == User.Role.ROOT:
        tenant_id = request.headers.get("X-Tenant-Id")
        if tenant_id:
            return Tenant.objects.filter(id=tenant_id, is_active=True).first()
        return None
    # Usuário de várias empresas escolhe em qual está atuando pelo mesmo header —
    # mas só entre as empresas a que ele pertence; qualquer outra coisa cai na de origem.
    tenant_id = request.headers.get("X-Tenant-Id")
    if tenant_id and str(user.tenant_id) != str(tenant_id):
        outra = Tenant.objects.filter(id=tenant_id, is_active=True, memberships__user=user).first() if str(tenant_id).isdigit() else None
        if outra is not None:
            return outra
    return user.tenant


class TenantScopedViewSet(viewsets.ModelViewSet):
    """Escopo multi-tenant explícito: filtra e injeta tenant em tudo."""

    def get_tenant(self):
        return get_request_tenant(self.request)

    def get_queryset(self):
        tenant = self.get_tenant()
        if tenant is None:
            return self.queryset.none()
        return self.queryset.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = self.get_tenant()
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        serializer.save(tenant=tenant)


# Caminhos até o tenant para modelos que não têm o campo direto (filhos de mapa, projeto, board…).
_CAMINHOS_ATE_O_TENANT = (
    "tenant_id", "map.tenant_id", "project.tenant_id", "board.tenant_id", "plan.tenant_id",
    "perspective.map.tenant_id", "activity.project.tenant_id", "task.board.tenant_id", "indicator.tenant_id",
)


def _tenant_id_de(obj):
    for caminho in _CAMINHOS_ATE_O_TENANT:
        alvo = obj
        try:
            for parte in caminho.split("."):
                alvo = getattr(alvo, parte)
        except AttributeError:
            continue
        return alvo
    return None


class SoDaEmpresaMixin:
    """Todo objeto que o cliente manda por id (FK ou lista) tem de ser da empresa em uso.

    Vale para criar E para alterar — é no PATCH que um id de outra empresa costuma passar
    despercebido, e o nome do objeto voltaria na resposta. Usuário vale se pertence à empresa
    (de origem ou vinculado). Objetos sem dono (ex.: modelos globais do catálogo) passam.
    """

    def validate(self, data):
        data = super().validate(data)
        tenant = self.context.get("tenant")
        if tenant is None and self.context.get("request") is not None:
            tenant = get_request_tenant(self.context["request"])
        if tenant is None:
            return data
        from rest_framework import serializers

        for campo, valor in data.items():
            for obj in (valor if isinstance(valor, (list, tuple)) else [valor]):
                if isinstance(obj, User):
                    ok = obj.belongs_to(tenant)
                elif hasattr(obj, "_meta"):
                    dono = _tenant_id_de(obj)
                    ok = dono is None or dono == tenant.id
                else:
                    continue
                if not ok:
                    raise serializers.ValidationError({campo: "Registro de outra empresa."})
        return data
