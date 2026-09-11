#!/usr/bin/env bash
# Restaura a base ao estado semente. Executado antes de CADA repetição, conforme a
# seção 9 da especificação funcional e a seção 3.4 da monografia.
set -euo pipefail

CONTAINER="${PG_CONTAINER:-tcc-postgres}"
docker exec -i "$CONTAINER" psql -q -U bench -d tccbench < "$(dirname "$0")/seed.sql"
