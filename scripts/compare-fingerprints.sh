#!/usr/bin/env bash
# Critério de aceite 8.1, parte final — as cinco implementações devem devolver os MESMOS
# registros para as mesmas requisições de leitura: mesma quantidade, mesmos identificadores,
# na mesma ordem.
#
#   ./scripts/compare-fingerprints.sh
#
# A base é restaurada ao estado semente antes de CADA implementação: a suíte de contrato
# insere registros, e sem a restauração a segunda implementação encontraria uma base
# diferente da primeira e a comparação não teria sentido.
#
# Grava results/fingerprint-<framework>.json e compara todos contra o Spring Boot, que é a
# implementação de referência.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE="infra/docker-compose.yml"
BASE_URL="${BASE_URL:-http://localhost:8080}"
FRAMEWORKS=(springboot django nestjs laravel aspnet)
REFERENCE="springboot"
OUT="results"

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
  echo "=== $fw ==="

  ./infra/reset-db.sh
  docker compose -f "$COMPOSE" --profile "$fw" up -d --force-recreate "$fw" >/dev/null 2>&1

  if ! wait_health "$fw"; then
    docker compose -f "$COMPOSE" --profile "$fw" rm -sf "$fw" >/dev/null 2>&1
    continue
  fi

  # O fingerprint sai pelo log do usuário virtual: handleSummary roda em contexto distinto
  # e não enxerga a variável (ver o comentário em k6/contract-test.js).
  bash scripts/k6-run.sh -e BASE_URL="http://$fw:8080" -e FW="$fw" k6/contract-test.js 2>&1 \
    | sed -n 's/.*FINGERPRINT \({.*}\).*/\1/p' > "$OUT/fingerprint-$fw.json"

  if [ ! -s "$OUT/fingerprint-$fw.json" ]; then
    echo "  AVISO: fingerprint vazio — a suíte de contrato falhou antes de emiti-lo"
  else
    echo "  $(wc -c < "$OUT/fingerprint-$fw.json") bytes gravados"
  fi

  docker compose -f "$COMPOSE" --profile "$fw" rm -sf "$fw" >/dev/null 2>&1
done

echo
echo "=== comparação contra $REFERENCE ==="
FAILED=0
REF_FILE="$OUT/fingerprint-$REFERENCE.json"

if [ ! -s "$REF_FILE" ]; then
  echo "ERRO: fingerprint da referência ($REFERENCE) ausente ou vazio" >&2
  exit 2
fi

for fw in "${FRAMEWORKS[@]}"; do
  [ "$fw" = "$REFERENCE" ] && continue
  if diff -q "$REF_FILE" "$OUT/fingerprint-$fw.json" >/dev/null 2>&1; then
    printf '  %-11s idêntico\n' "$fw"
  else
    printf '  %-11s DIVERGENTE\n' "$fw"
    diff "$REF_FILE" "$OUT/fingerprint-$fw.json" | sed 's/^/      /' | cut -c1-200
    FAILED=1
  fi
done

echo
if [ "$FAILED" -eq 0 ]; then
  echo "Critério 8.1 satisfeito: os cinco fingerprints são idênticos."
else
  echo "Critério 8.1 NÃO satisfeito: há divergência de registros entre implementações." >&2
fi

exit "$FAILED"
