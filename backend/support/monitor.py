"""Leitura de saúde do servidor da plataforma: host (via /proc), Postgres, Redis, Celery e contadores da aplicação."""
import os
import shutil
import time

from django.conf import settings
from django.db import connection


def _proc(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def cpu_percent(intervalo=0.4):
    """Uso de CPU do host (os contêineres compartilham o kernel) medido em `intervalo` s."""
    def ler():
        linha = _proc("/proc/stat").splitlines()[0].split()
        if len(linha) < 5 or linha[0] != "cpu":
            return None
        vals = [int(x) for x in linha[1:]]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        return idle, sum(vals)
    a = ler()
    if a is None:
        return None
    time.sleep(intervalo)
    b = ler()
    if b is None or b[1] == a[1]:
        return None
    return round(100 * (1 - (b[0] - a[0]) / (b[1] - a[1])), 1)


def memoria():
    info = {}
    for linha in _proc("/proc/meminfo").splitlines():
        partes = linha.split()
        if len(partes) >= 2 and partes[0].rstrip(":") in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
            info[partes[0].rstrip(":")] = int(partes[1]) * 1024
    if "MemTotal" not in info:
        return None
    total, disp = info["MemTotal"], info.get("MemAvailable", 0)
    return {
        "total": total, "usado": total - disp, "disponivel": disp,
        "pct": round(100 * (total - disp) / total, 1) if total else None,
        "swap_total": info.get("SwapTotal", 0), "swap_usado": info.get("SwapTotal", 0) - info.get("SwapFree", 0),
    }


def disco(caminho="/"):
    try:
        u = shutil.disk_usage(caminho)
    except OSError:
        return None
    return {"caminho": caminho, "total": u.total, "usado": u.used, "livre": u.free, "pct": round(100 * u.used / u.total, 1) if u.total else None}


def load():
    partes = _proc("/proc/loadavg").split()
    if len(partes) < 3:
        return None
    return {"m1": float(partes[0]), "m5": float(partes[1]), "m15": float(partes[2]), "cpus": os.cpu_count() or 1}


def uptime():
    partes = _proc("/proc/uptime").split()
    return int(float(partes[0])) if partes else None


def postgres():
    out = {}
    with connection.cursor() as cur:
        cur.execute("SELECT pg_database_size(current_database()), version()")
        tam, versao = cur.fetchone()
        out["tamanho"] = int(tam)
        out["versao"] = versao.split(",")[0]
        cur.execute("SELECT count(*), count(*) FILTER (WHERE state = 'active') FROM pg_stat_activity WHERE datname = current_database()")
        out["conexoes"], out["conexoes_ativas"] = cur.fetchone()
        cur.execute("SELECT setting::int FROM pg_settings WHERE name = 'max_connections'")
        out["max_conexoes"] = cur.fetchone()[0]
        cur.execute("""SELECT CASE WHEN blks_hit + blks_read = 0 THEN NULL ELSE round(100.0 * blks_hit / (blks_hit + blks_read), 1) END
                       FROM pg_stat_database WHERE datname = current_database()""")
        out["cache_hit_pct"] = float(cur.fetchone()[0] or 0)
        cur.execute("""SELECT relname, n_live_tup, n_dead_tup, pg_total_relation_size(relid), last_autovacuum, last_autoanalyze
                       FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 25""")
        out["tabelas"] = [
            {"tabela": r[0], "linhas": int(r[1] or 0), "mortas": int(r[2] or 0), "tamanho": int(r[3] or 0),
             "autovacuum": r[4], "autoanalyze": r[5]}
            for r in cur.fetchall()
        ]
        cur.execute("""SELECT coalesce(sum(pg_total_relation_size(relid)), 0) FROM pg_stat_user_tables""")
        out["tamanho_tabelas"] = int(cur.fetchone()[0])
    return out


def redis_info():
    try:
        import redis

        r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2)
        info = r.info()
        filas = {}
        for fila in ("celery",):
            try:
                filas[fila] = int(r.llen(fila))
            except Exception:  # noqa: BLE001
                filas[fila] = None
        return {
            "ok": True, "versao": info.get("redis_version"), "memoria": int(info.get("used_memory", 0)),
            "memoria_pico": int(info.get("used_memory_peak", 0)), "clientes": int(info.get("connected_clients", 0)),
            "chaves": sum(int(v.get("keys", 0)) for k, v in info.items() if k.startswith("db") and isinstance(v, dict)),
            "uptime": int(info.get("uptime_in_seconds", 0)), "filas": filas,
            "hits": int(info.get("keyspace_hits", 0)), "misses": int(info.get("keyspace_misses", 0)),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erro": str(exc)[:120]}


def celery_info():
    """Workers vivos e tarefas em execução (inspect com timeout curto)."""
    try:
        from core.celery import app

        insp = app.control.inspect(timeout=1.5)
        ativos = insp.active() or {}
        reservadas = insp.reserved() or {}
        return {
            "ok": True, "workers": sorted(ativos.keys()),
            "em_execucao": sum(len(v) for v in ativos.values()),
            "reservadas": sum(len(v) for v in reservadas.values()),
            "tarefas": [{"worker": w, "nome": t.get("name"), "inicio": t.get("time_start")} for w, ts in ativos.items() for t in ts][:20],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erro": str(exc)[:120]}


def aplicacao():
    from accounts.models import Tenant, User
    from erp.models import Connector
    from erp.sync import ENTITY_MODELS
    from indicators.models import Indicator, IndicatorValue

    from .models import Ticket

    espelho = 0
    vistos = set()
    for model in ENTITY_MODELS.values():
        if model in vistos:
            continue
        vistos.add(model)
        espelho += model.objects.count()
    conectores = Connector.objects.filter(is_active=True)
    return {
        "empresas": Tenant.objects.filter(is_active=True).count(),
        "usuarios": User.objects.filter(is_active=True).count(),
        "indicadores": Indicator.objects.filter(is_active=True).count(),
        "valores": IndicatorValue.objects.count(),
        "linhas_espelho": espelho,
        "conectores": conectores.count(),
        "agentes_online": sum(1 for c in conectores if c.online),
        "chamados_abertos": Ticket.objects.exclude(status__in=["resolvido", "fechado"]).count(),
    }


def amostra_rapida():
    """Números leves para guardar a cada 5 min (histórico)."""
    m = memoria() or {}
    d = disco() or {}
    l = load() or {}
    with connection.cursor() as cur:
        cur.execute("SELECT pg_database_size(current_database())")
        db = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        conexoes = int(cur.fetchone()[0])
    return {
        "cpu_pct": cpu_percent(), "mem_pct": m.get("pct"), "mem_usada": m.get("usado"),
        "disco_pct": d.get("pct"), "disco_usado": d.get("usado"), "load_m1": l.get("m1"),
        "db_bytes": db, "db_conexoes": conexoes,
    }
