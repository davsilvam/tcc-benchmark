#!/usr/bin/env bash
# Teste de carga fixa — campanha de coleta (seção 3.4 da monografia).
#
#   RATES="40 80 120" DURATION=300s ./scripts/run-experiment.sh
#
# Modelo aberto: os cinco frameworks recebem exatamente as mesmas taxas de chegada, que
# correspondem a 25%, 50% e 75% da menor capacidade utilizável observada no teste de
# capacidade (scripts/run-capacity.sh). As taxas NÃO têm valor padrão: dependem desse
# teste, e o script se recusa a rodar sem elas.
#
# Organização da campanha — rodadas intercaladas, não blocos:
#   para cada repetição n = 1..REPS
#     sorteia a ordem dos frameworks (semente ORDER_SEED e n; ordem gravada em ordem.csv)
#     para cada framework, na ordem sorteada
#       para cada taxa de RATES
#         1. restaura a base ao estado semente
#         2. recria APENAS o contêiner da aplicação (o PostgreSQL permanece ativo)
#         3. aguarda /api/health
#         4. aquecimento na MESMA taxa, por WARMUP_DURATION — dados descartados
#         5. medição por DURATION, com coleta paralela de docker stats
#         6. remove o contêiner da aplicação
# A repetição n de todos os tratamentos termina antes do início da n + 1, de modo que
# variações lentas do ambiente — aquecimento térmico, atividade do sistema hospedeiro — se
# distribuam entre os frameworks em vez de recair sobre um só.
#
# RETOMADA: uma execução cujo resultado já existe em disco é pulada. Uma campanha
# interrompida continua de onde parou, sem refazer o que já foi medido e sem alterar a
# ordem sorteada.
#
# VALIDADE: toda execução com erro ou com iterações descartadas é registrada em
# invalidas.csv. O protocolo manda investigar cada uma e, se o erro decorrer de falha do
# ambiente, repeti-la — o script não descarta nem repete nada sozinho.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source scripts/common.sh
require_postgres || exit 1

: "${RATES:?informe RATES, ex.: RATES=\"40 80 120\" — taxas derivadas do teste de capacidade}"
: "${DURATION:?informe DURATION, ex.: DURATION=300s — duração da medição}"
# 150 s: o estudo-piloto mediu o Spring Boot entrando em regime aos 90 s (seção 9 de
# docs/versoes-e-configuracao.md). Aos 60 s ele ainda estava 35% acima do regime.
WARMUP_DURATION="${WARMUP_DURATION:-150s}"
REPS="${REPS:-10}"
ORDER_SEED="${ORDER_SEED:-20260922}"
OUT="${OUT:-results/campaign}"
read -r -a FRAMEWORKS <<< "${FRAMEWORKS:-${ALL_FRAMEWORKS[*]}}"
read -r -a RATE_LIST <<< "$RATES"

mkdir -p "$OUT"
[ -f "$OUT/ordem.csv" ] || echo "repeticao,posicao,framework" > "$OUT/ordem.csv"
[ -f "$OUT/invalidas.csv" ] || echo "execucao,taxa_erro,iteracoes_descartadas" > "$OUT/invalidas.csv"

{
  echo "iniciado_em=$(date -Is)"
  echo "rates=${RATE_LIST[*]}"
  echo "duration=$DURATION"
  echo "warmup_duration=$WARMUP_DURATION"
  echo "reps=$REPS"
  echo "order_seed=$ORDER_SEED"
  echo "frameworks=${FRAMEWORKS[*]}"
} >> "$OUT/parametros.txt"

# Embaralhamento determinístico: a mesma semente produz a mesma ordem, e a ordem usada fica
# gravada de qualquer forma em ordem.csv.
shuffle() {
  python -c "import random,sys; r=random.Random(int(sys.argv[1])); l=sys.argv[2:]; r.shuffle(l); print(' '.join(l))" "$@"
}

trap 'stats_stop' EXIT

echo "taxas=${RATE_LIST[*]} req/s  medição=$DURATION  aquecimento=$WARMUP_DURATION  repetições=$REPS"

for rep in $(seq 1 "$REPS"); do
  read -r -a ORDER <<< "$(shuffle "$((ORDER_SEED * 1000 + rep))" "${FRAMEWORKS[@]}")"
  if ! grep -q "^$rep," "$OUT/ordem.csv"; then
    pos=1
    for fw in "${ORDER[@]}"; do echo "$rep,$pos,$fw" >> "$OUT/ordem.csv"; pos=$((pos + 1)); done
  fi
  echo "### rodada $rep — ordem: ${ORDER[*]}"

  for fw in "${ORDER[@]}"; do
    mkdir -p "$OUT/$fw"
    for rate in "${RATE_LIST[@]}"; do
      tag="${fw}_${rate}rps_rep$(printf '%02d' "$rep")"
      result="$OUT/$fw/$tag.json"

      if [ -s "$result" ]; then
        echo "  $tag — já medido, pulando"
        continue
      fi
      echo "  $tag"

      reset_db
      app_up "$fw"
      if ! wait_health "$fw"; then
        app_down "$fw"
        echo "$tag,falha_de_prontidao," >> "$OUT/invalidas.csv"
        continue
      fi

      k6_run -q -e BASE_URL="$(service_url "$fw")" -e RATE="$rate" \
        -e DURATION="$WARMUP_DURATION" -e WARMUP=1 -e RUN_ID="$rep" k6/load-test.js

      rm -f "$OUT/$fw/$tag.stats.csv"
      stats_start "$fw" "$OUT/$fw/$tag.stats.csv"
      k6_run -q -e BASE_URL="$(service_url "$fw")" -e RATE="$rate" \
        -e DURATION="$DURATION" -e RUN_ID="$rep" -e RESULT_FILE="$result" k6/load-test.js \
        >/dev/null
      stats_stop

      app_down "$fw"

      if [ -s "$result" ]; then
        python - "$result" "$tag" "$OUT/invalidas.csv" <<'PY'
import io, json, sys
row = json.load(io.open(sys.argv[1], encoding='utf-8'))['row']
erro, desc = row['errorRate'], row['droppedIterations']
print('    p95=%.1f ms  média=%.1f ms  obtida=%.1f req/s  erro=%.3f%%  descartadas=%d'
      % (row['latencyP95Ms'], row['latencyAvgMs'], row['achievedRps'], erro * 100, desc))
if erro > 0 or desc > 0:
    with io.open(sys.argv[3], 'a', encoding='utf-8') as f:
        f.write('%s,%s,%s\n' % (sys.argv[2], erro, desc))
    print('    ATENÇÃO: execução registrada em invalidas.csv para investigação')
PY
      else
        echo "$tag,sem_resultado," >> "$OUT/invalidas.csv"
        echo "    ATENÇÃO: o k6 não gravou resultado"
      fi
    done
  done
done

echo "concluído: $OUT  (analisar com: python scripts/analyze-experiment.py $OUT)"
