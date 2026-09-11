#!/usr/bin/env bash
# Registro das versões exatas — pendências 1 e 2 da seção 10 da especificação funcional.
#
# Extrai as versões DIRETAMENTE dos gerenciadores de dependência, e não de anotações
# manuais: o Apêndice da monografia deve reproduzir o que de fato foi executado. Rodar
# imediatamente antes da campanha de coleta.
#
#   ./scripts/collect-versions.sh            # todos
#   ./scripts/collect-versions.sh springboot # apenas um
set -uo pipefail

# Sem isto, o Git Bash do Windows converte os caminhos internos do contêiner (-w /p) em
# caminhos Windows (P:/) e o docker run falha.
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/results/versions"
mkdir -p "$OUT"

if [ "$#" -gt 0 ]; then
  FRAMEWORKS=("$@")
else
  FRAMEWORKS=(springboot django nestjs laravel aspnet)
fi

header() {
  printf '=== %s ===\n' "$1"
}

collect_springboot() {
  header "runtime"
  docker run --rm -v "$ROOT/apps/spring-boot:/p" -w /p maven:3.9-eclipse-temurin-25 \
    sh -c 'java -version 2>&1; mvn -v 2>&1 | head -1'
  header "dependencias resolvidas (mvn dependency:list)"
  # sem -q: com -q o plugin dependency:list não imprime as linhas [INFO] da árvore
  docker run --rm -v "$ROOT/apps/spring-boot:/p" -w /p maven:3.9-eclipse-temurin-25 \
    mvn -B dependency:list -DincludeScope=runtime 2>/dev/null \
    | sed -n 's/^\[INFO\][[:space:]]\{3,\}\([a-z][a-zA-Z0-9._-]*:[^:]*:.*\)$/\1/p' | sort -u
}

collect_django() {
  header "runtime"
  docker run --rm --entrypoint sh tcc-bench-django -c 'python --version; nginx -v 2>&1'
  header "dependencias instaladas (pip freeze)"
  docker run --rm --entrypoint sh tcc-bench-django -c 'pip freeze'
}

collect_nestjs() {
  header "runtime"
  docker run --rm --entrypoint sh tcc-bench-nestjs -c 'node --version; npm --version'
  header "dependencias instaladas (npm list --omit=dev)"
  docker run --rm --entrypoint sh tcc-bench-nestjs -c 'npm list --omit=dev --depth=0 2>/dev/null'
}

collect_laravel() {
  header "runtime"
  docker run --rm --entrypoint sh tcc-bench-laravel -c 'php -v | head -2; nginx -v 2>&1'
  header "extensoes PHP carregadas"
  docker run --rm --entrypoint sh tcc-bench-laravel -c 'php -m | tr "\n" " "'
  header "dependencias instaladas (composer show)"
  docker run --rm --entrypoint sh tcc-bench-laravel -c 'cd /app && composer show --no-dev 2>/dev/null'
}

collect_aspnet() {
  header "runtime"
  docker run --rm --entrypoint sh tcc-bench-aspnet -c 'dotnet --info | head -12'
  header "pacotes (dotnet list package --include-transitive)"
  docker run --rm -v "$ROOT/apps/aspnet:/p" -w /p mcr.microsoft.com/dotnet/sdk:10.0 \
    sh -c 'DOTNET_NOLOGO=1 dotnet list package --include-transitive 2>/dev/null'
}

collect_infra() {
  {
    header "PostgreSQL"
    docker exec tcc-postgres psql -tA -U bench -d tccbench -c 'SELECT version();' 2>/dev/null \
      || echo 'conteiner tcc-postgres nao esta ativo'
    header "PostgreSQL — agrupamento e parametros relevantes"
    docker exec tcc-postgres psql -U bench -d tccbench -c \
      "SELECT name, setting FROM pg_settings WHERE name IN
       ('server_version','lc_collate','shared_buffers','max_connections','log_statement');" 2>/dev/null
    header "k6"
    k6 version 2>&1 || echo 'k6 nao encontrado no PATH'
    header "cloc"
    cloc --version 2>&1 || echo 'cloc nao encontrado no PATH — usar: docker run --rm -v "$PWD:/t" aldanial/cloc --version'
    header "Docker"
    docker --version
    header "coletado em"
    date -Is
  } > "$OUT/infra.txt" 2>&1
  echo "  infra      -> results/versions/infra.txt"
}

for fw in "${FRAMEWORKS[@]}"; do
  case "$fw" in
    springboot|django|nestjs|laravel|aspnet) ;;
    *) echo "framework desconhecido: $fw" >&2; continue ;;
  esac
  "collect_$fw" > "$OUT/$fw.txt" 2>&1
  printf '  %-10s -> results/versions/%s.txt\n' "$fw" "$fw"
done

collect_infra

echo
echo "Contagem SLOC (secao 7), com a versao do cloc registrada acima:"
echo "  docker run --rm -v \"\$PWD/apps:/t\" aldanial/cloc --quiet \\"
echo "    --exclude-dir=node_modules,vendor,target,bin,obj,dist \\"
echo "    --not-match-f='(package-lock\\.json|composer\\.lock)' /t/<framework>"
