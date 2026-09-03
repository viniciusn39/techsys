#!/usr/bin/env bash
#
# Instalador do agente TechSys (coletor WinThor) — Linux / systemd. Roda como root.
#
# One-liner (gerado na tela de Integrações, já com a chave da empresa):
#   curl -fsSL https://SEU-SERVIDOR/api/coletor/install.sh | sudo bash -s -- \
#     --server https://SEU-SERVIDOR --key CHAVE --user TECHSYS --password 'SENHA'   # --dsn é OPCIONAL
#
# Sem --dsn, o agente DESCOBRE o Oracle sozinho nesta máquina (oratab, tnsnames.ora,
# listener.ora, IPs locais) e valida com uma conexão real.
#
set -euo pipefail

SERVER=""; KEY=""; INTERVAL=""; DSN=""; DBUSER=""; DBPASS=""; SCHEMA=""; NAME="$(hostname)"; INSECURE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --server) SERVER="${2:-}"; shift 2;;
    --key)    KEY="${2:-}"; shift 2;;
    --dsn)    DSN="${2:-}"; shift 2;;
    --user)   DBUSER="${2:-}"; shift 2;;
    --password) DBPASS="${2:-}"; shift 2;;
    --schema) SCHEMA="${2:-}"; shift 2;;
    --name)   NAME="${2:-}"; shift 2;;
    --interval) INTERVAL="${2:-}"; shift 2;;
    --allow-insecure) INSECURE="1"; shift;;
    *) shift;;
  esac
done
[[ $EUID -ne 0 ]] && { echo "Rode como root (sudo)."; exit 1; }
[[ -z "$SERVER" || -z "$KEY" ]] && { echo "Uso: install.sh --server URL --key CHAVE [--dsn ... --user ... --password ...]"; exit 1; }

DIR="/opt/techsys-agente"
mkdir -p "$DIR"
export PATH="/usr/local/bin:$PATH"

# --- código: local (se rodou do pacote) ou baixado da plataforma (com a chave) ---
SRC="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo /nonexistent)"
if [[ -f "$SRC/agente.py" ]]; then
  cp -f "$SRC/agente.py" "$DIR/"
else
  curl -fsSL -H "X-Coletor-Token: $KEY" "${SERVER%/}/api/coletor/agente.py" -o "$DIR/agente.py" \
    || { echo "!! falha ao baixar agente.py (chave correta? servidor acessível?)"; exit 1; }
fi

PM=""; for c in apt-get dnf yum zypper; do command -v "$c" >/dev/null 2>&1 && { PM="$c"; break; }; done

# --- Python 3 COM SSL ---
_py_ok() { "$1" -c 'import ssl' >/dev/null 2>&1; }
PYBIN=""
for c in python3 python3.12 python3.11 python3.10 python3.9 python3.8 python3.7 python3.6; do
  P="$(command -v "$c" 2>/dev/null || true)"; [[ -n "$P" ]] && _py_ok "$P" && { PYBIN="$P"; break; }
done
if [[ -z "$PYBIN" ]]; then
  [[ -n "$PM" ]] && $PM install -y python3 >/dev/null 2>&1 || true
  P="$(command -v python3 2>/dev/null || true)"; [[ -n "$P" ]] && _py_ok "$P" && PYBIN="$P"
fi
[[ -z "$PYBIN" ]] && { echo "!! Nenhum Python 3 com SSL — instale python3 e rode de novo."; exit 1; }
command -v python3 >/dev/null 2>&1 && _py_ok "$(command -v python3)" || { ln -sf "$PYBIN" /usr/local/bin/python3; hash -r; }

# --- driver Oracle: oracledb (thin, 12c+) OU cx_Oracle (thick, 11g) ---
PY_MINOR="$(python3 -c 'import sys; print(sys.version_info[1])' 2>/dev/null || echo 0)"
if ! python3 -c 'import oracledb' 2>/dev/null && ! python3 -c 'import cx_Oracle' 2>/dev/null; then
  echo "→ Instalando driver Oracle…"
  if [[ "${PY_MINOR:-0}" -ge 7 ]]; then
    python3 -m pip install --quiet oracledb >/dev/null 2>&1 \
      || python3 -m pip install --quiet --break-system-packages oracledb >/dev/null 2>&1 || true
  fi
  if ! python3 -c 'import oracledb' 2>/dev/null; then
    [[ -n "$PM" ]] && $PM install -y gcc python3-devel >/dev/null 2>&1 || true
    CFLAGS="-std=gnu99" python3 -m pip install --quiet "cx_Oracle==8.3.0" >/dev/null 2>&1 \
      || CFLAGS="-std=gnu99" python3 -m pip install --quiet --break-system-packages "cx_Oracle==8.3.0" >/dev/null 2>&1 || true
  fi
fi
python3 -c 'import oracledb' 2>/dev/null || python3 -c 'import cx_Oracle' 2>/dev/null \
  || echo "!! driver Oracle não instalado. Py3.6/11g: CFLAGS=\"-std=gnu99\" pip3 install cx_Oracle==8.3.0 (+ Instant Client)."

python3 -c 'import psutil' 2>/dev/null || python3 -m pip install --quiet psutil >/dev/null 2>&1 \
  || python3 -m pip install --quiet --break-system-packages psutil >/dev/null 2>&1 || true

# --- Oracle client p/ cx_Oracle (thick) sob systemd ---
ORA_ENV=""
ORA_LIB="$(find /u01 /u02 /opt/oracle /usr/lib/oracle /oracle -name 'libclntsh.so*' 2>/dev/null | grep -vi 'inventory' | head -1 || true)"
if [[ -n "$ORA_LIB" ]]; then
  ORA_LIBDIR="$(dirname "$ORA_LIB")"; ORA_HOME="$(dirname "$ORA_LIBDIR")"
  ORA_ENV="Environment=LD_LIBRARY_PATH=${ORA_LIBDIR}
Environment=ORACLE_HOME=${ORA_HOME}"
  echo "→ Oracle client detectado (${ORA_LIBDIR})"
fi

# --- config.json via --apply (chmod 600) ---
APPLY=(--apply --server "${SERVER%/}" --key "$KEY" --name "$NAME")
[[ -n "$DSN"      ]] && APPLY+=(--dsn "$DSN")
[[ -n "$DBUSER"   ]] && APPLY+=(--user "$DBUSER")
[[ -n "$DBPASS"   ]] && APPLY+=(--password "$DBPASS")
[[ -n "$SCHEMA"   ]] && APPLY+=(--schema "$SCHEMA")
[[ -n "$INTERVAL" ]] && APPLY+=(--interval "$INTERVAL")
[[ -n "$INSECURE" ]] && APPLY+=(--allow-insecure)
( cd "$DIR" && env ${ORA_LIBDIR:+LD_LIBRARY_PATH="$ORA_LIBDIR"} ${ORA_HOME:+ORACLE_HOME="$ORA_HOME"} \
    python3 agente.py "${APPLY[@]}" )

# --- serviço ---
PY="$(command -v python3 || echo /usr/bin/python3)"
if ! command -v systemctl >/dev/null 2>&1; then
  echo "→ Sem systemd — nohup + @reboot no cron"
  EXP=""; [[ -n "${ORA_LIBDIR:-}" ]] && EXP="LD_LIBRARY_PATH=$ORA_LIBDIR ORACLE_HOME=${ORA_HOME:-}"
  pkill -f 'techsys-agente/agente.py' 2>/dev/null || true; sleep 1
  ( cd "$DIR" && env $EXP nohup "$PY" -u agente.py --service >> /var/log/techsys-agente.log 2>&1 & )
  ( crontab -l 2>/dev/null | grep -v 'techsys-agente' || true
    echo "@reboot cd $DIR && env $EXP nohup $PY -u agente.py --service >> /var/log/techsys-agente.log 2>&1 &"
    echo "*/5 * * * * pgrep -f 'techsys-agente/agente.py' >/dev/null || (cd $DIR && env $EXP nohup $PY -u agente.py --service >> /var/log/techsys-agente.log 2>&1 &)" ) | crontab -
  echo "✓ instalado (modo legado — log em /var/log/techsys-agente.log)."; exit 0
fi

cat > /etc/systemd/system/techsys-agente.service <<EOF
[Unit]
Description=TechSys Agente (coletor WinThor)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=PYTHONUNBUFFERED=1
${ORA_ENV}
WorkingDirectory=$DIR
ExecStart=$PY -u $DIR/agente.py --service
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

cat > /usr/local/bin/techsys-agente <<'EOF'
#!/usr/bin/env bash
DIR=/opt/techsys-agente
case "${1:-status}" in
  status)    systemctl status techsys-agente --no-pager; (cd $DIR && python3 agente.py --status);;
  once)      (cd $DIR && python3 agente.py --once);;
  descobrir) (cd $DIR && python3 agente.py --discover);;
  logs)      journalctl -u techsys-agente -f;;
  restart)   systemctl restart techsys-agente;;
  version)   (cd $DIR && python3 agente.py --version);;
  *) echo "uso: techsys-agente {status|once|descobrir|logs|restart|version}";;
esac
EOF
chmod +x /usr/local/bin/techsys-agente

systemctl daemon-reload
systemctl enable techsys-agente >/dev/null 2>&1
# restart (não `enable --now`): numa REINSTALAÇÃO o serviço já está ativo e o
# `--now` não reinicia — o processo continuaria rodando o agente.py antigo.
systemctl restart techsys-agente
sleep 2
systemctl is-active --quiet techsys-agente && echo "✓ techsys-agente instalado e rodando (techsys-agente status | logs)" \
  || { echo "!! serviço não subiu — veja: journalctl -u techsys-agente -n 50"; exit 1; }
