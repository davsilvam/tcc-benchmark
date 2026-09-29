#!/usr/bin/env bash
# Rotinas comuns aos scripts do protocolo. Uso: `source "$(dirname "$0")/common.sh"`.
#
# Concentram-se aqui as etapas que TODAS as execuções repetem — restaurar a base, recriar o
# contêiner da aplicação, aguardar prontidão, coletar docker stats —, para que uma correção
# valha para todos os scripts de uma vez. O motivo é concreto: o run-experiment.sh recriava
# o contêiner com `up -d --force-recreate` SEM o nome do serviço, o que sob um profile recria
# também o PostgreSQL. A base era destruída e recarregada pelo initdb a cada repetição, e o
# SGBD reiniciado entre medições — o oposto do que a seção 3.4 exige.

# Sem isto, o Git Bash do Windows converte caminhos internos de contêiner em caminhos
# Windows e o docker run falha.
export MSYS_NO_PATHCONV=1

COMPOSE_FILE="${COMPOSE_FILE:-infra/docker-compose.yml}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8080/api/health}"
ALL_FRAMEWORKS=(springboot django nestjs laravel aspnet)

# Recria APENAS o contêiner da aplicação. O nome do serviço é obrigatório: sem ele, o
# compose recria todos os serviços do profile ativo, inclusive o postgres, que não tem
# profile e está sempre ativo.
app_up() {
  local fw="$1"
  docker compose -f "$COMPOSE_FILE" --profile "$fw" up -d --force-recreate --no-deps "$fw" >/dev/null 2>&1
}

# Remove APENAS o contêiner da aplicação. `down` atuaria sobre o projeto inteiro.
app_down() {
  local fw="$1"
  docker compose -f "$COMPOSE_FILE" --profile "$fw" rm -sf "$fw" >/dev/null 2>&1
}

# Pré-condição de qualquer medição: o PostgreSQL precisa estar ativo e aceitando conexões.
#
# A verificação é explícita porque duas decisões, ambas corretas em si, se combinam mal:
# app_up usa --no-deps para não recriar o banco, de modo que também NÃO o inicia se estiver
# parado; e /api/health não toca o banco (seção 4.6 da especificação), de modo que a
# aplicação responde "UP" com o banco morto. Sem esta checagem, uma campanha inteira roda
# contra um banco ausente e só se descobre depois, pelas taxas de erro.
require_postgres() {
  local pg="${PG_CONTAINER:-tcc-postgres}"
  if ! docker exec "$pg" pg_isready -U bench -d tccbench >/dev/null 2>&1; then
    echo "ERRO: o contêiner $pg não está aceitando conexões." >&2
    echo "      Suba-o antes de medir:" >&2
    echo "        docker compose -f $COMPOSE_FILE up -d postgres" >&2
    return 1
  fi
}

wait_health() {
  local fw="$1" limite="${2:-180}"
  for _ in $(seq 1 "$limite"); do
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  echo "ERRO: $fw não ficou pronto em $limite s" >&2
  return 1
}

reset_db() {
  ./infra/reset-db.sh
}

# Coleta de CPU e memória do contêiner, em laço contínuo, até receber SIGTERM.
#
# Cada chamada de `docker stats --no-stream` lê duas amostras do daemon e calcula a CPU
# sobre o intervalo entre elas (cerca de 1 s); a chamada seguinte começa assim que a
# anterior termina. O intervalo efetivo entre amostras não é fixado — depende de quanto a
# chamada demora — e por isso cada linha leva o instante em milissegundos: o intervalo real
# é MEDIDO a partir do próprio arquivo (scripts/analyze-experiment.py), não suposto.
#
# Formato: epoch_ms,cpu_percent,mem_usage
#   cpu_percent é relativo a UM núcleo: 200% é o teto de um contêiner com 2 vCPU
stats_start() {
  local fw="$1" destino="$2"
  (
    trap 'exit 0' TERM
    while true; do
      linha="$(docker stats --no-stream --format '{{.CPUPerc}},{{.MemUsage}}' "tcc-$fw" 2>/dev/null)"
      [ -n "$linha" ] && printf '%s,%s\n' "$(date +%s%3N)" "$linha" >> "$destino"
    done
  ) &
  STATS_PID=$!
}

stats_stop() {
  if [ -n "${STATS_PID:-}" ]; then
    kill "$STATS_PID" 2>/dev/null || true
    wait "$STATS_PID" 2>/dev/null || true
    STATS_PID=""
  fi
}

# Executa o k6 em contêiner, na rede dos serviços (ver scripts/k6-run.sh).
k6_run() {
  bash scripts/k6-run.sh "$@"
}

# Endereço do serviço NA REDE do compose, usado pelo k6 conteinerizado.
service_url() {
  echo "http://$1:8080"
}
