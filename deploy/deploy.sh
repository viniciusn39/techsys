#!/usr/bin/env bash
#
# Publica o TechSys Gestão no servidor (rsync + docker compose prod).
#   deploy/deploy.sh                      # usa os padrões abaixo
#   HOST=1.2.3.4 PORT=2022 deploy/deploy.sh
#
# Primeira vez: gera o .env no servidor com segredos aleatórios, sobe a stack,
# roda migrações, cria o root e o cliente Nordeste Boi. Vezes seguintes: só
# sincroniza o código e reconstrói o que mudou (dados ficam nos volumes).
set -euo pipefail

HOST="${HOST:-51.81.64.223}"
PORT="${PORT:-22}"
USER_="${USER_:-administrador}"
DOMAIN="${DOMAIN:-techsys.vsystems.com.br}"
DIR="${DIR:-/opt/techsys-gestao}"
ROOT_EMAIL="${ROOT_EMAIL:-root@techsys.local}"

SSH="ssh -o BatchMode=yes -p $PORT $USER_@$HOST"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

echo "→ sincronizando código para $USER_@$HOST:$DIR"
rsync -az --delete \
  --exclude '.git' --exclude 'node_modules' --exclude 'dist' --exclude '__pycache__' \
  --exclude '*.pyc' --exclude '.env' --exclude 'staticfiles' --exclude 'media' \
  --exclude '.claude' --exclude '.DS_Store' \
  -e "ssh -p $PORT" "$HERE/" "$USER_@$HOST:$DIR/"

echo "→ preparando .env (só na primeira vez) e subindo a stack"
$SSH "set -e; cd $DIR
if [ ! -f .env ]; then
  cat > .env <<EOF
DOMAIN=$DOMAIN
SECRET_KEY=\$(openssl rand -base64 48 | tr -d '\n/+=')
POSTGRES_DB=techsys_gestao
POSTGRES_USER=techsys
POSTGRES_PASSWORD=\$(openssl rand -base64 30 | tr -d '\n/+=')
EOF
  chmod 600 .env
  echo '  .env criado com segredos novos'
fi
docker compose -f docker-compose.prod.yml up -d --build --remove-orphans
echo '→ aguardando a API'
for i in \$(seq 1 60); do
  docker compose -f docker-compose.prod.yml exec -T backend curl -fsS http://localhost:8000/api/health/ >/dev/null 2>&1 && break
  sleep 3
done
docker compose -f docker-compose.prod.yml exec -T backend curl -fsS http://localhost:8000/api/health/; echo
echo '→ usuário root e cliente Nordeste Boi (idempotente)'
docker compose -f docker-compose.prod.yml exec -T backend python manage.py shell -c \"
import secrets
from accounts.models import User
u, created = User.objects.get_or_create(email='$ROOT_EMAIL', defaults={'first_name': 'Root', 'role': 'root', 'is_staff': True, 'is_superuser': True})
if created:
    senha = secrets.token_urlsafe(12)
    u.set_password(senha); u.save()
    print('  ROOT CRIADO -> $ROOT_EMAIL / ' + senha)
else:
    print('  root já existia')
\"
docker compose -f docker-compose.prod.yml exec -T backend python manage.py seed_nordesteboi | tail -8
docker compose -f docker-compose.prod.yml ps --format 'table {{.Service}}\t{{.Status}}'
"
echo "✓ publicado em https://$DOMAIN"
