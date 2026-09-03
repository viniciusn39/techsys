"""API do conector ERP.

Duas famílias de endpoints:

  /api/coletor/*   — usados pelo AGENTE no cliente (auth por X-Coletor-Token,
                     sem JWT, sem sessão). Só conexões de saída do cliente.
  /api/erp/*       — usados pela TELA (JWT, escopo do tenant): conectores,
                     status de sincronização, catálogo de métricas, comandos.
"""
import hashlib
import os

from django.conf import settings
from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsGestorOrAbove, IsGestorStrict, IsRoot, IsTenantAdminStrict
from accounts.tenancy import TenantScopedViewSet

from .coletor import (
    connector_from_token,
    enqueue_command,
    log_comm,
    long_poll_commands,
    new_token,
    record_result,
    register_ingest,
    touch,
)
from .metrics import catalog_payload, compute_metric, get_metric
from .models import AgentCommand, Connector, ConnectorLog, EntitySyncState
from .serializers import (
    AgentCommandSerializer,
    ConnectorLogSerializer,
    ConnectorSerializer,
    EntitySyncStateSerializer,
)
from .sync import map_and_upsert
from .winthor import DEFAULT_SYNC, WINTHOR_QUERIES, oracle_user_script, queries_do_plano

AGENT_FILE = "agente.py"


# --------------------------------------------------------------------------- agente

def _agent_info():
    """(versão, sha256, bytes) do agente publicado no servidor."""
    path = os.path.join(settings.AGENTE_DIR, AGENT_FILE)
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return "", "", b""
    version = ""
    for line in data.decode("utf-8", errors="replace").splitlines():
        if line.startswith("VERSION = "):
            version = line.split('"')[1]
            break
    return version, hashlib.sha256(data).hexdigest(), data


def _coletor(request):
    connector = connector_from_token(request.headers.get("X-Coletor-Token"))
    if connector is not None:
        touch(connector)
    return connector


def _forbidden():
    return Response({"detail": "Token inválido."}, status=status.HTTP_403_FORBIDDEN)


@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def coletor_plan(request):
    connector = _coletor(request)
    if connector is None:
        return _forbidden()
    version, sha256, _ = _agent_info()
    cfg = connector.config or {}
    return Response({
        "interval": int(cfg.get("interval") or 600),
        "queries": queries_do_plano(connector),
        "latest": version,
        "sha256": sha256,
    })


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def coletor_ingest(request):
    connector = _coletor(request)
    if connector is None:
        return _forbidden()
    entity = request.data.get("entity") or ""
    items = request.data.get("items") or []
    fields = (DEFAULT_SYNC.get(entity) or {}).get("fields")
    if not fields:
        # Entidade fora do plano padrão: guardamos crua (ErpRecord) para não perder.
        fields = {"external_id": "EXTERNAL_ID"}
    imported, error = map_and_upsert(connector, entity, items, fields)
    register_ingest(connector, entity, len(items), imported, error)
    log_comm(connector, ConnectorLog.Kind.INGEST, f"{entity}: {imported}/{len(items)}",
             {"entity": entity, "imported": imported, "received": len(items), "error": error})
    return Response({"entity": entity, "imported": imported, "error": error})


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def coletor_heartbeat(request):
    connector = _coletor(request)
    if connector is None:
        return _forbidden()
    health = request.data if isinstance(request.data, dict) else {}
    if health:
        Connector.objects.filter(pk=connector.pk).update(health=health)
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def coletor_error(request):
    connector = _coletor(request)
    if connector is None:
        return _forbidden()
    log_comm(connector, ConnectorLog.Kind.ERROR,
             f"{request.data.get('context', '')}: {str(request.data.get('error', ''))[:200]}",
             {"context": request.data.get("context"), "error": request.data.get("error"),
              "version": request.data.get("version")})
    return Response({"ok": True})


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def coletor_queries(request):
    """Auditoria do que o agente executou no ERP (best effort)."""
    connector = _coletor(request)
    if connector is None:
        return _forbidden()
    items = request.data.get("items") or []
    falhas = [i for i in items if not i.get("ok")]
    log_comm(connector, ConnectorLog.Kind.PLAN, f"ciclo: {len(items)} consultas, {len(falhas)} falha(s)",
             {"items": [{k: v for k, v in i.items() if k != "sql"} for i in items][:40]})
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def coletor_commands(request):
    connector = _coletor(request)
    if connector is None:
        return _forbidden()
    cmds = long_poll_commands(connector)
    return Response([{"id": c.id, "command": c.command, "payload": c.payload} for c in cmds])


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def coletor_command_result(request, pk):
    connector = _coletor(request)
    if connector is None:
        return _forbidden()
    record_result(connector, pk, bool(request.data.get("ok")),
                  request.data.get("result"), str(request.data.get("error") or ""))
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def coletor_agent_code(request):
    connector = connector_from_token(
        request.headers.get("X-Coletor-Token") or request.query_params.get("key")
    )
    if connector is None:
        return _forbidden()
    version, _, data = _agent_info()
    if not data:
        return Response({"detail": "agente.py não publicado no servidor."}, status=404)
    log_comm(connector, ConnectorLog.Kind.UPDATE, f"download do agente v{version}")
    return HttpResponse(data, content_type="text/x-python")


def _public_url(request, connector=None):
    """Endereço que o agente usa para falar com a plataforma."""
    cfg = (connector.config if connector is not None else {}) or {}
    return (cfg.get("public_url") or settings.PUBLIC_URL
            or request.build_absolute_uri("/")).rstrip("/")


def _read_agent_file(name):
    try:
        with open(os.path.join(settings.AGENTE_DIR, name), "rb") as f:
            return f.read().decode("utf-8")
    except OSError:
        return None


@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def coletor_install_script(request, script):
    if script not in ("install.sh", "install.ps1", "uninstall.sh", "uninstall.ps1"):
        return Response(status=404)
    body = _read_agent_file(script)
    if body is None:
        return Response({"detail": "script não publicado."}, status=404)
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def coletor_prefilled_script(request, token, ext):
    """Instalador PRONTO para o cliente: servidor e chave já embutidos.

    O técnico baixa `instalar-<empresa>.sh` (ou .ps1), leva para a máquina e
    roda só com o usuário/senha do Oracle. A chave identifica a empresa; sem
    ela o arquivo não existe (404), então a URL não vaza nada de outro tenant.
    """
    connector = connector_from_token(token)
    if connector is None or ext not in ("sh", "ps1"):
        return _forbidden()
    server = _public_url(request, connector)
    slug = connector.tenant.slug
    if ext == "sh":
        base = _read_agent_file("install.sh")
        if base is None:
            return Response({"detail": "script não publicado."}, status=404)
        # Injeta os defaults logo depois do shebang: os flags --server/--key
        # continuam aceitos e sobrescrevem, mas não são mais obrigatórios.
        header = (
            "#!/usr/bin/env bash\n"
            f"# Instalador pronto — empresa: {connector.tenant.name}\n"
            f"# Uso: sudo bash instalar-{slug}.sh --user TECHSYS --password 'SENHA' [--dsn host:1521/SERVICO]\n"
            f"set -- --server '{server}' --key '{token}' \"$@\"\n"
        )
        body = header + base.split("\n", 1)[1]
        filename = f"instalar-{slug}.sh"
        ctype = "application/x-sh"
    else:
        base = _read_agent_file("install.ps1")
        if base is None:
            return Response({"detail": "script não publicado."}, status=404)
        # PowerShell: troca os parâmetros obrigatórios por defaults com a chave.
        body = base.replace(
            '[Parameter(Mandatory=$true)][string]$Server,', f'[string]$Server = "{server}",'
        ).replace(
            '[Parameter(Mandatory=$true)][string]$Key,', f'[string]$Key = "{token}",'
        )
        body = f"# Instalador pronto — empresa: {connector.tenant.name}\n# Uso: .\\instalar-{slug}.ps1 -User TECHSYS -Password 'SENHA' [-Dsn host:1521/SERVICO]\n" + body
        filename = f"instalar-{slug}.ps1"
        ctype = "text/plain"
    log_comm(connector, ConnectorLog.Kind.UPDATE, f"download do instalador .{ext}")
    resp = HttpResponse(body, content_type=f"{ctype}; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


class InstaladorView(APIView):
    """Instalador remoto (root): escolhe a empresa, garante o conector e devolve
    a chave + comandos + links dos scripts prontos — tudo numa chamada."""

    permission_classes = [IsRoot]

    def get(self, request):
        from accounts.models import Tenant

        tenant_id = request.query_params.get("tenant")
        if not tenant_id:
            raise ValidationError({"tenant": "Informe a empresa."})
        tenant = Tenant.objects.filter(pk=tenant_id, is_active=True).first()
        if tenant is None:
            raise ValidationError({"tenant": "Empresa não encontrada."})

        connector = Connector.objects.filter(tenant=tenant, is_active=True).order_by("id").first()
        if connector is None:
            connector = Connector.objects.create(
                tenant=tenant, name="WinThor", erp=Connector.Erp.WINTHOR,
                perfil=Connector.Perfil.MISTO, ingest_token=new_token(),
            )
            log_comm(connector, ConnectorLog.Kind.PLAN, "conector criado pelo instalador")

        server = _public_url(request, connector)
        token = connector.ingest_token
        version, _, _ = _agent_info()
        return Response({
            "tenant": {"id": tenant.id, "name": tenant.name, "slug": tenant.slug},
            "connector": ConnectorSerializer(connector).data,
            "server": server,
            "token": token,
            "agent_version": version,
            "linux": {
                "oneliner": (
                    f"curl -fsSL {server}/api/coletor/install.sh | sudo bash -s -- "
                    f"--server {server} --key {token} --user TECHSYS --password 'SENHA_DO_ORACLE'"
                ),
                "script_url": f"{server}/api/coletor/instalar/{token}.sh",
                "script_name": f"instalar-{tenant.slug}.sh",
                "run": f"sudo bash instalar-{tenant.slug}.sh --user TECHSYS --password 'SENHA_DO_ORACLE'",
                "check": "techsys-agente status\ntechsys-agente logs",
                "uninstall": f"curl -fsSL {server}/api/coletor/uninstall.sh | sudo bash",
            },
            "windows": {
                "script_url": f"{server}/api/coletor/instalar/{token}.ps1",
                "script_name": f"instalar-{tenant.slug}.ps1",
                "run": (
                    f"powershell -ExecutionPolicy Bypass -File .\\instalar-{tenant.slug}.ps1 "
                    f"-User TECHSYS -Password 'SENHA_DO_ORACLE'"
                ),
                "check": f"python C:\\ProgramData\\techsys-agente\\agente.py --status",
                "uninstall": f"powershell -ExecutionPolicy Bypass -c \"iwr {server}/api/coletor/uninstall.ps1 -OutFile u.ps1; .\\u.ps1\"",
            },
            "dba_script": oracle_user_script(),
            "entities": [q["entity"] for q in queries_do_plano(connector)],
        })

    def post(self, request):
        """Gera nova chave para a empresa (o agente instalado precisa ser reinstalado)."""
        from accounts.models import Tenant

        tenant = Tenant.objects.filter(pk=request.data.get("tenant")).first()
        connector = Connector.objects.filter(tenant=tenant, is_active=True).order_by("id").first() if tenant else None
        if connector is None:
            raise ValidationError({"tenant": "Empresa sem conector."})
        connector.ingest_token = new_token()
        connector.save(update_fields=["ingest_token"])
        log_comm(connector, ConnectorLog.Kind.PLAN, "chave rotacionada pelo instalador")
        return Response({"token": connector.ingest_token})


# --------------------------------------------------------------------------- tela

class ConnectorViewSet(TenantScopedViewSet):
    queryset = Connector.objects.all()
    serializer_class = ConnectorSerializer
    # Só admin do tenant vê o conector: aqui estão a chave e os dados brutos da carga.
    permission_classes = [IsTenantAdminStrict]
    pagination_class = None

    def perform_create(self, serializer):
        tenant = self.get_tenant()
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        serializer.save(tenant=tenant, ingest_token=new_token())

    @action(detail=True, methods=["post"], url_path="rotate-token")
    def rotate_token(self, request, pk=None):
        connector = self.get_object()
        connector.ingest_token = new_token()
        connector.save(update_fields=["ingest_token"])
        return Response(ConnectorSerializer(connector).data)

    @action(detail=True, methods=["get"])
    def install(self, request, pk=None):
        """Comando de instalação pronto + script do DBA."""
        connector = self.get_object()
        base = request.build_absolute_uri("/").rstrip("/")
        public = (connector.config or {}).get("public_url") or settings.PUBLIC_URL or base
        token = connector.ingest_token
        return Response({
            "server": public,
            "token": token,
            "linux": (
                f"curl -fsSL {public}/api/coletor/install.sh | sudo bash -s -- "
                f"--server {public} --key {token} --user TECHSYS --password 'SENHA_DO_ORACLE'"
            ),
            "windows": (
                f"powershell -ExecutionPolicy Bypass -c \"iwr {public}/api/coletor/install.ps1 -OutFile install.ps1; "
                f".\\install.ps1 -Server {public} -Key {token} -User TECHSYS -Password 'SENHA_DO_ORACLE'\""
            ),
            "dba_script": oracle_user_script(),
            "entities": [q["entity"] for q in queries_do_plano(connector)],
        })

    @action(detail=True, methods=["get"], url_path="status")
    def sync_status(self, request, pk=None):
        connector = self.get_object()
        planned = [q["entity"] for q in queries_do_plano(connector)]
        states = {s.entity: s for s in EntitySyncState.objects.filter(connector=connector)}
        rows = []
        for entity in planned:
            s = states.get(entity)
            rows.append({
                "entity": entity,
                **(EntitySyncStateSerializer(s).data if s else {
                    "last_ingest_at": None, "rows_received": 0, "rows_imported": 0,
                    "total_imported": 0, "last_error": "",
                }),
            })
        logs = ConnectorLog.objects.filter(connector=connector).order_by("-created_at")[:30]
        commands = AgentCommand.objects.filter(connector=connector).order_by("-created_at")[:10]
        return Response({
            "connector": ConnectorSerializer(connector).data,
            "entities": rows,
            "logs": ConnectorLogSerializer(logs, many=True).data,
            "commands": AgentCommandSerializer(commands, many=True).data,
        })

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        """Progressão da carga: registros por minuto (por entidade) + estado do agente.

        Alimenta a tela ao vivo. A série vem dos logs de ingest (cada lote grava
        `imported`); o avanço da carga gradual (janela em meses) e a marca d'água
        vêm do heartbeat do agente (health.progresso).
        """
        from collections import defaultdict
        from datetime import timedelta

        from django.utils import timezone

        connector = self.get_object()
        minutos = min(int(request.query_params.get("minutos") or 120), 24 * 60)
        desde = timezone.now() - timedelta(minutes=minutos)

        logs = ConnectorLog.objects.filter(
            connector=connector, kind=ConnectorLog.Kind.INGEST, created_at__gte=desde,
        ).only("created_at", "data")
        por_minuto = defaultdict(lambda: defaultdict(int))
        totais = defaultdict(int)
        for log in logs:
            entity = (log.data or {}).get("entity") or "?"
            n = int((log.data or {}).get("imported") or 0)
            minuto = timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M")
            por_minuto[minuto][entity] += n
            totais[entity] += n

        entidades = sorted(totais, key=lambda e: -totais[e])
        serie = [
            {"minuto": m, **{e: por_minuto[m].get(e, 0) for e in entidades}}
            for m in sorted(por_minuto)
        ]

        planned = [q["entity"] for q in queries_do_plano(connector)]
        states = {s.entity: s for s in EntitySyncState.objects.filter(connector=connector)}
        progresso_agente = (connector.health or {}).get("progresso") or {}
        por_entidade_agente = progresso_agente.get("entidades") or {}
        plano = {q["entity"]: q for q in WINTHOR_QUERIES}
        rows = []
        for entity in planned:
            s = states.get(entity)
            ag = por_entidade_agente.get(entity) or {}
            alvo = int(plano.get(entity, {}).get("backfill_meses") or 0)
            passe = ag.get("passe") or {}
            esperado = passe.get("esperado")
            lidos = int(passe.get("lidos") or 0)
            # 0–100 % do passe atual/último: quanto do que o ERP tem para esta
            # entidade já chegou. Sem contagem: 100 % se o passe terminou bem.
            janela = ag.get("janela")
            if esperado:
                pct = min(100.0, lidos * 100.0 / esperado)
            elif passe and not passe.get("em_andamento") and passe.get("ok"):
                pct = 100.0
            elif passe:
                pct = 0.0
            elif s and s.total_imported > 0:
                # Sincronizada por um agente que ainda não informa o passe: o que
                # está no espelho é o passe concluído. Com carga gradual, o
                # avanço é a janela; sem a janela informada, não se sabe.
                if alvo:
                    pct = min(100.0, janela * 100.0 / alvo) if janela else None
                else:
                    pct = 100.0
            else:
                pct = None
            rows.append({
                "esperado": esperado,
                "lidos": lidos,
                "importados_passe": int(passe.get("importados") or 0),
                "em_andamento": bool(passe.get("em_andamento")),
                "passe_ok": passe.get("ok"),
                "pct": pct,
                "entity": entity,
                "last_ingest_at": s.last_ingest_at if s else None,
                "rows_received": s.rows_received if s else 0,
                "rows_imported": s.rows_imported if s else 0,
                "total_imported": s.total_imported if s else 0,
                "last_error": s.last_error if s else "",
                "ultimos_min": totais.get(entity, 0),
                "marca": ag.get("marca"),
                "janela": ag.get("janela"),
                "janela_alvo": alvo or None,
                "incremental": bool(plano.get(entity, {}).get("incremental")),
                "cadencia_min": plano.get(entity, {}).get("every_minutes"),
            })

        return Response({
            "connector": ConnectorSerializer(connector).data,
            "coletando": bool(progresso_agente.get("coletando")),
            "minutos": minutos,
            "serie": serie,
            "entidades_serie": entidades,
            "entities": rows,
            "total_geral": sum(r["total_imported"] for r in rows),
            "total_periodo": sum(totais.values()),
        })

    @action(detail=True, methods=["post"])
    def command(self, request, pk=None):
        """Enfileira um comando para o agente (só os de leitura/diagnóstico)."""
        connector = self.get_object()
        command = request.data.get("command")
        if command not in ("ping", "validar_schema", "coletar", "reset_state", "descobrir_oracle", "reiniciar"):
            raise ValidationError({"command": "Comando não permitido."})
        cmd = enqueue_command(connector, command, request.data.get("payload") or {})
        log_comm(connector, ConnectorLog.Kind.COMMAND, f"enfileirado: {command}", {"id": cmd.id})
        return Response(AgentCommandSerializer(cmd).data, status=201)

    @action(detail=True, methods=["post"], url_path="recalcular")
    def recalcular(self, request, pk=None):
        from .tasks import calcular_indicadores_erp

        from .tasks import sincronizar_metas_erp

        connector = self.get_object()
        meses = int(request.data.get("meses") or 12)
        sincronizar_metas_erp.delay(tenant_id=connector.tenant_id, meses=meses)
        calcular_indicadores_erp.delay(tenant_id=connector.tenant_id, meses=meses)
        return Response({"queued": True})


class MetricCatalogView(APIView):
    def get(self, request):
        return Response(catalog_payload())


class TargetCatalogView(APIView):
    """Fontes de meta do ERP (PCMETA, cadastro do RCA) que um indicador pode usar."""

    def get(self, request):
        from .targets import catalogo_payload

        return Response(catalogo_payload())


class PainelErpView(APIView):
    """Mini BI do espelho do ERP + conferência dos indicadores ligados a ele."""

    permission_classes = [IsGestorStrict]

    def get(self, request):
        from accounts.tenancy import get_request_tenant

        from .bi import painel

        tenant = get_request_tenant(request)
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        from datetime import date

        try:
            meses = max(1, min(int(request.query_params.get("meses", 12)), 36))
        except ValueError:
            raise ValidationError({"meses": "Inteiro entre 1 e 36."})
        branch = request.query_params.get("branch") or None
        ate = None
        raw = request.query_params.get("ate")
        if raw:
            try:
                ate = date.fromisoformat(raw if len(raw) > 7 else f"{raw}-01").replace(day=1)
            except ValueError:
                raise ValidationError({"ate": "Use AAAA-MM."})
        return Response(painel(tenant, meses=meses, branch=branch, ate=ate))


class MetricPreviewView(APIView):
    """Calcula uma métrica agora, sem gravar — para o gestor conferir antes de vincular."""

    permission_classes = [IsGestorOrAbove]

    def get(self, request):
        from datetime import date

        from accounts.tenancy import get_request_tenant

        tenant = get_request_tenant(request)
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        key = request.query_params.get("metric")
        if get_metric(key) is None:
            raise ValidationError({"metric": "Métrica desconhecida."})
        raw = request.query_params.get("period")
        period = date.fromisoformat(raw) if raw else date.today()
        filters = {}
        if request.query_params.get("branch"):
            codes = [c.strip() for c in request.query_params["branch"].split(",") if c.strip()]
            filters["branch"] = codes[0] if len(codes) == 1 else codes
        value = compute_metric(key, tenant, period, filters)
        return Response({"metric": key, "period": period.replace(day=1), "value": value})
