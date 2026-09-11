// Script único de carga — TCC
// Executado sem alteração contra os cinco frameworks; apenas BASE_URL muda.
//
//   k6 run -e BASE_URL=http://localhost:8080 -e VUS=50 -e DURATION=300s \
//          -e RUN_ID=1 -e RESULT_FILE=out/springboot_50_01.json k6/load-test.js
//
// A fase de aquecimento é uma invocação SEPARADA deste mesmo script (WARMUP=1), de modo
// que nenhum dado de aquecimento entre no sumário da execução de medição.

import exec from 'k6/execution';
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const RUN_ID = parseInt(__ENV.RUN_ID || '1', 10);
const IS_WARMUP = __ENV.WARMUP === '1';
const RESULT_FILE = __ENV.RESULT_FILE || 'summary.json';

// VUS e DURATION são constantes próprias, e não lidas de `options` dentro de
// handleSummary: no k6 v2 o objeto exportado é consolidado pelo motor antes do resumo e
// `options.scenarios.load` chega indefinido, fazendo handleSummary lançar exceção — e,
// com ela, o arquivo de resultado da medição NÃO ser gravado.
const VUS = parseInt(__ENV.VUS || '50', 10);
const DURATION = __ENV.DURATION || (IS_WARMUP ? '60s' : '300s');

// BUCKET_S ativa a marcação por INTERVALO DE TEMPO, usada apenas pelo critério de aceite
// 8.3 (estabilidade sob aquecimento). Verificar se a latência estabiliza exige série
// temporal, e o resumo do k6 só produz agregados do teste inteiro. Marcando cada
// requisição com o intervalo em que ocorreu, e declarando um limiar por intervalo — que é
// o que faz o k6 materializar a sub-métrica correspondente —, o resumo passa a trazer
// http_req_duration{bucket:N} para cada N.
//
// Com BUCKET_S ausente ou zero nada disso é avaliado, e o caminho de medição da campanha
// permanece exatamente como era. O teste de aquecimento usa, assim, o MESMO perfil de
// carga da coleta, em vez de uma reimplementação que poderia divergir dele.
const BUCKET_S = parseInt(__ENV.BUCKET_S || '0', 10);
const DURATION_S = parseInt(DURATION, 10) || 0;

function bucketThresholds() {
  if (BUCKET_S <= 0 || DURATION_S <= 0) return {};
  const out = {};
  for (let i = 0; i * BUCKET_S < DURATION_S; i += 1) {
    // limiar trivialmente satisfeito: serve para materializar a sub-métrica, não para
    // reprovar a execução
    out[`http_req_duration{bucket:${i}}`] = ['max>=0'];
    out[`http_req_failed{bucket:${i}}`] = ['rate>=0'];
  }
  return out;
}

export const options = {
  scenarios: {
    load: {
      executor: 'constant-vus',
      vus: VUS,
      duration: DURATION,
      gracefulStop: '10s',
    },
  },
  discardResponseBodies: true,
  noConnectionReuse: false,
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: bucketThresholds(),
};

// --- Gerador congruente linear (MINSTD) -------------------------------------------------
// Cada usuário virtual mantém seu próprio estado, semeado por (RUN_ID, __VU). A mesma
// repetição aplica, portanto, exatamente a mesma sequência de requisições aos cinco
// frameworks. Sem isso, parte da variação observada decorreria do sorteio da carga.
let rng = 0;
let seq = 0;

function nextInt(bound) {
  if (rng === 0) {
    rng = ((RUN_ID * 7919 + __VU * 104729) % 2147483646) + 1;
  }
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

// ISBN das escritas começa com 9; os dados semente começam com 0. Faixas disjuntas
// eliminam colisão de chave única durante a execução.
// O segundo dígito distingue AQUECIMENTO de MEDIÇÃO. As duas fases são invocações
// separadas do k6 sobre a MESMA base — reset-db.sh roda antes da repetição, não entre as
// fases — e cada invocação reinicia `seq` em 1. Sem esse dígito, toda escrita da medição
// cujo `seq` já tivesse sido usado no aquecimento colidiria na chave única e devolveria
// 409, inflando a taxa de erro que a seção 8.3 exige nula.
function newIsbn() {
  seq += 1;
  return '9' + (IS_WARMUP ? '1' : '0') + pad(__VU, 3) + pad(seq, 8);
}

export default function () {
  if (BUCKET_S > 0) {
    // currentTestRunDuration é o tempo decorrido desde o início do teste, em ms
    exec.vu.tags.bucket = Math.floor(
      exec.instance.currentTestRunDuration / 1000 / BUCKET_S,
    );
  }

  const draw = nextInt(100);

  if (draw < 40) {
    const page = nextInt(200);
    const res = http.get(`${BASE}/api/books?page=${page}&size=20`, { tags: { endpoint: 'list' } });
    check(res, { 'list 200': (r) => r.status === 200 });

  } else if (draw < 60) {
    const id = 1 + nextInt(SEED_BOOKS);
    const res = http.get(`${BASE}/api/books/${id}`, { tags: { endpoint: 'byId' } });
    check(res, { 'byId 200': (r) => r.status === 200 });

  } else if (draw < 70) {
    const title = WORDS[nextInt(WORDS.length)];
    const res = http.get(`${BASE}/api/books/search?title=${title}&size=20`, { tags: { endpoint: 'search' } });
    check(res, { 'search 200': (r) => r.status === 200 });

  } else if (draw < 90) {
    const body = JSON.stringify({
      authorId: 1 + nextInt(SEED_AUTHORS),
      title: `${WORDS[nextInt(WORDS.length)]} ${pad(nextInt(999999), 6)}`,
      isbn: newIsbn(),
      publicationYear: 1450 + nextInt(576),
      price: money(),
    });
    const res = http.post(`${BASE}/api/books`, body, { ...JSON_HEADERS, tags: { endpoint: 'create' } });
    check(res, { 'create 201': (r) => r.status === 201 });

  } else {
    const id = 1 + nextInt(SEED_BOOKS);
    const body = JSON.stringify({
      title: `${WORDS[nextInt(WORDS.length)]} ${pad(nextInt(999999), 6)}`,
      publicationYear: 1450 + nextInt(576),
      price: money(),
    });
    const res = http.put(`${BASE}/api/books/${id}`, body, { ...JSON_HEADERS, tags: { endpoint: 'update' } });
    check(res, { 'update 200': (r) => r.status === 200 });
  }
}

export function handleSummary(data) {
  // Série temporal para o critério de aceite 8.3. Precede o desvio de aquecimento porque
  // esta execução não é aquecimento: ela mede o aquecimento.
  if (BUCKET_S > 0) {
    const series = [];
    for (let i = 0; i * BUCKET_S < DURATION_S; i += 1) {
      const dur = data.metrics[`http_req_duration{bucket:${i}}`];
      const fail = data.metrics[`http_req_failed{bucket:${i}}`];
      if (!dur) continue;
      series.push({
        fromSeconds: i * BUCKET_S,
        requests: dur.values.count,
        latencyAvgMs: dur.values.avg,
        latencyP95Ms: dur.values['p(95)'],
        errorRate: fail ? fail.values.rate : null,
      });
    }
    const out = {
      baseUrl: BASE,
      vus: VUS,
      duration: DURATION,
      bucketSeconds: BUCKET_S,
      errorRate: data.metrics.http_req_failed.values.rate,
      series,
    };
    const text = JSON.stringify(out, null, 2);
    return { stdout: text + '\n', [RESULT_FILE]: text };
  }

  if (IS_WARMUP) {
    return { stdout: 'warm-up concluido; dados descartados\n' };
  }

  const req = data.metrics.http_req_duration.values;
  const row = {
    runId: RUN_ID,
    baseUrl: BASE,
    vus: VUS,
    duration: DURATION,
    iterations: data.metrics.iterations.values.count,
    throughputRps: data.metrics.http_reqs.values.rate,
    errorRate: data.metrics.http_req_failed.values.rate,
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
