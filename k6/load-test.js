// Script único de carga — TCC
// Executado sem alteração contra os cinco frameworks; apenas BASE_URL muda.
//
// MODELO ABERTO. As requisições chegam a uma taxa fixa (RATE, em requisições por segundo),
// independentemente da conclusão das anteriores — executor constant-arrival-rate. Cada
// iteração emite exatamente UMA requisição, de modo que a taxa de iterações é a taxa de
// requisições.
//
//   k6 run -e BASE_URL=http://springboot:8080 -e RATE=100 -e DURATION=300s \
//          -e RUN_ID=1 -e RESULT_FILE=results/x.json k6/load-test.js
//
// O mesmo script serve às quatro situações do protocolo; o que muda são as variáveis:
//   aquecimento        WARMUP=1            (resumo descartado)
//   medição            (padrão)
//   patamar do teste   SEGMENT=<n>         (scripts/run-capacity.sh)
//   de capacidade
//   verificação 8.3    BUCKET_S=10         (série temporal por intervalo)
//
// DURATION deve ser dada em segundos (ex.: 300s).

import exec from 'k6/execution';
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const RUN_ID = parseInt(__ENV.RUN_ID || '1', 10);
const IS_WARMUP = __ENV.WARMUP === '1';
const RESULT_FILE = __ENV.RESULT_FILE || 'summary.json';

// Constantes próprias, e não lidas de `options` dentro de handleSummary: no k6 v2 o objeto
// exportado é consolidado pelo motor antes do resumo, e `options.scenarios.load` chega
// indefinido — o que fazia handleSummary lançar exceção e o arquivo de resultado NÃO ser
// gravado.
const RATE = parseInt(__ENV.RATE || '0', 10);
const DURATION = __ENV.DURATION || (IS_WARMUP ? '150s' : '300s');
const DURATION_S = parseInt(DURATION, 10) || 0;

if (!(RATE > 0)) {
  throw new Error('RATE (requisições por segundo) é obrigatória no modelo aberto');
}

// Usuários virtuais disponíveis ao executor. No modelo aberto eles não definem a carga:
// são o reservatório do qual o k6 retira um usuário para cada chegada. Pela Lei de Little,
// o número em uso é taxa × tempo de resposta. Quando uma chegada não encontra usuário
// livre, o k6 a DESCARTA e a conta em dropped_iterations — o critério (iii) da definição de
// capacidade utilizável.
//
// A regra é a mesma para os cinco frameworks: teto de um segundo de fila à taxa
// configurada (MAX_VUS = RATE), com piso de 200. O descarte passa a significar, então, que
// o sistema sob teste manteve em andamento mais requisições do que a taxa de um segundo.
//
// TODO o teto é pré-alocado (PRE_VUS = MAX_VUS), e isso não é detalhe: com poucos usuários
// pré-alocados, o k6 aloca os que faltam DURANTE o teste, e as chegadas que ocorrem enquanto
// ele aloca são descartadas. Uma sondagem a 50 req/s com 20 pré-alocados descartou 28
// iterações usando só 48 dos 200 disponíveis — o critério (iii) mediria a velocidade de
// alocação do k6, e não o limite do framework. O custo da pré-alocação é baixo: 1.500
// usuários ocupam cerca de 285 MiB no contêiner do k6.
const MAX_VUS = parseInt(__ENV.MAX_VUS || String(Math.max(200, RATE)), 10);
const PRE_VUS = parseInt(__ENV.PRE_VUS || String(MAX_VUS), 10);

// SEGMENT identifica a invocação do k6 dentro de um mesmo estado da base. Duas invocações
// sobre a mesma base precisam gerar ISBN distintos (chave única) e sequências distintas de
// requisições — ver newIsbn() e seedFor().
const SEGMENT = parseInt(__ENV.SEGMENT || (IS_WARMUP ? '0' : '1'), 10);

// BUCKET_S ativa a marcação por INTERVALO DE TEMPO, usada apenas pela verificação de
// estabilidade sob aquecimento (critério 8.3). O resumo do k6 só produz agregados do teste
// inteiro; marcando cada requisição com o intervalo em que ocorreu e declarando um limiar
// por intervalo — que é o que faz o k6 materializar a sub-métrica —, o resumo passa a trazer
// http_req_duration{bucket:N} para cada N. Sem BUCKET_S, nada disso é avaliado.
const BUCKET_S = parseInt(__ENV.BUCKET_S || '0', 10);

function bucketThresholds() {
  if (BUCKET_S <= 0 || DURATION_S <= 0) return {};
  const out = {};
  for (let i = 0; i * BUCKET_S < DURATION_S; i += 1) {
    // limiar trivialmente satisfeito: materializa a sub-métrica, não reprova a execução
    out[`http_req_duration{bucket:${i}}`] = ['max>=0'];
    out[`http_req_failed{bucket:${i}}`] = ['rate>=0'];
  }
  return out;
}

export const options = {
  scenarios: {
    load: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: PRE_VUS,
      maxVUs: MAX_VUS,
      gracefulStop: '10s',
    },
  },
  discardResponseBodies: true,
  noConnectionReuse: false,
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: bucketThresholds(),
};

// --- Sequência determinística -----------------------------------------------------------
// No modelo aberto, a atribuição de iterações a usuários virtuais NÃO é determinística: o
// usuário que atende a chegada k depende de quais estavam livres naquele instante, o que
// depende do tempo de resposta do framework. Semear pelo usuário virtual daria a cada
// framework uma sequência diferente. A semente vem, por isso, do número GLOBAL da iteração
// no teste (exec.scenario.iterationInTest), atribuído na ordem das chegadas e independente
// do sistema sob teste, combinado com a repetição (RUN_ID) e com o SEGMENT.
//
// O gerador continua sendo o congruente linear MINSTD. A semente, porém, passa antes por uma
// função de mistura não linear: num gerador linear, sementes consecutivas produzem primeiras
// saídas em progressão aritmética módulo m, e a operação sorteada por `saída % 100` seguiria
// um padrão periódico em vez de uma distribuição 40/20/10/20/10.
//
// O SEGMENT na semente importa. Aquecimento e medição rodam sobre a mesma base, e se
// aplicassem a MESMA sequência, cada PUT da medição regravaria no mesmo livro os mesmos
// valores gravados pelo aquecimento. Hibernate e EF Core detectam que nada mudou e
// SUPRIMEM o UPDATE; Django e Eloquent, como implementados, o emitem sempre — uma assimetria
// de 1 contra 2 instruções SQL em 10% das requisições, apenas em dois tratamentos.
function mix32(x) {
  let h = x | 0;
  h = Math.imul(h ^ (h >>> 16), 0x7feb352d);
  h = Math.imul(h ^ (h >>> 15), 0x846ca68b);
  return (h ^ (h >>> 16)) >>> 0;
}

function seedFor(runId, segment, iteration) {
  let h = mix32(runId + 0x9e3779b9);
  h = mix32(h ^ (segment + 0x85ebca6b));
  h = mix32(h ^ iteration);
  return (h % 2147483646) + 1;
}

let rng = 1;

function nextInt(bound) {
  rng = (rng * 48271) % 2147483647;
  return rng % bound;
}

const WORDS = [
  'Alfa', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel',
  'India', 'Juliett', 'Kilo', 'Lima', 'Mike', 'November', 'Oscar', 'Papa',
  'Quebec', 'Romeo', 'Sierra', 'Tango', 'Uniform', 'Victor', 'Whiskey',
  'Xray', 'Yankee', 'Zulu', 'Ancora', 'Boreal', 'Cristal', 'Dunas',
  'Enigma', 'Farol', 'Granito', 'Horizonte', 'Inverno', 'Jangada',
  'Labirinto', 'Miragem', 'Nevoa', 'Oceano', 'Pantano', 'Quimera',
  'Recife', 'Solstice', 'Trovoada', 'Urutau', 'Vertigem', 'Wanderer',
  'Xisto', 'Zenite',
];

const SEED_BOOKS = 200000;
const SEED_AUTHORS = 1000;
const JSON_HEADERS = { headers: { 'Content-Type': 'application/json' } };

function pad(value, width) {
  return String(value).padStart(width, '0');
}

// `10 + n/100` produz valores como 11.120000000000001 em ponto flutuante binário: 5,26%
// dos 19.000 valores possíveis serializam com mais de duas casas decimais e são recusados
// com 400 pelas cinco implementações, que validam no máximo duas (seção 4.4). O
// arredondamento explícito mantém a carga dentro do contrato.
function money() {
  return Number((10 + nextInt(19000) / 100).toFixed(2));
}

// ISBN das escritas: '9' + SEGMENT (2 dígitos) + iteração global (10 dígitos). O dígito 9
// separa as escritas dos dados semente, que começam com 0. O SEGMENT separa as invocações do
// k6 que compartilham a mesma base — aquecimento e medição, ou os patamares do teste de
// capacidade —, porque cada invocação reinicia a numeração das iterações em zero e, sem
// ele, colidiria na chave única e devolveria 409.
function newIsbn(iteration) {
  return '9' + pad(SEGMENT, 2) + pad(iteration, 10);
}

export default function () {
  const iteration = exec.scenario.iterationInTest;
  rng = seedFor(RUN_ID, SEGMENT, iteration);

  if (BUCKET_S > 0) {
    // currentTestRunDuration é o tempo decorrido desde o início do teste, em ms
    exec.vu.tags.bucket = Math.floor(
      exec.instance.currentTestRunDuration / 1000 / BUCKET_S,
    );
  }

  // O rótulo `name` é obrigatório aqui, e não cosmético. Sem ele o k6 usa a URL inteira como
  // nome da série temporal, e as URLs de byId e de update carregam o id do livro: cada
  // requisição criaria uma série distinta. A 1.200 req/s por 60 s isso dá cerca de 21.600 URLs
  // únicas e, a nove métricas por conjunto de rótulos, mais de 200.000 séries — o k6 avisa
  // acima de 100.000 porque o consumo de memória cresce, e ele roda na mesma máquina que o
  // sistema sob teste. Pausas de coleta de lixo do próprio gerador entram na latência que ele
  // reporta, o que é indistinguível de latência do framework.
  const draw = nextInt(100);

  if (draw < 40) {
    const page = nextInt(200);
    const res = http.get(`${BASE}/api/books?page=${page}&size=20`, { tags: { endpoint: 'list', name: '/api/books?page&size' } });
    check(res, { 'list 200': (r) => r.status === 200 });

  } else if (draw < 60) {
    const id = 1 + nextInt(SEED_BOOKS);
    const res = http.get(`${BASE}/api/books/${id}`, { tags: { endpoint: 'byId', name: '/api/books/:id' } });
    check(res, { 'byId 200': (r) => r.status === 200 });

  } else if (draw < 70) {
    const title = WORDS[nextInt(WORDS.length)];
    const res = http.get(`${BASE}/api/books/search?title=${title}&size=20`, { tags: { endpoint: 'search', name: '/api/books/search?title&size' } });
    check(res, { 'search 200': (r) => r.status === 200 });

  } else if (draw < 90) {
    const body = JSON.stringify({
      authorId: 1 + nextInt(SEED_AUTHORS),
      title: `${WORDS[nextInt(WORDS.length)]} ${pad(nextInt(999999), 6)}`,
      isbn: newIsbn(iteration),
      publicationYear: 1450 + nextInt(576),
      price: money(),
    });
    const res = http.post(`${BASE}/api/books`, body, { ...JSON_HEADERS, tags: { endpoint: 'create', name: '/api/books' } });
    check(res, { 'create 201': (r) => r.status === 201 });

  } else {
    const id = 1 + nextInt(SEED_BOOKS);
    const body = JSON.stringify({
      title: `${WORDS[nextInt(WORDS.length)]} ${pad(nextInt(999999), 6)}`,
      publicationYear: 1450 + nextInt(576),
      price: money(),
    });
    const res = http.put(`${BASE}/api/books/${id}`, body, { ...JSON_HEADERS, tags: { endpoint: 'update', name: '/api/books/:id' } });
    check(res, { 'update 200': (r) => r.status === 200 });
  }
}

function valueOf(data, metric, stat, fallback) {
  const m = data.metrics[metric];
  return m && m.values[stat] !== undefined ? m.values[stat] : fallback;
}

export function handleSummary(data) {
  const base = {
    runId: RUN_ID,
    segment: SEGMENT,
    baseUrl: BASE,
    rateTarget: RATE,
    duration: DURATION,
    preAllocatedVUs: PRE_VUS,
    maxVUs: MAX_VUS,
    vusMaxUsed: valueOf(data, 'vus_max', 'max', null),
    iterations: valueOf(data, 'iterations', 'count', 0),
    // dropped_iterations só existe no resumo quando houve descarte
    droppedIterations: valueOf(data, 'dropped_iterations', 'count', 0),
    requests: valueOf(data, 'http_reqs', 'count', 0),
    achievedRps: DURATION_S > 0 ? valueOf(data, 'http_reqs', 'count', 0) / DURATION_S : null,
    errorRate: valueOf(data, 'http_req_failed', 'rate', 0),
  };

  // Série temporal para a verificação de estabilidade. Precede o desvio de aquecimento
  // porque esta execução não é aquecimento: ela mede o aquecimento.
  if (BUCKET_S > 0) {
    const series = [];
    for (let i = 0; i * BUCKET_S < DURATION_S; i += 1) {
      const dur = data.metrics[`http_req_duration{bucket:${i}}`];
      const fail = data.metrics[`http_req_failed{bucket:${i}}`];
      if (!dur) continue;
      series.push({
        fromSeconds: i * BUCKET_S,
        latencyAvgMs: dur.values.avg,
        latencyP95Ms: dur.values['p(95)'],
        errorRate: fail ? fail.values.rate : null,
      });
    }
    const out = { ...base, bucketSeconds: BUCKET_S, series };
    const text = JSON.stringify(out, null, 2);
    return { stdout: text + '\n', [RESULT_FILE]: text };
  }

  if (IS_WARMUP) {
    return {
      stdout: `aquecimento concluído (${RATE} req/s, ${DURATION}); dados descartados; `
        + `descartadas=${base.droppedIterations} erro=${(base.errorRate * 100).toFixed(3)}%\n`,
    };
  }

  const req = data.metrics.http_req_duration.values;
  const row = {
    ...base,
    latencyAvgMs: req.avg,
    latencyMedMs: req.med,
    latencyP90Ms: req['p(90)'],
    latencyP95Ms: req['p(95)'],
    latencyP99Ms: req['p(99)'],
    latencyMaxMs: req.max,
  };

  return {
    stdout: JSON.stringify(row, null, 2) + '\n',
    [RESULT_FILE]: JSON.stringify({ row, raw: data }, null, 2),
  };
}
