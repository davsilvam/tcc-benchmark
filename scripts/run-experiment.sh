#!/usr/bin/env bash
# Campanha de coleta de um framework — 3 níveis de carga x 10 repetições.
# Executar a partir da raiz do repositório, com o contêiner do PostgreSQL já ativo.
#
#   ./scripts/run-experiment.sh springboot
#
# Cada repetição segue exatamente esta sequência:
#   1. restaura a base ao estado semente
#   2. recria o contêiner da aplicação (estado inicial idêntico, JIT frio)
#   3. aguarda /api/health responder 200
#   4. aquecimento de 150 s — dados descartados (invocação k6 separada)
#   5. medição, com coleta paralela de docker stats
#   6. remove o contêiner da aplicação (o do PostgreSQL permanece ativo)
set -euo pipefail

FW="${1:?uso: run-experiment.sh <springboot|django|nestjs|laravel|aspnet>}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
# BASE_URL serve à sondagem de prontidão, feita por curl no host, pela porta publicada.
# K6_BASE_URL é o endereço do serviço NA REDE do compose: o k6 roda em contêiner
# (ver scripts/k6-run.sh e a seção 9.3 de docs/versoes-e-configuracao.md).
K6_BASE_URL="${K6_BASE_URL:-http://$FW:8080}"
DURATION="${DURATION:-300s}"
# 150 s, e não 60 s: o critério 8.3 mediu o Spring Boot entrando em regime aos 90 s
# (ver a seção 9 de docs/versoes-e-configuracao.md). Aos 60 s ele ainda está 35%
# acima do regime, e medir ali incluiria a cauda da compilação em tempo de execução
# na janela de medição — só nos dois tratamentos com JIT.
WARMUP_DURATION="${WARMUP_DURATION:-150s}"
LEVELS=(${LEVELS:-50 100 200})
REPS="${REPS:-10}"
OUT="results/$FW"

mkdir -p "$OUT"

wait_health() {
  for _ in $(seq 1 120); do
    if curl -sf "$BASE_URL/api/health" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  echo "ERRO: $FW nao ficou pronto em 120 s" >&2
  exit 1
}

collect_stats() {
  local target="$1"
  while true; do
    docker stats --no-stream --format '{{.CPUPerc}},{{.MemUsage}}' "tcc-$FW" 2>/dev/null \
      | sed "s/^/$(date +%s),/" >> "$target"
    sleep 1
  done
}

echo "framework=$FW  niveis=${LEVELS[*]}  repeticoes=$REPS  duracao=$DURATION"

for vus in "${LEVELS[@]}"; do
  for rep in $(seq 1 "$REPS"); do
    tag="${FW}_${vus}vu_rep$(printf '%02d' "$rep")"
    echo "=== $tag ==="

    ./infra/reset-db.sh
    docker compose -f infra/docker-compose.yml --profile "$FW" up -d --force-recreate >/dev/null
    wait_health

    bash scripts/k6-run.sh -q -e BASE_URL="$K6_BASE_URL" -e VUS="$vus" -e DURATION="$WARMUP_DURATION" \
           -e WARMUP=1 -e RUN_ID="$rep" k6/load-test.js

    collect_stats "$OUT/$tag.stats.csv" &
    stats_pid=$!

    bash scripts/k6-run.sh -q -e BASE_URL="$K6_BASE_URL" -e VUS="$vus" -e DURATION="$DURATION" \
           -e RUN_ID="$rep" -e RESULT_FILE="$OUT/$tag.json" k6/load-test.js

    kill "$stats_pid" 2>/dev/null || true
    # `rm -sf "$FW"`, e não `down`: docker compose down atua sobre o PROJETO inteiro e
    # derrubaria também o contêiner do PostgreSQL. Como não ha volume nomeado, isso
    # destruiria a base a cada repetição e reiniciaria o SGBD entre as medicoes — o oposto
    # do que a seção 3.4 exige (o mesmo SGBD ativo durante toda a campanha).
    docker compose -f infra/docker-compose.yml --profile "$FW" rm -sf "$FW" >/dev/null
  done
done

echo "concluido: $OUT"
