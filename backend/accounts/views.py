from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import OrgUnit, Tenant, User
from .permissions import IsRoot, IsTenantAdmin
from .serializers import MeSerializer, OrgUnitSerializer, TenantSerializer, UserSerializer
from .tenancy import TenantScopedViewSet, get_request_tenant


class MeView(APIView):
    def get(self, request):
        data = MeSerializer(request.user).data
        tenant = get_request_tenant(request)
        data["acting_tenant"] = TenantSerializer(tenant).data if tenant else None
        return Response(data)


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [IsRoot]
    # Sem DELETE: todo dado de negócio aponta para o tenant com on_delete=PROTECT,
    # então a exclusão estouraria. Desativar é a operação correta e reversível.
    http_method_names = ["get", "post", "patch", "put", "head", "options"]

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        tenant = self.get_object()
        tenant.is_active = not tenant.is_active
        tenant.save(update_fields=["is_active"])
        return Response(TenantSerializer(tenant).data)


class UserViewSet(TenantScopedViewSet):
    queryset = User.objects.select_related("org_unit")
    serializer_class = UserSerializer
    permission_classes = [IsTenantAdmin]
    search_fields = ["first_name", "last_name", "email"]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise PermissionDenied("Você não pode excluir a si mesmo.")
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class OrgUnitViewSet(TenantScopedViewSet):
    queryset = OrgUnit.objects.select_related("manager", "parent")
    serializer_class = OrgUnitSerializer
    permission_classes = [IsTenantAdmin]
    pagination_class = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    @action(detail=False, methods=["get"])
    def tree(self, request):
        units = list(self.get_queryset())
        by_parent = {}
        for u in units:
            by_parent.setdefault(u.parent_id, []).append(u)

        def build(parent_id):
            return [
                {**OrgUnitSerializer(u).data, "children": build(u.id)}
                for u in by_parent.get(parent_id, [])
            ]

        return Response(build(None))
