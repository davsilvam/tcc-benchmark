// Suíte de contrato — critério de aceite 8.1 da especificação funcional.
// Executada contra CADA implementação antes de qualquer coleta.
//
//   k6 run -e BASE_URL=http://localhost:8080 -e FW=springboot k6/contract-test.js
//
// Sai com código diferente de zero se qualquer verificação falhar (threshold em checks).
// Grava fingerprint.json com os identificadores retornados por consultas fixas: os cinco
// arquivos devem ser idênticos entre si.

import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const FW = __ENV.FW || 'unknown';

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: { checks: ['rate==1.00'] },
};

const JSON_HEADERS = { headers: { 'Content-Type': 'application/json' } };
const isNum = (v) => typeof v === 'number';
const isStr = (v) => typeof v === 'string';

let fingerprint = {};

function body(res) {
  try { return JSON.parse(res.body); } catch (e) { return {}; }
}

function assertBookShape(label, b) {
  check(b, {
    [`${label}: id numerico`]: (x) => isNum(x.id),
    [`${label}: title string`]: (x) => isStr(x.title),
    [`${label}: isbn com 13 digitos`]: (x) => isStr(x.isbn) && /^[0-9]{13}$/.test(x.isbn),
    [`${label}: publicationYear numerico`]: (x) => isNum(x.publicationYear),
    [`${label}: price numerico`]: (x) => isNum(x.price),
    [`${label}: createdAt string`]: (x) => isStr(x.createdAt),
    [`${label}: author embutido`]: (x) => x.author && isNum(x.author.id) && isStr(x.author.name)
      && isStr(x.author.nationality) && isNum(x.author.birthYear),
  });
}

export default function () {
  // --- 4.6 health --------------------------------------------------------------------
  let res = http.get(`${BASE}/api/health`);
  check(res, {
    'health 200': (r) => r.status === 200,
    'health status UP': (r) => body(r).status === 'UP',
  });

  // --- 4.1 listagem paginada ----------------------------------------------------------
  res = http.get(`${BASE}/api/books?page=3&size=20`);
  let b = body(res);
  check(res, { 'list 200': (r) => r.status === 200 });
  check(b, {
    'list page ecoado': (x) => x.page === 3,
    'list size ecoado': (x) => x.size === 20,
    'list content com 20 itens': (x) => Array.isArray(x.content) && x.content.length === 20,
    'list sem totalElements': (x) => x.totalElements === undefined,
  });
  if (b.content && b.content.length) assertBookShape('list', b.content[0]);
  fingerprint.listPage3 = (b.content || []).map((x) => x.id);

  res = http.get(`${BASE}/api/books?size=1`);
  check(res, { 'list size=1 default page 0': (r) => body(r).page === 0 });

  res = http.get(`${BASE}/api/books`);
  check(res, { 'list size padrao 20': (r) => body(r).size === 20 });

  check(http.get(`${BASE}/api/books?page=-1`), { 'list page negativa 400': (r) => r.status === 400 });
  check(http.get(`${BASE}/api/books?size=0`), { 'list size 0 -> 400': (r) => r.status === 400 });
  check(http.get(`${BASE}/api/books?size=101`), { 'list size 101 -> 400': (r) => r.status === 400 });
  check(http.get(`${BASE}/api/books?page=abc`), { 'list page nao numerica 400': (r) => r.status === 400 });

  // --- 4.2 busca por identificador -----------------------------------------------------
  res = http.get(`${BASE}/api/books/1234`);
  b = body(res);
  check(res, { 'byId 200': (r) => r.status === 200 });
  check(b, { 'byId id correto': (x) => x.id === 1234 });
  assertBookShape('byId', b);
  fingerprint.book1234 = { isbn: b.isbn, title: b.title, authorId: b.author && b.author.id };

  check(http.get(`${BASE}/api/books/99999999`), { 'byId inexistente 404': (r) => r.status === 404 });
  check(http.get(`${BASE}/api/books/abc`), { 'byId nao numerico 400': (r) => r.status === 400 });

  // --- 4.3 busca por prefixo -----------------------------------------------------------
  res = http.get(`${BASE}/api/books/search?title=Alfa&size=20`);
  b = body(res);
  check(res, { 'search 200': (r) => r.status === 200 });
  check(b, {
    'search size ecoado': (x) => x.size === 20,
    'search 20 itens': (x) => Array.isArray(x.content) && x.content.length === 20,
    'search prefixo respeitado': (x) => x.content.every((i) => i.title.indexOf('Alfa') === 0),
  });
  fingerprint.searchAlfa = (b.content || []).map((x) => x.id);

  // sensível a maiúsculas: 'alfa' minúsculo não deve retornar nada
  res = http.get(`${BASE}/api/books/search?title=alfa`);
  check(res, { 'search sensivel a caixa': (r) => body(r).content.length === 0 });

  check(http.get(`${BASE}/api/books/search`), { 'search sem title 400': (r) => r.status === 400 });
  check(http.get(`${BASE}/api/books/search?title=`), { 'search title vazio 400': (r) => r.status === 400 });

  // --- 4.4 criação ----------------------------------------------------------------------
  const isbn = '9' + String(Date.now()).slice(-12);
  res = http.post(`${BASE}/api/books`, JSON.stringify({
    authorId: 42, title: 'Contrato de Teste', isbn,
    publicationYear: 1998, price: 79.90,
  }), JSON_HEADERS);
  b = body(res);
  check(res, {
    'create 201': (r) => r.status === 201,
    'create Location correto': (r) => (r.headers['Location'] || '').indexOf('/api/books/') === 0,
  });
  check(b, {
    'create ecoa title': (x) => x.title === 'Contrato de Teste',
    'create ecoa isbn': (x) => x.isbn === isbn,
    'create ecoa price': (x) => x.price === 79.9,
    'create autor 42': (x) => x.author && x.author.id === 42,
  });
  assertBookShape('create', b);
  const createdId = b.id;

  check(http.post(`${BASE}/api/books`, JSON.stringify({
    authorId: 42, title: 'Duplicado', isbn, publicationYear: 1998, price: 10.00,
  }), JSON_HEADERS), { 'create isbn duplicado 409': (r) => r.status === 409 });

  const invalid = [
    ['autor inexistente', { authorId: 999999, title: 'X', isbn: '9111111111111', publicationYear: 2000, price: 1 }],
    ['title vazio', { authorId: 42, title: '', isbn: '9111111111112', publicationYear: 2000, price: 1 }],
    ['isbn curto', { authorId: 42, title: 'X', isbn: '123', publicationYear: 2000, price: 1 }],
    ['isbn nao numerico', { authorId: 42, title: 'X', isbn: 'ABCDEFGHIJKLM', publicationYear: 2000, price: 1 }],
    ['ano abaixo do minimo', { authorId: 42, title: 'X', isbn: '9111111111113', publicationYear: 1000, price: 1 }],
    ['ano acima do maximo', { authorId: 42, title: 'X', isbn: '9111111111114', publicationYear: 3000, price: 1 }],
    ['preco negativo', { authorId: 42, title: 'X', isbn: '9111111111115', publicationYear: 2000, price: -1 }],
    ['campo ausente', { authorId: 42, isbn: '9111111111116', publicationYear: 2000, price: 1 }],
  ];
  invalid.forEach(([label, payload]) => {
    const r = http.post(`${BASE}/api/books`, JSON.stringify(payload), JSON_HEADERS);
    check(r, {
      [`create ${label} -> 400`]: (x) => x.status === 400,
      [`create ${label} -> corpo de erro`]: (x) => {
        const e = body(x);
        return e.status === 400 && isStr(e.message);
      },
    });
  });

  // --- 4.5 atualização -------------------------------------------------------------------
  res = http.put(`${BASE}/api/books/${createdId}`, JSON.stringify({
    title: 'Contrato Atualizado', publicationYear: 2004, price: 55.00,
  }), JSON_HEADERS);
  b = body(res);
  check(res, { 'update 200': (r) => r.status === 200 });
  check(b, {
    'update aplica title': (x) => x.title === 'Contrato Atualizado',
    'update aplica ano': (x) => x.publicationYear === 2004,
    'update aplica price': (x) => x.price === 55,
    'update preserva isbn': (x) => x.isbn === isbn,
    'update preserva autor': (x) => x.author && x.author.id === 42,
  });

  check(http.put(`${BASE}/api/books/99999999`, JSON.stringify({
    title: 'X', publicationYear: 2000, price: 1,
  }), JSON_HEADERS), { 'update inexistente 404': (r) => r.status === 404 });

  check(http.put(`${BASE}/api/books/${createdId}`, JSON.stringify({
    title: '', publicationYear: 2000, price: 1,
  }), JSON_HEADERS), { 'update title vazio 400': (r) => r.status === 400 });

  // handleSummary roda em contexto distinto do usuário virtual e não enxerga esta
  // variável; o fingerprint sai pelo log e é capturado pelo script de execução.
  console.log('FINGERPRINT ' + JSON.stringify(fingerprint));
}

export function handleSummary(data) {
  return {
    stdout: `contrato ${FW}: ${data.metrics.checks.values.passes} ok, ` +
            `${data.metrics.checks.values.fails} falhas\n`,
  };
}
