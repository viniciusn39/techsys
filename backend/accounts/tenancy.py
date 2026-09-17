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
        outra = user.extra_tenants.filter(id=tenant_id, is_active=True).first() if str(tenant_id).isdigit() else None
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
