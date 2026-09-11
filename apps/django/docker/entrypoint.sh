#!/bin/sh
# Gunicorn escuta em socket unix; o nginx é quem fala HTTP com o gerador de carga.
# O socket unix — e não uma porta de loopback — evita que o churn de conexões do worker
# síncrono do Gunicorn consuma portas efêmeras dentro do próprio contêiner.
set -e

mkdir -p /run/gunicorn
gunicorn -c gunicorn.conf.py bookapi.wsgi:application --daemon
exec nginx -g 'daemon off;'
