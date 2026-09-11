#!/usr/bin/env bash
# Executa o k6 em contêiner, na mesma rede dos contêineres de aplicação.
#
#   ./scripts/k6-run.sh -e BASE_URL=http://django:8080 k6/contract-test.js
#
# Por que não no host: o gerador de carga não pode ter, ele próprio, um limite mais estreito
# que o do sistema medido. Executando no Windows, o k6 esgotava as 16.384 portas efêmeras do
# host em cerca de 14 s sob 1.200 req/s, e os sockets em TIME_WAIT (120 s no padrão do
# Windows) contaminavam as execuções SEGUINTES — ver a seção 9.3 de
# docs/versoes-e-configuracao.md. Em contêiner o k6 tem espaço de nomes de rede próprio,
# com faixa de portas completa, e a pilha TCP do Windows sai do caminho da medição.
#
# Consequência para quem chama: o endereço de destino é o NOME DO SERVIÇO na rede do
# compose (http://django:8080), e não http://localhost:8080.
set -uo pipefail

export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Versão fixada: a mesma registrada em results/versions/infra.txt. Deixá-la flutuante
# significaria trocar de instrumento de medida no meio da campanha.
K6_IMAGE="${K6_IMAGE:-grafana/k6:2.2.0}"
NETWORK="${K6_NETWORK:-tcc-bench_bench}"

exec docker run --rm -i \
  --network "$NETWORK" \
  -v "$ROOT:/work" -w /work \
  --entrypoint k6 \
  "$K6_IMAGE" run "$@"
