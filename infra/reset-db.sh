#!/usr/bin/env bash
# Restaura a base ao estado semente. Executado antes de CADA execução, conforme a
# seção 9.4 da especificação funcional e a seção 3.4 da monografia.
#
# Duas verificações, e não apenas o `psql`:
#
# ON_ERROR_STOP=1 — sem ele o psql PROSSEGUE após um erro e termina com código zero. Um
# TRUNCATE que falhasse por bloqueio deixaria as inserções rodarem sobre os dados antigos,
# a restauração seria reportada como bem-sucedida e a execução seguinte mediria uma base
# maior. Observado na prática: uma restauração falhou em silêncio e deixou 642 linhas
# residuais, que produziram colisões de ISBN e 4% de erro na medição seguinte.
#
# Conferência do volume — a base precisa terminar com exatamente 1.000 autores e 200.000
# livros (seção 2.4). É a única forma de garantir que a restauração de fato aconteceu.
set -euo pipefail

CONTAINER="${PG_CONTAINER:-tcc-postgres}"
AUTORES_ESPERADOS=1000
LIVROS_ESPERADOS=200000

docker exec -i "$CONTAINER" psql -q -v ON_ERROR_STOP=1 -U bench -d tccbench \
  < "$(dirname "$0")/seed.sql"

contagem="$(docker exec "$CONTAINER" psql -tA -U bench -d tccbench \
  -c "SELECT (SELECT count(*) FROM authors) || ' ' || (SELECT count(*) FROM books);")"
read -r autores livros <<< "$contagem"

if [ "$autores" != "$AUTORES_ESPERADOS" ] || [ "$livros" != "$LIVROS_ESPERADOS" ]; then
  echo "ERRO: base não voltou ao estado semente — autores=$autores livros=$livros" \
       "(esperado $AUTORES_ESPERADOS e $LIVROS_ESPERADOS)" >&2
  exit 1
fi
