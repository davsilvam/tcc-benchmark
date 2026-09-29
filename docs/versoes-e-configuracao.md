# Versões, configuração e decisões de implementação

**Versão 1.0 — 10 de setembro de 2026**
Documento de apoio ao Apêndice da monografia. Complementa
[`especificacao-funcional-api.md`](especificacao-funcional-api.md), registrando o que a
especificação deixou em aberto e o que a implementação das cinco APIs obrigou a decidir.

Três coisas são registradas aqui, e apenas elas:

1. as versões efetivamente utilizadas, e como reproduzir esse registro (seções 1 e 2);
2. as decisões de configuração e de implementação que a especificação não determinava, com
   a justificativa de cada uma (seções 3 e 4);
3. as divergências entre o texto da especificação e o que se verificou na prática, para que
   a especificação seja corrigida antes da coleta (seção 5).

---

## 1. Versões utilizadas

> **A tabela abaixo é o registro de referência; a fonte primária é a saída de
> `scripts/collect-versions.sh`**, que extrai as versões dos próprios gerenciadores de
> dependência. Reexecutar o script imediatamente antes da campanha e anexar `results/versions/`
> ao Apêndice — é o que atende à pendência 1 da seção 10 da especificação.

Conferidas em 10/09/2026, a partir de `results/versions/`.

| Camada | Spring Boot | Django | NestJS | Laravel | ASP.NET Core |
|---|---|---|---|---|---|
| **Framework** | 4.1.1 | 6.1.1 | 12.0.1 | 13.31.0 | 10.0.12 |
| **Runtime** | Java 25.0.4 (Temurin 25.0.4+7) | Python 3.13.15 | Node.js 24.21.0 | PHP 8.5.10 | .NET 10.0.x |
| **ORM** | Hibernate ORM 7.4.5.Final | Django ORM 6.1.1 | TypeORM 1.1.1 | Eloquent 13.31.0 | EF Core 10.0.4 |
| **Camada de dados** | Spring Data JPA 4.1.1 | — | @nestjs/typeorm 12.0.1 | — | Npgsql.EntityFrameworkCore.PostgreSQL 10.0.3 |
| **Driver** | PostgreSQL JDBC 42.7.13 | psycopg 3.3.5 | pg 8.23.0 | pdo_pgsql (PHP 8.5.10) | Npgsql 10.0.3 |
| **Pool** | HikariCP 7.0.2 | psycopg-pool 3.3.1 | pool do `pg` | PDO persistente | pool do Npgsql |
| **Servidor** | Tomcat 11.0.24 | Gunicorn 26.2.0 | Express (embarcado) | nginx 1.26.3 + PHP-FPM | Kestrel |
| **Validação** | Hibernate Validator 9.1.3.Final | django.forms | class-validator 0.15.1 | Illuminate\Validation | DataAnnotations |
| **Serialização** | Jackson 3.1.5 (`tools.jackson`) | json (stdlib) | JSON.stringify | json_encode | System.Text.Json |
| **Construção** | Maven 3.9.16 | pip | npm 11.19.0 | Composer 2 | dotnet SDK 10.0.401 |

**Infraestrutura**

| Componente | Versão |
|---|---|
| PostgreSQL | 16.13 (Debian 16.13-1.pgdg13+1) |
| Docker | 29.7.2 |
| k6 | v2.2.0 (go1.26.5, windows/amd64) |
| `cloc` | **não instalado** — ver seção 6 |

Parâmetros do PostgreSQL efetivamente em vigor: `shared_buffers = 65536` (512 MB),
`max_connections = 200`, `log_statement = none` durante a coleta.

Duas observações de registro:

- **Spring Boot 4 migrou para o Jackson 3** (`tools.jackson`, e não `com.fasterxml.jackson`).
  O serializador continua sendo o padrão do framework, como exige a seção 3 da
  especificação, mas é uma linhagem diferente da usada pelo Spring Boot 3.
- **TypeORM chegou à versão 1.1.1**, saindo da série 0.3.x. A opção `find({ join: ... })`
  foi removida na 1.0, o que muda o código idiomático de junção — ver seção 4.3.

---

## 2. Como reproduzir o registro de versões

```bash
docker compose -f infra/docker-compose.yml up -d postgres
for fw in springboot django nestjs laravel aspnet; do
  docker compose -f infra/docker-compose.yml --profile $fw build $fw
done
./scripts/collect-versions.sh
```

O script grava um arquivo por framework em `results/versions/`, com runtime, gerenciador de
dependências e a árvore de dependências resolvida, além de `infra.txt` com PostgreSQL, k6,
`cloc` e Docker. As versões vêm dos artefatos construídos, não de anotações manuais: o
Apêndice deve reproduzir o que de fato foi executado.

### Contagem SLOC (seção 7 da especificação)

`cloc` não é instalado no ambiente; a execução é por contêiner. A contagem completa está
automatizada em `./scripts/count-sloc.sh`, cujos resultados constam da seção 8. O comando
subjacente, para inspeção avulsa de um framework:

```bash
docker run --rm -v "$PWD/apps:/t" aldanial/cloc --quiet \
  --exclude-dir=node_modules,vendor,target,bin,obj,dist \
  --exclude-lang=Markdown,Text \
  --not-match-f='(package-lock\.json|composer\.lock)' /t/spring-boot
```

A distinção SLOC-A / SLOC-B da seção 7 depende de saber quais arquivos são scaffolding não
modificado. A seção 4 deste documento registra, por framework, exatamente o que foi gerado
pela ferramenta e o que foi escrito à mão.

`--exclude-lang=Markdown,Text` é regra de contagem, não conveniência: o `cloc` conta
Markdown como linguagem, e os arquivos de prosa gerados pelo scaffolding entrariam na conta
de alguns tratamentos e não de outros. A seção 7 conta *código-fonte da aplicação* e
*configuração escrita à mão*; prosa não é nem uma coisa nem outra. A regra está sendo fixada
**antes** de qualquer contagem, como a própria seção 7 exige.

---

## 3. Decisões de configuração

### 3.1 Pool de conexões: o agregado é que vale 10

A seção 6.1 da especificação fixa "pool de conexões: mínimo 10, máximo 10". A seção 6.2
adota, para cada framework, o modelo de concorrência de sua documentação oficial. Os dois
requisitos entram em conflito nos frameworks multiprocesso, porque cada processo mantém o
próprio pool.

| Framework | Processos | Pool por processo | Conexões ao banco |
|---|---|---|---|
| Spring Boot | 1 | 10 (HikariCP) | 10 |
| ASP.NET Core | 1 | 10 (Npgsql) | 10 |
| NestJS | 1 | 10 (node-postgres) | 10 |
| Django | 5 (Gunicorn) | **2** (psycopg-pool) | 10 |
| Laravel | 10 (PHP-FPM) | 1 conexão persistente (PDO) | 10 |

**Decisão: o parâmetro controlado é o número total de conexões que cada tratamento abre
contra o PostgreSQL — 10 em todos os cinco casos.** Aplicar "10" literalmente por processo
daria ao Django 50 conexões e ao Laravel 10, e o fator deixaria de ser constante justamente
onde a seção 6.1 pretende mantê-lo constante: na concorrência disponível no banco.

O caso do Laravel merece registro à parte: **o PHP não possui pool de conexões**. Sem
`PDO::ATTR_PERSISTENT`, cada requisição abriria e fecharia uma conexão TCP com o PostgreSQL,
e a medição incluiria o custo de estabelecimento de conexão que nenhum dos outros quatro
paga. Com conexões persistentes, cada processo filho do PHP-FPM reaproveita a sua, e
`pm.max_children = 10` produz as mesmas 10 conexões. Isso está em
`apps/laravel/config/database.php`.

### 3.2 Escopo de configuração: apenas o que a API utiliza

Spring Boot declara três starters (`web`, `data-jpa`, `validation`) — sem segurança, sem
camada de visão. O mesmo critério foi aplicado aos demais, e é o que torna a comparação
legítima: nenhum tratamento carrega subsistemas que outro não carrega.

| Framework | Removido do template padrão |
|---|---|
| ASP.NET Core | `WeatherForecast*` (exemplo), OpenAPI, `UseHttpsRedirection`, `UseAuthorization`, `Properties/launchSettings.json` |
| Django | `contrib.admin`, `auth`, `sessions`, `messages`, `staticfiles` e os middlewares correspondentes; validadores de senha; motor de templates |
| NestJS | `AppController`/`AppService` (exemplo) e os testes de amostra |
| Laravel | `app/Models/User.php` (exemplo), `database/migrations`, `factories`, `seeders`, `tests/` |

As migrations foram removidas por exigência da seção 2.4: o esquema é externo, e nenhuma
migration é gerada ou executada em nenhum dos cinco.

Os arquivos de configuração *gerados* (`config/*.php` do Laravel, `tsconfig.json` do
NestJS, `appsettings.json`) permanecem no projeto — é exatamente o que a contagem SLOC-A da
seção 7 pretende capturar.

### 3.3 Otimizações de produção documentadas

A seção 6.2 manda usar "a configuração de produção recomendada pela documentação oficial de
cada framework". Aplicada literalmente, isso inclui etapas de compilação/cache que não têm
equivalente nos cinco:

| Framework | Etapa | Onde |
|---|---|---|
| Laravel | OPcache com `validate_timestamps=0`; `config:cache` e `route:cache` na partida | `docker/php.ini`, `docker/entrypoint.sh` |
| ASP.NET Core | `dotnet publish -c Release`; `AsNoTracking()` nas leituras | `Dockerfile`, `Api/BookController.cs` |
| NestJS | `npm ci --omit=dev`, `NODE_ENV=production`, execução do JavaScript compilado | `Dockerfile` |
| Django | `DEBUG=False`, `USE_I18N=False`, cache de aplicação nulo; Gunicorn atrás de nginx, por socket unix | `bookapi/settings.py`, `docker/nginx.conf` |
| Spring Boot | `open-in-view: false`, cache de segundo nível desabilitado | `application.yml` |

Duas dessas são as menos óbvias, e ficam justificadas aqui:

- **OPcache no Laravel.** Sem ele, cada requisição recompilaria os arquivos-fonte PHP. A
  medição refletiria a ausência de uma etapa que qualquer implantação real executa, e o
  resultado do Laravel seria artificialmente ruim.
- **`AsNoTracking()` no ASP.NET Core.** É a recomendação da documentação do EF Core para
  consultas somente leitura. Django e Eloquent não possuem rastreamento de entidades; o
  Hibernate possui, mas com `open-in-view: false` o contexto de persistência é descartado
  ao fim de cada chamada de repositório. Desabilitar o rastreamento nas leituras aproxima o
  EF Core do comportamento dos demais em vez de afastá-lo.

### 3.4 Fuso horário dos contêineres

Todos os contêineres executam em UTC. O campo `createdAt` sai, portanto, com deslocamento
`+00:00`, e não `-03:00` como no exemplo da seção 5.1 da especificação. É uma diferença de
apresentação do exemplo, não de contrato: o formato continua sendo ISO 8601 com
deslocamento, idêntico nos cinco.

---

## 4. Decisões de implementação, por framework

Esta seção registra o que cada ORM exigiu para satisfazer a coluna "Consultas" da seção 4 da
especificação. **Todas são armadilhas reais: o comportamento padrão de cada ferramenta
violaria o contrato.**

### 4.1 Spring Boot — JPA/Hibernate

`join fetch` explícito nas três consultas de leitura. Sem ele, `FetchType.LAZY` no
`@ManyToOne` dispara uma consulta por item (problema N+1). A paginação usa `Pageable` com
uma consulta JPQL própria, e não o tipo `Page`, que emitiria um `COUNT(*)` adicional.

### 4.2 ASP.NET Core — EF Core

`Include(b => b.Author)` produz uma única instrução com `INNER JOIN` para associações
*-para-um. `Skip`/`Take` viram `LIMIT`/`OFFSET` sem contagem — o EF Core, ao contrário dos
outros quatro, só emite `COUNT(*)` quando chamado explicitamente.

Duas particularidades:

- **O identificador de rota é recebido como `string`.** Uma restrição `{id:long}` faria o
  ASP.NET devolver **404** para `/api/books/abc`, e o contrato exige 400. A conversão é
  manual, com `long.TryParse`.
- **`DecimalPlacesAttribute` é código próprio.** A regra "no máximo 2 casas decimais" da
  seção 4.4 sai de graça nos outros quatro (`@Digits`, `DecimalField`, `maxDecimalPlaces`,
  `decimal:0,2`); o `System.ComponentModel.DataAnnotations` não tem equivalente, e o EF Core
  arredondaria em silêncio ao gravar em `NUMERIC(10,2)`. Essa assimetria é característica do
  ecossistema e deve ser contada como tal na métrica de produtividade.

### 4.3 NestJS — TypeORM

- **`limit`/`offset`, nunca `take`/`skip`.** Com junções, `take`/`skip` levam o TypeORM a
  emitir uma consulta adicional de identificadores distintos antes da consulta principal —
  duas instruções onde o contrato exige uma.
- **`innerJoinAndSelect` por construtor de consultas.** O TypeORM 1.x removeu a opção
  `find({ join: ... })`; a alternativa `relations` faz apenas `LEFT JOIN`.
- **Os analisadores de tipo do `pg` são reconfigurados em `main.ts`.** O node-postgres
  devolve `int8` e `numeric` como *string*, para não perder precisão. Sem
  `pg.types.setTypeParser`, `id` e `price` sairiam como texto no JSON e o contrato da seção
  3 (número JSON) seria violado apenas nesta implementação.

### 4.4 Django

- **`select_related('author')`**, e não `prefetch_related`: o primeiro faz `JOIN` na mesma
  consulta, o segundo emitiria uma consulta adicional.
- **Fatiamento do QuerySet, e não `Paginator`.** O `Paginator` emite `COUNT(*)`; a resposta
  do contrato não tem `totalElements` (seção 4.1).
- **`float(price)` na serialização.** O `JsonResponse` usa `DjangoJSONEncoder`, que
  serializa `Decimal` como **string**.
- **`save(update_fields=[...])`** restringe o `UPDATE` às três colunas do contrato.
- **Validação com `django.forms`; Django REST Framework não é utilizado.** A razão decisiva
  está na própria especificação: a seção 3 fixa "Serializador: o padrão de cada framework,
  sem customização de desempenho", e o DRF substitui a serialização padrão do Django pela
  dele — adotá-lo quebraria um fator já declarado controlado.

  O critério aplicado às cinco implementações não é "apenas primeira parte" — o NestJS usa
  `class-validator`, que é pacote externo. O critério é **usar o que a documentação oficial
  do próprio framework prescreve para a tarefa**: a do Nest prescreve `class-validator`, a
  do Django prescreve `django.forms`. O DRF é projeto de terceiros, fora da documentação do
  Django, e estruturalmente é um framework de aplicação sobre o Django — ciclo próprio de
  requisição, viewsets, negociação de conteúdo, renderers. Medir Django + DRF contra Spring
  Boot compararia uma pilha de duas camadas contra uma de uma.

  **Limitação conhecida:** o DRF é, na prática, o padrão de fato para APIs em Django, de
  modo que a contagem SLOC do Django aqui não corresponde à de um projeto típico de
  mercado. É limitação de validade externa da dimensão de produtividade, não de validade
  interna da comparação.

### 4.5 Laravel — Eloquent

- **Junção explícita com colunas do autor sob alias, e não `with('author')`.** O eager
  loading do Eloquent emite **duas** instruções: uma para os livros e outra para os autores.
  É a divergência mais fácil de deixar passar em toda a implementação, porque `with()` é a
  solução idiomática para o problema N+1 e resolve o N+1 — só que com duas consultas.
- **`where('title', 'like', ...)`, e não `whereLike(...)`.** O `whereLike` do Laravel é
  **insensível a maiúsculas por padrão** e traduz-se em `ILIKE` no PostgreSQL, o que
  descartaria o índice `idx_books_title` e violaria a seção 4.3. O operador `like` literal
  preserva a sensibilidade a caixa.
- **`'price' => 'float'` no `$casts`**, e não `'decimal:2'`: o cast decimal devolve string.
- **Atualização pelo construtor de consultas, e não `$book->save()`:** o modelo é hidratado
  com colunas do autor sob alias, e `save()` tentaria gravá-las.
- **`clear_env = no` no pool do PHP-FPM.** Sem essa linha as variáveis `DB_*` do contêiner
  não chegam aos processos filhos, e a aplicação cai silenciosamente nos padrões do `.env`.

---

## 5. Divergências em relação à especificação

Itens em que o texto da especificação não corresponde ao ambiente verificado. **Corrigir a
especificação antes da coleta**, para que o Apêndice não se contradiga.

### 5.1 Versão do k6 — **resolvido**

A seção 6.3 registrava **k6 1.7.1**; o k6 instalado e efetivamente utilizado em toda a
verificação é o **v2.2.0** (`go1.26.5, windows/amd64`). A tabela da especificação já foi
corrigida.

A diferença não é apenas de numeração: entre a série 1.x e a 2.x o k6 passou a consolidar o
objeto `options` antes de invocar `handleSummary`, o que quebrava o script de carga — ver a
seção 5.9.

### 5.2 PHP 8.5, e não 8.4 — **resolvido**

A seção 6.3 fixava PHP 8.4, mas o critério declarado por ela mesma — "a escolha da versão
estável mais recente nos demais ecossistemas" — apontava para o **8.5**, já disponível.
Manter o 8.4 seria aplicar ao PHP um critério diferente do aplicado ao Django, ao NestJS e
ao ASP.NET Core.

**Decisão: PHP 8.5.** A especificação já foi corrigida (seção 6.3), e o contêiner do Laravel
executa **PHP 8.5.10**. O `composer.json` gerado pelo Laravel 13 declara `"php": "^8.3"`, de
modo que o `composer.lock` resolvido continua válido — a construção foi refeita sem
alteração de dependências.

A migração exigiu um ajuste no `Dockerfile`: **a imagem `php:8.5-fpm` já traz o OPcache
compilado estaticamente** (aparece em `php -m` como `Zend OPcache`), e
`docker-php-ext-install opcache` falha com `cp: cannot stat 'modules/*'`. A extensão saiu da
lista de instalação; a configuração de produção permanece em `docker/php.ini` e foi
confirmada em execução (`ini_get('opcache.enable')` devolve `1`).

Reverificado após a migração: **76/76** na suíte de contrato e 1 / 1 / 1 / 2 / 2 consultas.

### 5.3 `log_statement` não podia ser ligado

A seção 8.2 instrui a habilitar `log_statement = 'all'` no PostgreSQL. O
`infra/docker-compose.yml` passava `-c log_statement=none` na **linha de comando** do
`postgres`, e parâmetros de linha de comando têm precedência sobre `postgresql.auto.conf`:
o `ALTER SYSTEM SET log_statement='all'` do `scripts/verify-queries.sh` era aceito e
**silenciosamente ignorado**. Verificado com `SELECT source FROM pg_settings WHERE
name = 'log_statement'`, que devolvia `command line`.

Corrigido: o parâmetro saiu da linha de comando (o padrão do PostgreSQL já é `none`) e o
`verify-queries.sh` passou a ligar e restaurar o registro por conta própria, com `trap` na
saída.

### 5.4 A contagem de consultas da seção 8.2 media zero

O `verify-queries.sh` contava apenas linhas `statement:` do log. **Os cinco ORMs usam o
protocolo estendido do PostgreSQL**, que registra `execute <portal>:`. O script devolvia
`0 consulta(s)` para todos os endpoints de todos os frameworks — e, como `0` difere do
esperado, teria sido lido como falha universal de implementação.

Corrigido: o padrão passou a aceitar as duas formas. Além disso, instruções de preparação de
**sessão** são agora excluídas — o psycopg do Django emite
`SELECT set_config('TimeZone','UTC',false)` a cada conexão nova entregue pelo pool, o que
inflava a contagem do Django e de mais nenhum, medindo o aquecimento do pool em vez do plano
de acesso da requisição.

### 5.5 `docker compose down` destruía a base entre repetições

O `scripts/run-experiment.sh` encerrava cada repetição com
`docker compose --profile "$FW" down`. O `down` atua sobre o **projeto inteiro**, não sobre o
serviço: derrubava também o contêiner do PostgreSQL. Como não há volume nomeado, isso
destruía a base e reiniciava o SGBD a cada uma das 30 repetições — o oposto do que a seção
3.4 exige ("o contêiner do PostgreSQL permanece ativo durante toda a campanha", conforme o
comentário do próprio `docker-compose.yml`).

Corrigido para `docker compose --profile "$FW" rm -sf "$FW"`. O mesmo aviso foi acrescentado
ao `README.md`.

### 5.6 A verificação do `PUT` acusava falha inexistente

Com um corpo de requisição fixo, o `verify-queries.sh` contava **1** consulta no `PUT` do
Spring Boot e do ASP.NET Core, e não 2. Não é defeito: Hibernate e EF Core fazem verificação
de sujeira e **suprimem o `UPDATE`** quando os valores enviados são iguais aos já gravados —
o que acontece a partir da segunda execução do script sobre o mesmo registro.

O script passou a enviar um título distinto a cada execução. A assimetria em si permanece:
sob o perfil de carga da seção 9, que sorteia os valores, ela não se manifesta; mas Django e
Eloquent, como implementados, emitem o `UPDATE` incondicionalmente.

### 5.7 Fuso horário dos contêineres

O exemplo da seção 5.1 mostra `createdAt` com deslocamento `-03:00`. Os contêineres executam
em UTC e o campo sai com `+00:00`. O contrato (ISO 8601 com deslocamento) é respeitado e o
formato é idêntico nos cinco. A diferença está apenas no exemplo da especificação.

### 5.8 Defeito corrigido na implementação de referência

O `POST /api/books` do **Spring Boot** emitia **3** consultas, e não 2: sem `@Transactional`,
a busca do autor e a gravação do livro ocorriam em contextos de persistência distintos, o
autor chegava destacado a `books.save()` e o Hibernate emitia um `SELECT` adicional sobre
`authors` para reassociá-lo (`select null, a1_0.birth_year, ...`).

Corrigido com `@Transactional` no método `create`. **A implementação de referência não
satisfazia o próprio critério de aceite 8.2** — o que só apareceu porque os defeitos 5.3 e
5.4 foram corrigidos antes.

---

### 5.9 A campanha não gravaria nenhum dado de medição

O `handleSummary` de `k6/load-test.js` lia `options.scenarios.load.vus` e
`options.scenarios.load.duration`. **No k6 v2 o objeto `options` exportado é consolidado
pelo motor antes do resumo, e `options.scenarios.load` chega indefinido**, de modo que
`handleSummary` lançava `TypeError: Cannot read property 'vus' of undefined`.

A consequência é severa e silenciosa: quando `handleSummary` lança, o k6 emite o resumo
padrão no terminal, **não grava o arquivo apontado por `RESULT_FILE` e encerra com código
zero**. O `run-experiment.sh` seguiria para a repetição seguinte sem notar. Ao fim das 30
repetições de cada framework restariam apenas os `.stats.csv` de `docker stats` — nenhuma
medição de latência ou vazão.

Corrigido: `VUS` e `DURATION` passaram a constantes do módulo, usadas tanto em `options`
quanto em `handleSummary`. Confirmado: o ensaio agora grava
`results/aspnet/aspnet_50vu_rep01.json` com os treze campos previstos.

### 5.10 O gerador de carga produzia preços fora do contrato

`price: (10 + nextInt(19000) / 100)` parece produzir duas casas decimais, mas em ponto
flutuante binário **5,26% dos 19.000 valores possíveis serializam com mais** — `10 + 112/100`
resulta em `11.120000000000001`. As cinco implementações validam no máximo duas casas
(seção 4.4) e recusavam esses corpos com **400**.

O efeito medido no ensaio foi exatamente esse: `update 200` falhava em 5,3% das iterações,
e a taxa de erro global ficava em 4,65% — contra a taxa nula que a seção 8.3 exige. Pior, o
custo de uma requisição recusada na validação não é o custo da operação que se pretende
medir: parte da carga nominal de escrita nunca chegava ao banco.

Corrigido com uma função `money()` que arredonda explicitamente.

### 5.11 Colisão de ISBN entre aquecimento e medição

O ISBN de escrita era `'9' + pad(__VU, 4) + pad(seq, 8)`. A faixa é disjunta da carga
semente, como a seção 9 prevê, mas **aquecimento e medição são invocações separadas do k6
sobre a mesma base** — `reset-db.sh` roda antes da repetição, não entre as fases — e cada
invocação reinicia `seq` em 1. Toda escrita da medição cujo `seq` já tivesse sido usado no
aquecimento colidia na chave única e devolvia **409**.

No ensaio isso levou `create 201` a 79% de sucesso. Como a proporção depende da razão entre
a duração do aquecimento e a da medição, o efeito seria maior em execuções curtas e variaria
com o nível de carga — contaminando justamente a comparação entre níveis.

Corrigido: o segundo dígito do ISBN passou a distinguir as fases
(`'9' + (IS_WARMUP ? '1' : '0') + pad(__VU, 3) + pad(seq, 8)`), mantendo os 13 dígitos.
Reverificado: **taxa de erro nula e 100% das verificações aprovadas** no ensaio.

> Os três defeitos desta seção só apareceram porque o `run-experiment.sh` foi ensaiado com
> parâmetros reduzidos antes da campanha. Nenhum deles é visível na suíte de contrato, que
> não usa o gerador de carga. É a justificativa para manter o ensaio como etapa obrigatória
> do protocolo.

---

## 6. Pendências

Em ordem de precedência.

**1. Critério 8.3 — satisfeito.** Taxa de erro nula nos cinco. Exigiu duas correções, já
aplicadas e descritas em 9.3 (Django atrás de nginx; k6 em contêiner), e a revisão do
período de aquecimento de 60 s para **150 s**, já em `scripts/run-experiment.sh`. Ver
seção 9.

**2. Django sem Django REST Framework — decidido.** Mantém-se `django.forms`; o DRF não é
adotado. Ver a justificativa na seção 4.4.

**3. Pendência 3 da seção 10 da especificação — resolvida.** Escopo definido: o Apêndice
reproduz as seções 2 a 6, 8 e 9 da especificação funcional.

**4. A campanha, no modelo aberto.** A revisão metodológica de 22/09/2026 substituiu o
modelo fechado pelo aberto e dividiu a medição em teste de capacidade e teste de carga fixa;
o aparato já está adaptado (seção 10). A sequência passa a ser: teste de capacidade para
obter C_min e os três níveis, reconfirmação do aquecimento sob taxa de chegada, piloto de
variabilidade para dimensionar as repetições, e só então a campanha.

**5. A campanha (estimativa anterior, do modelo fechado).** 5 frameworks × 3 níveis × 10 repetições. O ensaio mediu 1.259 req/s a
50 VUs em 30 s no ASP.NET Core; cada repetição de medição são ~8,5 min (150 s de aquecimento +
300 s de medição + restauração e recriação do contêiner), o que dá **~4,3 h por framework**
e ~21 h no total.
Convém rodar um framework por vez e conferir os resultados antes de seguir.

---

## 7. Estado de verificação

Execução de 10/09/2026, com PostgreSQL 16.13 e carga semente íntegra (1.000 autores,
200.000 livros).

### 7.1 Critérios de aceite

| Framework | Contrato (8.1) | Registros idênticos (8.1) | Consultas (8.2) | Plano da busca (8.2) | Aquecimento (8.3) |
|---|---|---|---|---|---|
| Spring Boot | 76/76 | referência | 1 / 1 / 1 / 2 / 2 | `Index Scan`, sem `Sort` | entra em regime aos 90 s, erro 0% |
| Django | 76/76 | idêntico | 1 / 1 / 1 / 2 / 2 | idem | entra em regime aos 10 s, erro 0% |
| NestJS | 76/76 | idêntico | 1 / 1 / 1 / 2 / 2 | idem | sem aquecimento, erro 0% |
| Laravel | 76/76 | idêntico | 1 / 1 / 1 / 2 / 2 | idem | sem aquecimento, erro 0% |
| ASP.NET Core | 76/76 | idêntico | 1 / 1 / 1 / 2 / 2 | idem | aquece em ~30 s, erro 0% |

Ordem das consultas: `list` / `byId` / `search` / `create` / `update`.

Comandos que reproduzem a tabela:

```bash
k6 run -e BASE_URL=http://localhost:8080 -e FW=<framework> k6/contract-test.js
./scripts/verify-queries.sh <framework>
./scripts/compare-fingerprints.sh
```

### 7.2 Equivalência de registros entre implementações

`scripts/compare-fingerprints.sh` restaura a base ao estado semente antes de cada
implementação, executa a suíte de contrato e confronta os identificadores devolvidos contra
a implementação de referência. Resultado: **os cinco fingerprints são byte a byte
idênticos** — mesma quantidade, mesmos identificadores, na mesma ordem, nos três endpoints
de leitura.

```json
{"listPage3":[61,62,...,80],
 "book1234":{"isbn":"0000000001234","title":"Inverno 81dc9bdb52d0","authorId":235},
 "searchAlfa":[9700,196900,192950,187350,...]}
```

Vale notar que `searchAlfa` **não** está em ordem de identificador: a ordenação é por
`title`, e a coincidência exata dessa sequência nas cinco implementações é a evidência de
que os cinco ORMs traduziram o filtro por prefixo e a ordenação da mesma forma.

### 7.3 Plano de execução da busca por prefixo

Confirma empiricamente a exigência de `COLLATE "C"` da seção 2.3, nas cinco implementações:

```
Limit
  ->  Nested Loop
        ->  Index Scan using idx_books_title on books b
              Index Cond: (((title)::text >= 'Alfa'::text) AND ((title)::text < 'Alfb'::text))
              Filter: ((title)::text ~~ 'Alfa%'::text)
        ->  Memoize
              ->  Index Only Scan using authors_pkey on authors a
```

Varredura de intervalo com `Index Cond` de limites de prefixo e **sem nó `Sort`** — o
resultado esperado pela seção 8.2.

### 7.4 Ensaio do protocolo de coleta

`run-experiment.sh` foi executado com parâmetros reduzidos
(`LEVELS=50 REPS=1 DURATION=30s WARMUP_DURATION=10s`) contra o ASP.NET Core, para exercitar
o protocolo antes de comprometer as ~18 h da campanha. **O ensaio revelou três defeitos no
gerador de carga**, registrados nas seções 5.9 a 5.11 — entre eles, um que faria a campanha
inteira terminar sem gravar um único dado de medição.

Após as correções:

| Métrica | Valor |
|---|---|
| Taxa de erro | **0** |
| Verificações | 100% (37.785 aprovadas, 0 falhas) |
| Vazão | 1.259 req/s |
| Latência média / p95 / p99 | 39,5 ms / 94,9 ms / 126,0 ms |
| CPU do contêiner | ~196% de 200% (2 vCPU) |
| Memória | ~110 MiB de 2 GiB |

Os artefatos previstos foram gravados: `aspnet_50vu_rep01.json` (linha de resultado mais o
resumo bruto do k6) e `aspnet_50vu_rep01.stats.csv` (amostragem de `docker stats` a cada
segundo). **Os números acima são de um ensaio de 30 s e não têm valor comparativo** — servem
apenas como evidência de que o protocolo funciona de ponta a ponta.

---

## 8. Métrica de produtividade — resultado

`cloc` **1.98**, executado por contêiner (`aldanial/cloc`). Regras de contagem e listas de
arquivos em `results/sloc/`; reprodução com `./scripts/count-sloc.sh`.

| Framework | SLOC-A | SLOC-B | A − B |
|---|---:|---:|---:|
| ASP.NET Core | 239 | 239 | 0 |
| Django | 258 | 234 | 24 |
| Spring Boot | 379 | 370 | 9 |
| NestJS | 397 | 339 | 58 |
| Laravel | 1.241 | 436 | 805 |

### 8.1 O ordenamento depende da escolha de contagem

É o eixo de sensibilidade que a seção 7 da especificação antecipou, e ele **de fato se
manifesta**:

| Posição | por SLOC-A | por SLOC-B |
|---|---|---|
| 1º | ASP.NET Core (239) | **Django (234)** |
| 2º | Django (258) | **ASP.NET Core (239)** |
| 3º | Spring Boot (379) | **NestJS (339)** |
| 4º | NestJS (397) | **Spring Boot (370)** |
| 5º | Laravel (1.241) | Laravel (436) |

Duas trocas de posição em cinco. A conclusão sobre "qual framework exige menos código" muda
conforme se conte ou não o scaffolding intocado. Apenas a última posição é estável nas duas
leituras.

### 8.2 Como cada diferença se explica

A diferença A − B é, ela própria, uma medida: **quanto código o gerador do framework deposita
no projeto e o desenvolvedor nunca toca.**

- **ASP.NET Core (0).** Nenhum arquivo do `dotnet new webapi` sobreviveu intocado: os três
  gerados que permaneceram (`Program.cs`, `appsettings.json`, `BookApi.csproj`) foram todos
  modificados, e os de exemplo foram removidos. É o único caso em que A e B coincidem.
- **Spring Boot (9).** Apenas a classe principal `BookApiApplication.java`.
- **Django (24).** `manage.py`, `asgi.py` e `wsgi.py` — o `__init__.py` é vazio.
- **NestJS (58).** Configuração de ferramentas: `tsconfig.json`, `tsconfig.build.json`,
  `nest-cli.json`, `.prettierrc`, `oxlint.json` e `vitest.config.ts`.
- **Laravel (805), duas terças partes do projeto.** O `composer create-project` deposita 43
  arquivos que nunca foram tocados: os dez `config/*.php` (631 linhas só de comentário), o
  `artisan`, o `public/index.php`, a página `welcome.blade.php` (209 linhas), os ativos de
  front-end em `resources/` e o `vite.config.js`. **Nada disso é usado pela API.**

O caso do Laravel é o que dá sentido à existência das duas medidas. Contar 1.241 sugere um
framework três vezes mais verboso que os demais; contar 436 mostra um custo de autoria
compatível com os outros quatro. As duas leituras são defensáveis — a seção 7 escolheu
reportar ambas, e o resultado justifica a escolha.

### 8.3 Como as listas foram derivadas

O que separa SLOC-A de SLOC-B é a resposta a "este arquivo foi tocado pelo desenvolvedor?".
Responder isso de memória seria frágil e não auditável. O método usado foi:

1. regerar o scaffold com **a mesma ferramenta e a mesma versão** que criaram o projeto
   (`dotnet new webapi --use-controllers`, `django-admin startproject`, `nest new`,
   `composer create-project laravel/laravel`);
2. comparar por `sha256`, arquivo a arquivo, com o projeto;
3. classificar como scaffolding intocado apenas o que coincide em caminho **e** conteúdo.

As listas resultantes ficam em `results/sloc/scaffolding-<framework>.txt` e
`results/sloc/autoria-<framework>.txt`, e os corpora efetivamente contados em
`results/sloc/corpus-{a,b}-<framework>.txt` — os cinco pares somam a evidência que o
Apêndice precisa.

**Ressalva única:** o Spring Boot já existia no repositório e não foi gerado nesta sessão,
de modo que não há scaffold original a comparar. Sua lista é a única assumida, e não
derivada: `BookApiApplication.java` é idêntico ao que o Spring Initializr emite. O cabeçalho
do arquivo registra a ressalva.

### 8.4 Duas decisões de contagem que afetam o resultado

Ambas fixadas **antes** de qualquer contagem, como a seção 7 exige.

- **Manifestos de dependências contam.** `pom.xml`, `package.json`, `composer.json`,
  `BookApi.csproj` e `requirements.txt` são configuração escrita à mão. Contá-los em quatro
  ecossistemas e não no quinto seria arbitrário — daí `requirements.txt` entrar, apesar de o
  `cloc` classificá-lo como texto puro.
- **`--force-lang=INI,conf` é necessário.** O `cloc` não reconhece a extensão `.conf` e
  ignoraria em silêncio `nginx.conf` e `php-fpm.conf`. Só o Laravel configura o servidor de
  aplicação em arquivos `.conf`; sem essa opção, e apenas ele, perderia 32 linhas que a
  seção 7 manda contar.

Os **arquivos de bloqueio** (`package-lock.json`, `composer.lock`), o `Dockerfile`, o
`.dockerignore`, o `entrypoint.sh`, os arquivos de controle de versão e de editor, o
Markdown e o `robots.txt` ficam de fora, conforme a seção 7.

---

## 9. Critério 8.3 — estabilidade sob aquecimento

100 VUs (nível intermediário), 300 s por framework, contêiner recém-criado e base restaurada
antes de cada um. Reprodução: `./scripts/verify-warmup.sh`; reanálise das séries já gravadas:
`python scripts/analyze-warmup.py "results/warmup/*.json"`.

A duração é maior que os 60 s que a seção 8.3 pede, e isso é deliberado: uma execução de
exatamente 60 s responde "estabilizou até aqui?", mas não responde "60 s bastam?". Se um
framework ainda estiver decaindo aos 60 s, é preciso ver quando ele para de decair para
saber quanto o aquecimento deveria durar — e a seção 8.3 prevê justamente essa revisão.

**A primeira execução reprovou por dois motivos independentes**, ambos corrigidos: o
aquecimento de 60 s era curto demais (9.2) e o gerador de carga era ele próprio o gargalo
(9.3). Os números abaixo são os da execução posterior às correções.

### 9.1 Resultado

| Framework | 1º intervalo | Regime estável | Entrada em regime | Dispersão na cauda | Taxa de erro |
|---|---:|---:|---:|---:|---:|
| NestJS | 83 ms | 76 ms | 0 s | 18% | **0%** |
| Django | 167 ms | 149 ms | 10 s | 9% | **0%** |
| Laravel | 681 ms | 575 ms | 10 s | 32% | **0%** |
| ASP.NET Core | 163 ms | 58 ms | 80 s | 38% | **0%** |
| Spring Boot | 542 ms | 104 ms | 90 s | 45% | **0%** |

**Taxa de erro nula nos cinco: a exigência de erro do critério 8.3 está satisfeita.**

Sobre o critério de "entrada em regime": exigir que todo intervalo posterior fique dentro de
uma faixa estreita confunde ruído com aquecimento — uma única oscilação tardia reprovaria uma
série que entrou em regime há muito tempo. Reporta-se, portanto, o primeiro intervalo cuja
média cai dentro de ±10% do regime estável, **acompanhado da dispersão observada depois desse
ponto**, que mede o ruído de fundo e permite julgar se a entrada foi real ou acidental.

### 9.2 O aquecimento de 60 s é insuficiente

```
Spring Boot   542 323 190 180 178 131 141 119 124 111 105 110 109 113 113 151 ...
ASP.NET Core  163 118  68  45  48  48  48  49  53  51  55  52  49  50  49  59 ...
Django        167 160 151 160 156 152 143 147 153 149 150 147 152 161 162 163 ...
NestJS         83  70  70  70  68  68  68  68  70  68  73  67  84  69  70  68 ...
Laravel       681 562 582 564 574 586 592 597 597 562 690 672 644 629 618 623 ...
              (média em ms, intervalos de 10 s)
```

O caso que fixa o período é o **Spring Boot**: primeiro intervalo a 542 ms, **5,2 vezes** o
regime de 104 ms, e aos 60 s ainda em 141 ms — **35% acima**. Entra em regime aos 90 s.

O ASP.NET Core aquece bem mais rápido do que a tabela sugere: aos 30 s já está em 45 ms,
abaixo do regime. Sua "entrada aos 80 s" é artefato de uma deriva lenta de subida ao longo
da execução (45 → 60 ms), que desloca o regime calculado sobre a cauda — não é aquecimento.

Django, NestJS e Laravel não exibem decaimento: entram em regime no primeiro ou no segundo
intervalo.

**Período de aquecimento adotado: 150 s**, contra os 60 s anteriores. É o pior caso (90 s)
com 67% de margem, aplicado igualmente aos cinco — a seção 8.3 determina que a revisão valha
para todos, e não só para o caso divergente. Já está em `scripts/run-experiment.sh`.

O custo é real e deve ser considerado: 90 s a mais por repetição, em 150 repetições, somam
**cerca de 3,7 h** à campanha.

A dispersão na cauda de Spring Boot (45%), ASP.NET Core (38%) e Laravel (32%) é alta e
merece registro: são séries ruidosas em regime, e leituras pontuais de latência média nesses
três têm incerteza correspondente. É argumento a favor das 10 repetições por nível que a
seção 3.4 já prevê.

### 9.3 O gerador de carga era o gargalo, e o Django o detonava — corrigido

Na primeira execução, Django e NestJS apresentaram **65,4% e 22,6% de erro**. Não era defeito
das implementações. A investigação mostrou:

1. Django isolado, 100 VUs por 30 s: **0,03% de falhas**, e as poucas com
   `WSAEADDRINUSE (10048)` — "Only one usage of each socket address is normally permitted".
2. Contagem de sockets no host: **13.722 em `TIME_WAIT` antes** de uma execução, **17.966
   depois**. O intervalo dinâmico padrão do Windows tem **16.384 portas**.
3. O erro por intervalo oscilava 0% → 100% → 0%, que é o ciclo de expiração do `TIME_WAIT`
   (120 s no padrão do Windows), não o comportamento de um servidor.

A causa de o Django detonar isso estava no cabeçalho de resposta:

| Framework | Servidor | `Connection`, antes | depois |
|---|---|---|---|
| **Django** | gunicorn (worker síncrono) | **`close`** | `keep-alive` |
| NestJS | Express | `keep-alive` | — |
| Laravel | nginx | `keep-alive` | — |
| Spring Boot | Tomcat | padrão HTTP/1.1 | — |
| ASP.NET Core | Kestrel | padrão HTTP/1.1 | — |

**O worker síncrono do Gunicorn não implementa keep-alive.** Cada requisição abria e fechava
uma conexão TCP; a ~1.200 req/s isso consumia as portas efêmeras do host em cerca de 14 s, e
os sockets em `TIME_WAIT` continuavam ocupando a faixa por 120 s — derrubando não só a
execução do Django, mas **as seguintes**. Daí o NestJS, que roda logo depois na sequência,
aparecer com 22,6% de erro; e o Laravel, cuja lentidão gera pouco churn, aparecer limpo.

Duas correções, ambas alinhando o aparato com a própria seção 6.2:

**(a) Django atrás de nginx, por socket unix.** A documentação do Gunicorn determina que ele
seja executado atrás de um servidor proxy. Expô-lo diretamente ao gerador de carga não é "a
configuração de produção recomendada pela documentação oficial" que a seção 6.2 exige, e
fazia o Django pagar estabelecimento de conexão em toda requisição enquanto os outros quatro
não pagavam — omissão de implantação, não característica do framework. O Laravel já rodava
atrás de nginx; a mudança torna os dois casos multiprocesso simétricos.

O canal entre nginx e Gunicorn é **socket unix**, e não porta de loopback: o churn de
conexões do worker síncrono continua existindo, e em TCP consumiria portas efêmeras dentro do
próprio contêiner. Arquivos em `apps/django/docker/`.

**(b) k6 fora do host Windows.** O gerador de carga não pode ter, ele próprio, um limite mais
estreito que o do sistema medido. `scripts/k6-run.sh` executa o k6 em contêiner na rede
`bench`, onde ele tem espaço de nomes de rede próprio, faixa de portas completa e `TIME_WAIT`
do Linux — e a pilha TCP do Windows sai do caminho da medição. Consequência para quem chama:
o destino passa a ser o nome do serviço (`http://django:8080`), não `localhost`.

Sem (b), a campanha de 30 repetições de 300 s por framework encontraria esgotamento de portas
repetidamente, e o resultado registraria o limite do host de carga em vez do desempenho dos
frameworks.

**Efeito das correções:** Django saiu de 65,4% para **0%** de erro, e os cinco passaram a
apresentar taxa de erro nula.

---

## 10. Modelo aberto de carga — mudanças no aparato (22/09/2026)

A revisão metodológica de 22/09/2026 substituiu o modelo fechado de geração de carga
(número fixo de usuários virtuais) pelo modelo aberto (taxa de chegada fixa) e dividiu a
medição em dois testes: o de capacidade e o de carga fixa. Esta seção registra o que mudou
no aparato, o que foi verificado e o que ainda depende do estudo-piloto.

### 10.1 O que mudou

| Antes | Agora |
|---|---|
| `constant-vus`, níveis de 50/100/200 usuários | `constant-arrival-rate`, taxas derivadas de C_min |
| semente do gerador: usuário virtual e repetição | semente: iteração global, repetição e fase |
| um único script de campanha, por framework | teste de capacidade + teste de carga fixa |
| campanha em blocos, um framework por vez | rodadas intercaladas, ordem sorteada por rodada |
| sem análise estatística | IC 95% por t de Student, diferenças por Welch, CV e dimensionamento |

Scripts novos ou reescritos:

| Arquivo | Papel |
|---|---|
| `scripts/common.sh` | rotinas comuns: restauração, ciclo do contêiner, prontidão, `docker stats` |
| `scripts/run-capacity.sh` | teste de capacidade, em patamares; subida em dois estágios na mesma sessão, repetições intercaladas e ordem sorteada |
| `scripts/run-experiment.sh` | teste de carga fixa, rodadas intercaladas, com retomada |
| `scripts/verify-warmup.sh` | critério 8.3 sob taxa de chegada |
| `scripts/analyze-capacity.py` | curva latência × taxa; capacidade utilizável pelo último patamar antes da 1ª violação, resumida por moda/mediana; C_min e os três níveis |

| `scripts/analyze-experiment.py` | médias com IC, CV, dimensionamento, diferenças de Welch |
| `scripts/analyze-warmup.py` | entrada em regime e critério do coeficiente de variação |
| `scripts/stats_util.py` | t de Student e Welch, sem dependências externas |

### 10.2 Decisões de implementação

**Patamares como invocações separadas, e não `ramping-arrival-rate`.** O critério (iii) da
capacidade utilizável exige `dropped_iterations` **por patamar**, e o k6 só reporta essa
métrica como total do teste. Com uma invocação de `constant-arrival-rate` por patamar, cada
resumo traz a sua. O custo é um intervalo de cerca de 1 s entre patamares, enquanto o k6
inicia. Se a monografia nomear o executor, é `constant-arrival-rate` encadeado.

**Todo o teto de usuários virtuais é pré-alocado.** Com poucos pré-alocados, o k6 aloca os
que faltam durante o teste e descarta as chegadas que ocorrem enquanto aloca. Medido: a
50 req/s com 20 pré-alocados, 28 iterações descartadas usando apenas 48 dos 200 disponíveis
— o critério (iii) estaria medindo a velocidade de alocação do gerador. Com pré-alocação
total, o descarte significa o que a definição pretende: o sistema sob teste manteve em
andamento mais requisições do que a taxa de um segundo. Custo verificado: 1.500 usuários
ocupam 285 MiB no contêiner do k6.

**A semente do gerador passa por uma função de mistura não linear.** Verificado sobre 200
mil iterações: com semeadura linear, apenas 12,4% das iterações consecutivas repetem a
operação, contra os 26% esperados de sorteio independente — um padrão periódico. Com a
mistura, 26,1%, e a distribuição observada é 40,1 / 20,0 / 10,0 / 20,0 / 10,0.

**A fase entra na semente.** Corrige uma assimetria que já existia no modelo fechado e
passara despercebida: aquecimento e medição usavam a mesma semente e, portanto, a mesma
sequência. Cada `PUT` da medição regravava no mesmo livro os valores já gravados no
aquecimento; Hibernate e EF Core suprimem o `UPDATE` quando nada muda, enquanto Django e
Eloquent o emitem sempre — uma instrução SQL contra duas, em 10% das requisições, e apenas
em dois dos cinco tratamentos.

### 10.3 Defeitos corrigidos no protocolo

**O `run-experiment.sh` recriava o PostgreSQL a cada execução.** O comando era
`up -d --force-recreate` **sem o nome do serviço**; sob um profile, isso recria todos os
serviços ativos, e o `postgres` não tem profile. Verificado por comparação do instante de
partida do contêiner: com o nome do serviço, preservado; sem ele, recriado. A base era
destruída e recarregada pelo `initdb` a cada execução, e o SGBD reiniciado entre medições —
o oposto do que a seção 3.4 exige.

**O `reset-db.sh` falhava em silêncio.** O `psql` prossegue após erro e termina com código
zero. Observado: uma restauração deixou 642 linhas residuais, que produziram colisões de
ISBN e 4% de erro na medição seguinte, sem nenhum aviso. Agora usa `ON_ERROR_STOP=1` e
confere que a base terminou com exatamente 1.000 autores e 200.000 livros.

**Uma campanha podia rodar contra um banco ausente.** Duas decisões corretas em si se
combinavam mal: `--no-deps` evita recriar o PostgreSQL, mas também não o inicia se estiver
parado; e `/api/health` não toca o banco (seção 4.6), de modo que a aplicação responde "UP"
com o banco morto. Ocorreu de fato, depois de a máquina suspender. Agora há a pré-condição
`require_postgres`, que recusa iniciar qualquer medição sem o banco aceitando conexões.

### 10.4 Medido, disponível para o texto

- **Intervalo efetivo de amostragem do `docker stats`: 2,10 s em média** (mín 2,01, máx
  2,37). Não é 1 s: cada amostra exige duas leituras do daemon, e o intervalo é medido pelos
  carimbos de tempo do próprio arquivo, não suposto. `analyze-experiment.py` o recalcula a
  cada análise.
- **Docker Desktop 4.90.0, engine 29.7.2** — confere com o texto da versão 1.1.
- A taxa obtida acompanha a configurada com precisão: 60,0 req/s medidos contra 60
  configurados, com CV de 0,0% entre execuções.

### 10.5 Pendente do estudo-piloto

Nenhum destes valores foi arbitrado pelo aparato; todos dependem de medição:

| Símbolo no texto | O que é | Como obter |
|---|---|---|
| [X] | teto do p95 na definição de capacidade | `analyze-capacity.py` reporta a latência de base e as taxas em que o p95 a supera em 2, 3 e 5 vezes |
| [Y], [Z] | incremento e duração do patamar | parâmetros `STEP` e `STEP_S` de `run-capacity.sh` |
| [N_A] | repetições do teste de capacidade | parâmetro `REPS` |
| [C_min] | menor capacidade entre os cinco | `analyze-capacity.py --p95-max X` |
| [D] | duração da medição | parâmetro `DURATION` de `run-experiment.sh` |
| [CV], [H] | variabilidade entre execuções e precisão projetada | `analyze-experiment.py` sobre ao menos 5 execuções-piloto por framework |
| [k] | janela do critério de coeficiente de variação | `analyze-warmup.py` reporta k = 3, 5 e 6 |

> **Sinal de alerta sobre [k].** Nas séries do modelo fechado, a 100 usuários virtuais, o
> critério de CV abaixo de 2% **não é atingido** por ASP.NET Core, Laravel e Spring Boot com
> janela de 5 ou 6 intervalos; mesmo com janela de 3, apenas 12% a 48% das janelas o
> satisfazem. Aquelas séries estavam em saturação, e sob taxa de chegada bem abaixo da
> capacidade a dispersão tende a ser menor — mas convém confirmar antes de fixar o limiar de
> 2%, sob pena de nenhum k servir.

---

## 11. Estudo-piloto de capacidade (25/09/2026)

Subida em patamares de 100 req/s, cada um mantido por 20 s, de 100 até a primeira violação.
Aquecimento de 150 s a 100 req/s antes do primeiro patamar; base restaurada e contêiner
recriado antes de cada framework. Reprodução:

```bash
# FINE_STEP=100 (= STEP) desliga o estagio fino, acrescentado ao script em 25/09/2026.
# Sem ele o padrao passa a ser STEP/4 e a execucao NAO reproduz o piloto como foi medido.
START=100 STEP=100 FINE_STEP=100 STEP_S=20 MAX_RATE=3000 P95_SAFETY=2000 \
  OUT=results/capacity-piloto ./scripts/run-capacity.sh
python scripts/analyze-capacity.py --dir results/capacity-piloto --p95-max <X>
```

### 11.1 Curvas latência × taxa

p95 em ms, por patamar (req/s):

| Framework | Curva | Último sustentado | Primeiro insustentável |
|---|---|---:|---|
| Laravel | 100:11 200:7 | **300** (ver 11.4) | 400: obtida 260, p95 1.989 ms |
| Django | 100:7 … 700:8 800:23 | **800** | 900: obtida 804, p95 1.437 ms |
| Spring Boot | 100:7 … 1400:6 | **1.400** | 1.500: obtida 771, p95 2.844 ms |
| NestJS | 100:6 … 1000:8 1100:9 1200:11 1300:14 1400:55 1500:38 1600:308 1700:967 | **1.300 a 1.700** | 1.800: obtida 1.722, p95 1.676 ms |
| ASP.NET Core | 100:8 … 1600:6 1700:19 1800:6 | **1.800** | 1.900: obtida 1.871, p95 1.059 ms |

**Quatro dos cinco não têm joelho.** A latência permanece plana — entre 4 e 11 ms — ao longo
de toda a faixa sustentável e salta duas a três ordens de grandeza no primeiro patamar
insustentável, sem degradação gradual. O NestJS é a exceção: degrada progressivamente a
partir de 1.100 req/s.

### 11.2 Sensibilidade da capacidade ao teto [X]

Capacidade utilizável (req/s) calculada sobre as mesmas curvas, variando apenas [X]:

| Framework | 20 ms | 30 ms | 50 ms | 100 ms | 500 ms | 1.000 ms |
|---|---:|---:|---:|---:|---:|---:|
| Laravel | 200 | 200 | 200 | 200 | 200 | 200 |
| Django | 700 | 800 | 800 | 800 | 800 | 800 |
| Spring Boot | 1.400 | 1.400 | 1.400 | 1.400 | 1.400 | 1.400 |
| **NestJS** | **1.300** | **1.300** | **1.500** | **1.500** | **1.600** | **1.700** |
| ASP.NET Core | 1.800 | 1.800 | 1.800 | 1.800 | 1.800 | 1.800 |

(valores do Laravel conforme a varredura original; ver 11.4)

Duas consequências para a seção 3.4.2 da monografia:

**A derivação de [X] "do joelho da curva" não se sustenta para quatro dos cinco.** Não há
joelho: a transição é abrupta. A opção (a) prevista no texto só teria referência empírica no
NestJS.

**O teto não é indiferente ao ordenamento.** Com [X] ≤ 30 ms, o Spring Boot supera o NestJS
em capacidade; com [X] ≥ 50 ms, a posição inverte. Como a capacidade utilizável é critério
HB da dimensão de desempenho, a escolha de [X] altera o resultado do SAW. Convém, portanto,
que [X] seja fixado por um critério declarado e anterior à observação — um limite de
responsividade da literatura, por exemplo —, e que a análise de sensibilidade da seção 3.5.4
inclua [X] entre os eixos examinados.

### 11.3 O caso do Laravel e a necessidade de [N_A] > 1

Na varredura completa, o Laravel — quarto framework da sequência, após cerca de 40 minutos de
carga contínua na máquina — colapsou em 300 req/s, indicando capacidade de 200. Repetida a
subida três vezes em sessão dedicada, ele sustentou **300 req/s em todas as três repetições**,
com p95 entre 8,7 e 10,0 ms, colapsando apenas em 400:

| Repetição | 100 | 200 | 300 | 400 |
|---|---:|---:|---:|---|
| rep01 | 9,5 | 8,8 | 9,4 | colapso (260 obtidas, 2.800 descartes) |
| rep02 | 9,3 | 8,5 | 10,0 | colapso (234 obtidas, 3.324 descartes) |
| rep03 | 9,9 | 9,9 | 8,7 | colapso (263 obtidas, 2.748 descartes) |

Medição isolada de CPU confirma que 300 req/s não satura o contêiner: 112% de utilização
média dos 200% disponíveis, com p95 de 10,4 ms e nenhum descarte.

**Ruído de fundo conhecido nestas três repetições.** Três laços coletores de `docker stats`
ficaram órfãos às 13:20:58 de 25/09/2026 e só foram encerrados horas depois; as repetições
dedicadas do Laravel (13:27:20 a 13:39:35) e a medição isolada de CPU correram inteiras
dentro dessa janela. A varredura dos cinco frameworks, encerrada às 13:16:54, é anterior e
não foi afetada. O viés é unidirecional — carga adicional na máquina —, de modo que os
300 req/s sustentados em 3/3 e a folga de CPU são estimativas conservadoras: os p95 de 8,7
a 10,0 ms e os 112% de utilização são limites superiores do que ocorreria sem o ruído. As
conclusões abaixo não dependem da magnitude exata desses valores.

Duas conclusões:

- **[N_A] = 1 é insuficiente.** A diferença entre 200 e 300 req/s é de 50% e propaga-se a
  todos os níveis da campanha, já que o Laravel define o C_min.
- **O efeito de posição na sessão, descrito na seção 3.6.1, é mensurável no teste de
  capacidade.** O argumento que justifica intercalar os tratamentos no teste de carga fixa
  (seção 3.4.4) aplica-se igualmente aqui. **Já aplicado:** desde 25/09/2026 o
  `scripts/run-capacity.sh` intercala as repetições e sorteia a ordem de cada rodada, com
  semente `ORDER_SEED` própria, distinta da do `run-experiment.sh` — se fossem iguais, a
  rodada *n* dos dois testes usaria a mesma ordem e um eventual efeito de posição se
  alinharia entre eles em vez de se distribuir. A ordem usada fica em `ordem.csv`. Os números
  desta seção 11, porém, foram obtidos **antes** da mudança, percorrendo os frameworks em
  bloco, e é isso que explica o caso do Laravel.

### 11.4 Valores provisórios

| Símbolo | Valor | Situação |
|---|---|---|
| [Y] grosso | 100 req/s | passo do estágio grosso; localiza o intervalo |
| [Y] fino | 25 req/s | passo do estágio fino; **é ele que fixa a resolução, ±12,5 req/s**. Precisa dividir o passo grosso, ou a resolução declarada exclui o valor verdadeiro — o script recusa a execução se não dividir |
| [Z] | 20 s | suficiente: a taxa obtida igualou a configurada em todos os patamares sustentáveis |
| [N_A] | ≥ 3 | 1 demonstradamente insuficiente (11.3) |
| [C_min] | 300 req/s (Laravel) | provisório: só o Laravel foi repetido |
| níveis | 75 / 150 / 225 req/s | decorrem de C_min = 300 |
| [X] | — | decisão pendente (11.2) |

Com C_min = 300 req/s, os demais tratamentos serão medidos entre 4% e 75% de sua capacidade:
o Laravel a 25–75%, o Django a 9–28%, o Spring Boot a 5–16%, o NestJS a 4–17% e o ASP.NET
Core a 4–12%. É consequência direta da restrição à menor capacidade, adotada deliberadamente
na seção 3.4.3, e convém registrar que a comparação de consumo de recursos ocorre, para
quatro dos cinco, em regime de baixa utilização.

### 11.5 Crescimento da base durante a subida

A base não é restaurada entre patamares e 20% das requisições são inserções. Volume final
por execução, contra os 200.000 da semente: Laravel 204.955; Django 220.641; Spring Boot
248.170; NestJS 271.279; ASP.NET Core 279.129. O crescimento acompanha a vazão acumulada e
concentra-se nos patamares altos. Como a latência permanece plana até o colapso, não há
indício de que tenha influenciado as curvas; o registro fica para que a afirmação seja
verificável.
