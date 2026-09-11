#!/usr/bin/env bash
# Critério de aceite 8.3 — estabilidade sob aquecimento.
#
#   ./scripts/verify-warmup.sh              # os cinco
#   ./scripts/verify-warmup.sh springboot   # apenas um
#
# A seção 8.3 pede uma execução preliminar de 60 s no nível de carga intermediário,
# verificando que a latência média se estabiliza e que a taxa de erro é nula.
#
# A execução aqui é MAIS LONGA que 60 s (180 s por padrão), e isso é deliberado: uma
# execução de exatamente 60 s responde "estabilizou até aqui?", mas não responde "60 s
# bastam?" — se um framework ainda estiver decaindo aos 60 s, é preciso ver quando ele
# para de decair para saber quanto o aquecimento deveria durar. A própria seção 8.3
# prevê revisão do período de aquecimento, e revisá-lo exige esse dado.
#
# Cada framework parte de contêiner RECÉM-CRIADO, com a base restaurada: é o estado frio
# de JIT que o protocolo da seção 3.4 reproduz a cada repetição.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE="infra/docker-compose.yml"
BASE_URL="${BASE_URL:-http://localhost:8080}"
VUS="${VUS:-100}"            # nível intermediário dos três da seção 3.4 (50 / 100 / 200)
DURATION="${DURATION:-180s}"
BUCKET_S="${BUCKET_S:-10}"
OUT="results/warmup"

if [ "$#" -gt 0 ]; then
  FRAMEWORKS=("$@")
else
  FRAMEWORKS=(springboot django nestjs laravel aspnet)
fi

mkdir -p "$OUT"

wait_health() {
  for _ in $(seq 1 180); do
    if curl -sf "$BASE_URL/api/health" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  echo "ERRO: $1 não ficou pronto em 180 s" >&2
  return 1
}

for fw in "${FRAMEWORKS[@]}"; do
  echo "=== $fw — $VUS VUs por $DURATION, intervalos de ${BUCKET_S}s ==="

  ./infra/reset-db.sh
  docker compose -f "$COMPOSE" --profile "$fw" up -d --force-recreate "$fw" >/dev/null 2>&1

  if ! wait_health "$fw"; then
    docker compose -f "$COMPOSE" --profile "$fw" rm -sf "$fw" >/dev/null 2>&1
    continue
  fi

  bash scripts/k6-run.sh -q \
    -e BASE_URL="http://$fw:8080" -e VUS="$VUS" -e DURATION="$DURATION" \
    -e BUCKET_S="$BUCKET_S" -e RUN_ID=1 \
    -e RESULT_FILE="$OUT/$fw.json" k6/load-test.js >/dev/null 2>&1

  docker compose -f "$COMPOSE" --profile "$fw" rm -sf "$fw" >/dev/null 2>&1

  if [ ! -s "$OUT/$fw.json" ]; then
    echo "  AVISO: sem série temporal — a execução do k6 falhou"
    continue
  fi
  echo "  série gravada em $OUT/$fw.json"

  echo
done

echo "=== análise ==="
python scripts/analyze-warmup.py "$OUT/*.json"
