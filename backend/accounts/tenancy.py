from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from .models import Tenant, User


def get_request_tenant(request):
    """Resolve o tenant da requisição.

    Usuário comum: sempre o próprio tenant. Root: pode assumir um tenant via
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
