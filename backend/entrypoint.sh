#!/bin/sh
set -e

python manage.py migrate --noinput

if [ "${DEBUG:-1}" = "1" ]; then
  exec python manage.py runserver 0.0.0.0:8000
else
  python manage.py collectstatic --noinput
  # timeout alto: um lote grande do agente (milhares de títulos) pode levar
  # minutos para gravar; com 60 s o gunicorn cortava e o lote era relido sempre.
  exec gunicorn core.wsgi:application --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" --timeout 600 --graceful-timeout 60 \
    --access-logfile - --error-logfile -
fi
