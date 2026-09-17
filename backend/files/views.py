import os

from django.http import FileResponse
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from accounts.models import User
from accounts.permissions import role_at_least
from accounts.tenancy import get_request_tenant

from .models import Attachment
from .targets import EXTENSOES_BLOQUEADAS, TAMANHO_MAXIMO, alvo_existe


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ["id", "kind", "object_id", "name", "size", "content_type", "uploaded_by", "uploaded_by_name", "created_at"]
        read_only_fields = ["name", "size", "content_type", "uploaded_by", "created_at"]

    def get_uploaded_by_name(self, obj):
        u = obj.uploaded_by
        return (u.get_full_name() or u.first_name or u.email) if u else ""


class AttachmentViewSet(viewsets.ModelViewSet):
    """/api/anexos/?kind=kanban_task&object_id=12 — listar, enviar (multipart: file), baixar e excluir."""

    queryset = Attachment.objects.select_related("uploaded_by")
    serializer_class = AttachmentSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filterset_fields = ["kind", "object_id"]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        tenant = get_request_tenant(self.request)
        return self.queryset.filter(tenant=tenant) if tenant else self.queryset.none()

    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request)
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        arquivo = self.request.FILES.get("file")
        if arquivo is None:
            raise ValidationError({"file": "Envie o arquivo."})
        if arquivo.size > TAMANHO_MAXIMO:
            raise ValidationError({"file": "Arquivo acima de 20 MB."})
        if os.path.splitext(arquivo.name)[1].lower() in EXTENSOES_BLOQUEADAS:
            raise ValidationError({"file": "Tipo de arquivo não permitido."})
        dados = serializer.validated_data
        if not alvo_existe(dados["kind"], dados["object_id"], tenant):
            raise ValidationError({"object_id": "Registro não encontrado nesta empresa."})
        serializer.save(tenant=tenant, file=arquivo, name=os.path.basename(arquivo.name)[:200], size=arquivo.size,
                        content_type=(arquivo.content_type or "")[:120], uploaded_by=self.request.user)

    def perform_destroy(self, instance):
        if instance.uploaded_by_id != self.request.user.id and not role_at_least(self.request, User.Role.GESTOR):
            raise PermissionDenied("Só quem enviou o arquivo (ou um gestor) pode excluí-lo.")
        instance.delete()

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        anexo = self.get_object()
        resposta = FileResponse(anexo.file.open("rb"), as_attachment=True, filename=anexo.name)
        resposta["X-Content-Type-Options"] = "nosniff"
        return resposta
