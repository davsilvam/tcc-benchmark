#!/usr/bin/env bash
# Teste de capacidade (seção 3.4 da monografia).
#
#   STEP=25 STEP_S=30 ./scripts/run-capacity.sh              # os cinco
#   STEP=25 STEP_S=30 REPS=3 ./scripts/run-capacity.sh aspnet
#
# Eleva a taxa de chegada em patamares — START, START+STEP, START+2·STEP… req/s —, cada um
# mantido por STEP_S segundos, até que um patamar viole a definição de capacidade utilizável:
#   (i)   percentil 95 da latência igual ou acima de P95_MAX ms   (só se P95_MAX for dado)
#   (ii)  taxa de erro de 1% ou mais
#   (iii) qualquer iteração descartada pelo gerador (dropped_iterations > 0)
# ou até MAX_RATE. Sem P95_MAX — como no estudo-piloto, que existe justamente para fundamentar
# esse teto —, a subida continua até (ii), (iii) ou P95_SAFETY, e o resultado é a curva
# latência × taxa completa, da qual o teto pode ser derivado.
#
# Cada patamar é uma invocação do k6 com executor constant-arrival-rate, na sequência e sem
# reiniciar o contêiner. A alternativa de um único ramping-arrival-rate foi descartada por um
# motivo prático: o k6 só reporta dropped_iterations como total do teste, e o critério (iii)
# precisa dele POR PATAMAR. Com uma invocação por patamar, cada resumo traz o seu. O custo é
# um intervalo de cerca de 1 s entre patamares, enquanto o k6 inicia.
#
# A subida tem DOIS ESTÁGIOS, na MESMA sessão de carga:
#
#   grosso  passo STEP, de START até a primeira violação;
#   fino    passo FINE_STEP (padrão STEP/4), dentro do intervalo (último sustentado, violado).
#
# A resolução do procedimento deixa de ser ±STEP/2 e passa a ±FINE_STEP/2. O estágio fino NÃO
# derruba o contêiner nem restaura a base: continua de onde o grosso parou. Isso é deliberado
# e tem duas razões. A primeira é de custo — um segundo estágio com derrubada pagaria outro
# aquecimento por repetição, o que domina o orçamento quando o aquecimento é longo. A segunda
# é de validade: a base cresce ao longo da subida (ver a nota sobre livros_ao_final abaixo), de
# modo que um estágio fino partindo da semente mediria os patamares refinados sobre uma base
# MENOR do que aquela em que a violação foi observada, e o número refinado não seria comparável
# ao grosso que selecionou o intervalo.
#
# Antes do primeiro patamar há um aquecimento de WARMUP_DURATION na taxa START, pelas mesmas
# razões do teste de carga fixa: sem ele, os primeiros patamares do Spring Boot e do
# ASP.NET Core mediriam compilação em tempo de execução, e o teto de latência poderia ser
# violado logo no início por um efeito que nada tem a ver com capacidade.
#
# A base NÃO é restaurada entre patamares — só antes de cada repetição —, porque a subida é
# uma única sessão contínua de carga.
#
# As repetições são INTERCALADAS, e não conduzidas em bloco: a repetição n de todos os
# frameworks termina antes que a n+1 comece, e a ordem dentro de cada rodada é sorteada com a
# semente ORDER_SEED. O piloto de 25/09/2026 mostrou por que isso importa justamente aqui: o
# Laravel sustentou 200 req/s medido em quarta posição, após cerca de vinte minutos de carga
# contínua, e 300 req/s em três de três execuções quando medido em sessão dedicada. Como a
# menor capacidade observada define as taxas de todo o teste de carga fixa, um viés de ordem
# nesta etapa se propagaria a toda a campanha.
#
# A semente padrão difere da do run-experiment.sh de propósito: se as duas fossem iguais, a
# rodada n do teste de capacidade e a rodada n da campanha usariam a mesma ordem, e um
# eventual efeito de posição se alinharia entre os dois testes em vez de se distribuir.
#
# Retomada: cada par (framework, repetição) tem seu próprio CSV, e um CSV que já contenha a
# linha "# fim" é considerado concluído e pulado. A ordem sorteada é reproduzida pela semente,
# de modo que uma execução interrompida no meio de uma rodada retoma a mesma sequência.
#
# Resultado: results/capacity/<framework>_repNN.csv, uma linha por patamar, com a coluna
# `estagio` em grosso/fino, e ordem.csv com a ordem sorteada de cada rodada. As linhas do
# estágio fino têm taxa MENOR que a do patamar violado, então o arquivo não está em ordem
# crescente de taxa — o analisador ordena antes de aplicar a definição. Análise:
#   python scripts/analyze-capacity.py [--p95-max X]
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source scripts/common.sh
require_postgres || exit 1

: "${STEP:?informe STEP (Y), incremento da taxa entre patamares em req/s}"
: "${STEP_S:?informe STEP_S (Z), duração de cada patamar em segundos}"
# Passo do estágio fino. FINE_STEP=$STEP desliga o refinamento e reproduz a subida de passo
# único — é o que faz o script reler o piloto de 25/09/2026 nos mesmos termos em que foi medido.
FINE_STEP="${FINE_STEP:-$((STEP / 4))}"
[ "$FINE_STEP" -lt 1 ] && FINE_STEP=1
# FINE_STEP TEM de dividir STEP. Se nao dividir, o ultimo patamar fino nao alcanca a borda
# superior do intervalo e a capacidade e reportada na borda inferior, de modo que a resolucao
# declarada de +-FINE_STEP/2 passa a excluir o valor verdadeiro. Exemplo real: STEP=100,
# FINE_STEP=30 e capacidade verdadeira de 1450 devolvem 1430 "+-15", intervalo que nao contem
# 1450. Erro em vez de aviso porque a execucao custa horas e o defeito e silencioso no CSV.
if [ $((STEP % FINE_STEP)) -ne 0 ]; then
  echo "erro: FINE_STEP=$FINE_STEP nao divide STEP=$STEP — a resolucao declarada de" >&2
  echo "       +-FINE_STEP/2 seria falsa. Use um divisor de $STEP, ou FINE_STEP=$STEP para" >&2
  echo "       desligar o estagio fino." >&2
  exit 1
fi
START="${START:-$STEP}"
MAX_RATE="${MAX_RATE:-5000}"
P95_MAX="${P95_MAX:-}"
P95_SAFETY="${P95_SAFETY:-5000}"
REPS="${REPS:-1}"
ORDER_SEED="${ORDER_SEED:-20260925}"
WARMUP_DURATION="${WARMUP_DURATION:-150s}"
OUT="${OUT:-results/capacity}"

if [ "$#" -gt 0 ]; then FRAMEWORKS=("$@"); else FRAMEWORKS=("${ALL_FRAMEWORKS[@]}"); fi

# O SEGMENT do patamar ocupa dois dígitos do ISBN (ver newIsbn em k6/load-test.js); 0 e 1
# são do aquecimento e da medição, de modo que restam os segmentos 2 a 99. O teto vale para a
# soma dos dois estágios, porque a base não é restaurada entre patamares e dois patamares com
# o mesmo SEGMENT gerariam o mesmo ISBN, colidindo na chave única.
MAX_SEGMENT=99
MAX_STEPS=90

mkdir -p "$OUT"
# O k6 roda em conteiner com apenas $ROOT montado em /work (ver scripts/k6-run.sh) e escreve
# o RESULT_FILE de dentro dele. Um OUT fora do repositorio nao existe no conteiner: o k6 falha
# ao gravar o resumo, todo patamar volta como k6_sem_resultado e a execucao inteira se perde.
# Verificar aqui custa nada e evita descobrir isso depois de cinco frameworks.
OUT_ABS="$(cd "$OUT" && pwd)"
case "$OUT_ABS/" in
  "$ROOT"/*) : ;;
  *)
    echo "erro: OUT=$OUT resolve para $OUT_ABS, fora de $ROOT." >&2
    echo "       O k6 e conteinerizado e so ve o repositorio; use um caminho interno," >&2
    echo "       por exemplo OUT=results/capacity." >&2
    exit 1
    ;;
esac
[ -f "$OUT/ordem.csv" ] || echo "repeticao,posicao,framework" > "$OUT/ordem.csv"
{
  echo "iniciado_em=$(date -Is)"
  echo "start=$START step=$STEP fine_step=$FINE_STEP step_s=$STEP_S max_rate=$MAX_RATE"
  echo "p95_max=${P95_MAX:-nao_informado} p95_safety=$P95_SAFETY reps=$REPS"
  echo "order_seed=$ORDER_SEED"
  echo "warmup=$WARMUP_DURATION@${START}rps frameworks=${FRAMEWORKS[*]}"
} >> "$OUT/parametros.txt"

# Embaralhamento determinístico: a mesma semente produz a mesma ordem, e a ordem usada fica
# gravada de qualquer forma em ordem.csv.
shuffle() {
  python -c "import random,sys; r=random.Random(int(sys.argv[1])); l=sys.argv[2:]; r.shuffle(l); print(' '.join(l))" "$@"
}

# Lê o resumo de um patamar e decide se a subida continua.
# Saída: ESTADO|VIOLAÇÃO|linha_csv, com ESTADO em SEGUE, PARA ou ERRO.
avaliar_patamar() {
  python - "$1" "$P95_MAX" "$P95_SAFETY" <<'PY'
import io, json, sys
try:
    r = json.load(io.open(sys.argv[1], encoding='utf-8'))['row']
except Exception:
    print('ERRO|k6_sem_resultado|')
    raise SystemExit
p95_max = float(sys.argv[2]) if sys.argv[2] else None
safety = float(sys.argv[3])
csv = '%d,%.2f,%.2f,%.2f,%.6f,%d,%s' % (
    r['rateTarget'], r['achievedRps'], r['latencyP95Ms'], r['latencyAvgMs'],
    r['errorRate'], r['droppedIterations'], r['vusMaxUsed'])
viol = []
if p95_max is not None and r['latencyP95Ms'] >= p95_max:
    viol.append('p95>=%g' % p95_max)
if r['errorRate'] >= 0.01:
    viol.append('erro>=1%')
if r['droppedIterations'] > 0:
    viol.append('descartadas')
if not viol and r['latencyP95Ms'] >= safety:
    viol.append('p95>=seguranca')
print('%s|%s|%s' % ('PARA' if viol else 'SEGUE', '+'.join(viol) or '-', csv))
PY
}

# Mede um patamar e registra a linha. Le os globais fw, rep, csv, json e seg; escreve os
# globais estado, violacao e dados, e avanca seg. O SEGMENT e um contador corrido sobre os
# dois estagios, e nao o indice do laco, justamente porque o estagio fino acrescenta patamares.
medir_patamar() {
  local taxa="$1" estagio="$2"
  rm -f "$json"
  k6_run -q -e BASE_URL="$(service_url "$fw")" -e RATE="$taxa" -e DURATION="${STEP_S}s" \
    -e RUN_ID="$rep" -e SEGMENT="$seg" -e RESULT_FILE="$json" k6/load-test.js \
    >/dev/null
  seg=$((seg + 1))

  IFS='|' read -r estado violacao dados <<< "$(avaliar_patamar "$json")"
  [ "$estado" = "ERRO" ] && return 0

  echo "$dados,$estagio" >> "$csv"
  echo "$dados" | awk -F, -v e="$estagio" '{printf "  %5d req/s  obtida=%.0f  p95=%.1f ms  erro=%.2f%%  descartadas=%-5s %s\n", $1, $2, $3, $5*100, $6, e}'
}

# Execucoes que terminaram sem medicao valida. Nao sao resultado: sao falha, e o script
# precisa dizer isso no codigo de saida, porque um "concluido" com codigo 0 sobre cinco
# execucoes vazias e indistinguivel de um experimento bem-sucedido.
falhas=()

# Interrupção limpa. Matar o processo do script NÃO mata o que ele deixou rodando: o
# contêiner da aplicação fica de pé, e o `docker run` do k6 vira órfão de PPID 1 e segue
# executando o patamar, porque quem o executa é o daemon e não o cliente. Em 06/10/2026
# isso deixou a máquina com 476% de CPU ocupada vários minutos depois de o experimento
# ter sido mandado parar.
limpar() {
  local st=$?
  trap - EXIT INT TERM
  [ -n "${fw:-}" ] && app_down "$fw" >/dev/null 2>&1
  local img="${K6_IMAGE:-grafana/k6:2.2.0}"
  docker ps -q --filter "ancestor=$img" 2>/dev/null | xargs -r docker rm -f >/dev/null 2>&1
  exit "$st"
}
trap limpar EXIT INT TERM

for rep in $(seq 1 "$REPS"); do
  read -r -a ORDER <<< "$(shuffle "$((ORDER_SEED * 1000 + rep))" "${FRAMEWORKS[@]}")"
  if ! grep -q "^$rep," "$OUT/ordem.csv"; then
    pos=1
    for fw in "${ORDER[@]}"; do echo "$rep,$pos,$fw" >> "$OUT/ordem.csv"; pos=$((pos + 1)); done
  fi
  echo "### rodada $rep — ordem: ${ORDER[*]}"

  for fw in "${ORDER[@]}"; do
    tag="${fw}_rep$(printf '%02d' "$rep")"
    csv="$OUT/$tag.csv"
    if [ -s "$csv" ] && grep -q '^# fim' "$csv" && ! grep -q 'SEM MEDICAO' "$csv"; then
      echo "=== $tag — já medido, pulando"
      continue
    fi
    echo "=== $tag"

    # O banco é verificado a cada célula, e não só no início do script. Se ele cair no meio
    # de uma execução de horas, a aplicação passa a devolver erro e o k6 grava um resumo
    # perfeitamente válido dizendo que 100% das requisições falharam. Sem esta verificação
    # isso é lido como violação do critério (ii) e registrado como capacidade abaixo de START,
    # que foi o que ocorreu em 30/09/2026 na primeira tentativa do NestJS com Z=60 s.
    if ! require_postgres; then
      falhas+=("$tag: banco indisponível antes da execução")
      continue
    fi
    echo "rate_target,achieved_rps,p95_ms,avg_ms,error_rate,dropped,vus_max_used,estagio" > "$csv"

    reset_db
    app_up "$fw"
    if ! wait_health "$fw"; then
      app_down "$fw"
      falhas+=("$tag: aplicação não ficou pronta")
      continue
    fi

    k6_run -q -e BASE_URL="$(service_url "$fw")" -e RATE="$START" \
      -e DURATION="$WARMUP_DURATION" -e WARMUP=1 -e RUN_ID="$rep" k6/load-test.js

    motivo="max_rate"
    json="$OUT/.$tag.step.json"
    seg=2
    ultimo_ok=0
    violado=0
    estado=""; violacao=""; dados=""

    # A subida só para quando DOIS patamares consecutivos violam. Uma violação isolada é
    # tratada como transitória e a subida prossegue, registrando-a.
    #
    # A razão está nos dados de 30/09/2026. Quatro dos cinco frameworks param por saturação
    # inequívoca: latência duas a três ordens de grandeza acima do teto e milhares de iterações
    # descartadas. O NestJS parava com p95 de 101 ms, um milissegundo acima do teto, e ZERO
    # descartes, voltando a 8 ms no patamar seguinte. Sem confirmação, o que se mede nele não é
    # capacidade, e sim a taxa em que o primeiro transitório esporádico calha de cruzar o teto —
    # uma grandeza que depende do comprimento do patamar. Daí a capacidade dele cair de 1.575
    # req/s com patamares de 20 s para 1.000 com patamares de 60 s, e o coeficiente de variação
    # subir de 0,7% para 12%, enquanto os outros quatro mal se movem.
    #
    # `pendente` guarda a taxa de uma violação ainda não confirmada; `violado` recebe a PRIMEIRA
    # do par confirmado, que é a borda superior do intervalo a refinar.
    pendente=0
    transitorios=""

    # Estagio grosso: passo STEP ate a primeira violacao confirmada.
    for i in $(seq 0 $((MAX_STEPS - 1))); do
      taxa=$((START + i * STEP))
      if [ "$taxa" -gt "$MAX_RATE" ]; then motivo="max_rate"; break; fi
      if [ "$seg" -gt "$MAX_SEGMENT" ]; then motivo="limite_de_segmentos"; break; fi

      medir_patamar "$taxa" grosso
      if [ "$estado" = "ERRO" ]; then motivo="$violacao"; break; fi

      if [ "$estado" = "PARA" ]; then
        if [ "$pendente" -gt 0 ]; then
          motivo="$violacao"
          violado="$pendente"
          break
        fi
        pendente="$taxa"
        echo "    (violação em $taxa req/s ainda não confirmada; medindo o próximo patamar)"
      else
        if [ "$pendente" -gt 0 ]; then
          echo "    (a violação em $pendente req/s não se confirmou: transitória)"
          transitorios="$transitorios $pendente"
          pendente=0
        fi
        ultimo_ok="$taxa"
      fi
      [ "$i" -eq $((MAX_STEPS - 1)) ] && motivo="limite_de_patamares"
    done

    # Estagio fino: refina (ultimo_ok, violado) com passo FINE_STEP, sem derrubar o conteiner e
    # sem restaurar a base. So corre se o grosso localizou um intervalo: se a violacao veio ja
    # no primeiro patamar, nao ha intervalo a refinar, e a capacidade fica abaixo de START.
    if [ "$violado" -gt 0 ] && [ "$ultimo_ok" -gt 0 ] && [ "$FINE_STEP" -lt "$STEP" ]; then
      echo "  --- refinando ($ultimo_ok, $violado) com passo $FINE_STEP"
      pendente=0
      taxa=$((ultimo_ok + FINE_STEP))
      while [ "$taxa" -lt "$violado" ]; do
        if [ "$seg" -gt "$MAX_SEGMENT" ]; then motivo="limite_de_segmentos"; break; fi
        medir_patamar "$taxa" fino
        if [ "$estado" = "ERRO" ]; then motivo="$violacao"; break; fi

        if [ "$estado" = "PARA" ]; then
          if [ "$pendente" -gt 0 ]; then
            motivo="fino:$violacao"
            break
          fi
          pendente="$taxa"
          echo "    (violação em $taxa req/s ainda não confirmada; medindo o próximo patamar)"
        else
          if [ "$pendente" -gt 0 ]; then
            echo "    (a violação em $pendente req/s não se confirmou: transitória)"
            transitorios="$transitorios $pendente"
            pendente=0
          fi
          ultimo_ok="$taxa"
        fi
        taxa=$((taxa + FINE_STEP))
      done
      # Saiu do laço com violação pendente: o patamar `violado`, já medido e violando, é o
      # patamar consecutivo seguinte e serve de confirmação.
      if [ "$pendente" -gt 0 ] && [ "$motivo" != "fino:$violacao" ]; then
        motivo="fino:confirmado_por_$violado"
      fi
    fi

    [ -n "$transitorios" ] && echo "# transitorios=$transitorios (violaram sem confirmacao)" >> "$csv"
    rm -f "$json"
    # A base NÃO é restaurada entre patamares, e 20% das requisições são inserções: nos
    # patamares altos isso acrescenta linhas à tabela `books`, de modo que parte da variação
    # de latência ao longo da subida pode refletir o crescimento da base. O volume final é
    # registrado para que o efeito seja quantificado, e não suposto.
    livros="$(docker exec "${PG_CONTAINER:-tcc-postgres}" psql -tA -U bench -d tccbench       -c 'SELECT count(*) FROM books;' 2>/dev/null | tr -d '[:space:]')"
    echo "# livros_ao_final=$livros (semente=200000)" >> "$csv"
    # Determinacao do proprio script, sob os criterios ativos nesta execucao; com P95_MAX
    # ausente ela nao incorpora o teto X, e o analisador continua sendo a fonte autoritativa.
    # awk, e nao $((FINE_STEP / 2)): a divisao inteira do shell registraria +-12 para um
    # passo fino de 25, e a resolucao declarada na metodologia e +-FINE_STEP/2 = +-12,5.
    resolucao="$(awk -v f="$FINE_STEP" 'BEGIN { printf "%.1f", f / 2 }')"
    if [ -z "$livros" ]; then
      # A contagem de livros falhou: o banco sumiu durante a execução. Tudo o que foi medido
      # a partir daí é erro de ambiente, não comportamento do framework.
      echo "# SEM MEDICAO — banco indisponível durante a execução" >> "$csv"
      echo "  SEM MEDIÇÃO: o banco ficou indisponível durante a execução" >&2
      falhas+=("$tag: banco caiu durante a execução")
    elif [ "$motivo" = "k6_sem_resultado" ]; then
      # O gerador nao produziu resumo: nada foi medido. Isso NAO e "capacidade abaixo de
      # START" — as duas situacoes escreveriam a mesma linha, e so o motivo as separa. Sem a
      # marca explicita, um log lido depois nao as distingue.
      echo "# SEM MEDICAO — falha de instrumento, nenhum patamar avaliado" >> "$csv"
      echo "  SEM MEDIÇÃO: o k6 não produziu resultado; nada foi medido" >&2
      falhas+=("$tag: $motivo")
    elif [ "$ultimo_ok" -eq 0 ]; then
      # Nem o primeiro patamar se sustentou: o que se sabe e que a capacidade fica abaixo de
      # START, e nao que seja zero. A resolucao do estagio fino nao se aplica, porque ele nao
      # correu — nao havia intervalo a refinar.
      echo "# capacidade_observada=<$START (nenhum patamar sustentado)" >> "$csv"
      echo "  capacidade < $START req/s  parada: $motivo"
    else
      echo "# capacidade_observada=$ultimo_ok (resolucao=+-$resolucao)" >> "$csv"
      echo "  capacidade=$ultimo_ok req/s  parada: $motivo"
    fi
    echo "# fim motivo=$motivo" >> "$csv"

    app_down "$fw"
  done
done

if [ "${#falhas[@]}" -gt 0 ]; then
  echo >&2
  echo "FALHOU: ${#falhas[@]} execução(ões) sem medição válida, de $((${#FRAMEWORKS[@]} * REPS)):" >&2
  for f in "${falhas[@]}"; do echo "  - $f" >&2; done
  echo "Os CSVs correspondentes estão marcados com SEM MEDICAO e serão refeitos na retomada." >&2
  exit 1
fi

echo "concluído: $OUT  (analisar com: python scripts/analyze-capacity.py)"
