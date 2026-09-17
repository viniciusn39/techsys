from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MODULOS, SETORES, AccessProfile, OrgUnit, Tenant, User, seed_access_profiles
from .permissions import IsRoot, IsTenantAdmin
from .serializers import AccessProfileSerializer, EmpresaSerializer, MeSerializer, OrgUnitSerializer, TenantSerializer, UserSerializer
from .tenancy import TenantScopedViewSet, get_request_tenant


class MeView(APIView):
    def get(self, request):
        data = MeSerializer(request.user).data
        tenant = get_request_tenant(request)
        data["acting_tenant"] = TenantSerializer(tenant).data if tenant else None
        user = request.user
        data["tenants"] = [] if user.role == User.Role.ROOT else [{"id": t.id, "name": t.name} for t in user.empresas()]
        # Perfil de acesso é da empresa de origem; nas vinculadas vale só o papel.
        if tenant is not None and user.tenant_id != tenant.id:
            data["modules"] = None
            data["sectors"] = None
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

    @action(detail=True, methods=["get"])
    def armazenamento(self, request, pk=None):
        """Disco ocupado pelos dados da empresa, por tabela e no total."""
        return Response({"tenant": pk, **armazenamento_do_tenant(self.get_object())})


class UserViewSet(TenantScopedViewSet):
    queryset = User.objects.select_related("org_unit")
    serializer_class = UserSerializer
    permission_classes = [IsTenantAdmin]
    search_fields = ["first_name", "last_name", "email"]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    def get_queryset(self):
        """Quem é da empresa e quem foi vinculado a ela vindo de outra."""
        from django.db.models import Q

        tenant = self.get_tenant()
        if tenant is None:
            return self.queryset.none()
        return self.queryset.filter(Q(tenant=tenant) | Q(extra_tenants=tenant)).distinct()

    def _so_da_casa(self, instance):
        if instance.tenant_id != self.get_tenant().id:
            raise PermissionDenied("Usuário vinculado: o cadastro é mantido na empresa de origem. Aqui só dá para desvincular.")

    def perform_update(self, serializer):
        self._so_da_casa(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise PermissionDenied("Você não pode excluir a si mesmo.")
        self._so_da_casa(instance)
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=False, methods=["post"])
    def vincular(self, request):
        """Dá acesso a esta empresa para alguém que já tem cadastro em outra (pelo e-mail)."""
        tenant = self.get_tenant()
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        email = (request.data.get("email") or "").strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).exclude(role=User.Role.ROOT).first()
        if user is None:
            return Response({"detail": "Nenhum usuário ativo com esse e-mail. Cadastre-o como novo usuário."}, status=404)
        if user.belongs_to(tenant):
            return Response({"detail": "Esse usuário já faz parte desta empresa."}, status=400)
        user.extra_tenants.add(tenant)
        return Response(UserSerializer(user, context=self.get_serializer_context()).data, status=201)

    @action(detail=True, methods=["post"])
    def desvincular(self, request, pk=None):
        user = self.get_object()
        tenant = self.get_tenant()
        if user.tenant_id == tenant.id:
            return Response({"detail": "Esta é a empresa de origem do usuário; desative-o em vez de desvincular."}, status=400)
        user.extra_tenants.remove(tenant)
        return Response(status=204)


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


class AccessProfileViewSet(TenantScopedViewSet):
    """Perfis de acesso por setor da empresa (admin edita; todos podem listar para escolher)."""

    queryset = AccessProfile.objects.all()
    serializer_class = AccessProfileSerializer
    permission_classes = [IsTenantAdmin]
    pagination_class = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    def perform_destroy(self, instance):
        if instance.is_system:
            raise PermissionDenied("Perfil padrão não pode ser excluído; ajuste os setores e módulos.")
        instance.users.update(access_profile=None)
        instance.delete()

    @action(detail=False, methods=["get"])
    def opcoes(self, request):
        return Response({
            "setores": [{"key": k, "label": v} for k, v in SETORES],
            "modulos": [{"key": k, "label": v} for k, v in MODULOS],
        })

    @action(detail=False, methods=["post"])
    def padrao(self, request):
        """Recria os perfis padrão que faltarem."""
        tenant = self.get_tenant()
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        return Response({"criados": seed_access_profiles(tenant)})


def armazenamento_do_tenant(tenant):
    """Quanto de disco os dados de uma empresa ocupam, tabela a tabela (estimativa).

    Tamanho em disco da tabela (dados + índices, pg_total_relation_size) rateado
    pela fração de linhas que pertencem à empresa. Só tabelas com coluna tenant.
    """
    from django.apps import apps
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("""SELECT relname, pg_total_relation_size(relid), greatest(n_live_tup, 1)
                       FROM pg_stat_user_tables""")
        fisico = {r[0]: (int(r[1]), int(r[2])) for r in cur.fetchall()}

    linhas = []
    for model in apps.get_models():
        campos = {f.name: f for f in model._meta.get_fields() if getattr(f, "concrete", False)}
        if "tenant" not in campos or model._meta.abstract or model._meta.proxy:
            continue
        tabela = model._meta.db_table
        tamanho, total = fisico.get(tabela, (0, 1))
        n = model.objects.filter(tenant=tenant).count()
        if n == 0:
            continue
        # A estimativa do Postgres (n_live_tup) pode estar abaixo da contagem real logo após carga grande.
        fracao = min(1.0, n / max(total, n))
        linhas.append({
            "tabela": tabela, "modelo": model._meta.verbose_name.title() if model._meta.verbose_name else model.__name__,
            "app": model._meta.app_label, "linhas": n, "bytes": int(tamanho * fracao), "tabela_bytes": tamanho,
        })
    linhas.sort(key=lambda r: -r["bytes"])
    return {"total_bytes": sum(r["bytes"] for r in linhas), "total_linhas": sum(r["linhas"] for r in linhas), "tabelas": linhas}


class EmpresaView(APIView):
    """Dados cadastrais da empresa em uso: todos leem, só o admin altera."""

    permission_classes = [IsTenantAdmin]

    def _tenant(self, request):
        tenant = get_request_tenant(request)
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        return tenant

    def get(self, request):
        return Response(EmpresaSerializer(self._tenant(request)).data)

    def patch(self, request):
        ser = EmpresaSerializer(self._tenant(request), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class EmpresasView(APIView):
    """As empresas do próprio cliente: lista as dele e deixa o admin abrir outra (grupo econômico)."""

    def get(self, request):
        user = request.user
        if user.role == User.Role.ROOT:
            return Response(EmpresaSerializer(Tenant.objects.all(), many=True).data)
        return Response(EmpresaSerializer(user.empresas(), many=True).data)

    def post(self, request):
        from django.utils.text import slugify

        from strategy.provisioning import bootstrap_tenant

        user = request.user
        if user.role not in (User.Role.ADMIN, User.Role.ROOT):
            raise PermissionDenied("Só o administrador abre uma nova empresa.")
        ser = EmpresaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        base = slugify(ser.validated_data["name"])[:40] or "empresa"
        slug, n = base, 2
        while Tenant.objects.filter(slug=slug).exists():
            slug, n = f"{base}-{n}", n + 1
        tenant = ser.save(slug=slug)
        bootstrap_tenant(tenant)
        seed_access_profiles(tenant)
        if user.role != User.Role.ROOT:
            user.extra_tenants.add(tenant)
        return Response(EmpresaSerializer(tenant).data, status=201)
