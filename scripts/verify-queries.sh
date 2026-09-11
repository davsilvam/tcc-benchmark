#!/usr/bin/env bash
# Critério de aceite 8.2 — equivalência do plano de acesso a dados.
# Conta as instruções SQL emitidas por UMA requisição de cada tipo e compara com o
# contrato. Executar com a aplicação ativa:
#
#   ./scripts/verify-queries.sh springboot
#
# O próprio script liga log_statement='all' e o restaura ao sair, inclusive em caso de
# erro: o registro de instruções tem custo e não pode permanecer ligado durante a coleta.
#
# NOTA: log_statement não pode ser passado na linha de comando do postgres. Parametros de
# linha de comando tem precedência sobre postgresql.auto.conf, e o ALTER SYSTEM abaixo
# seria silenciosamente ignorado. Ver o comentário em infra/docker-compose.yml.
set -uo pipefail

FW="${1:?uso: verify-queries.sh <framework>}"
BASE="${BASE_URL:-http://localhost:8080}"
PG="${PG_CONTAINER:-tcc-postgres}"

declare -A EXPECTED=(
  [list]=1 [byId]=1 [search]=1 [create]=2 [update]=2
)

# Os cinco ORMs usam o protocolo estendido do PostgreSQL, que registra "execute <portal>:"
# e não "statement:". Contar apenas "statement:" daria zero em todos eles. Instruções de
# controle de sessão e de transação (DISCARD ALL, BEGIN, COMMIT, SET, DEALLOCATE) ficam de
# fora porque o contrato conta instruções de dados.
SQL_PATTERN='(statement|execute [^:]*): *(SELECT|INSERT|UPDATE|DELETE|select|insert|update|delete)'

# Instruções de preparação de SESSÃO, emitidas uma vez por conexão aberta pelo pool e não
# por requisição. O psycopg do Django emite SELECT set_config('TimeZone','UTC',false) ao
# entregar cada conexão nova; contá-las inflaria o resultado do Django e de mais nenhum,
# medindo o aquecimento do pool em vez do plano de acesso a dados da requisição.
SESSION_PATTERN='set_config\(|: *(SELECT|select) 1 *;?$|SET SESSION|SET TIME ZONE'

statements_since() {
  local marker="$1"
  docker logs "$PG" 2>&1 | sed -n "/$marker/,\$p" | grep -E "$SQL_PATTERN" | grep -vE "$SESSION_PATTERN"
}

run_case() {
  local name="$1"; shift
  local marker="MARKER_${name}_$RANDOM"

  docker exec "$PG" psql -q -U bench -d tccbench -c "SELECT '$marker'" >/dev/null
  sleep 1
  "$@" >/dev/null
  sleep 1

  local captured n expected
  captured=$(statements_since "$marker")
  # descarta a própria consulta marcadora, que também casa com o padrão
  n=$(( $(printf '%s\n' "$captured" | grep -cE "$SQL_PATTERN") - 1 ))
  expected="${EXPECTED[$name]}"

  if [ "$n" -eq "$expected" ]; then
    printf '  %-8s %s consulta(s)  OK\n' "$name" "$n"
  else
    printf '  %-8s %s consulta(s)  ESPERADO %s  <-- FALHA\n' "$name" "$n" "$expected"
    # Na falha, mostra o que foi emitido: é o que diz se a causa foi carregamento tardio,
    # consulta de contagem adicional ou verificação redundante.
    printf '%s\n' "$captured" | grep -vE "MARKER_" | sed 's/^/      | /' | cut -c1-160
    FAILED=1
  fi
}

set_log_statement() {
  docker exec "$PG" psql -q -U bench -d tccbench -c "ALTER SYSTEM SET log_statement='$1'" >/dev/null
  docker exec "$PG" psql -tAq -U bench -d tccbench -c "SELECT pg_reload_conf()" >/dev/null
  sleep 1
}

FAILED=0
echo "verificando plano de acesso a dados — $FW"

trap 'set_log_statement none' EXIT
set_log_statement all

if [ "$(docker exec "$PG" psql -tA -U bench -d tccbench -c 'SHOW log_statement' | tr -d "[:space:]")" != "all" ]; then
  echo "ERRO: nao foi possivel ligar log_statement='all' no conteiner $PG." >&2
  exit 2
fi

run_case list   curl -sf "$BASE/api/books?page=5&size=20"
run_case byId   curl -sf "$BASE/api/books/1234"
run_case search curl -sf "$BASE/api/books/search?title=Alfa&size=20"
run_case create curl -sf -X POST "$BASE/api/books" -H 'Content-Type: application/json' \
  -d "{\"authorId\":42,\"title\":\"Verificacao\",\"isbn\":\"9$(date +%s%N | cut -c1-12)\",\"publicationYear\":2000,\"price\":10.00}"
# O título carrega um valor distinto a cada execução. Hibernate e EF Core fazem verificação
# de sujeira (dirty checking) e SUPRIMEM o UPDATE quando os valores enviados são iguais aos
# já gravados — reexecutar com um corpo fixo contaria 1 consulta em vez de 2 e acusaria uma
# falha inexistente. O perfil de carga da seção 9 sorteia os valores, de modo que a
# supressão não ocorre durante a coleta.
run_case update curl -sf -X PUT "$BASE/api/books/1234" -H 'Content-Type: application/json' \
  -d "{\"title\":\"Verificacao $(date +%s%N | tail -c 7)\",\"publicationYear\":2000,\"price\":10.00}"

echo
echo "plano de execucao da busca por prefixo — esperado Index Scan using idx_books_title,"
echo "com Index Cond de limites de prefixo e SEM no de ordenacao (Sort):"
docker exec "$PG" psql -q -U bench -d tccbench \
  -c "EXPLAIN SELECT b.* FROM books b JOIN authors a ON a.id=b.author_id WHERE b.title LIKE 'Alfa%' ORDER BY b.title LIMIT 20;"

exit "$FAILED"
