#!/usr/bin/env bash
# Remove o agente TechSys (coletor WinThor) desta máquina. Roda como root.
#   curl -fsSL https://SEU-SERVIDOR/api/coletor/uninstall.sh | sudo bash
set -uo pipefail
[[ $EUID -ne 0 ]] && { echo "Rode como root (sudo)."; exit 1; }

DIR="/opt/techsys-agente"
if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now techsys-agente 2>/dev/null || true
  rm -f /etc/systemd/system/techsys-agente.service
  systemctl daemon-reload
else
  pkill -f 'techsys-agente/agente.py' 2>/dev/null || true
  ( crontab -l 2>/dev/null | grep -v 'techsys-agente' || true ) | crontab - 2>/dev/null || true
fi
rm -f /usr/local/bin/techsys-agente
rm -rf "$DIR"
echo "✓ techsys-agente removido (o usuário TECHSYS no Oracle continua — revogue no banco se quiser)."
