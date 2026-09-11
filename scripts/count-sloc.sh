#!/usr/bin/env bash
# Métrica de produtividade — seção 7 da especificação funcional.
#
#   ./scripts/count-sloc.sh
#
# Produz as DUAS contagens exigidas pela seção 7:
#
#   SLOC-A  todo o projeto, incluindo o scaffolding gerado que permanece — sob o argumento
#           de que o volume de código que um framework impõe ao projeto é, ele próprio,
#           característica do framework.
#   SLOC-B  apenas o que o desenvolvedor escreveu ou modificou, excluindo o scaffolding
#           intocado.
#
# As listas em results/sloc/ foram DERIVADAS por comparação byte a byte (sha256) com o
# scaffold regerado pela mesma ferramenta e versão — não por julgamento:
#
#   scaffolding-<fw>.txt  arquivos idênticos ao scaffold: gerados e nunca tocados
#   autoria-<fw>.txt      arquivos ausentes do scaffold ou com conteúdo diferente
#
# A única exceção é o Spring Boot, cujo projeto já existia no repositório e para o qual não
# há scaffold original a comparar; o cabeçalho daqueles arquivos registra a ressalva.
#
# As DUAS contagens passam pelo mesmo mecanismo — uma lista explícita de arquivos, via
# --list-file. Não é preciosismo: o cloc IGNORA --not-match-f e --exclude-lang quando
# recebe --list-file, de modo que misturar os dois mecanismos daria a A e a B corpora
# diferentes por motivos invisíveis. Com listas explícitas, A e B diferem apenas pela
# subtração do scaffolding, e ambas ficam auditáveis em results/sloc/.
#
# Regras de exclusão, todas fixadas ANTES de qualquer contagem, conforme a seção 7:
#   - diretórios de dependências e de saída de compilação
#   - arquivos de bloqueio de dependências (package-lock.json, composer.lock)
#   - Dockerfile, .dockerignore e entrypoint.sh (orquestração)
#   - arquivos de controle de versão e de editor
#   - Markdown: a seção 7 conta código-fonte e configuração escrita à mão, e prosa não é
#     nem uma coisa nem outra
#   - robots.txt e demais ativos estáticos de scaffolding
#
# Permanecem contabilizados, por exigência explícita da seção 7:
#   - configuração do servidor de aplicação: gunicorn.conf.py, nginx.conf, php-fpm.conf,
#     php.ini
#   - configuração da aplicação: application.yml, settings.py, appsettings.json, .env
#   - manifestos de dependências escritos à mão: pom.xml, package.json, composer.json,
#     BookApi.csproj, requirements.txt — contá-los em quatro ecossistemas e não no quinto
#     seria arbitrário
set -uo pipefail

# Sem isto, o Git Bash do Windows converte os caminhos internos do contêiner em caminhos
# Windows e o docker run falha.
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CLOC_IMAGE="${CLOC_IMAGE:-aldanial/cloc}"
OUT="results/sloc"
FRAMEWORKS=(springboot django nestjs laravel aspnet)

# nome do diretório em apps/ (difere do rótulo do framework apenas no Spring Boot)
dir_of() {
  case "$1" in
    springboot) echo 'spring-boot' ;;
    *) echo "$1" ;;
  esac
}

# Um único padrão para as duas contagens.
EXCLUDE='(/node_modules/|/vendor/|/target/|/dist/|/\.git/|/\.idea/|/obj/|/bin/|/(Dockerfile|\.dockerignore|\.gitignore|\.gitattributes|\.editorconfig|\.npmrc|entrypoint\.sh|package-lock\.json|composer\.lock|robots\.txt)$|\.tsbuildinfo$|\.md$)'

mkdir -p "$OUT"

{
  echo "=== cloc ==="
  docker run --rm "$CLOC_IMAGE" --version
  echo
  echo "=== regra de exclusão (seção 7) ==="
  echo "$EXCLUDE"
  echo
  echo "coletado em: $(date -Is)"
} > "$OUT/cloc-versao.txt" 2>&1

printf '%-12s %10s %10s %10s\n' framework SLOC-A SLOC-B 'A - B'
printf '%-12s %10s %10s %10s\n' ------------ ---------- ---------- ----------

for fw in "${FRAMEWORKS[@]}"; do
  d="$(dir_of "$fw")"

  # corpus de SLOC-A: tudo em apps/<framework>, menos as exclusões da seção 7
  find "apps/$d" -type f | tr -d '\r' | grep -vE "$EXCLUDE" | sort > "$OUT/corpus-a-$fw.txt"

  # corpus de SLOC-B: o de A, menos o scaffolding intocado
  grep -v '^#' "$OUT/scaffolding-$fw.txt" | sort > "$OUT/.scaf.tmp"
  comm -23 "$OUT/corpus-a-$fw.txt" "$OUT/.scaf.tmp" > "$OUT/corpus-b-$fw.txt"
  rm -f "$OUT/.scaf.tmp"

  for variante in a b; do
    sed 's|^|/t/|' "$OUT/corpus-$variante-$fw.txt" > "$OUT/.list.tmp"
    docker run --rm -v "$ROOT:/t" "$CLOC_IMAGE" --quiet --force-lang=INI,conf \
      --list-file="/t/$OUT/.list.tmp" > "$OUT/sloc-$variante-$fw.txt" 2>&1
    rm -f "$OUT/.list.tmp"
  done

  a="$(awk '/^SUM:/ { print $NF }' "$OUT/sloc-a-$fw.txt")"
  b="$(awk '/^SUM:/ { print $NF }' "$OUT/sloc-b-$fw.txt")"
  a="${a:-0}"; b="${b:-0}"

  printf '%-12s %10s %10s %10s\n' "$fw" "$a" "$b" "$((a - b))"
done

echo
echo "Relatórios em $OUT/: sloc-a-*.txt e sloc-b-*.txt (cloc), corpus-a-*.txt e"
echo "corpus-b-*.txt (arquivos contados), cloc-versao.txt (versão e regra de exclusão)."
