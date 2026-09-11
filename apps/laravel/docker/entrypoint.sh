#!/bin/sh
# Os caches de configuração e de rotas são gerados na PARTIDA, e não na construção da
# imagem: config:cache congela os valores de env(), e as variáveis DB_* só existem quando
# o contêiner sobe. São as otimizações de produção recomendadas pela documentação do
# Laravel (seção 6.2).
set -e

php /app/artisan config:cache
php /app/artisan route:cache

php-fpm -D
exec nginx -g 'daemon off;'
