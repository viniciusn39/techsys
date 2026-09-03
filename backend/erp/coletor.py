"""Serviços do lado da plataforma para o agente (coletor).

O agente roda no cliente e fala com a plataforma só por conexões de SAÍDA,
autenticado por token opaco (Connector.ingest_token) no header X-Coletor-Token.
"""
import logging
import secrets
import time

from django.db import transaction
from django.utils import timezone

from .models import AgentCommand, Connector, ConnectorLog, EntitySyncState

log = logging.getLogger("coletor")

LONGPOLL_TIMEOUT = 25.0
LONGPOLL_INTERVAL = 1.0


def new_token() -> str:
    return secrets.token_urlsafe(36)


def connector_from_token(token):
    token = (token or "").strip()
    if not token:
        return None
    return Connector.objects.select_related("tenant").filter(ingest_token=token, is_active=True).first()


def log_comm(connector, kind, summary, data=None):
    try:
        ConnectorLog.objects.create(
            tenant=connector.tenant, connector=connector, kind=kind,
            summary=str(summary)[:240], data=data or {},
        )
    except Exception:  # noqa: BLE001 — log nunca derruba a comunicação
        pass
    log.info("coletor[%s] conn=%s %s", kind, connector.id, summary)


def touch(connector):
    Connector.objects.filter(pk=connector.pk).update(last_seen_at=timezone.now())


def register_ingest(connector, entity, received, imported, error):
    state, _ = EntitySyncState.objects.get_or_create(
        tenant=connector.tenant, connector=connector, entity=entity
    )
    state.last_ingest_at = timezone.now()
    state.rows_received = received
    state.rows_imported = imported
    state.total_imported = (state.total_imported or 0) + imported
    state.last_error = error or ""
    state.save()


def enqueue_command(connector, command, payload=None):
    return AgentCommand.objects.create(
        tenant=connector.tenant, connector=connector, command=command, payload=payload or {}
    )


def lease_pending(connector, limit=20):
    with transaction.atomic():
        pendentes = list(
            AgentCommand.objects.select_for_update(skip_locked=True)
            .filter(connector=connector, status=AgentCommand.Status.PENDING)
            .order_by("created_at")[:limit]
        )
        if pendentes:
            AgentCommand.objects.filter(id__in=[c.id for c in pendentes]).update(
                status=AgentCommand.Status.SENT, leased_at=timezone.now()
            )
    return pendentes


def long_poll_commands(connector, _sleep=time.sleep):
    deadline = time.monotonic() + LONGPOLL_TIMEOUT
    while True:
        cmds = lease_pending(connector)
        if cmds or time.monotonic() >= deadline:
            return cmds
        _sleep(LONGPOLL_INTERVAL)


def record_result(connector, command_id, ok, result=None, error=""):
    cmd = AgentCommand.objects.filter(pk=command_id, connector=connector).first()
    if cmd is None:
        return None
    cmd.status = AgentCommand.Status.DONE if ok else AgentCommand.Status.ERROR
    cmd.result = result or {}
    cmd.error = error or ""
    cmd.finished_at = timezone.now()
    cmd.save(update_fields=["status", "result", "error", "finished_at"])
    log_comm(connector, ConnectorLog.Kind.RESULT, f"{cmd.command}: {'ok' if ok else 'erro'}",
             {"command": cmd.command, "ok": ok, "error": error[:300]})
    return cmd
