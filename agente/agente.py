#!/usr/bin/env python3
"""Agente TechSys (coletor WinThor) — roda na rede do CLIENTE, junto ao Oracle do ERP.

Arquivo ÚNICO, só stdlib + driver Oracle (oracledb OU cx_Oracle). Instalado pelo
install.sh (Linux/systemd) ou install.ps1 (Windows/Task Scheduler) com a chave
gerada na tela de Integrações da plataforma. Toda comunicação é de SAÍDA (HTTPS):

  GET  {server}/api/coletor/plan/           plano de coleta (queries, intervalo, versão)
  POST {server}/api/coletor/ingest/         sobe os dados coletados (lote por entidade)
  POST {server}/api/coletor/queries/        auditoria do que rodou no ERP
  POST {server}/api/coletor/heartbeat/      saúde do host + conexão Oracle
  GET  {server}/api/coletor/commands/       long-poll de tarefas de diagnóstico
  POST {server}/api/coletor/commands/<id>/result/
  GET  {server}/api/coletor/agente.py       código novo (auto-update)

Segurança:
  - SOMENTE LEITURA no ERP: não existe caminho de escrita neste agente.
  - config.json local (chmod 600 — tem a senha do banco).
  - Auto-update só por HTTPS, validado por sha256 anunciado no /plan/.

Modos:
  agente.py --service              # loop (o que o serviço roda) — padrão
  agente.py --once                 # um ciclo de coleta e sai (teste)
  agente.py --apply --server URL --key CHAVE [--dsn H:P/SVC --user U --password S]
            [--name NOME --interval SEG --schema DONO]
  agente.py --discover | --status | --version
"""
import glob
import hashlib
import json
import os
import platform
import re
import socket
import ssl
import sys
import threading
import time
import traceback
import urllib.request

VERSION = "1.0.2"  # BUMP ao publicar: os agentes instalados se auto-atualizam

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else HERE
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
CRASH_PATH = os.path.join(BASE_DIR, "crash.log")
LOG_PATH = os.path.join(BASE_DIR, "agent.log")

BUSY = threading.Event()      # coleta em andamento -> adia o auto-update
STOP = threading.Event()


# --------------------------------------------------------------------------- config/estado
def load_config():
    try:
        cfg = json.load(open(CONFIG_PATH))
    except Exception:
        cfg = {}
    cfg.setdefault("server", "")
    cfg.setdefault("key", "")
    cfg.setdefault("name", platform.node())
    cfg.setdefault("interval", 600)
    cfg.setdefault("oracle", {})
    return cfg


def save_config(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_PATH)
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except Exception:
        pass


def load_state():
    try:
        return json.load(open(STATE_PATH))
    except Exception:
        return {}


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)


def _arg(flag, default=""):
    argv = sys.argv
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def _crash(text):
    try:
        with open(CRASH_PATH, "a") as f:
            f.write("[%s]\n%s\n" % (time.strftime("%F %T"), text))
    except Exception:
        pass
    print(text, file=sys.stderr)


def _log(msg):
    print("[%s] %s" % (time.strftime("%F %T"), msg), flush=True)


# --------------------------------------------------------------------------- descoberta do Oracle
def _ler(caminho):
    try:
        with open(caminho, "r", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def _hosts_locais():
    """IPs por onde o listener pode escutar — o do WinThor costuma ser o da LAN, não o loopback."""
    hosts = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        hosts.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        nome = socket.gethostname()
        hosts.append(nome)
        for info in socket.getaddrinfo(nome, None, socket.AF_INET):
            hosts.append(info[4][0])
    except Exception:
        pass
    hosts += ["127.0.0.1", "localhost"]
    return list(dict.fromkeys(h for h in hosts if h))


def _dirs_rede_oracle():
    dirs = []
    if os.environ.get("TNS_ADMIN"):
        dirs.append(os.environ["TNS_ADMIN"])
    if os.environ.get("ORACLE_HOME"):
        dirs.append(os.path.join(os.environ["ORACLE_HOME"], "network", "admin"))
    for linha in _ler("/etc/oratab").splitlines():
        partes = linha.strip().split(":")
        if len(partes) >= 2 and partes[1] and not linha.strip().startswith("#"):
            dirs.append(os.path.join(partes[1], "network", "admin"))
    for padrao in ("/u01/app/oracle/product/*/*/network/admin",
                   "/opt/oracle/product/*/*/network/admin",
                   "/oracle/product/*/*/network/admin"):
        dirs += glob.glob(padrao)
    return [d for d in dict.fromkeys(dirs) if os.path.isdir(d)]


def _servicos_e_portas():
    servicos, portas = [], []
    for linha in _ler("/etc/oratab").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and ":" in linha:
            servicos.append(linha.split(":")[0])
    for d in _dirs_rede_oracle():
        for arq in ("tnsnames.ora", "listener.ora"):
            txt = _ler(os.path.join(d, arq))
            servicos += re.findall(r"(?:SERVICE_NAME|SID_NAME|GLOBAL_DBNAME)\s*=\s*([A-Za-z0-9_.\-]+)", txt, re.I)
            portas += re.findall(r"PORT\s*=\s*(\d+)", txt)
    servicos += ["WINT", "WINTHOR", "ORCL", "XE"]
    portas += ["1521"]
    return list(dict.fromkeys(servicos)), list(dict.fromkeys(portas))


def _porta_aberta(host, porta, timeout=1.0):
    try:
        with socket.create_connection((host, int(porta)), timeout=timeout):
            return True
    except Exception:
        return False


def descobrir_dsn(cfg, log=_log):
    """Acha o DSN do Oracle nesta máquina: oratab/tnsnames/listener + IPs locais + conexão real."""
    ora = cfg.get("oracle") or {}
    if not ora.get("user"):
        return None
    drivers = _drivers()
    if not drivers:
        return None
    servicos, portas = _servicos_e_portas()
    hosts = _hosts_locais()
    log("[descoberta] hosts=%s portas=%s servicos=%s" % (hosts, portas, servicos[:6]))
    tentativas = 0
    for porta in portas:
        for host in hosts:
            if not _porta_aberta(host, porta):
                continue
            log("[descoberta] listener respondeu em %s:%s" % (host, porta))
            for servico in servicos:
                # O nome pode ser SERVICE NAME (host:porta/nome) ou SID
                # (host:porta:nome) — WinThor antigo quase sempre é SID.
                for dsn in ("%s:%s/%s" % (host, porta, servico),
                            "%s:%s:%s" % (host, porta, servico)):
                    tentativas += 1
                    if tentativas > 60:
                        return None
                    for drv in drivers:
                        try:
                            conn = drv.connect(user=ora["user"], password=ora.get("password", ""),
                                               dsn=_dsn_para_driver(dsn))
                            conn.close()
                            log("[descoberta] CONECTOU em %s" % dsn)
                            return dsn
                        except Exception:
                            continue
    return None


def aplicar_descoberta(cfg, platform_api=None):
    dsn = descobrir_dsn(cfg)
    if not dsn:
        return False
    atual = load_config()
    atual.setdefault("oracle", {})["dsn"] = dsn
    save_config(atual)
    cfg.setdefault("oracle", {})["dsn"] = dsn
    if platform_api is not None:
        platform_api.report_error("descoberta-oracle", "DSN descoberto automaticamente: %s" % dsn)
    return True


# --------------------------------------------------------------------------- Oracle
_DSN_SID = re.compile(r"^([^:/\s]+):(\d+):([A-Za-z0-9_$#.]+)$")


def _dsn_para_driver(dsn):
    """Traduz `host:porta:SID` num descritor TNS.

    A sintaxe curta `host:porta/nome` é só para SERVICE NAME. WinThor antigo
    costuma expor SID (ex.: WINT), e nem oracledb nem cx_Oracle aceitam SID no
    formato curto — o connect falha com ORA-12514/12505 sem explicar. Aqui o
    formato `host:porta:SID` vira um descritor completo com (SID=...).
    `host:porta/servico` e descritores prontos passam intocados.
    """
    m = _DSN_SID.match((dsn or "").strip())
    if not m:
        return dsn
    host, porta, sid = m.groups()
    return ("(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=%s)(PORT=%s))"
            "(CONNECT_DATA=(SID=%s)))" % (host, porta, sid))


def _drivers():
    """oracledb (thin) não conecta em Oracle <12.1 (DPY-3010): cai para cx_Oracle (thick)."""
    out = []
    try:
        import oracledb
        out.append(oracledb)
    except Exception:
        pass
    try:
        import cx_Oracle
        out.append(cx_Oracle)
    except Exception:
        pass
    return out


class Oracle:
    """Conexão SOMENTE LEITURA com o Oracle do WinThor."""

    def __init__(self, cfg):
        self.cfg = cfg.get("oracle") or {}
        self._conn = None
        self.schema = ""
        self.last_error = ""

    def connect(self):
        drivers = _drivers()
        if not drivers:
            raise RuntimeError("driver Oracle ausente (pip install oracledb OU cx_Oracle)")
        if not (self.cfg.get("user") and self.cfg.get("dsn")):
            raise RuntimeError("config oracle incompleta (user/dsn)")
        last = None
        for ora in drivers:
            try:
                self._conn = ora.connect(user=self.cfg["user"],
                                         password=self.cfg.get("password", ""),
                                         dsn=_dsn_para_driver(self.cfg["dsn"]))
                self._apontar_schema()
                return self._conn
            except Exception as exc:  # noqa: BLE001 — tenta o próximo driver
                last = exc
        raise last

    def _apontar_schema(self):
        """ALTER SESSION SET CURRENT_SCHEMA = dono das PC* — o SQL usa FROM PCPEDC sem prefixo.

        Sem isto, usuário que não é o dono recebe ORA-00942 mesmo com GRANT,
        a menos que exista sinônimo tabela a tabela.
        """
        try:
            dono = (self.cfg.get("schema") or "").strip()
            if not dono:
                cur = self._conn.cursor()
                try:
                    cur.execute("SELECT owner FROM all_tables WHERE table_name = 'PCPEDC' AND ROWNUM = 1")
                    linha = cur.fetchone()
                finally:
                    cur.close()
                dono = (linha[0] if linha else "") or ""
            usuario = (self.cfg.get("user") or "").upper()
            if not dono or dono.upper() == usuario:
                self.schema = dono
                return
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_$#]{0,29}", dono):
                return
            cur = self._conn.cursor()
            try:
                cur.execute('ALTER SESSION SET CURRENT_SCHEMA = "%s"' % dono.upper())
            finally:
                cur.close()
            self.schema = dono.upper()
        except Exception:  # noqa: BLE001
            pass

    def close(self):
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn = None

    def _ensure(self):
        if self._conn is None:
            self.connect()
        return self._conn

    def query(self, sql, params=None):
        cur = self._ensure().cursor()
        try:
            cur.execute(sql, params or {})
            cols = [d[0] for d in (cur.description or [])]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            cur.close()

    def ping(self):
        try:
            cur = self._ensure().cursor()
            cur.execute("SELECT 1 FROM DUAL")
            cur.fetchone()
            cur.close()
            self.last_error = ""
            return True
        except Exception as exc:  # noqa: BLE001 — a falha vira diagnóstico
            self.last_error = ("%s: %s" % (type(exc).__name__, exc))[:300]
            _log("ping do Oracle falhou: %s" % self.last_error)
            self.close()
            return False


def _to_jsonable(rows):
    out = []
    for row in rows:
        out.append({k: (v if isinstance(v, (int, float, str, type(None))) else str(v))
                    for k, v in row.items()})
    return out


# --------------------------------------------------------------------------- HTTP (plataforma)
class Platform:
    def __init__(self, cfg):
        self.base = (cfg.get("server") or "").rstrip("/")
        self.key = cfg.get("key", "")
        self.ctx = ssl.create_default_context()
        if cfg.get("allow_insecure"):
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def _req(self, path, payload=None, method=None, timeout=60, raw=False):
        req = urllib.request.Request(
            self.base + path,
            data=None if payload is None else json.dumps(payload, default=str).encode(),
            method=method or ("POST" if payload is not None else "GET"),
            headers={"Content-Type": "application/json", "X-Coletor-Token": self.key,
                     "User-Agent": "techsys-agente/%s" % VERSION},
        )
        with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as r:
            body = r.read()
        if raw:
            return body
        return json.loads(body.decode() or "{}")

    def plan(self):
        return self._req("/api/coletor/plan/", timeout=30)

    def ingest(self, entity, items):
        # Lote grande pode levar mais de 60 s para o servidor gravar.
        return self._req("/api/coletor/ingest/", {"entity": entity, "items": items}, timeout=300)

    def report_queries(self, items, machine=""):
        if not items:
            return
        try:
            self._req("/api/coletor/queries/", {"items": items, "machine": machine}, timeout=20)
        except Exception:  # noqa: BLE001
            pass

    def report_error(self, context, error):
        try:
            self._req("/api/coletor/error/",
                      {"context": str(context)[:80], "error": str(error)[:2000], "version": VERSION},
                      timeout=15)
        except Exception:  # noqa: BLE001
            pass

    def heartbeat(self, health):
        try:
            self._req("/api/coletor/heartbeat/", health or {}, timeout=15)
        except Exception:  # noqa: BLE001
            pass

    def poll_commands(self):
        return self._req("/api/coletor/commands/", timeout=40)

    def post_result(self, command_id, ok, result=None, error=""):
        try:
            self._req("/api/coletor/commands/%s/result/" % command_id,
                      {"ok": ok, "result": result or {}, "error": error}, timeout=30)
        except Exception as exc:  # noqa: BLE001
            print("[cmd] falha ao devolver resultado:", exc, file=sys.stderr)

    def download_agent(self):
        return self._req("/api/coletor/agente.py", timeout=120, raw=True)


def _na_janela(horas, hora_atual=None):
    if not horas:
        return True
    try:
        inicio, fim = int(horas[0]), int(horas[-1])
    except (TypeError, ValueError, IndexError):
        return True
    h = time.localtime().tm_hour if hora_atual is None else int(hora_atual)
    if inicio <= fim:
        return inicio <= h <= fim
    return h >= inicio or h <= fim


def _progresso_da_carga():
    """Resumo do state.json para a tela: marca d'água e carga gradual por entidade.

    É o que responde "até onde a carga inicial já foi": `janela` de 4/24 meses
    em notas fiscais diz que ainda falta histórico, mesmo com o agente online.
    """
    state = load_state()
    janelas = state.get("_janela") or {}
    out = {}
    for entity, marca in state.items():
        if entity.startswith("_"):
            continue
        out[entity] = {"marca": marca}
    for entity, janela in janelas.items():
        out.setdefault(entity, {})["janela"] = janela
    return {"entidades": out, "coletando": BUSY.is_set()}


def collect_health(oracle):
    ok = oracle.ping()
    health = {"oracle_ok": ok, "agent_version": VERSION,
              "oracle_erro": "" if ok else getattr(oracle, "last_error", ""),
              "schema": getattr(oracle, "schema", "") or "",
              "host": platform.node(), "python": platform.python_version(),
              "progresso": _progresso_da_carga()}
    try:
        import psutil
        health["cpu_percent"] = psutil.cpu_percent(interval=0.5)
        health["mem_percent"] = psutil.virtual_memory().percent
        health["disk_percent"] = psutil.disk_usage(os.path.abspath(os.sep)).percent
    except Exception:  # noqa: BLE001 — psutil é opcional
        pass
    return health


# --------------------------------------------------------------------------- compatibilidade de schema
def _itens_do_select(sql):
    ini = sql.upper().find("SELECT") + 6
    prof = 0
    for i in range(ini, len(sql)):
        if sql[i] == "(":
            prof += 1
        elif sql[i] == ")":
            prof -= 1
        elif prof == 0 and (sql[i:i + 6].upper() == "\nFROM " or sql[i:i + 6].upper() == " FROM "):
            fim = i
            break
    else:
        return None, None, None
    corpo = sql[ini:fim]
    itens, atual, prof = [], "", 0
    for ch in corpo:
        if ch == "(":
            prof += 1
        elif ch == ")":
            prof -= 1
        if ch == "," and prof == 0:
            itens.append(atual)
            atual = ""
        else:
            atual += ch
    itens.append(atual)
    return itens, ini, fim


def remover_coluna(sql, coluna):
    """Tira do SELECT o item que usa `coluna` (versões do WinThor diferem)."""
    itens, ini, fim = _itens_do_select(sql)
    if itens is None:
        return None
    alvo = re.compile(r"\b%s\b" % re.escape(coluna), re.I)
    mantidos = [it for it in itens if not alvo.search(it)]
    if len(mantidos) == len(itens) or not mantidos:
        return None
    novo = sql[:ini] + ",".join(mantidos) + sql[fim:]
    if alvo.search(novo):
        return None
    return novo


def _coluna_invalida(erro):
    txt = str(erro)
    if "ORA-00904" not in txt:
        return None
    m = re.search(r'"([A-Z0-9_$#]+)"\s*:\s*invalid identifier', txt, re.I)
    if m:
        return m.group(1)
    m = re.search(r'([A-Z0-9_$#]+)\s*:\s*invalid identifier', txt, re.I)
    return m.group(1) if m else None


def _erro_transitorio(exc):
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (408, 429, 500, 502, 503, 504)
    if isinstance(exc, (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError, OSError)):
        return True
    return "timed out" in str(exc).lower()


def _marca_futura(valor, folga_dias=2):
    """Data suja do ERP (ano 2502) não pode virar marca d'água — congelaria a entidade."""
    if not isinstance(valor, str) or len(valor) < 10 or valor[4:5] != "-" or not valor[:4].isdigit():
        return False
    limite = time.strftime("%Y-%m-%d", time.localtime(time.time() + folga_dias * 86400))
    return valor[:10] > limite


# --------------------------------------------------------------------------- coleta
def run_sync(platform_api, oracle, plan, state, machine=""):
    """Roda as queries do plano (cada uma isolada) e sobe em lotes por entidade.

    Incremental: :since = marca d'água (NULL na 1ª vez). A marca avança POR LOTE
    CONFIRMADO pelo servidor — queda de rede não perde progresso e lote recusado
    é relido no próximo ciclo. :janela = backfill gradual em meses.
    """
    auditoria = []
    avisados_sem_marca = set()
    agora = time.time()
    ultimas = state.setdefault("_ultima_execucao", {})
    for q in plan.get("queries") or []:
        entity, sql = q.get("entity"), q.get("sql") or ""
        if not (entity and sql):
            continue
        espera = int(q.get("every_minutes") or 0) * 60
        if espera and (agora - float(ultimas.get(entity) or 0)) < espera:
            continue
        if not _na_janela(q.get("horas")):
            continue
        inicio = time.time()
        try:
            params = {}
            if ":since" in sql:
                marca = state.get(entity)
                if _marca_futura(marca):
                    _log("[sync] %s: marca d'água futura (%s) descartada" % (entity, marca))
                    platform_api.report_error("marca:%s" % entity,
                                              "marca d'água futura (%s) descartada — coleta reiniciada" % marca)
                    state.pop(entity, None)
                    save_state(state)
                    marca = None
                params["since"] = marca
            if ":janela" in sql:
                alvo = int(q.get("backfill_meses") or 6)
                passo = int(q.get("backfill_passo") or 1)
                janelas = state.setdefault("_janela", {})
                anterior = int(janelas.get(entity) or 0)
                atual = min(alvo, (anterior + passo) if anterior else passo)
                janelas[entity] = atual
                params["janela"] = atual
                if anterior < alvo and ":since" in sql:
                    # Enquanto a janela cresce, lê a janela INTEIRA (upsert deduplica).
                    params["since"] = None
            removidas = []
            for _ in range(6):
                try:
                    rows = _to_jsonable(oracle.query(sql, params or None))
                    break
                except Exception as exc:  # noqa: BLE001
                    coluna = _coluna_invalida(exc)
                    novo_sql = remover_coluna(sql, coluna) if coluna else None
                    if not novo_sql:
                        raise
                    removidas.append(coluna)
                    sql = novo_sql
            else:
                raise RuntimeError("colunas demais ausentes: %s" % removidas)
            if removidas:
                platform_api.report_error("schema:%s" % entity,
                                          "colunas ausentes neste WinThor, ignoradas: %s" % ", ".join(removidas))
            batch = int(q.get("batch") or 500)
            since_col = q.get("since_column")
            incremental = bool(q.get("incremental")) and bool(since_col)
            if incremental:
                rows = sorted(rows, key=lambda r: (r.get(since_col) is None, r.get(since_col)))
            imported = 0
            interrompido = None
            for i in range(0, len(rows), batch):
                lote = rows[i:i + batch]
                res = None
                for tentativa in range(4):
                    try:
                        res = platform_api.ingest(entity, lote)
                        break
                    except Exception as exc:  # noqa: BLE001
                        if tentativa < 3 and _erro_transitorio(exc):
                            espera_s = (2, 5, 15)[tentativa]
                            _log("[sync] %s: plataforma indisponível (%s) — nova tentativa em %ss"
                                 % (entity, str(exc)[:80], espera_s))
                            time.sleep(espera_s)
                            continue
                        interrompido = exc
                        break
                if res is None:
                    break
                imported += int(res.get("imported") or 0)
                if res.get("error"):
                    _log("[sync] %s: erro do servidor: %s" % (entity, res["error"]))
                    interrompido = RuntimeError(str(res["error"])[:300])
                    break
                if incremental:
                    marcas_lote = [r.get(since_col) for r in lote
                                   if r.get(since_col) is not None and not _marca_futura(r.get(since_col))]
                    if marcas_lote:
                        state[entity] = max(marcas_lote)
                        save_state(state)
            if incremental and rows and entity not in avisados_sem_marca:
                if not any(r.get(since_col) is not None for r in rows):
                    avisados_sem_marca.add(entity)
                    platform_api.report_error(
                        "marca:%s" % entity,
                        "coluna %s veio vazia em %d linha(s): a coleta de %s está sempre em carga cheia"
                        % (since_col, len(rows), entity))
            _log("[sync] %s: %d lidos, %d importados%s"
                 % (entity, len(rows), imported, " (INTERROMPIDO: %s)" % interrompido if interrompido else ""))
            if interrompido is not None:
                raise interrompido
            ultimas[entity] = time.time()
            save_state(state)
            if ":janela" in sql:
                janela_atual = (state.get("_janela") or {}).get(entity)
                alvo = int(q.get("backfill_meses") or 6)
                if janela_atual and janela_atual < alvo:
                    _log("[sync] %s: carga gradual em %d/%d meses" % (entity, janela_atual, alvo))
            auditoria.append({"entity": entity, "rows": len(rows),
                              "duration_ms": int((time.time() - inicio) * 1000), "ok": True})
        except Exception as exc:  # noqa: BLE001 — uma entidade não derruba as demais
            _log("[sync] ERRO em %s: %s" % (entity, exc))
            platform_api.report_error("sync:%s" % entity, exc)
            auditoria.append({"entity": entity, "rows": 0,
                              "duration_ms": int((time.time() - inicio) * 1000), "ok": False,
                              "error": str(exc)[:2000]})
    platform_api.report_queries(auditoria, machine)


# --------------------------------------------------------------------------- comandos (diagnóstico)
class Handlers:
    """Tarefas de DIAGNÓSTICO que a plataforma pode pedir. Nenhuma escreve no ERP."""

    def __init__(self, oracle, cfg, plan, platform_api=None):
        self.oracle = oracle
        self.cfg = cfg
        self.plan = plan or {}
        self.platform_api = platform_api

    def dispatch(self, command, payload):
        fn = getattr(self, "do_" + str(command), None)
        if fn is None:
            raise ValueError("comando desconhecido: %s" % command)
        return fn(payload or {})

    def do_ping(self, payload):
        return {"pong": True, "version": VERSION, "oracle_ok": self.oracle.ping(), "echo": payload}

    def do_descobrir_oracle(self, payload):
        cfg = load_config()
        achou = aplicar_descoberta(cfg)
        if achou:
            self.oracle.cfg = (load_config().get("oracle") or {})
            self.oracle.close()
        return {"descoberto": achou, "dsn": (load_config().get("oracle") or {}).get("dsn"),
                "oracle_ok": self.oracle.ping()}

    def do_validar_schema(self, payload):
        """Roda cada consulta com ROWNUM = 0: testa tabela, colunas e GRANT de uma vez."""
        plano = self.plan.get("queries") or []
        if not plano:
            try:
                self.plan = Platform(self.cfg).plan() or {}
                plano = self.plan.get("queries") or []
            except Exception:  # noqa: BLE001
                pass
        laudo, tabelas_ruins = [], {}
        for q in plano:
            entidade, sql = q.get("entity"), q.get("sql") or ""
            if not (entidade and sql):
                continue
            params = {}
            if ":since" in sql:
                params["since"] = None
            if ":janela" in sql:
                params["janela"] = 1
            atual, removidas, erro = sql, [], ""
            for _ in range(8):
                try:
                    self.oracle.query("SELECT * FROM (%s) WHERE ROWNUM = 0" % atual.strip().rstrip(";"),
                                      params or None)
                    erro = ""
                    break
                except Exception as exc:  # noqa: BLE001
                    erro = str(exc).strip().splitlines()[0][:160]
                    coluna = _coluna_invalida(exc)
                    novo = remover_coluna(atual, coluna) if coluna else None
                    if not novo:
                        break
                    removidas.append(coluna)
                    atual = novo
            if not erro:
                estado = "parcial" if removidas else "ok"
            else:
                estado = "falha"
                for tab in re.findall(r"(?:FROM|JOIN)\s+([A-Z0-9_$#]+)", sql, re.I):
                    tab = tab.upper()
                    if tab in tabelas_ruins:
                        continue
                    try:
                        self.oracle.query("SELECT 1 FROM %s WHERE ROWNUM = 0" % tab)
                        tabelas_ruins[tab] = "ok"
                    except Exception as e2:  # noqa: BLE001
                        tabelas_ruins[tab] = self._diagnostico_ora942(tab, e2)
            laudo.append({"entidade": entidade, "estado": estado,
                          "colunas_ignoradas": removidas, "erro": erro})
        inacessiveis = {t: m for t, m in tabelas_ruins.items() if m != "ok"}
        return {
            "resumo": {"total": len(laudo),
                       "ok": sum(1 for x in laudo if x["estado"] == "ok"),
                       "parcial": sum(1 for x in laudo if x["estado"] == "parcial"),
                       "falha": sum(1 for x in laudo if x["estado"] == "falha")},
            "entidades": laudo,
            "tabelas_inacessiveis": inacessiveis,
            "oracle": (self.cfg.get("oracle") or {}).get("dsn"),
            "schema": self.oracle.schema,
            "versao_agente": VERSION,
        }

    def _diagnostico_ora942(self, tabela, erro):
        """ORA-00942 cobre 3 casos: não existe / falta GRANT / falta sinônimo — separa e diz o que o DBA faz."""
        bruto = str(erro).strip().splitlines()[0][:80]
        if "ORA-00942" not in bruto.upper():
            return bruto
        try:
            dono = self.oracle.query("SELECT OWNER FROM ALL_TABLES WHERE TABLE_NAME = :t", {"t": tabela})
            if not dono:
                return "a tabela não existe neste ERP (%s)" % bruto
            owner = dono[0].get("OWNER")
            priv = self.oracle.query(
                "SELECT 1 AS OK FROM ALL_TAB_PRIVS WHERE TABLE_NAME = :t AND GRANTEE = USER AND PRIVILEGE = 'SELECT'",
                {"t": tabela})
            if not priv:
                return "falta permissão: GRANT SELECT ON %s.%s TO %s;" % (owner, tabela, self._usuario())
            return "tem permissão; aponte o schema (config oracle.schema=%s) ou crie sinônimo" % owner
        except Exception:  # noqa: BLE001
            return bruto

    def _usuario(self):
        try:
            return (self.oracle.query("SELECT USER AS U FROM DUAL")[0] or {}).get("U") or "TECHSYS"
        except Exception:  # noqa: BLE001
            return "TECHSYS"

    def do_coletar(self, payload):
        """Coleta AGORA. payload: {"entities": [...]} ou vazio; "cheia": true ignora a marca."""
        if self.platform_api is None:
            raise RuntimeError("coleta sob demanda indisponível neste contexto")
        alvos = payload.get("entities") or []
        plano = dict(self.plan or {})
        consultas = [q for q in (plano.get("queries") or []) if not alvos or q.get("entity") in alvos]
        if not consultas:
            raise ValueError("nenhuma entidade do plano corresponde a %s" % (alvos or "—"))
        estado = load_state()
        if payload.get("cheia"):
            for q in consultas:
                estado.pop(q.get("entity"), None)
                (estado.get("_janela") or {}).pop(q.get("entity"), None)
        plano["queries"] = [{k: v for k, v in q.items() if k not in ("every_minutes", "horas")} for q in consultas]
        BUSY.set()
        try:
            run_sync(self.platform_api, self.oracle, plano, estado, socket.gethostname())
        finally:
            BUSY.clear()
        return {"entidades": [q.get("entity") for q in consultas], "carga_cheia": bool(payload.get("cheia"))}

    def do_reset_state(self, payload):
        estado = load_state()
        if payload.get("all"):
            removidas = sorted(k for k in estado if not k.startswith("_"))
            estado = {}
        else:
            alvos = payload.get("entities") or []
            if not alvos:
                raise ValueError("informe entities=[...] ou all=true")
            removidas = [e for e in alvos if e in estado]
            for e in alvos:
                estado.pop(e, None)
                (estado.get("_ultima_execucao") or {}).pop(e, None)
                (estado.get("_janela") or {}).pop(e, None)
        save_state(estado)
        return {"resetadas": removidas, "restantes": sorted(estado.keys())}

    def do_update_config(self, payload):
        """Só campos seguros: dsn, oracle_user, schema, interval, name. Senha e chave NUNCA."""
        cfg = load_config()
        changed = {}
        if payload.get("dsn"):
            cfg.setdefault("oracle", {})["dsn"] = str(payload["dsn"])
            changed["dsn"] = cfg["oracle"]["dsn"]
        if payload.get("oracle_user"):
            cfg.setdefault("oracle", {})["user"] = str(payload["oracle_user"])
            changed["oracle_user"] = cfg["oracle"]["user"]
        if payload.get("schema") is not None:
            cfg.setdefault("oracle", {})["schema"] = str(payload["schema"])
            changed["schema"] = cfg["oracle"]["schema"]
        if payload.get("interval"):
            cfg["interval"] = int(payload["interval"])
            changed["interval"] = cfg["interval"]
        if payload.get("name"):
            cfg["name"] = str(payload["name"])
            changed["name"] = cfg["name"]
        if not changed:
            raise ValueError("nada para alterar (campos aceitos: dsn, oracle_user, schema, interval, name)")
        save_config(cfg)
        self.cfg.update(cfg)
        self.oracle.cfg = cfg.get("oracle") or {}
        self.oracle.close()
        return {"alterado": changed, "oracle_ok": self.oracle.ping()}

    def do_run_query(self, payload):
        sql = payload.get("sql") or ""
        if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
            raise PermissionError("run_query aceita apenas SELECT")
        rows = self.oracle.query(sql, payload.get("params"))
        return {"rows": _to_jsonable(rows[:500]), "count": len(rows)}


# --------------------------------------------------------------------------- auto-update
def _ver_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except Exception:
        return (0,)


def maybe_self_update(cfg, platform_api, plan):
    latest = (plan or {}).get("latest") or ""
    if not latest or _ver_tuple(latest) <= _ver_tuple(VERSION):
        return
    if BUSY.is_set():
        _log("auto-update adiado: coleta em andamento")
        return
    server = (cfg.get("server") or "")
    if not server.startswith("https://"):
        _log("auto-update recusado: canal de atualização exige HTTPS")
        return
    try:
        data = platform_api.download_agent()
        want = (plan.get("sha256") or "").lower()
        got = hashlib.sha256(data).hexdigest()
        motivo = ""
        if not want:
            motivo = "plano não anuncia sha256; update recusado"
        elif len(data) < 1000:
            motivo = "arquivo muito pequeno (%d bytes)" % len(data)
        elif b'VERSION = "' not in data:
            motivo = "conteúdo não parece o agente"
        elif got != want:
            motivo = "sha256 diferente do anunciado (%s != %s)" % (got[:12], want[:12])
        if motivo:
            _log("auto-update abortado: " + motivo)
            platform_api.report_error("auto-update", motivo)
            return
        dst = os.path.abspath(__file__)
        tmp = dst + ".new"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dst)
        _log("auto-update %s -> %s. Reiniciando…" % (VERSION, latest))
        platform_api.report_error("auto-update", "atualizado %s -> %s, reiniciando" % (VERSION, latest))
        try:
            STOP.set()
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as exc:  # noqa: BLE001
            print("re-exec falhou (%s); saindo para o supervisor reiniciar" % exc, file=sys.stderr)
            os._exit(0)
    except Exception as exc:  # noqa: BLE001
        _log("auto-update: %s" % exc)
        platform_api.report_error("auto-update", exc)


# --------------------------------------------------------------------------- loops
def sync_loop(cfg, platform_api, oracle):
    state = load_state()
    while not STOP.is_set():
        cfg = load_config()
        state = load_state()
        novo_oracle = cfg.get("oracle") or {}
        if novo_oracle != oracle.cfg:
            oracle.cfg = novo_oracle
            oracle.close()
        interval = int(cfg.get("interval", 600))
        plan = {}
        try:
            plan = platform_api.plan()
            interval = int(plan.get("interval") or interval)
        except Exception as exc:  # noqa: BLE001
            _log("[plan] indisponível: %s" % exc)
            platform_api.report_error("plan", exc)
        if plan.get("queries") and not oracle.ping():
            _log("[oracle] conexão indisponível — tentando descobrir o DSN…")
            if aplicar_descoberta(cfg, platform_api):
                oracle.cfg = (load_config().get("oracle") or {})
                oracle.close()
        maybe_self_update(cfg, platform_api, plan)
        if plan.get("queries"):
            BUSY.set()
            try:
                run_sync(platform_api, oracle, plan, state, socket.gethostname())
            except Exception:  # noqa: BLE001
                _crash(traceback.format_exc())
                platform_api.report_error("sync", traceback.format_exc()[-1500:])
            finally:
                BUSY.clear()
                oracle.close()
        maybe_self_update(cfg, platform_api, plan)
        STOP.wait(max(30, interval))


def command_loop(cfg, platform_api, oracle):
    plan_cache = {}
    while not STOP.is_set():
        try:
            try:
                plan_cache = platform_api.plan() or plan_cache
            except Exception:  # noqa: BLE001
                pass
            for cmd in platform_api.poll_commands() or []:
                handlers = Handlers(oracle, cfg, plan_cache, platform_api)
                try:
                    result = handlers.dispatch(cmd.get("command"), cmd.get("payload"))
                    platform_api.post_result(cmd.get("id"), True, result)
                except Exception as exc:  # noqa: BLE001
                    platform_api.post_result(cmd.get("id"), False, error=str(exc))
                    platform_api.report_error("comando:%s" % cmd.get("command"), exc)
        except Exception as exc:  # noqa: BLE001
            _log("[cmd] longpoll falhou: %s" % exc)
            STOP.wait(10)


def heartbeat_loop(cfg, platform_api, oracle):
    while not STOP.is_set():
        platform_api.heartbeat(collect_health(oracle))
        STOP.wait(60)


def run_service(cfg):
    if os.name == "nt":
        log = open(LOG_PATH, "a", buffering=1, encoding="utf-8", errors="replace")
        sys.stdout = sys.stderr = log
    _log("techsys-agente v%s — servidor %s" % (VERSION, cfg.get("server")))
    platform_api = Platform(cfg)
    threads = [
        threading.Thread(target=sync_loop, args=(cfg, platform_api, Oracle(cfg)), daemon=True),
        threading.Thread(target=command_loop, args=(cfg, platform_api, Oracle(cfg)), daemon=True),
        threading.Thread(target=heartbeat_loop, args=(cfg, platform_api, Oracle(cfg)), daemon=True),
    ]
    for t in threads:
        t.start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        STOP.set()


# --------------------------------------------------------------------------- entrada
def main():
    if "--version" in sys.argv:
        print(VERSION)
        return
    if "--apply" in sys.argv:
        cfg = load_config()
        for flag, key in (("--server", "server"), ("--key", "key"), ("--name", "name")):
            v = _arg(flag)
            if v:
                cfg[key] = v
        for flag, key in (("--dsn", "dsn"), ("--user", "user"), ("--password", "password"), ("--schema", "schema")):
            v = _arg(flag)
            if v:
                cfg.setdefault("oracle", {})[key] = v
        if _arg("--interval"):
            cfg["interval"] = int(_arg("--interval"))
        if "--allow-insecure" in sys.argv:
            cfg["allow_insecure"] = True
        save_config(cfg)
        print("config gravada em", CONFIG_PATH)
        if not (cfg.get("oracle") or {}).get("dsn"):
            print("DSN não informado — procurando o Oracle nesta máquina…")
            if aplicar_descoberta(cfg):
                print("DSN descoberto:", (load_config().get("oracle") or {}).get("dsn"))
            else:
                print("!! não encontrei o Oracle automaticamente; informe --dsn host:1521/SERVICO")
        return
    if "--discover" in sys.argv:
        cfg = load_config()
        if aplicar_descoberta(cfg):
            print("DSN descoberto:", (load_config().get("oracle") or {}).get("dsn"))
        else:
            print("não encontrei o Oracle automaticamente")
        return
    if "--status" in sys.argv:
        cfg = load_config()
        print("techsys-agente v%s" % VERSION)
        print("  servidor : %s" % cfg.get("server"))
        print("  oracle   : %s @ %s" % ((cfg.get("oracle") or {}).get("user"), (cfg.get("oracle") or {}).get("dsn")))
        state = load_state()
        marcas = {k: v for k, v in state.items() if not k.startswith("_")}
        if marcas:
            print("  última coleta por entidade (marca d'água):")
            for k in sorted(marcas):
                print("    %-20s %s" % (k, marcas[k]))
        else:
            print("  nenhuma coleta incremental registrada ainda (state.json vazio)")
        if os.path.exists(CRASH_PATH):
            tail = open(CRASH_PATH, encoding="utf-8", errors="replace").read().strip().splitlines()[-3:]
            print("  último erro registrado (crash.log):")
            for ln in tail:
                print("    " + ln)
        return
    if "--once" in sys.argv:
        cfg = load_config()
        platform_api = Platform(cfg)
        plan = platform_api.plan()
        oracle = Oracle(cfg)
        run_sync(platform_api, oracle, plan, load_state(), socket.gethostname())
        oracle.close()
        return
    run_service(load_config())


if __name__ == "__main__":
    main()
