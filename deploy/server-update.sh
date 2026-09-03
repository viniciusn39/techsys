#!/usr/bin/env bash
# Roda NO SERVIDOR (chamado pelo GitHub Actions a cada push na main, ou à mão):
# atualiza o código a partir do GitHub e reconstrói só o que mudou. As
# migrações rodam no entrypoint do backend; dados ficam nos volumes.
set -euo pipefail

DIR="${DIR:-/opt/techsys-gestao}"
SHA="${1:-origin/main}"
LOCK="/tmp/techsys-deploy.lock"

cd "$DIR"
exec 9>"$LOCK"
flock -w 600 9 || { echo "outro deploy em andamento"; exit 1; }

echo "→ $(date '+%F %T') atualizando para $SHA"
git fetch --prune origin
git reset --hard "$SHA"
git log -1 --format='  %h %s (%an, %ar)'

echo "→ reconstruindo containers"
docker compose -f docker-compose.prod.yml up -d --build --remove-orphans

echo "→ aguardando a API"
for i in $(seq 1 60); do
  if docker compose -f docker-compose.prod.yml exec -T backend curl -fsS http://localhost:8000/api/health/ >/dev/null 2>&1; then
    echo "  API ok"
    break
  fi
  sleep 3
done

# Imagens antigas acumulam a cada build; limpa sem tocar em volumes.
docker image prune -f >/dev/null 2>&1 || true
docker compose -f docker-compose.prod.yml ps --format 'table {{.Service}}\t{{.Status}}'
echo "✓ deploy concluído $(date '+%F %T')"
