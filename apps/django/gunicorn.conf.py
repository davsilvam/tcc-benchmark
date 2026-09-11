# Servidor WSGI — seção 6.2 da especificação.
# 5 trabalhadores = fórmula (2 x vCPU) + 1 da documentação do Gunicorn, com os 2 vCPU
# do contêiner. Uma thread por trabalhador: o modelo síncrono é o padrão documentado.

# Socket unix, não porta TCP: o nginx à frente é quem escuta em 8080 (ver
# docker/nginx.conf e a seção 9.3 de docs/versoes-e-configuracao.md).
bind = "unix:/run/gunicorn/gunicorn.sock"
umask = 0o000
workers = 5
threads = 1
worker_class = "sync"
loglevel = "warning"
accesslog = None
errorlog = "-"
