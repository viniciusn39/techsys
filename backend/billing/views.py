from datetime import date

from django.db.models import Sum
from django.http import FileResponse
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import Tenant, User
from accounts.permissions import role_at_least
from accounts.tenancy import get_request_tenant

from .models import Invoice


class InvoiceSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    overdue = serializers.BooleanField(read_only=True)
    has_file = serializers.SerializerMethodField()
    tenant = serializers.PrimaryKeyRelatedField(queryset=Tenant.objects.all(), required=False)

    class Meta:
        model = Invoice
        fields = ["id", "tenant", "tenant_name", "number", "description", "reference", "amount", "due_date", "status", "status_label",
                  "overdue", "paid_at", "payment_url", "notes", "has_file", "created_at"]
        read_only_fields = ["created_at"]

    def get_has_file(self, obj):
        return bool(obj.file)

    def validate(self, data):
        status = data.get("status", getattr(self.instance, "status", None))
        if status == Invoice.Status.PAGA and not data.get("paid_at", getattr(self.instance, "paid_at", None)):
            data["paid_at"] = date.today()
        if status != Invoice.Status.PAGA:
            data["paid_at"] = None
        return data


class InvoiceViewSet(viewsets.ModelViewSet):
    """Empresa (admin): lê as próprias faturas. Root: lança, altera e exclui as de qualquer empresa (?tenant=)."""

    queryset = Invoice.objects.select_related("tenant")
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_permissions(self):
        # Escrever é só do root, e isso é decidido antes de validar o corpo da requisição.
        from rest_framework.permissions import SAFE_METHODS

        from accounts.permissions import IsRoot

        return [IsAuthenticated()] if self.request.method in SAFE_METHODS else [IsRoot()]

    def _root(self):
        return self.request.user.role == User.Role.ROOT

    def get_queryset(self):
        qs = self.queryset
        tenant = get_request_tenant(self.request)
        if self._root() and tenant is None:
            t = self.request.query_params.get("tenant", "")
            return qs.filter(tenant_id=t) if t.isdigit() else qs
        if tenant is None or not role_at_least(self.request, User.Role.ADMIN):
            return qs.none()
        qs = qs.filter(tenant=tenant)
        if self.request.query_params.get("status") in Invoice.Status.values:
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def _so_root(self):
        if not self._root():
            raise PermissionDenied("Só o administrador da plataforma lança faturas.")

    def perform_create(self, serializer):
        self._so_root()
        tenant = serializer.validated_data.get("tenant") or get_request_tenant(self.request)
        if tenant is None:
            raise PermissionDenied("Escolha a empresa da fatura.")
        serializer.save(tenant=tenant, file=self.request.FILES.get("file"))

    def perform_update(self, serializer):
        self._so_root()
        extra = {"file": self.request.FILES["file"]} if "file" in self.request.FILES else {}
        serializer.save(tenant=serializer.instance.tenant, **extra)

    def perform_destroy(self, instance):
        self._so_root()
        arquivo = instance.file
        instance.delete()
        if arquivo:
            arquivo.delete(save=False)

    @action(detail=False, methods=["get"])
    def resumo(self, request):
        qs = self.get_queryset()
        hoje = date.today()
        abertas = qs.filter(status=Invoice.Status.ABERTA)
        return Response({
            "total": qs.exclude(status=Invoice.Status.CANCELADA).aggregate(s=Sum("amount"))["s"] or 0,
            "em_aberto": abertas.aggregate(s=Sum("amount"))["s"] or 0,
            "pagas": qs.filter(status=Invoice.Status.PAGA).count(),
            "abertas": abertas.filter(due_date__gte=hoje).count(),
            "atrasadas": abertas.filter(due_date__lt=hoje).count(),
        })

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        fatura = self.get_object()
        if not fatura.file:
            raise NotFound("Esta fatura não tem arquivo.")
        nome = f"fatura-{fatura.number}{fatura.file.name[fatura.file.name.rfind('.'):]}"
        resposta = FileResponse(fatura.file.open("rb"), as_attachment=True, filename=nome)
        resposta["X-Content-Type-Options"] = "nosniff"
        return resposta
