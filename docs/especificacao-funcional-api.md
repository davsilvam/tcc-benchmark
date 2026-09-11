# Especificação funcional da API de referência

**Versão 1.0 — 10 de setembro de 2026**
Documento de apoio às seções 3.2, 3.3, 3.4 e 3.6 do TCC. Destina-se a compor o Apêndice da
monografia como evidência do controle do fator "especificação funcional da API".

Este documento define o contrato único que as cinco implementações (Spring Boot, Django,
NestJS, Laravel e ASP.NET Core) devem satisfazer. Nenhuma coleta de dados se inicia antes de
as cinco implementações passarem integralmente nos critérios de aceite da seção 8.

---

## 1. Princípio de equivalência

A seção 3.2 da monografia trata a especificação funcional da API como fator controlado,
mantido constante entre todos os tratamentos. Operacionalmente, isso exige que as cinco
implementações sejam equivalentes em três planos:

| Plano | Exigência | Verificação |
|---|---|---|
| Contrato HTTP | Mesmas rotas, mesmos códigos de status, mesmo formato de corpo | Suíte de contrato (seção 8.1) |
| Plano de acesso a dados | Mesmo número e mesma natureza de consultas SQL por requisição | Log do PostgreSQL (seção 8.2) |
| Configuração de execução | Mesmos parâmetros controláveis (seção 6) | Inspeção documentada (Apêndice) |

A equivalência no plano de acesso a dados é o ponto crítico: se um mapeamento
objeto-relacional emitir consultas adicionais por carregamento tardio de associação
(problema N+1) e outro não, a diferença medida decorrerá da implementação e não do
framework. Esse risco é tratado como critério de aceite, não como ameaça residual.

---

## 2. Modelo de dados

Duas entidades em relação 1–N, deliberadamente mínimas: o objetivo é exercitar leitura
indexada, leitura paginada com junção, filtro por prefixo e escrita transacional, sem
introduzir regra de negócio que desloque o custo da requisição do banco para a aplicação.

### 2.1 `authors`

| Coluna | Tipo | Restrições |
|---|---|---|
| `id` | `BIGINT` | PK |
| `name` | `VARCHAR(120)` | `NOT NULL` |
| `nationality` | `VARCHAR(60)` | `NOT NULL` |
| `birth_year` | `INTEGER` | `NOT NULL` |

### 2.2 `books`

| Coluna | Tipo | Restrições |
|---|---|---|
| `id` | `BIGSERIAL` | PK |
| `author_id` | `BIGINT` | `NOT NULL`, FK → `authors(id)` |
| `title` | `VARCHAR(200) COLLATE "C"` | `NOT NULL` |
| `isbn` | `CHAR(13)` | `NOT NULL`, `UNIQUE` |
| `publication_year` | `INTEGER` | `NOT NULL` |
| `price` | `NUMERIC(10,2)` | `NOT NULL` |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`, `DEFAULT now()` |

### 2.3 Índices

```
books_pkey            (id)          -- implícito
books_isbn_key        (isbn)        -- implícito, UNIQUE
idx_books_author_id   (author_id)
idx_books_title       (title)
```

> **A cláusula `COLLATE "C"` da coluna `title` é requisito, não detalhe de implementação.**
> Sob o agrupamento padrão do banco, um índice btree comum não atende a `LIKE 'prefixo%'`,
> e o endpoint de busca (seção 4.3) deixaria de medir um filtro indexado. A verificação
> empírica dos planos de execução confirmou o efeito: com agrupamento padrão e ordenação
> por `id`, o planejador do PostgreSQL 16 descartou o índice de título e optou por percorrer
> a chave primária aplicando o filtro linha a linha, removendo 980 registros por 20
> retornados. Sob `COLLATE "C"`, o mesmo índice `idx_books_title` atende ao filtro por
> prefixo **e** à ordenação em uma única varredura de intervalo, sem etapa de ordenação
> subsequente. Essa é a razão de o endpoint de busca ordenar por `title` e não por `id`
> (seção 4.3).

### 2.4 Volume e criação do esquema

Volume fixo: **1.000 autores** e **200.000 livros**.

O esquema e a carga inicial são criados por **script SQL puro** (`infra/schema.sql` e
`infra/seed.sql`), executados uma única vez na inicialização do contêiner do PostgreSQL.
As migrations dos ORMs **não são utilizadas** e devem permanecer desabilitadas
(`ddl-auto: none`, `managed = False`, `synchronize: false`, ausência de `migrate`,
`EnsureCreated` desativado).

Justificativa metodológica: se cada ORM gerar o próprio esquema, tipos de coluna, índices e
restrições divergirão entre as cinco implementações, e a diferença medida passaria a
refletir a política de geração de DDL de cada ferramenta, e não o desempenho do framework.
Com esquema externo, cada ORM apenas mapeia uma estrutura idêntica e pré-existente.

Os dados são gerados deterministicamente a partir de `generate_series` e `md5`, sem
qualquer fonte de aleatoriedade, de modo que o mesmo script produza exatamente o mesmo
conjunto de dados em qualquer reexecução.

---

## 3. Convenções gerais

- Prefixo de todas as rotas: `/api`
- Formato de entrada e de saída: `application/json`, codificação UTF-8
- Serializador: **o padrão de cada framework**, sem customização de desempenho
- Nomes de campo no JSON: `camelCase` em todas as implementações
- Datas e horas: ISO 8601 com deslocamento (`2026-09-10T09:01:00-03:00`)
- Valores monetários: número JSON com duas casas decimais
- Porta interna do contêiner: `8080` em todas as implementações
- Sem compressão de resposta, sem cabeçalhos de cache, sem ETag, sem HTTPS

---

## 4. Endpoints

Cinco endpoints funcionais e um endpoint de prontidão. A coluna "Consultas" indica o número
exato de instruções SQL que a implementação deve emitir por requisição bem-sucedida — é
requisito de aceite, verificado conforme a seção 8.2.

| # | Método e rota | Perfil | Consultas |
|---|---|---|---|
| 1 | `GET /api/books` | Leitura paginada com junção | 1 |
| 2 | `GET /api/books/{id}` | Leitura pontual por PK | 1 |
| 3 | `GET /api/books/search` | Leitura filtrada por prefixo indexado | 1 |
| 4 | `POST /api/books` | Escrita com validação | 2 |
| 5 | `PUT /api/books/{id}` | Leitura + atualização | 2 |
| 6 | `GET /api/health` | Prontidão | 0 |

### 4.1 `GET /api/books`

Listagem paginada de livros, com o autor embutido na representação.

**Parâmetros de consulta**

| Nome | Tipo | Padrão | Restrição |
|---|---|---|---|
| `page` | inteiro | `0` | ≥ 0 |
| `size` | inteiro | `20` | 1 ≤ `size` ≤ 100 |

**SQL de referência**

```sql
SELECT b.*, a.*
  FROM books b JOIN authors a ON a.id = b.author_id
 ORDER BY b.id
 LIMIT :size OFFSET :page * :size;
```

**Resposta `200`**

```json
{
  "page": 0,
  "size": 20,
  "content": [ { "...BookResponse..." } ]
}
```

> **Ausência deliberada de contagem total.** A resposta não inclui `totalElements`. Os
> mecanismos de paginação de alto nível dos cinco ecossistemas (`Page` do Spring Data,
> `Paginator` do Django, `findAndCount` do TypeORM, `paginate()` do Eloquent) emitem
> automaticamente uma consulta `COUNT(*)` adicional, enquanto o Entity Framework Core exige
> chamada explícita. Incluir a contagem obrigaria a padronizar um comportamento que cada
> ferramenta implementa de forma distinta, com risco de divergência no número de consultas.
> A supressão da contagem mantém o endpoint em exatamente uma instrução SQL nos cinco casos
> e é registrada como decisão de projeto na seção 3.4 da monografia.

**Erros:** `400` se `page` < 0, `size` fora do intervalo, ou valor não numérico.

### 4.2 `GET /api/books/{id}`

**Resposta `200`:** um `BookResponse`.
**Erros:** `404` se não existir; `400` se `{id}` não for inteiro.

**SQL de referência**

```sql
SELECT b.*, a.* FROM books b JOIN authors a ON a.id = b.author_id WHERE b.id = :id;
```

### 4.3 `GET /api/books/search`

**Parâmetros de consulta**

| Nome | Tipo | Padrão | Restrição |
|---|---|---|---|
| `title` | string | — | obrigatório, 1 a 200 caracteres |
| `size` | inteiro | `20` | 1 ≤ `size` ≤ 100 |

Correspondência por **prefixo, sensível a maiúsculas e minúsculas**, com ordenação por
título.

**SQL de referência**

```sql
SELECT b.*, a.*
  FROM books b JOIN authors a ON a.id = b.author_id
 WHERE b.title LIKE :title || '%'
 ORDER BY b.title
 LIMIT :size;
```

A ordenação por `title` — e não por `id`, como nos demais endpoints de leitura — decorre da
verificação de plano descrita na seção 2.3: é o que mantém a operação em uma varredura de
intervalo do índice `idx_books_title`, sem etapa de ordenação adicional. Sob `COLLATE "C"`
a ordem é a de bytes, portanto determinística e idêntica nas cinco implementações.

> **Sensibilidade a maiúsculas é requisito, não detalhe.** Uma busca insensível a caixa
> traduz-se em `ILIKE` no PostgreSQL, em `UPPER(title) LIKE UPPER(...)` no Django com
> `__istartswith`, e em variações conforme o ORM — formas que não utilizam o índice
> `varchar_pattern_ops` e cujo plano de execução difere entre as implementações. A
> correspondência sensível a caixa mapeia-se para `LIKE` simples nos cinco ORMs
> (`startsWith` no JPA, `__startswith` no Django, `Like()` no TypeORM, `where('title','like',…)`
> no Eloquent, `EF.Functions.Like` no EF Core), preservando o mesmo plano de execução.

**Resposta `200`**

```json
{ "size": 20, "content": [ { "...BookResponse..." } ] }
```

**Erros:** `400` se `title` ausente ou vazio.

### 4.4 `POST /api/books`

**Corpo da requisição**

```json
{
  "authorId": 42,
  "title": "Alfa 9f2c1b…",
  "isbn": "9000000000123",
  "publicationYear": 1998,
  "price": 79.90
}
```

**Regras de validação**

| Campo | Regra |
|---|---|
| `authorId` | obrigatório, inteiro positivo, autor deve existir |
| `title` | obrigatório, 1 a 200 caracteres |
| `isbn` | obrigatório, exatamente 13 dígitos decimais |
| `publicationYear` | obrigatório, 1450 ≤ ano ≤ 2100 |
| `price` | obrigatório, ≥ 0, no máximo 2 casas decimais |

**Sequência de consultas (exatamente 2)**

1. `SELECT` do autor por PK — a existência do autor é verificada explicitamente, e não
   delegada à violação de chave estrangeira, porque o tratamento de erro de integridade
   difere entre os ORMs e produziria caminhos de execução distintos.
2. `INSERT` do livro.

**Resposta `201`:** cabeçalho `Location: /api/books/{id}` e corpo com o `BookResponse`
criado.
**Erros:** `400` para violação de validação ou autor inexistente; `409` para `isbn`
duplicado.

### 4.5 `PUT /api/books/{id}`

**Corpo da requisição**

```json
{ "title": "Bravo 3ae81f…", "publicationYear": 2004, "price": 55.00 }
```

O campo `authorId` **não** é atualizável. A restrição é deliberada: permitir a troca de
autor exigiria uma terceira consulta para validar o novo autor, e o número de consultas
passaria a depender do conteúdo da requisição.

**Sequência de consultas (exatamente 2):** `SELECT` do livro com junção do autor,
seguido de `UPDATE` das três colunas.

**Resposta `200`:** o `BookResponse` atualizado.
**Erros:** `404` se o livro não existir; `400` para violação de validação.

### 4.6 `GET /api/health`

Resposta `200` com `{"status":"UP"}`. Não acessa o banco de dados. Serve exclusivamente
como porta de prontidão do script de coleta: a fase de aquecimento só começa depois que
este endpoint responde `200`.

---

## 5. Representações

### 5.1 `BookResponse`

```json
{
  "id": 137452,
  "title": "Alfa 9f2c1b7d4e…",
  "isbn": "0000000137452",
  "publicationYear": 1987,
  "price": 42.50,
  "createdAt": "2026-09-10T09:01:00-03:00",
  "author": {
    "id": 42,
    "name": "Autor 0042",
    "nationality": "Brasileira",
    "birthYear": 1954
  }
}
```

### 5.2 Corpo de erro

Formato único para todos os erros, em todas as implementações:

```json
{
  "status": 400,
  "message": "Validation failed",
  "violations": [ { "field": "isbn", "message": "must have exactly 13 digits" } ]
}
```

O campo `violations` é omitido quando não houver violações de campo (por exemplo, em `404`).

---

## 6. Configuração de execução padronizada

### 6.1 Parâmetros idênticos nos cinco frameworks

| Parâmetro | Valor |
|---|---|
| Modo de execução | Produção, depuração desabilitada |
| Nível de log | `WARN` ou equivalente; sem log de requisições |
| Pool de conexões | mínimo 10, máximo 10 |
| Cache de aplicação | desabilitado |
| Cache de segundo nível do ORM | desabilitado |
| Compressão de resposta | desabilitada |
| Limites do contêiner | 2 vCPU, 2 GB (conforme seção 3.4) |
| Porta interna | 8080 |

O pool fixo em 10 conexões é o parâmetro mais relevante desta tabela: os valores padrão
divergem amplamente entre os ecossistemas, e deixá-los livres significaria medir a decisão
de configuração de cada projeto, não o comportamento do framework sob carga.

### 6.2 Parâmetros que não admitem equivalência

O modelo de concorrência do servidor não é padronizável entre os cinco ecossistemas: o
Node.js opera sobre laço de eventos de thread única, o Django exige um servidor WSGI com
processos trabalhadores, o Laravel exige PHP-FPM com processos filhos, e Spring Boot e
ASP.NET Core utilizam pools de threads gerenciados pela plataforma. Forçar uma equivalência
numérica artificial entre esses modelos configuraria intervenção arbitrária no objeto
medido.

Decisão adotada: **utilizar a configuração de produção recomendada pela documentação
oficial de cada framework, dimensionada aos 2 vCPU do contêiner**, e registrar cada
configuração explicitamente na monografia.

| Framework | Servidor | Configuração de concorrência |
|---|---|---|
| Spring Boot | Tomcat embarcado | pool de threads padrão (`server.tomcat.threads.max=200`) |
| Django | Nginx + Gunicorn (WSGI) | `--workers 5 --threads 1` (fórmula `2 × vCPU + 1` da documentação) |
| NestJS | HTTP embarcado (Express) | processo único, sem clusterização |
| Laravel | Nginx + PHP-FPM | `pm = static`, `pm.max_children = 10` |
| ASP.NET Core | Kestrel | pool de threads padrão do runtime |

A opção pelo processo único no NestJS merece registro na seção 3.6.1: o Node.js não utiliza
os 2 vCPU alocados sem clusterização explícita, o que constitui característica do seu modelo
de execução e não deficiência da implementação. A alternativa — clusterizar — introduziria
uma decisão arquitetural de aplicação ausente do padrão do framework.

### 6.3 Versões (conferidas em 10/09/2026)

| Framework | Versão | Runtime |
|---|---|---|
| Spring Boot | 4.1.1 | Java 25 (LTS) |
| Django | 6.1.1 | Python 3.13 |
| NestJS | 12.0.1 | Node.js 24 LTS |
| Laravel | 13.x | PHP 8.5 |
| ASP.NET Core | 10.0.x (LTS) | .NET 10 |
| PostgreSQL | 16 | — |
| k6 | 2.2.0 | — |

Django 6.1.1 é a versão estável mais recente; a LTS vigente é a 5.2. A adoção da 6.1.1
mantém a coerência com a escolha da versão estável mais recente nos demais ecossistemas.

Pelo mesmo critério, o PHP adotado é o **8.5**, e não o 8.4: a 8.5 é a versão estável mais
recente, e o `composer.json` gerado pelo Laravel 13 declara `"php": "^8.3"`, que a
contempla.
Cada versão exata, incluindo a revisão de correção, deve ser registrada no Apêndice a partir
da saída dos gerenciadores de dependência no momento da coleta.

---

## 7. Métrica de produtividade — regras de contagem de SLOC

As regras são fixadas **antes** da implementação. Defini-las após observar os resultados
comprometeria a métrica.

**Ferramenta:** `cloc`, versão registrada no Apêndice. Linhas em branco e comentários são
descartados por padrão pela ferramenta.

**Contabilizado**

- Código-fonte da aplicação nas linguagens do projeto
- Mapeamentos objeto-relacionais, validações, roteamento, DTOs
- Arquivos de configuração da aplicação escritos à mão (`application.yml`, `settings.py`,
  `appsettings.json`, `.env` versionado, configuração do servidor de aplicação)
- Arquivos de scaffolding gerados pelo framework que permanecem no projeto

**Não contabilizado**

- Diretórios de dependências (`node_modules`, `vendor`, `target`, `bin`, `obj`)
- Arquivos de bloqueio de dependências (`package-lock.json`, `composer.lock`)
- `Dockerfile` e arquivos de orquestração
- Arquivos de IDE e de controle de versão
- Testes automatizados (ausentes por igual nas cinco implementações)
- Migrations (inexistentes: o esquema é externo, conforme seção 2.4)

**Sem bibliotecas de geração de código.** Nenhuma das cinco implementações utiliza
bibliotecas que suprimam código-fonte por geração em tempo de compilação ou de execução
além do que o próprio framework oferece por padrão — Lombok no Spring Boot é o caso mais
evidente. A adoção seletiva de uma ferramenta dessa natureza alteraria a contagem SLOC de
um único tratamento por decisão do pesquisador, e não por característica do framework.

**Duas medidas, não uma.** A contagem principal (SLOC-A) inclui o scaffolding gerado, sob o
argumento de que o volume de código que um framework impõe ao projeto é, ele próprio,
característica do framework. A contagem secundária (SLOC-B) exclui os arquivos de
scaffolding não modificados pelo desenvolvedor. A divergência entre SLOC-A e SLOC-B
alimenta um eixo adicional da análise de sensibilidade da seção 3.5.4, verificando se o
ordenamento da dimensão de produtividade depende dessa escolha de contagem.

---

## 8. Critérios de aceite

Nenhuma implementação entra na coleta antes de satisfazer integralmente esta seção.

### 8.1 Equivalência de contrato

A suíte `k6/contract-test.js` é executada contra cada implementação e verifica, para cada
endpoint: código de status, presença e tipo de cada campo da representação, comportamento
de paginação, aplicação de cada regra de validação, formato do corpo de erro e correção do
cabeçalho `Location`. Adicionalmente, verifica que a mesma requisição de leitura retorna
**registros idênticos** nas cinco implementações — mesma quantidade e mesmos identificadores,
na mesma ordem.

### 8.2 Equivalência do plano de acesso a dados

Com `log_statement = 'all'` habilitado no PostgreSQL, executa-se uma requisição de cada tipo
contra cada implementação e conta-se o número de instruções SQL registradas. Os valores
devem corresponder exatamente à coluna "Consultas" da tabela da seção 4. Divergência indica
carregamento tardio não intencional, consulta de contagem adicional ou verificação
redundante, e é tratada como defeito de implementação a ser corrigido antes da coleta.

Registra-se também o plano de execução (`EXPLAIN`) do endpoint de busca em cada
implementação, para confirmar o uso do índice `idx_books_title` nos cinco casos. O plano
esperado é uma varredura de intervalo (`Index Scan using idx_books_title`) com `Index Cond`
de limites de prefixo, sem nó de ordenação (`Sort`). A presença de um nó `Sort`, ou de uma
varredura de `books_pkey` com filtro sobre `title`, indica que o ORM traduziu a consulta de
forma divergente e é tratada como defeito de implementação.

### 8.3 Estabilidade sob aquecimento

Execução preliminar de 60 segundos no nível de carga intermediário, verificando que a
latência média se estabiliza e que a taxa de erro é nula. Frameworks com compilação em
tempo de execução que não estabilizem em 60 segundos exigem revisão do período de
aquecimento definido na seção 3.4 — para todos, e não apenas para o caso divergente.

---

## 9. Perfil de carga

Distribuição de operações por iteração de usuário virtual, correspondente ao mix de
70% de leitura e 30% de escrita:

| Operação | Proporção |
|---|---|
| `GET /api/books` | 40% |
| `GET /api/books/{id}` | 20% |
| `GET /api/books/search` | 10% |
| `POST /api/books` | 20% |
| `PUT /api/books/{id}` | 10% |

**Sequência determinística.** O script k6 seleciona a operação e seus parâmetros por meio de
um gerador congruente linear com semente derivada do identificador do usuário virtual e do
número da repetição. Consequentemente, a repetição *n* aplica exatamente a mesma sequência
de requisições, com os mesmos identificadores e os mesmos prefixos de busca, aos cinco
frameworks. Sem essa precaução, cada framework receberia um sorteio distinto de
identificadores, e parte da variação observada decorreria da carga e não da tecnologia.

**Restauração do estado do banco.** Como 30% das operações alteram a base, o volume de
`books` cresce ao longo de cada execução, e o custo de inserção e de manutenção de índice não
é o mesmo na primeira e na centésima quinquagésima execução. Antes de **cada** repetição, a
base é restaurada ao estado semente pelo procedimento de `infra/reset-db.sh`
(`TRUNCATE` seguido de recarga a partir dos scripts, com reinício das sequências). O
procedimento consta da seção 3.4 da monografia como etapa do protocolo de coleta.

Os ISBN gerados pelas operações de escrita iniciam com o dígito `9`, faixa disjunta da
utilizada pelos dados semente (que iniciam com `0`), eliminando colisões de chave única
durante a execução.

---

## 10. Pendências desta especificação

1. Confirmar a versão exata de correção de cada framework no momento da coleta e registrá-la
   no Apêndice.
2. Registrar a versão do `cloc` utilizada.
3. Definir se o Apêndice reproduz a especificação integralmente ou apenas as seções 2, 4 e 6.
