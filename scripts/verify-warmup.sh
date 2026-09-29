#!/usr/bin/env bash
# Critério de aceite 8.3 — estabilidade sob aquecimento, no modelo aberto.
#
#   RATE=80 ./scripts/verify-warmup.sh              # os cinco, na mesma taxa
#   RATE=80 ./scripts/verify-warmup.sh springboot   # apenas um
#
# RATE deve ser o nível intermediário do teste de carga fixa (50% da menor capacidade
# utilizável) e é obrigatória: o aquecimento precisa ser verificado sob a carga em que a
# campanha vai medir. O período de 150 s foi estabelecido no estudo-piloto sob o modelo
# FECHADO; sob taxa de chegada fixa, e em geral mais baixa, o comportamento pode mudar.
#
# A execução é MAIS LONGA que o período de aquecimento (300 s por padrão), deliberadamente:
# uma execução do tamanho do aquecimento responde "estabilizou até aqui?", mas não "o
# período basta?". Para saber quanto o aquecimento deveria durar é preciso ver quando a
# latência para de mudar.
#
# Cada framework parte de contêiner RECÉM-CRIADO, com a base restaurada: é o estado frio de
# compilação em tempo de execução que o protocolo reproduz a cada execução.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source scripts/common.sh
require_postgres || exit 1

: "${RATE:?informe RATE, a taxa do nível intermediário do teste de carga fixa (req/s)}"
DURATION="${DURATION:-300s}"
BUCKET_S="${BUCKET_S:-10}"
OUT="${OUT:-results/warmup-aberto}"

if [ "$#" -gt 0 ]; then FRAMEWORKS=("$@"); else FRAMEWORKS=("${ALL_FRAMEWORKS[@]}"); fi

mkdir -p "$OUT"
echo "iniciado_em=$(date -Is) rate=$RATE duration=$DURATION bucket_s=$BUCKET_S" >> "$OUT/parametros.txt"

for fw in "${FRAMEWORKS[@]}"; do
  echo "=== $fw — $RATE req/s por $DURATION, intervalos de ${BUCKET_S}s ==="

  reset_db
  app_up "$fw"
  if ! wait_health "$fw"; then app_down "$fw"; continue; fi

  k6_run -q -e BASE_URL="$(service_url "$fw")" -e RATE="$RATE" -e DURATION="$DURATION" \
    -e BUCKET_S="$BUCKET_S" -e RUN_ID=1 -e RESULT_FILE="$OUT/$fw.json" k6/load-test.js \
    >/dev/null 2>&1

  app_down "$fw"

  if [ -s "$OUT/$fw.json" ]; then
    echo "  série gravada em $OUT/$fw.json"
  else
    echo "  AVISO: sem série temporal — a execução do k6 falhou"
  fi
done

echo "=== análise ==="
python scripts/analyze-warmup.py "$OUT/*.json"
