# Aparato experimental — TCC

Análise comparativa multicritério de frameworks back-end. Este repositório contém o
contrato único da API de referência, o ambiente controlado, o gerador de carga e as
implementações.

```
docs/especificacao-funcional-api.md   contrato único das cinco implementações (Apêndice)
docs/versoes-e-configuracao.md        versões, decisões de configuração e divergências
infra/schema.sql                      DDL — criado por SQL puro, nunca por migrations
infra/seed.sql                        carga semente determinística (1.000 autores / 200.000 livros)
infra/docker-compose.yml              PostgreSQL 16 + um profile por framework
infra/reset-db.sh                     restauração ao estado semente, antes de cada repetição
k6/contract-test.js                   critério de aceite 8.1 — equivalência de contrato
scripts/compare-fingerprints.sh       critério de aceite 8.1 — mesmos registros nos cinco
k6/load-test.js                       script único de carga, idêntico para os cinco
scripts/verify-queries.sh             critério de aceite 8.2 — equivalência do plano de acesso
scripts/collect-versions.sh           registro das versões exatas para o Apêndice
scripts/count-sloc.sh                 métrica de produtividade (seção 7) — SLOC-A e SLOC-B
scripts/verify-warmup.sh              critério de aceite 8.3 — estabilidade sob aquecimento
scripts/run-capacity.sh               teste de capacidade — patamares de taxa de chegada
scripts/common.sh                     rotinas comuns do protocolo de coleta
scripts/analyze-capacity.py           curva latência × taxa, capacidade e C_min
scripts/analyze-experiment.py         médias com IC 95%, CV e diferenças entre frameworks
scripts/stats_util.py                 t de Student e Welch, sem dependências externas
scripts/analyze-warmup.py             análise das séries do critério 8.3
scripts/k6-run.sh                     executa o k6 em contêiner, na rede dos serviços
scripts/run-experiment.sh             campanha completa de um framework
apps/spring-boot/                     implementação de referência
apps/{django,nestjs,laravel,aspnet}/  demais implementações
```

## Sequência de uso

```bash
# 1. banco de dados (permanece ativo durante toda a campanha)
docker compose -f infra/docker-compose.yml up -d postgres

# 2. subir um framework
docker compose -f infra/docker-compose.yml --profile springboot up -d --build
# ao trocar de framework, remova apenas o serviço da aplicação — `down` derrubaria
# também o PostgreSQL e destruiria a base:
#   docker compose -f infra/docker-compose.yml --profile springboot rm -sf springboot

# 3. critérios de aceite — obrigatórios antes de qualquer coleta
k6 run -e BASE_URL=http://localhost:8080 -e FW=springboot k6/contract-test.js
./scripts/verify-queries.sh springboot
./scripts/compare-fingerprints.sh   # roda os cinco e confronta os fingerprints

# 4. campanha: 3 níveis de carga x 10 repetições
RATES="..." DURATION=300s ./scripts/run-experiment.sh
```

O passo 3 é o que sustenta, perante a banca, a afirmação de que a especificação funcional
da API foi mantida constante entre os tratamentos. Nenhum dado coletado antes de os cinco
`fingerprint-*.json` serem idênticos entre si tem validade comparativa.

## Ordem de implementação sugerida

Spring Boot (referência) → ASP.NET Core → NestJS → Django → Laravel. Os dois primeiros
compartilham o modelo de ORM com rastreamento de entidades, o que torna a tradução direta;
Django e Laravel exigem atenção redobrada ao número de consultas por requisição, por
carregarem associações de forma tardia por padrão.

## Licença

[MIT](LICENSE) — © 2026 David Silva.

As dependências de cada implementação mantêm as próprias licenças. Nenhuma é redistribuída
neste repositório: são instaladas na construção das imagens, a partir dos arquivos de
bloqueio versionados.
