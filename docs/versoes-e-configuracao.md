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

**19/10/2026 — os itens 4 e 5 estão vencidos.** O teste de capacidade e a reconfirmação do
aquecimento foram executados, e as seções 12 a 14 os registram: [C_min] = 325 req/s, níveis de
81, 162 e 243 req/s, aquecimento de 150 s. Da sequência prevista no item 4, o piloto de
variabilidade deixou de ser etapa separada, pelo motivo da seção 13.5 — suas execuções são
execuções do nível intermediário e contam como as primeiras repetições. E as ~21 h do item 5,
herdadas do modelo fechado, cederam lugar às ~19 h da seção 13.2. Os dois itens ficam como
estavam, por serem o registro do que se planejava antes de medir.

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
# FINE_STEP=100 (= STEP) desliga o estágio fino, acrescentado ao script em 25/09/2026.
# Sem ele o padrão passa a ser STEP/4 e a execução NÃO reproduz o piloto como foi medido.
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

---

## 12. Teste de capacidade formal (30/09/2026)

Cinco repetições por framework, intercaladas, com a ordem de cada rodada sorteada. Produzido
pelo commit `1c33acb`, registrado em `results/capacity/parametros.txt`. Reprodução:

```bash
START=100 STEP=100 FINE_STEP=25 STEP_S=20 P95_MAX=100 MAX_RATE=3000 \
  WARMUP_DURATION=150s REPS=5 OUT=results/capacity ./scripts/run-capacity.sh
python scripts/analyze-capacity.py --dir results/capacity --p95-max 100
```

As 25 execuções concluíram sem falha de instrumento, e o estágio fino correu em todas.
Duração total de cerca de três horas.

### 12.1 Resultado

| Framework | Repetições (req/s) | Valor-resumo | Critério | CV |
|---|---|---:|---|---:|
| Laravel | 275 300 325 350 350 | **325** | mediana | 10,2% |
| Django | 675 750 750 775 800 | **750** | mediana | 6,2% |
| Spring Boot | 1375 1475 1550 1575 1675 | **1.550** | mediana | 7,3% |
| NestJS | 1575 1575 1575 1575 1600 | **1.575** | moda (4/5) | **0,7%** |
| ASP.NET Core | 1725 1875 1975 2025 2175 | **1.975** | mediana | 8,6% |

**[C_min] = 325 req/s (Laravel).** Níveis do teste de carga fixa, arredondados para baixo
porque o k6 lê `RATE` com `parseInt` e a taxa tem de ser inteira:

| Nível | Exato | Taxa a usar |
|---|---:|---:|
| 25% | 81,25 req/s | **81** |
| 50% | 162,50 req/s | **162** |
| 75% | 243,75 req/s | **243** |

O NestJS é a exceção em estabilidade: quatro repetições idênticas e CV de 0,7%, contra 6% a
10% nos outros quatro. A dispersão dos demais confirma com folga que [N_A] = 1 era
insuficiente, como a seção 11.3 já indicava.

### 12.2 Por que a moda passou a exigir maioria

A regra original — patamar mais frequentemente sustentado, ou a mediana na ausência de moda —
produziu um resultado indesejado no único framework em que ele tem consequência. As cinco
repetições do Laravel vão de 275 a 350, e o 350 aparece duas vezes: há moda, e ela é o **maior
valor observado**. Como o Laravel define o C_min, esse valor fixaria os três níveis de toda a
campanha.

O risco é concreto porque a transição do Laravel é uma falésia, e não uma degradação: o p95
fica entre 8,5 e 9,2 ms até a capacidade e salta para 2.000 a 2.900 ms no passo seguinte, de
25 req/s, com milhares de iterações descartadas. O ponto da falésia varia por sessão — 375 nas
repetições 1 e 2, 350 na 5, 325 na 3 e **300 na 4**.

| [C_min] | Nível de 75% | Folga até a pior falésia (275) |
|---|---:|---|
| moda, 350 | 262,5 req/s | +12,5 req/s — **uma unidade de resolução** |
| mediana, 325 | 243,8 req/s | +31,2 req/s — 2,5 unidades |
| mínimo, 275 | 206,2 req/s | +68,8 req/s — 5,5 unidades |

A seção 3.4.3 da monografia justifica a folga de 25% do nível superior como o que mantém a
taxa abaixo da capacidade de todos os tratamentos. Essa folga foi concebida contra a diferença
**entre** frameworks; a variância do Laravel consigo mesmo, de 27% entre sessões, consome 20
dos 25 pontos.

A causa é que, com [N_A] = 5 e resolução de 25 req/s, uma moda de 2 em 5 quase não é evidência
sobre os valores que aparecem uma vez. **A regra passou a exigir maioria** — mais da metade das
repetições, isto é, ao menos 3 de 5 —, caindo para a mediana caso contrário. Aplicada aos dados
acima, ela preserva a moda do NestJS (4/5), não altera o Django (moda e mediana coincidem em
750) e leva o Laravel de 350 para 325. Está em `resumir_patamares`, em
`scripts/analyze-capacity.py`.

### 12.3 Efeito de posição, agora medido

Capacidade de cada execução relativa à mediana do próprio framework, agrupada pela posição que
o tratamento ocupou na rodada:

| Posição na rodada | 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|
| Desvio médio | +3,7% | 0,0% | +1,4% | −3,0% | −5,6% |

Cerca de nove pontos percentuais entre a primeira e a última posição, de forma quase monótona.
A intercalação **não elimina** o efeito: ela o distribui entre os cinco tratamentos, que é
exatamente o que a seção 3.6.1 da monografia afirma. O dado permite trocar o argumento por uma
medida.

Não há efeito de rodada: os desvios médios por rodada são −0,4%, +1,5%, −4,1%, −4,2% e +3,7%,
sem tendência. Não houve deriva ao longo das três horas de sessão.

### 12.4 O que ainda falta

| Símbolo | Situação |
|---|---|
| [C_min] | **325 req/s**, fechado |
| níveis | **81 / 162 / 243 req/s**, fechados |
| [Z] | 20 s; ver a ressalva da seção 12.5 |
| aquecimento, [k], limiar | dependem da execução de reconfirmação, agora possível: ela roda no nível intermediário, 162 req/s |
| [CV], [H] | deixaram de ser lacunas; passam a ser resultado a reportar |

### 12.5 Ressalva sobre [Z] e o NestJS

O NestJS foi o único framework a exibir curva não monótona no estudo-piloto (54,59 ms a 1.400
req/s contra 38,40 ms a 1.500), padrão que reapareceu no ensaio a seco. Com 28.000 requisições
por janela de 20 s, isso não é ruído de amostra pequena: é variabilidade real do sistema dentro
da janela. Uma janela maior faria a média sobre mais desses eventos transitórios.

A distinção importa porque foi essa não monotonicidade que motivou a regra do "último patamar
antes da primeira violação" na seção 3.4.2. Se ela for função do comprimento da janela, a regra
descreve o instrumento; se for do framework, descreve o objeto. Uma repetição do NestJS com
[Z] = 60 s resolve, a um custo de cerca de 30 minutos. Não justifica elevar [Z] para todos: a
transição dos outros quatro é de duas ordens de grandeza, e o teste formal iria de três para
cerca de treze horas.

---

## 13. Reconfirmação do aquecimento sob o modelo aberto (30/09/2026)

Execução no nível intermediário do teste de carga fixa, 162 req/s, por 600 s em cada
framework, com contêiner recém-criado e base restaurada. Produzida pelo commit `72134db`.
Reprodução:

```bash
RATE=162 DURATION=600s BUCKET_S=10 OUT=results/warmup-aberto ./scripts/verify-warmup.sh
```

A duração é o dobro da padrão de propósito: era preciso enxergar o platô muito além do
período de aquecimento em exame, e não apenas verificar se ele havia sido alcançado.

### 13.1 Resultado

| Framework | 1º intervalo | Regime | Entrada (±10%) | Regime (k=5, 2%) | Erro |
|---|---:|---:|---:|---:|---:|
| Spring Boot | 594,3 ms | 2,50 ms | 50 s | **90 s** | 0% |
| ASP.NET Core | 87,0 ms | 2,61 ms | 10 s | 60 s | 0% |
| NestJS | 3,3 ms | 2,76 ms | 10 s | 70 s | 0% |
| Django | 10,2 ms | 3,65 ms | 10 s | 50 s | 0% |
| Laravel | 6,5 ms | 5,87 ms | 0 s | 50 s | 0% |

**Os 150 s adotados se confirmam com folga:** 67% de margem sobre o pior caso de 90 s. Taxa de
erro nula nos cinco, de modo que o critério de aceite 8.3 fica satisfeito também sob o modelo
aberto.

### 13.2 A estimativa anterior de ~350 s estava errada

Antes desta execução, estimou-se por modelo de volume acumulado que o Spring Boot precisaria
de cerca de 350 s a esta taxa, e recomendou-se orçar cerca de 8 h adicionais à campanha. **A
medição refuta a estimativa**, e o registro do erro fica porque o raciocínio chegou a entrar na
redação da metodologia.

A série do Spring Boot mostra o que de fato ocorre:

```
594  5  3  3  3  3  3  3  3  3  3 ...   (média em ms, intervalos de 10 s)
```

Um intervalo de 594 ms — 1.620 requisições — e o tratamento está aquecido.

O erro foi tomar os "90 s até o regime" do piloto de modelo fechado como medida de compilação
em tempo de execução e escalá-los pelo volume acumulado. A 100 VUs concorrentes o Spring Boot
estava **saturado**: o regime de 104 ms daquele piloto era latência de fila, não latência
quente do framework. O regime verdadeiro, medido agora sob taxa de chegada fixa em cerca de
10% da capacidade, é de **2,50 ms** — quarenta vezes menor. A premissa do volume acumulado vale
para o compilador; a grandeza à qual ela foi aplicada não era compilação.

A consequência prática é que a campanha volta à estimativa de cerca de 19 h, e não 27 h.

### 13.3 O par (k, limiar): 5 e 2%

Pior caso entre os cinco frameworks, por par, sobre as mesmas séries:

| k | 2% | 3% | 5% | 10% |
|---|---|---|---|---|
| 3 | 70 s | 70 s | 50 s | 40 s |
| **5** | **90 s** | 90 s | 70 s | 70 s |
| 6 | 220 s | 100 s | 80 s | 80 s |
| 10 | **não atingido** | 200 s | 200 s | 110 s |

**Adotado: k = 5 intervalos de 10 s, com CV < 2%.** Três razões. O limiar de 2% é o que
Georges, Buytaert e Eeckhout (2007) adotam na própria avaliação. É a maior janela em que os
cinco frameworks atingem esse limiar. E os 90 s resultantes cabem nos 150 s de aquecimento com
margem.

O k = 10 dos autores permanece inatingível a 2%, mas por motivo diferente do observado no
piloto de modelo fechado. Lá o obstáculo era o piso de ruído alto, de 4,6% a 17,2%, produzido
pela saturação. Aqui os pisos são baixos — Laravel 2,3%, Django 3,3%, NestJS 6,5%, ASP.NET
Core 7,5%. O obstáculo passou a ser a escala: com latência de regime de 2,5 ms, um único evento
transitório destrói a janela. O Spring Boot tem um pico isolado de 16 ms no intervalo 33 que
contamina dez janelas consecutivas e leva o coeficiente de variação da cauda dele a 80%.

O par está em `CV_MAX` e `K_ADOTADO`, em `scripts/analyze-warmup.py`, que passou a reportar o
pior caso do par adotado e a sinalizar quando algum framework não o atinge.

### 13.4 Convergência de dois critérios independentes

O critério de ±10% em torno do regime e o critério do coeficiente de variação foram calculados
sobre os mesmos dados sem partilhar formulação. O primeiro sugere 90 s de aquecimento como
pior caso com margem; o segundo dá pior caso de 90 s. A coincidência não prova a suficiência do
período, mas mostra que ela não depende de qual dos dois critérios se adote.

### 13.5 O que resta

| Símbolo | Situação |
|---|---|
| aquecimento | **150 s**, confirmado com 67% de margem |
| [k], limiar | **5 intervalos, CV < 2%**, fechados |
| [C_min], níveis | 325 req/s; 81 / 162 / 243 req/s |
| [CV], [H] | resultado a reportar, e não lacuna a preencher |
| [Z] | 20 s; a ressalva da seção 12.5 sobre o NestJS segue aberta |

Nada mais bloqueia a campanha. O piloto de variabilidade deixa de ser etapa separada: suas
execuções são execuções do nível intermediário e contam como as primeiras repetições.

---

## 14. Teste de capacidade com confirmação de violação (06/10/2026)

Reexecução das vinte e cinco células do teste formal, após a seção 12, sob duas regras novas
de parada. Substitui os resultados da seção 12, preservados em
`results/capacity-v1-sem-confirmacao/`. Reprodução:

```bash
START=100 STEP=100 FINE_STEP=25 STEP_S=20 P95_MAX=100 MAX_RATE=3000 \
  WARMUP_DURATION=150s REPS=5 OUT=results/capacity ./scripts/run-capacity.sh
python scripts/analyze-capacity.py --dir results/capacity --p95-max 100
```

A execução foi interrompida com 15 das 25 células concluídas e retomada em seguida; a
retomada por célula funcionou como previsto, refazendo apenas a célula parcial. Tempo de
máquina total em torno de 3h45min.

### 14.1 Resultado

| Framework | Repetições (req/s) | Valor-resumo | Critério | CV |
|---|---|---:|---|---:|
| Laravel | 275 325 325 325 350 | **325** | moda (3/5) | 8,6% |
| Django | 675 700 775 800 800 | **775** | mediana | 7,8% |
| Spring Boot | 1300 1375 1400 1450 1500 | **1.400** | mediana | 5,4% |
| NestJS | 1275 1375 1525 1575 1600 | **1.525** | mediana | 9,5% |
| ASP.NET Core | 1500 1600 1700 2050 2325 | **1.700** | mediana | 18,7% |

**[C_min] = 325 req/s (Laravel).** Níveis do teste de carga fixa: **81, 162 e 243 req/s**,
arredondados para baixo a partir de 81,25, 162,50 e 243,75. São os mesmos valores que a seção
12 produzia, por coincidência numérica e não por equivalência de método.

### 14.2 Primeira regra: confirmação da violação de p95

A seção 12 definia a capacidade pelo último patamar antes da **primeira** violação. Isso
media, para um framework com eventos transitórios, a taxa em que o primeiro deles calha de
cruzar o teto, e não a capacidade. A grandeza assim medida depende da duração do patamar: a
capacidade do NestJS caía de 1.575 req/s com patamares de 20 s para 1.000 com patamares de
60 s, e o coeficiente de variação subia de 0,7% para 12%.

Aqueles 0,7% mereciam desconfiança e não foram desconfiados a tempo. Não eram precisão: eram
a varredura truncando reiteradamente no mesmo evento precoce, isto é, medindo com consistência
a coisa errada. Sob a regra atual o CV do NestJS é de 9,5%, da mesma ordem dos demais.

A regra passou a exigir que a violação se repita no patamar imediatamente seguinte.

### 14.3 Segunda regra: descarte de iterações é terminal

A confirmação, aplicada a **qualquer** violação, produziu um resultado indefensável. Na
repetição 4 do Spring Boot:

```
   1300 req/s   p95    5,4 ms   descartes      0
   1400 req/s   p95 2820,4 ms   descartes 13291   <- colapso
   1500 req/s   p95    5,8 ms   descartes      0
   1600 req/s   p95 2775,2 ms   descartes 14395   <- colapso
   1700 req/s   p95    5,8 ms   descartes      0
```

Como as taxas seguintes voltavam ao normal, os dois colapsos foram tratados como transitórios
e a capacidade foi reportada como 1.700 req/s. Isso contradiz a definição do próprio texto: a
seção 3.4.2 da monografia descreve o descarte de iterações como condição operacional de
saturação, e uma taxa em que o sistema saturou não é uma taxa que ele sustentou.

Descarte de iterações e taxa de erro passaram a interromper a varredura de imediato. Só o teto
de p95 pede confirmação, que é onde está o ruído de medição. Das 19 violações isoladas
observadas nas 25 varreduras, **9 são de p95 com zero descartes**, em três dos cinco
frameworks (ASP.NET Core, NestJS e Spring Boot); as outras 10 trazem descartes e passam a ser
terminais.

A mudança **não exigiu reexecução**: a regra nova para antes da anterior, sempre num prefixo
da mesma curva, de modo que os dados coletados a sustentam.

### 14.4 Procedência dos arquivos

Os CSVs em `results/capacity/` foram gravados pelo script sob a regra intermediária, que exigia
confirmação para qualquer violação. Em consequência, as linhas `# transitorios=` e
`# capacidade_observada=` neles **refletem aquela regra**, e não a final. Os valores
autoritativos são os do `analyze-capacity.py`, que aplica a regra de 14.3 na leitura. Quem for
reler os arquivos diretamente precisa saber disso.

### 14.5 Biestabilidade do Spring Boot

O comportamento mostrado em 14.3 não é degradação progressiva: o tratamento alterna entre
5,8 ms e 2,8 s em taxas adjacentes. A interpretação plausível é uma cascata disparada por
evento transitório, em que as requisições se acumulam, o conjunto de conexões se esgota e o
gerador deixa de iniciar iterações no instante previsto. Como cada patamar é uma invocação
independente do k6, com conexões novas, a cascata não atravessa para o patamar seguinte.

É característica do sistema sob teste, e não do instrumento. Pode valer uma linha na seção
3.6.1 da monografia, para antecipar a pergunta.

### 14.6 Dispersão e o caso do ASP.NET Core

O CV do ASP.NET Core é de 18,7%, o maior dos cinco, com repetições entre 1.500 e 2.325 req/s.
Não é piora da medição: é a dispersão real de quando ele satura pela primeira vez, que a regra
da seção 12 escondia ao ignorar saturações.

**23/10/2026 — a leitura acima fica enfraquecida.** Remedida a capacidade no modo de energia
Desempenho Máximo (seção 21), o CV do ASP.NET Core cai para 3,2%, e o de Django e NestJS para
1,9% e 2,9%. Boa parte da dispersão atribuída aqui ao comportamento do tratamento parece ter
vindo do gerenciamento de energia do host. Para o ASP.NET Core a atribuição não é limpa: entre
as duas medições mudou também o runtime, de 10.0.12 para 10.0.13 (seção 19). Ele é o framework com mais eventos de saturação
esporádica, dez nas cinco execuções, contra cinco do Spring Boot, dois do Laravel, dois do
NestJS e nenhum do Django.

Convém registrar que, para esse tratamento, a leitura alternativa da definição — o maior
patamar que satisfaz as condições — daria valores bem mais altos, até 2.475 req/s numa
repetição cujo valor adotado é 1.500. A distância entre as duas leituras mede o quanto a
capacidade dele é esporádica, e é mais um argumento para a leitura conservadora adotada.

### 14.6.1 Deriva de sessão: não há

Acrescentado em 21/10/2026, depois que a seção 15.3.6 mediu que o tempo de vida do processo
do PostgreSQL degrada a latência de regime. O teste desta seção correu cerca de 3 h 45 com o
contêiner do banco ativo do começo ao fim. Se a mesma degradação o atingisse, as células
tardias teriam capacidade sistematicamente menor e o [C_min] seria artefato da ordem de
execução.

O teste não exige medição nova. Cada uma das 25 células tem uma posição na sessão, dada por
(repetição − 1) × 5 + posição na rodada, que o `ordem.csv` registra; a capacidade de cada
uma é comparada à **mediana do próprio framework**, o que remove a diferença entre
tratamentos e deixa só o desvio atribuível à sessão. Sobre esses desvios calculam-se a
inclinação por célula e a correlação de Pearson contra o índice. As capacidades saem do
`analyze-capacity.py`, e não são recalculadas.

```bash
python scripts/analyze-capacity-deriva.py --dir results/capacity
```

| | |
|---|---|
| células | 25 |
| inclinação | **+0,202% por célula** |
| correlação de Pearson | **r = +0,132** |

Deriva por envelhecimento preveria inclinação negativa e correlação apreciável. A inclinação
observada é positiva e desprezível. Os dados da seção 14 não mostram deriva de sessão, o que
é coerente com a ausência de efeito de rodada que 12.3 reportou para os dados da seção 12.

**O limite do teste.** Com n = 25 e a dispersão entre repetições do mesmo framework sendo
grande — o ASP.NET Core vai de 1.500 a 2.325 req/s —, o teste tem pouca potência: descarta
deriva grande, e não deriva pequena. Convém também registrar que a capacidade pode ser menos
sensível ao estado do banco que a latência de regime, por ser medida onde o limite do próprio
sistema domina, de modo que a ausência de deriva aqui não contradiz a degradação medida em
15.3.6 a 162 req/s.

### 14.7 A regra de resumo, e uma divergência entre texto e código

O valor-resumo de cada framework sai do `resumir_patamares`, em
`scripts/analyze-capacity.py`, que exige **maioria** das repetições para adotar a moda e cai
para a mediana quando nenhum patamar a reúne. A exigência de maioria foi decidida em
30/09/2026 pelo motivo registrado em 12.2: com [N_A] = 5 e resolução de 25 req/s, um valor
repetido em duas de cinco repetições quase não se distingue dos que aparecem uma vez, e aquela
moda fraca caiu justamente sobre o maior valor observado do framework que define o C_min.

A seção 3.4.2 da monografia, porém, descreveu a regra até 06/10/2026 como "patamar mais
frequentemente sustentado entre as repetições ou, na ausência de moda, pela mediana" — moda
simples, sem exigência de maioria. A decisão foi registrada aqui e implementada no código, mas
a frase correspondente da monografia não foi atualizada na ocasião.

**17/10/2026 — divergência sanada.** A seção 3.4.2 da monografia passou a descrever a regra
de maioria, nos termos em que ela está em `resumir_patamares`. O parágrafo acima fica como
registro de que texto e código estiveram em desacordo entre 30/09/2026 e 17/10/2026, e do que
a monografia dizia nesse intervalo.

Sobre os dados desta seção, as duas leituras divergem em um framework:

| Framework | Repetições | Moda simples | Maioria (adotada) |
|---|---|---:|---:|
| Laravel | 275 325 325 325 350 | 325 (moda, 3/5) | 325 (moda, 3/5) |
| **Django** | 675 700 775 800 800 | **800** (moda, 2/5) | **775** (mediana) |
| Spring Boot | 1300 1375 1400 1450 1500 | 1.400 (mediana) | 1.400 (mediana) |
| NestJS | 1275 1375 1525 1575 1600 | 1.525 (mediana) | 1.525 (mediana) |
| ASP.NET Core | 1500 1600 1700 2050 2325 | 1.700 (mediana) | 1.700 (mediana) |

O [C_min] não depende da escolha: é 325 req/s nas duas leituras, e os níveis permanecem 81,
162 e 243 req/s. O que muda é o valor do Django, que entra no modelo multicritério como
critério de capacidade.

### 14.8 Os dados da seção 12 estão superados

Registra-se porque a confusão já ocorreu uma vez. As capacidades do Laravel na seção 12 são
350, 350, 300, 275 e 325 req/s; as desta seção são 275, 325, 325, 325 e 350. São execuções
distintas, sob regras de parada distintas, e **apenas as desta seção valem**. Aplicar a regra
de resumo aos números da seção 12 dá C_min de 350 req/s e níveis de 87, 175 e 262, que não são
os do aparato.

Os arquivos da seção 12 seguem em `results/capacity-v1-sem-confirmacao/` para comparação, e não
para uso.

### 14.9 Estado

| Símbolo | Valor |
|---|---|
| [X] | 100 ms |
| [Y] | 100 req/s no estágio grosso, 25 no fino; resolução ±12,5 |
| [Z] | 20 s |
| [N_A] | 5 |
| [D] | 300 s |
| aquecimento | 150 s |
| [k], limiar | 5 intervalos de 10 s, CV < 2% |
| [C_min] | **325 req/s** |
| níveis | **81 / 162 / 243 req/s** |
| [CV], [H] | resultado a reportar |

O aparato está fechado. Resta a campanha: 5 frameworks × 3 níveis × 10 repetições, cerca de
19 h, com retomada por célula.

---

## 15. Congelamento do protocolo (19/10/2026)

O aparato de coleta está congelado na tag anotada `protocolo-v2`, que aponta para o commit
`b5499ea`. Dali em diante, alteração em `scripts/`, `k6/` ou `infra/` quebra a comparabilidade
das células já medidas e exige nova tag. Ficam **fora** da tag o `README.md`, o `docs/` e o
`results/`: documentação e dados seguem sendo escritos sem que o protocolo se mova.

### 15.1 Os critérios de aceite não foram reexecutados, e não precisavam ser

Nada que D.1 a D.3 verificam mudou desde a execução que estabeleceu cada um.

**D.1 e D.2** vêm da execução de 10/09/2026, na seção 7.1. O `k6/contract-test.js`, o
`scripts/verify-queries.sh` e o `scripts/compare-fingerprints.sh` nunca foram alterados desde
o commit inicial, e `apps/` só mudou em `e124eeb`, que trocou o campo `license` do
`package.json` do NestJS de `UNLICENSED` para `MIT`. No que esses dois critérios verificam, as
implementações sob teste são as mesmas que passaram. Os cinco `results/fingerprint-*.json`
seguem com um único sha256, `d397c641…c476`.

**D.3** vem da execução de 30/09/2026 em `results/warmup-aberto/`, cujo `parametros.txt`
registra o commit `72134db` — o último a alterar o `verify-warmup.sh`. Recomputada em
19/10/2026 pelo `analyze-warmup.py`: taxa de erro nula nos cinco e regime aos 90 s no pior
caso sob (k = 5, CV < 2%), dentro dos 150 s adotados.

### 15.2 O rótulo `name` e D.3

O `k6/load-test.js` mudou **depois** da execução que estabeleceu D.3, em `8ce8612`
(30/09/2026, 18h01), que passou a agrupar as URLs nas métricas do k6 com o rótulo `name`. A
série de aquecimento foi coletada sem o rótulo; a campanha roda com ele. A pergunta — se os
150 s seguem válidos — se responde sem reexecução, por três vias.

**O que D.3 mede não depende do rótulo.** A série por intervalo sai da sub-métrica
`http_req_duration{bucket:N}`, materializada pelos limiares de `bucketThresholds()` e lida em
`handleSummary`. O conjunto de amostras de `{bucket:N}` é o mesmo com ou sem um segundo
rótulo em cada requisição, e a média e o p95 do intervalo não mudam por isso. O rótulo altera
quantas séries o k6 materializa, não como a latência do intervalo é agregada.

**A cardinalidade não contaminou aquela execução.** O risco que o rótulo evita é indireto: as
séries acumuladas consomem memória do gerador, que roda na mesma máquina, e suas pausas de
coleta de lixo entrariam na latência reportada. O efeito cresceria ao longo da execução,
porque a cardinalidade cresce — da ordem de 29 mil URLs únicas ao fim dos 600 s, sob o esquema
antigo de séries. A série não mostra isso. Média por terço, descartados os 100 s de entrada:

| Framework | 100–266 s | 266–433 s | 433–600 s | deriva | p95 do 1º | p95 do 3º |
|---|---:|---:|---:|---:|---:|---:|
| ASP.NET Core | 2,61 ms | 2,62 ms | 2,69 ms | +3,2% | 5,41 ms | 5,58 ms |
| Django | 3,76 ms | 3,65 ms | 3,71 ms | −1,3% | 6,42 ms | 6,22 ms |
| Laravel | 5,81 ms | 5,93 ms | 5,90 ms | +1,5% | 8,67 ms | 8,85 ms |
| NestJS | 2,85 ms | 2,75 ms | 2,83 ms | −0,5% | 5,51 ms | 5,47 ms |
| Spring Boot | 2,59 ms | 3,49 ms | 2,56 ms | −1,3% | 5,23 ms | 5,22 ms |

O terço final é o de cardinalidade máxima, e é onde a contaminação apareceria. Não aparece: a
deriva fica dentro de ±3,2% e o p95 por terço acompanha. O terço do meio do Spring Boot
carrega o pico isolado de 16 ms do intervalo 33, já descrito em 13.3.

**A direção do risco é favorável.** Aquela execução correu na condição de *mais* séries, a de
maior sobrecarga do gerador. A campanha corre com o rótulo, com cinco nomes de série em lugar
de dezenas de milhares. Um período de aquecimento que bastou sob o gerador mais pesado basta
sob o mais leve.

A comparação que havia sido feita à parte — `results/capacity-nestjs-z60-name/` contra
`results/capacity-nestjs-z60/`, 1.000 contra 1.350 req/s — **não** serve para decidir isto:
são três repetições cada, sob [Z] = 60 s, e a diferença não se separa da dispersão do NestJS.
Ela mede capacidade, cujo critério é o p95 por patamar e é sensível a evento transitório, e
não estabilização da média, que é o que D.3 verifica.

Registra-se um detalhe da mesma execução: o Spring Boot completou 97.080 requisições das
97.201 dos demais, com 121 iterações descartadas. O arquivo guarda apenas o total, e o
primeiro intervalo, de 594,3 ms, é onde a compilação em tempo de execução as produz — ou seja,
dentro do que os 150 s de aquecimento descartam. A taxa de erro é nula nos cinco, como D.3
exige.

O `verify-warmup.sh` foi reexecutado em 19/10/2026 para fechar a questão por medição direta.
A execução não a fechou, por motivo alheio ao rótulo: ver a seção 15.3.

---

## 15.3 Reexecução do aquecimento em 19/10/2026 — inconclusiva

Reexecução do `verify-warmup.sh` sob o aparato congelado, com os parâmetros da seção 13 —
162 req/s, 600 s, intervalos de 10 s —, gravada em `results/warmup-aberto-name/`. Não
reproduz a série de 30/09 e **não decide** a questão do rótulo.

| | 30/09, sem rótulo | 19/10, com rótulo |
|---|---|---|
| taxa de erro | nula nos cinco | nula nos cinco |
| pior caso (k = 5, CV < 2%) | 90 s | **560 s**, no Django |
| iterações descartadas | 121, no Spring Boot | **2.786** no Django; 83 no Spring Boot |
| regime do Spring Boot | 2,96 ms | 4,77 ms (+62%) |
| regime do Django | 3,70 ms | 4,39 ms (+19%) |
| regime do ASP.NET Core | 2,65 ms | 2,96 ms (+12%) |

### 15.3.1 O que ocorreu

Entre 110 s e 199 s o Django saturou: média por intervalo de até 4.183,9 ms, p95 de até
11.270,7 ms e 2.786 iterações nunca iniciadas no instante previsto — 2,9% das 97.201
esperadas. Pela condição (iii) da seção 3.4.2, descarte de iterações é saturação operacional.
Isso a 162 req/s, que são 21% dos 775 req/s de capacidade medidos para o Django na seção 14.1.
Antes e depois da excursão a série dele fica entre 3,5 e 4,5 ms.

### 15.3.2 A execução não é comparável à de 30/09

A latência de regime subiu em quatro dos cinco tratamentos, o Spring Boot em 62%. Isso indica
carga ambiente maior nesta sessão do que naquela: a medição foi disparada de uma sessão de
trabalho que seguia ativa na mesma máquina, condição que a de 30/09 não tinha. É exatamente a
ameaça que a seção 3.6.1 da monografia descreve. Uma reconfirmação válida exige máquina
ociosa, e esta execução não a substitui.

### 15.3.3 O rótulo `name` não é candidato a causa

O rótulo reduz a cardinalidade de séries e, com ela, a sobrecarga do gerador; uma parada de
quatro segundos no tratamento não vem daí. O argumento de mecanismo da seção 15.2 — a
sub-métrica `http_req_duration{bucket:N}` agrega sobre todas as requisições do intervalo, com
ou sem um segundo rótulo — não é afetado por esta execução.

### 15.3.4 O que fica em aberto, e é outra coisa

Se uma parada de 90 s pode ocorrer a 162 req/s, ela cabe dentro dos 300 s de medição de uma
célula da campanha. O aparato já prevê o caso, e a primeira versão desta seção errou ao dizer
que não: o `run-experiment.sh` registra toda execução com erro ou iterações descartadas em
`invalidas.csv`, o `analyze-experiment.py` as destaca como execuções a investigar antes de
usar, e o protocolo manda investigar cada uma e repeti-la quando o erro decorrer de falha do
ambiente. O script não descarta nem repete nada sozinho, deliberadamente.

O que fica em aberto é a frequência. Se paradas como esta forem reprodutíveis a 162 req/s,
parte das 150 células da campanha cairá em `invalidas.csv`, e o custo de calendário deixa de
ser as ~19 h da seção 13.2. É isso que uma reexecução em máquina ociosa mediria.

Sobre a causa, nada se afirma. Os logs do PostgreSQL mostram checkpoints de 270 s a cada
5 min durante toda a sessão, inclusive nas janelas dos outros quatro tratamentos, e o
`parametros.txt` registra apenas o início da execução inteira, não o de cada tratamento, de
modo que a série do Django não pode ser alinhada ao log com precisão suficiente para imputar
a excursão a um checkpoint. Registrar a lacuna é mais útil que escolher uma explicação.

### 15.3.5 Repetição só do Django — a parada não reaparece

Repetição do `verify-warmup.sh` apenas para o Django, mesmos parâmetros, em
`results/warmup-django-ocioso/`. **A parada de 90 s não se reproduziu:** zero iterações
descartadas, 97.201 requisições completas, taxa de erro nula. A excursão de 15.3.1 era do
ambiente, e não do tratamento.

O período de aquecimento, porém, segue sem ficar estabelecido. Entre as duas execuções sem
descarte:

| | 30/09 | 19/10 |
|---|---:|---:|
| 1º intervalo | 10,19 ms | 19,04 ms |
| média de 0 a 100 s | 4,30 ms | 6,43 ms |
| média de 100 a 200 s | 3,74 ms | 4,54 ms |
| média de 400 a 600 s | 3,70 ms | 3,77 ms |
| entrada sustentada na banda de ±10% | 10 s | **290 s** |
| pior caso (k = 5, CV < 2%) | 50 s | **410 s** |

As duas convergem para o mesmo regime — 3,69 e 3,83 ms, diferença de 3,8% — mas a de 19/10
leva de 300 a 400 s para chegar lá. O ponto de chegada é o mesmo; o tempo de chegada, não.

**Esta execução também não correu em máquina controlada.** Dois contêineres de outro projeto,
`veredaedu-postgres-test` e `veredaedu-localstack-test`, estavam de pé durante toda a medição.
Subiram 13 min antes dela — 17:50:14 e 17:50:35 UTC, contra início às 18:03:37 UTC —, de modo
que a partida deles não cai na janela, mas o que executaram durante ela não é observável a
posteriori.

**E o teste de validade adotado era inadequado.** Fixou-se, antes de medir, o critério de
comparar a latência de regime com os 3,70 ms de 30/09; ela passou, com 3,83 ms. Mas o regime
se calcula sobre os últimos 300 s, isto é, depois de qualquer interferência inicial — e os
primeiros intervalos são justamente o que determina o período de aquecimento. O critério não
podia detectar a contaminação da parte da série que decide a questão. Um teste útil olharia os
primeiros intervalos e registraria os contêineres de pé antes e depois.

**Uma hipótese a testar, com consequência para a campanha.** O contêiner do PostgreSQL estava
de pé havia cinco horas, com 20 GB de WAL escritos e 58 checkpoints temporizados, cada um
espalhando escrita por 270 s. A execução de 30/09 partiu de instância bem mais nova. Como o
Apêndice E mantém o banco de pé ao longo de toda a campanha de propósito, recriando apenas o
contêiner da aplicação, a condição desta execução é a das células da campanha, e a de 30/09 é
a da primeira delas. Se a pressão de escrita acumulada eleva o tempo de aquecimento, os 150 s
foram calibrados na condição favorável.

Nada disso está estabelecido. Separar as duas coisas pede duas execuções do Django em máquina
sem outra carga: uma com o PostgreSQL recém-subido e em repouso, outra imediatamente após uma
célula de escrita intensa. Cerca de 25 min.

### 15.3.6 O par de execuções: é o tempo de vida do processo do banco

As duas execuções foram feitas, em `results/warmup-django-pg-novo/` (A, PostgreSQL reiniciado
38 s antes) e `results/warmup-django-pg-usado/` (B, imediatamente após A, com o banco de pé há
11 min e uma célula de escrita intensa no histórico). Carga ambiente medida antes de cada uma:
os dois contêineres de outro projeto em 0,01% a 0,03% de CPU, isto é, presentes e ociosos.

| Execução | Estado do PostgreSQL | 0 a 100 s | 100 a 200 s | 400 a 600 s | (k=5, CV<2%) | descartes |
|---|---|---:|---:|---:|---:|---:|
| 30/09 | instância nova | 4,30 ms | 3,74 ms | 3,70 ms | 50 s | 0 |
| 19/10, 1ª | de pé há ~5 h | 5,57 ms | **676,52 ms** | 4,24 ms | 560 s | **2.786** |
| 19/10, 2ª | de pé há ~5 h | 6,43 ms | 4,54 ms | 3,77 ms | 410 s | 0 |
| **A** | **reiniciado há 38 s** | 4,43 ms | 3,73 ms | 3,71 ms | **50 s** | 0 |
| **B** | de pé há 11 min, após A | 4,07 ms | 3,84 ms | 3,71 ms | **60 s** | 0 |

A reprodução é limpa. A instância nova de 30/09, a reiniciada da A e a de uma célula de uso da
B concordam entre si — 50 a 60 s pelo critério adotado, séries planas a partir do segundo
intervalo. As duas execuções sobre a instância de cinco horas são as discordantes, e são
também as únicas em que o aquecimento excede os 150 s adotados.

**Uma célula de escrita intensa não degrada; horas de acúmulo degradam.** A B carrega uma
execução completa de 600 s a 162 req/s, com 30% de operações de escrita e a recarga de 200 mil
livros do `reset_db`, e ainda assim fica em 60 s. A diferença entre B e as de 19/10 não é a
quantidade de escrita recente, e sim o tempo de vida do processo.

**A causa não está identificada, e não se afirma.** Descarta-se o inchaço de tabela, porque o
`reset_db` trunca e recarrega antes de cada execução. Descarta-se o rótulo `name`, pela seção
15.2 e porque A e B o usam. Descartam-se os contêineres vizinhos, medidos ociosos. Restam
candidatos não separados: estado de memória do contêiner do banco, cache de disco da máquina
virtual do Docker, acúmulo de segmentos de WAL. Um reinício do contêiner preserva o esquema,
porque o volume persiste e o entrypoint só executa os scripts de inicialização em diretório
vazio — verificado nesta sessão.

### 15.3.7 Consequência para a campanha, a decidir

O Apêndice E mantém o banco de pé durante toda a campanha de propósito, recriando apenas o
contêiner da aplicação. A campanha é estimada em cerca de 19 h. A degradação apareceu com o
processo de pé havia cinco horas, de modo que a maior parte das células correria na condição
em que o aquecimento do Django pede 290 a 560 s, e não os 150 s adotados.

Três saídas, nenhuma adotada aqui:

1. Reiniciar o contêiner do banco periodicamente durante a campanha — custa cerca de um
   segundo e preserva o esquema. Toca o `run-experiment.sh`, que está congelado pela tag
   `protocolo-v2`, e exigiria nova tag e ajuste do Apêndice E.
2. Caracterizar o limiar, medindo a partir de quantas horas a degradação aparece, para decidir
   com dado em lugar de margem. Custa execuções longas.
3. Não mudar nada e confiar no `invalidas.csv`, que registra as células com descarte para
   investigação, conforme 15.3.4. Aceita refazer células e não cobre a degradação sem descarte,
   como a 2ª execução de 19/10, que não descartou nada e ainda assim levou 410 s.

---

## 16. Alteração do aparato: reinício do banco por célula (19/10/2026)

Decidida a partir de 15.3.6. O `restart_postgres`, em `scripts/common.sh`, reinicia o
processo do PostgreSQL e aguarda prontidão; o `run-experiment.sh` o chama antes do `reset_db`
em cada célula, e o `verify-warmup.sh` antes de cada tratamento, para que o critério de
aceite meça o aquecimento nas condições em que a campanha mede. Custa cerca de cinco segundos
por célula, algo como 12 min nas 150. Falha de reinício entra em `invalidas.csv` como
`banco_nao_reiniciou`.

Corrigiu-se, no mesmo trabalho, um defeito achado de passagem: a verificação de queda do
banco introduzida em `273a558` estava aninhada dentro do ramo de falha do `wait_health`, e não
depois da medição, de modo que nunca rodava no caminho em que importa. Um banco que caísse
durante a medição deixaria um JSON com 100% de erros que a retomada consideraria concluído.

### 16.1 Reverificação de D.3 sob o aparato alterado

`results/warmup-protocolo-v3/`, 162 req/s por 600 s nos cinco.

| Framework | 1º intervalo | Regime | 1º / regime | Entrada ±10% | (k=5, CV<2%) | Erro |
|---|---:|---:|---:|---:|---:|---:|
| ASP.NET Core | 109,7 ms | 2,81 ms | 39,1× | 10 s | 170 s | 0% |
| Django | 11,4 ms | 4,04 ms | 2,8× | 130 s | **50 s** | 0% |
| Laravel | 6,1 ms | 6,09 ms | 1,0× | 0 s | 100 s | 0% |
| NestJS | 3,4 ms | 2,81 ms | 1,2× | 30 s | 200 s | 0% |
| Spring Boot | 331,7 ms | 2,67 ms | 124,2× | 60 s | 120 s | 0% |

**O que se consertou.** O Django sai de 290 a 560 s para **50 s**, o mesmo valor de 30/09 e
das execuções A e B de 15.3.6. A patologia que motivou a alteração desapareceu, e a taxa de
erro é nula nos cinco, como D.3 exige.

**O que não passou.** O pior caso sob o par adotado é de **200 s**, acima dos 150 s. Mas não
é aquecimento: o NestJS começa a 3,4 ms contra regime de 2,81 ms, isto é, a 1,2× do regime —
não há transiente a esperar. Do segundo intervalo em diante sua série tem amplitude total de
1,20 ms e desvio de 0,25 ms, e os intervalos fora da banda de ±10% são o 1, 2, 15, 27, **48 e
52** — espalhados por toda a execução, inclusive aos 480 s e 520 s, muito depois de qualquer
aquecimento. O ASP.NET Core é igual: fora da banda nos intervalos 11, 30 e 50.

É a fragilidade que 13.3 já havia descrito para k = 10 e que agora alcança k = 5: com regime
de 2,8 ms, um pico isolado destrói dez janelas consecutivas, e o valor que o critério devolve
depende de onde o ruído cai, não de quando o tratamento aqueceu.

### 16.2 A convergência de 13.4 não vale mais

A seção 13.4 apresentava como corroboração o fato de os dois critérios independentes — ±10% em
torno do regime e coeficiente de variação — darem ambos 90 s. Sob esta execução eles divergem:
o de ±10% dá pior caso de **130 s**, dentro dos 150 s adotados; o do coeficiente de variação dá
**200 s**, fora. O argumento de convergência deixa de estar disponível, e os 150 s passam a se
apoiar no critério de ±10% mais o argumento de que o outro é inadequado nesta escala.

**Não se emitiu a tag `protocolo-v3`.** Emití-la agora seria afirmar D.3 satisfeito quando um
dos dois critérios não o afirma. A decisão não é de aparato, e sim de método, e cabe ao texto:

1. Manter os 150 s e registrar na seção 3.4.3 que o critério do coeficiente de variação é
   reportado, mas que sua instabilidade em regimes de poucos milissegundos o torna inadequado
   como teste de suficiência, ficando o de ±10% como operativo. É a leitura que os dados acima
   sustentam.
2. Elevar o aquecimento para os 210 s que o script sugere. Custa cerca de 2 h 30 na campanha e
   **não** resolve: o critério é movido por ruído pós-aquecimento, de modo que a próxima
   execução pode devolver outro valor.
3. Tornar o critério robusto a pico isolado, por mediana ou variação aparada. É alteração de
   instrumento sobre um critério citado de Georges, Buytaert e Eeckhout (2007), e exige
   justificativa no texto.

**19/10/2026, mais tarde — retificação.** O parágrafo acima e a tabela de 16.1 concluíram que
o critério de ±10% era o operativo e o do coeficiente de variação o inadequado. Está errado
pela metade: a reanálise das séries brutas, em 16.3, mostra que **os dois** são movidos por
eventos posteriores ao aquecimento. O de ±10% herda o defeito pela via do regime, que ele
toma pela média da cauda. O texto acima fica como registro da leitura intermediária.

### 16.3 Reanálise das séries de D.3

As duas definições de 16.1 discordavam — 130 s por uma, 200 s pela outra — e 16.2 atribuiu a
discordância à inadequação do critério do coeficiente de variação. A reanálise das séries
brutas de `results/warmup-protocolo-v3/*.json` mostra que o diagnóstico estava incompleto.

**O regime inflado.** O `analyze-warmup.py` tomava o regime pela MÉDIA dos últimos 30% dos
intervalos. Na série do Django há uma rajada entre 490 e 530 s — 6,00, 4,94, 4,42, 6,72 e
7,39 ms — contra platô de 3,62 ms desde o segundo intervalo. A média da cauda sobe a
4,305 ms e a banda de ±10% vira [3,874; 4,735], **acima do platô real**. Os intervalos do
platô ficam, portanto, fora da banda, e a entrada é reportada aos 130 s embora o tratamento
estivesse em regime aos 10 s. Com a MEDIANA da cauda o regime é 3,630 ms, a banda
[3,267; 3,993] contém o platô, e a entrada volta aos 10 s.

**A terceira definição.** Acrescentada ao `analyze-warmup.py` ao lado das duas anteriores,
que seguem sendo reportadas: regime pela mediana dos últimos 30%, entrada no primeiro
intervalo a partir do qual `K_PERSISTENCIA` = 5 intervalos consecutivos ficam dentro de
±10%, e contagem dos intervalos que saem da banda DEPOIS da entrada, com seus instantes.
Nenhum valor adotado mudou: `WARMUP_DURATION`, `CV_MAX` e `K_ADOTADO` seguem 150 s, 2% e 5.

| Framework | (1) CV, k=5 | (2) ±10% da média | (3) mediana + persistência | Excursões após a entrada, em (3) |
|---|---:|---:|---:|---|
| ASP.NET Core | 170 s | 10 s | **10 s** | 4: 110, 180, 300, 500 s |
| Django | 50 s | 130 s | **10 s** | 9: 130, 140, 250, 450 s… |
| Laravel | 100 s | 0 s | **0 s** | 4: 180, 290, 390, 480 s |
| NestJS | 200 s | 30 s | **30 s** | 6: 150, 270, 290, 480 s… |
| Spring Boot | 120 s | 60 s | **70 s** | 5: 150, 280, 470, 510 s… |
| **pior caso** | **200 s** | **130 s** | **70 s** |  |

**A terceira é a única reprodutível entre sessões.** Aplicadas às duas séries completas de
cinco frameworks que existem:

| Série | (1) CV | (2) ±10% da média | (3) mediana + persistência |
|---|---:|---:|---:|
| `warmup-aberto`, 30/09 | 90 s | 50 s | **80 s** |
| `warmup-protocolo-v3`, 19/10 | 200 s | 130 s | **70 s** |

O critério do coeficiente de variação salta de 90 para 200 s e o da média de 50 para 130 s,
entre sessões que medem o mesmo aparato; a terceira fica em 80 e 70 s. Reprodutibilidade
entre sessões é requisito mínimo de um critério, e só a terceira o cumpre — argumento
independente do que motivou propô-la. Nas duas séries do Django isolado as três concordam:
50 / 10 / 10 s em `warmup-django-pg-novo` e 60 / 10 / 10 s em `warmup-django-pg-usado`.
**21/10/2026 — a alegação de reprodutibilidade acima não se sustentou.** A segunda série
deu 220 s pela terceira definição, contra os 80 e 70 s das duas primeiras. O parágrafo fica
como registro; o que a segunda série mostrou está em 16.5, e explica também por que nenhuma
das três definições pode certificar D.3 neste nível de carga.

**Duas ressalvas que limitam o que isto autoriza a dizer.** A terceira definição foi
proposta DEPOIS de ver os dados de 19/10, e o docstring do script o declara: não é
pré-registrada, e um critério escolhido à luz da série que ele vai julgar pede confirmação
em série nova. E há **uma série por framework**, não mais: as excursões tabeladas acima
podem ser características do tratamento ou acidentes de sessão, e com n = 1 não há como
separar.

**Hipótese não testada sobre a rajada.** A seção 15.3.4 registra checkpoints de 270 s a
cada 5 min. Com o reinício do banco por tratamento, o relógio do checkpoint passa a zerar
junto com a execução. No log do PostgreSQL, a execução do Django em `protocolo-v3` correu
entre 19:51:50 e 20:01:49 UTC, e dentro dela há um `checkpoint starting: time` às 19:56:44
que se completa às 20:01:14 com `write=269,385 s` — fase de escrita espalhada de cerca de
294 s a 564 s da execução. A rajada de 490 a 530 s cai dentro dessa janela, no último sexto
dela. Mas o platô de 3,62 ms entre 294 e 490 s cai dentro da MESMA janela, de modo que a
coincidência não estabelece causa: o checkpoint estar ativo não produziu, por si, a rajada.
Fica como hipótese a testar, não como explicação.

**O que isto permite afirmar.** Não se afirma D.3 satisfeito. Afirma-se que os dados são
**compatíveis** com os 150 s pelas três leituras — a mais exigente dá 200 s, e é a que a
reanálise mostra movida por ruído posterior; as outras duas dão 130 e 70 s — e que falta uma
segunda série por framework para que a afirmação deixe de depender de n = 1.

#### Comando da segunda série

Em máquina ociosa, com o PostgreSQL de pé (passo 1 da sequência do README) e sem outra
carga:

```bash
RATE=162 DURATION=600s BUCKET_S=10 OUT=results/warmup-d3-serie2 ./scripts/verify-warmup.sh
```

`OUT` precisa ser diretório novo, sob o repositório: o k6 é conteinerizado e só enxerga a
raiz do projeto. `BUCKET_S=10` é obrigatório — sem ele o script não marca os intervalos e
não há série a analisar. O script reinicia o banco e recria o contêiner de cada aplicação
por conta própria.

Duração medida, e não estimada: a execução de `protocolo-v3` levou **50 min 49 s** nos
cinco, de 16:41:29 a 17:32:18 de 19/10/2026, com 10 min 10 s por tratamento. Conferir depois
com:

```bash
python scripts/analyze-warmup.py "results/warmup-d3-serie2/*.json"
```

### 16.4 A detecção de queda do banco, exercitada

A correção de aninhamento descrita em 16 nunca havia sido exercitada, porque exige derrubar
o banco no meio de uma medição. Foi exercitada em 19/10/2026, numa célula fora de
`results/campaign`, depois descartada. O contêiner não tem política de reinício
(`RestartPolicy=no`), de modo que nada o religava sozinho.

Uma célula de `springboot` a 81 req/s por 60 s, com os 150 s de aquecimento, e o banco
parado 40 s dentro da medição. Resultado: o k6 acusou VUs insuficientes, o
`require_postgres` posterior à medição falhou, o JSON da célula foi removido, e
`invalidas.csv` recebeu `banco_caiu_durante`. Religado o banco, a reexecução **refez** a
célula em lugar de pulá-la, e gravou medição íntegra: p95 de 7,2 ms, 81,0 req/s obtidas,
erro nulo, zero descartes. A guarda funciona de ponta a ponta.

Duas observações do teste. O `.stats.csv` da célula **não** é removido junto com o JSON;
não é defeito, porque a reexecução o sobrescreve, mas um diretório de campanha interrompida
pode conter `.stats.csv` órfãos. E o rótulo `banco_caiu_durante` é gravado na coluna
`taxa_erro` do `invalidas.csv`, que o cabeçalho sugere numérica — é a convenção já usada
por todos os modos de falha, e quem ler o arquivo com script precisa saber.

### 16.5 Segunda série de D.3 (21/10/2026): a tolerância é menor que o ruído

Executada com os parâmetros de 16.3, em `results/warmup-d3-serie2/`, na condição mais limpa
de toda a investigação: daemon do Docker recém-subido, nenhum contêiner de outro projeto,
PostgreSQL com 2 s de vida, semente íntegra, 0,05% de CPU na linha de base e 0,14% ao final.

| Definição | `warmup-aberto`, 30/09 | `warmup-protocolo-v3`, 19/10 | `warmup-d3-serie2`, 21/10 |
|---|---:|---:|---:|
| (1) CV, k=5 | 90 s | 200 s | **550 s** |
| (2) ±10% da média | 50 s | 130 s | **não entrou** |
| (3) mediana + persistência | 80 s | 70 s | **220 s** |

**A alegação de 16.3 está refutada.** A terceira definição foi apresentada ali como a única
reprodutível entre sessões, por dar 80 e 70 s. Na série que não participou de sua
formulação ela dá 220 s. Registre-se que a alegação foi feita sobre duas séries e caiu na
terceira — que é o que uma definição posterior aos dados arrisca.

Registre-se também o que a segunda definição fez: no Django, o último intervalo da série
traz 30,7 ms isolados, o que leva a média da cauda a 5,8 ms, e **nenhum** intervalo cai
dentro de ±10% dela. Um único intervalo em 60 reprova a série inteira. É o defeito que
16.3 diagnosticou, agora na sua forma extrema.

#### A causa, e ela é reprodutível

O que não se reproduz é o valor que os critérios devolvem. O que se reproduz é a razão:
compara-se a meia-largura da banda, 0,10 × regime, com o desvio-padrão do próprio platô —
do segundo intervalo em diante, descartados os três maiores valores como picos isolados:

| Framework | 30/09 | 19/10 | 21/10 |
|---|---:|---:|---:|
| ASP.NET Core | 0,30× | 0,40× | 0,39× |
| Django | 0,23× | 0,80× | 0,36× |
| Laravel | 0,17× | 0,45× | 0,72× |
| NestJS | 0,27× | 0,60× | 0,60× |
| **Spring Boot** | **0,95×** | **1,14×** | **1,37×** |

Nos quatro primeiros a banda acomoda o ruído com folga. No Spring Boot o ruído do platô
**iguala ou excede** a banda, nas três séries. Com regime de 2,95 ms, a banda é de ±0,295 ms
e o platô oscila entre 2,62 e 3,21 ms: a tolerância relativa caiu abaixo da variação
própria da medição. O efeito é visível no detalhe — na segunda série o intervalo de 210 s
dá 2,645 ms contra limite inferior de 2,657 ms, e esses 0,012 ms de diferença quebram a
janela de persistência e empurram a entrada de 180 s para 220 s.

Os 220 s do Spring Boot, portanto, não medem aquecimento. Sua série começa em 310 ms, cai a
4,1 ms no segundo intervalo e está em 2,93 ms aos 40 s; os valores que atrasam a entrada são
picos isolados aos 100, 140, 150 e 170 s, mais dois intervalos que passam a 0,5% abaixo do
limite da banda.

#### O que isto estabelece, e o que não

Estabelece que **nenhuma** das três definições serve como teste de suficiência do
aquecimento para o Spring Boot neste nível de carga, e por um motivo que não é de
formulação: tolerância relativa de ±10%, ou CV de 2%, sobre regime de 2,6 a 3,0 ms exige
precisão que a medição não tem. Trocar a regra de entrada não resolve o que é um problema
de resolução.

Mantém-se o que as três séries afirmam de modo consistente: **taxa de erro nula nos cinco
frameworks, nas três execuções**, que é a metade de D.3 que não depende de critério de
estabilização. E a leitura direta das séries continua compatível com os 150 s: os cinco
tratamentos estão a menos de 1,5× do regime a partir do segundo intervalo, e o único
transiente de ordem de grandeza — o primeiro intervalo do Spring Boot e do ASP.NET Core —
se extingue em 10 s.

Não estabelece que D.3 está satisfeito, e **a tag `protocolo-v3` segue não emitida**.

Fica também registrado, sem explicação, que o regime do Laravel subiu entre as sessões —
5,86, 6,04 e 6,95 ms —, um aumento de 19% da primeira à terceira. Se o regime de um
tratamento varia entre sessões, a comparação de tempos de entrada entre sessões fica
confundida, e essa é mais uma razão para não decidir o aquecimento por um único número.

#### Uma saída possível, não adotada

Um piso absoluto na tolerância — ±10% **ou** ±0,5 ms, o que for maior — devolveria sentido
ao critério quando o regime se aproxima da resolução da medição. Seria, no entanto, a
segunda definição proposta depois de ver os dados, e a primeira já caiu na série seguinte.
Se for adotada, deve ser em texto, declarada como tal, e verificada em série nova — não
nestas três.

### 16.6 Série de verificação do piso (21/10/2026): passa no número, falha no sentido

O piso absoluto na tolerância — banda igual a max(±10%, ±0,5 ms) — foi adotado na terceira
definição e verificado em série nova, `results/warmup-d3-serie3/`, na mesma condição limpa:
nenhum contêiner de outro projeto, 0,00% de CPU na linha de base.

Sobre as três séries que motivaram o piso, ele leva a terceira definição de 80, 70 e 220 s
para 40, 60 e 70 s. Na série de verificação, que não o motivou, o pior caso é de **40 s**.

| Framework | (1) CV, k=5 | (2) ±10% da média | (3) com piso | Excursões após a entrada |
|---|---:|---:|---:|---:|
| ASP.NET Core | 70 s | 10 s | 10 s | 3 |
| Django | 60 s | 20 s | 20 s | 3 |
| Laravel | 60 s | 10 s | 10 s | 1 |
| NestJS | 90 s | 10 s | **40 s** | 2 |
| Spring Boot | 370 s | 110 s | 20 s | **31** |
| **pior caso** | 370 s | 110 s | **40 s** |  |

**O número passa.** Quarenta segundos, contra os 150 s adotados, por um critério que não foi
ajustado nesta série. Era o desfecho anunciado como favorável antes de executar.

**Mas a entrada do Spring Boot não significa o que diz.** As 31 excursões posteriores — de 59
intervalos — denunciam o problema. A mediana da cauda dele é de 3,283 ms e a do corpo, dos
intervalos 1 a 41, é de 2,782 ms: a cauda está **acima** do corpo, puxada por picos aos 470,
480, 530, 540 e 560 s, de 4,0 a 4,9 ms. A banda que sai dessa cauda é [2,783; 3,783] e fica,
portanto, acima do corpo da série: **25 dos 59 intervalos caem abaixo dela**. A entrada aos
20 s vem de um trecho de cinco intervalos que por acaso cai na banda, entre 20 e 60 s, antes
de a série descer para 2,6 a 2,8 ms e sair. Não descreve estabilização.

**O piso mudou o problema de lugar, não o resolveu.** Em 16.5 a cauda do Django estava
contaminada por rajada e inflava o regime; aqui a cauda do Spring Boot está elevada em
relação ao corpo e a banda sobe junto. A raiz é anterior à tolerância: as três definições
tomam o regime dos últimos 30% da série e supõem que esse trecho representa o estado
estacionário. As quatro séries mostram que ele não representa de forma confiável — por rajada
tardia, por pico isolado ou por elevação da cauda sobre o corpo.

Corrigir isso seria a terceira correção post hoc do mesmo critério. A primeira caiu na série
seguinte à que a motivou; a segunda passa no valor e falha na interpretação. Não se propõe
uma terceira.

#### O que as quatro séries estabelecem sem critério de banda

Vinte execuções de framework, cinco tratamentos em quatro sessões. Lidas sem nenhuma banda:

| Afirmação | Evidência |
|---|---|
| taxa de erro nula | 0,0000% nas **20** execuções |
| o transiente está no 1º intervalo | 1º intervalo entre 1,0× e 303× a mediana do corpo |
| e só nele | do 2º intervalo em diante, 0 a 5 intervalos acima de 1,5× a mediana do corpo |

Por tratamento, o primeiro intervalo sobre a mediana do corpo: Spring Boot de 107× a 303×,
ASP.NET Core de 33× a 40×, Django de 2,8× a 5,2×, Laravel e NestJS de 1,0× a 1,2× — estes
dois últimos chegam quentes. Em nenhuma das 20 execuções há transiente de ordem de grandeza
depois do primeiro intervalo de 10 s.

Os 150 s adotados são, por essa leitura, quinze vezes a duração do único transiente
observado. A folga não depende de qual das três definições se prefira, e é o que há de mais
robusto no conjunto.

#### Recomendação

Declarar a limitação em lugar de consertar o critério pela terceira vez. Em concreto: que a
seção 3.4.3 registre que o critério do coeficiente de variação de Georges, Buytaert e
Eeckhout (2007) é reportado, mas que, com latência de regime entre 2,4 e 7,0 ms e variação
própria da medição da ordem de 0,1 a 0,5 ms, nenhum critério de banda relativa sobre os
últimos 30% da série se mostrou estável entre sessões neste aparato; e que D.3 se sustente no
que as quatro séries afirmam de modo consistente — taxa de erro nula e transiente confinado
ao primeiro intervalo de 10 s, contra 150 s de aquecimento.

Isso é decisão de texto, não de aparato. **A tag `protocolo-v3` segue não emitida.**

Fica registrado que o primeiro intervalo do Spring Boot variou entre sessões — 594, 332, 310
e 854 ms —, numa razão de 2,8 entre o menor e o maior, sem explicação. E que o regime do
Laravel voltou a 5,88 ms nesta série, depois dos 6,95 ms de 16.5, o que enfraquece a leitura
de deriva que aquela seção levantou: são 5,85, 5,88, 7,01 e 5,88 ms nas quatro sessões, e o
valor alto é isolado.

---

## 17. D.3: conclusão

Decidido em 21/10/2026, depois de 16.6: para de se ajustar o critério de aquecimento. Não há
terceira correção. A conclusão de D.3 passa a se apoiar em evidência direta, e os critérios
de banda ficam **reportados**, sem servir de teste de suficiência.

### 17.1 Evidência direta

Vinte execuções de framework, cinco tratamentos em quatro sessões, por
`scripts/analyze-d3.py`. As grandezas não dependem de banda nem de supor que os últimos 30%
da série representem o estado estacionário:

```bash
python scripts/analyze-d3.py
```

O **corpo** é a mediana dos intervalos 1 a 41, de 10 s a 410 s: exclui o primeiro intervalo,
que é o transiente a medir, e os últimos 30%, que 16.3, 16.5 e 16.6 mostraram sujeitos a
rajada tardia, pico isolado e elevação da cauda sobre o corpo.

| Sessão | Framework | Erro | 1º (ms) | 1º / corpo | Acima de 1,5× | 1ª janela / resto |
|---|---|---:|---:|---:|---:|---:|
| 30/09 | ASP.NET Core | 0,0000% | 87,0 | 33,6× | 0 | 1,006 |
| 30/09 | Django | 0,0000% | 10,2 | 2,8× | 0 | 0,995 |
| 30/09 | Laravel | 0,0000% | 6,5 | 1,1× | 0 | 0,974 |
| 30/09 | NestJS | 0,0000% | 3,3 | 1,2× | 0 | 1,005 |
| 30/09 | Spring Boot | 0,0000% | 594,3 | 225,5× | 2 | 0,937 |
| 19/10 | ASP.NET Core | 0,0000% | 109,7 | 39,1× | 1 | 0,981 |
| 19/10 | Django | 0,0000% | 11,4 | 3,2× | 3 | 0,987 |
| 19/10 | Laravel | 0,0000% | 6,1 | 1,1× | 0 | 0,964 |
| 19/10 | NestJS | 0,0000% | 3,4 | 1,2× | 0 | 0,969 |
| 19/10 | Spring Boot | 0,0000% | 331,7 | 124,8× | 2 | 1,038 |
| 21/10 a | ASP.NET Core | 0,0000% | 105,2 | 35,5× | 0 | 0,960 |
| 21/10 a | Django | 0,0000% | 15,3 | 3,5× | 1 | 0,994 |
| 21/10 a | Laravel | 0,0000% | 8,6 | 1,2× | 1 | 1,120 |
| 21/10 a | NestJS | 0,0000% | 3,9 | 1,1× | 0 | 1,007 |
| 21/10 a | Spring Boot | 0,0000% | 310,4 | 108,1× | 4 | 1,063 |
| 21/10 b | ASP.NET Core | 0,0000% | 108,8 | 39,6× | 0 | 0,978 |
| 21/10 b | Django | 0,0000% | 19,5 | 5,2× | 0 | 0,967 |
| 21/10 b | Laravel | 0,0000% | 6,8 | 1,2× | 0 | 0,989 |
| 21/10 b | NestJS | 0,0000% | 3,3 | 1,2× | 0 | 1,005 |
| 21/10 b | Spring Boot | 0,0000% | 854,2 | 307,0× | 5 | 1,051 |

Agregado: **taxa de erro nula nas 20 execuções**; primeiro intervalo de 1,1× a 307× o corpo;
de 0 a 5 intervalos acima de 1,5× o corpo do segundo em diante; primeiro minuto da janela de
medição sobre o resto dela entre **0,937 e 1,120**.

Esta última coluna é a que fala diretamente sobre a suficiência dos 150 s: compara a mediana
de [150, 210) s com a de [210, 450) s, isto é, o primeiro minuto medido contra o resto da
janela. Se o aquecimento não bastasse, o primeiro minuto viria sistematicamente mais alto.
Nas 20 execuções a razão fica a menos de 7% de 1, e em 12 delas abaixo de 1.

### 17.2 Os critérios de banda, reportados

| Definição | 30/09 | 19/10 | 21/10 a | 21/10 b | Natureza |
|---|---:|---:|---:|---:|---|
| (1) CV < 2% em k = 5 | 90 s | 200 s | 550 s | 370 s | da monografia, seção 3.4.3 |
| (2) ±10% da média da cauda | 50 s | 130 s | não entrou | 110 s | da monografia, seção 3.4.3 |
| (3) mediana + persistência | 80 s | 70 s | 220 s | 40 s | **post hoc**, 19/10 |
| (3) + piso de ±0,5 ms | 40 s | 60 s | 70 s | 40 s | **post hoc**, 21/10 |

As definições (1) e (2) são as do texto e ficam reportadas. As definições (3) e (3) com piso
foram propostas **depois** de ver os dados que julgam, **não são pré-registradas**, e os
docstrings do `analyze-warmup.py` o declaram. A primeira delas caiu na série seguinte à que a
motivou, passando de 80 e 70 s para 220 s; a segunda passa no valor e falha na interpretação,
pelo caso do Spring Boot em 16.6.

**Nenhum critério de banda relativa sobre os últimos 30% da série se mostrou estável entre
sessões neste aparato.** A causa está em 16.5 e 16.6: com latência de regime entre 2,4 e
7,0 ms e variação própria da medição entre 0,1 e 0,5 ms, a tolerância relativa desce abaixo
do ruído; e o regime tomado da cauda não representa o estado estacionário de forma confiável.

Não se afirma que os critérios de banda foram satisfeitos.

### 17.3 D.3 é sustentado por

1. **Taxa de erro nula** nas 20 execuções, em quatro sessões, nos cinco tratamentos.
2. **Transiente confinado ao primeiro intervalo de 10 s**, contra os 150 s de aquecimento
   adotados — quinze vezes a duração do único transiente observado. Do segundo intervalo em
   diante não há, em nenhuma das 20 execuções, transiente de ordem de grandeza; o que resta
   são de 0 a 5 intervalos acima de 1,5× o corpo, isolados.

A isso se soma, como verificação independente, a razão entre o primeiro minuto da janela de
medição e o resto dela, entre 0,937 e 1,120.

### 17.4 Dois achados sem explicação

**O primeiro intervalo do Spring Boot varia 2,8× entre sessões:** 594, 332, 310 e 854 ms, nas
quatro. É o transiente de compilação em tempo de execução, e a razão entre o menor e o maior
não tem explicação registrada. Não afeta a conclusão — nas quatro ele está extinto no
segundo intervalo —, mas afeta qualquer tentativa de prever a duração do aquecimento a
partir de uma execução só.

**O regime do Laravel:** 5,85, 5,88, 7,01 e 5,88 ms. A seção 16.5 levantou a leitura de que o
regime dele estaria derivando, com base nos três primeiros valores; a quarta sessão desfaz a
leitura. O valor de 7,01 ms é isolado, e não tendência. Fica registrado porque a hipótese de
deriva chegou a ser escrita.

---

## 18. A campanha: comando, duração e conferência

Escrito em 21/10/2026, com o aparato congelado em `protocolo-v3`. Nada aqui foi executado.

**23/10/2026.** O congelamento passou a `protocolo-v4` (`2b1a729`), que só acrescenta a
interrupção limpa da seção 20; o comando, a duração e a conferência abaixo não mudam. A 18.0
foi acrescentada nesta data, com os pré-requisitos de ambiente que a tentativa de começar a
campanha revelou.

### 18.0 Pré-requisitos de ambiente

A campanha é uma execução de cerca de 19 h numa máquina de uso pessoal. O aparato não
controla o ambiente em que roda, e três condições dele, medidas em 22 e 23/10/2026, a
interromperiam ou a contaminariam. Nenhuma é opcional.

**1. O Docker Desktop de pé, e estável.** Ele caiu duas vezes durante a preparação: uma
deixou o `tcc-postgres` em `Exited (255)` dez horas antes de ser notado, e a outra deixou o
daemon fora do ar em 23/10. Sem o daemon o script morre; a retomada por célula refaz só a
célula em curso, mas a campanha para até alguém religá-la.

**2. A máquina sem outra carga.** Em 22/10, com o aparato pronto, uma suíte de testes de
outro projeto rodava com Testcontainers — `quay.io/keycloak/keycloak:26.0`,
`postgres:16-alpine` e o coletor `testcontainers/ryuk` —, e o PostgreSQL dela marcou **88%
de CPU** numa amostra. Já se mediu o que carga ambiente faz aqui: na reexecução de
aquecimento de 19/10 a latência de regime do Spring Boot subiu 62% (seção 15.3.2). Durante as
19 h, nada além do aparato deve usar o Docker nem disputar CPU.

**3. A máquina sem suspender.** Pelas configurações de energia lidas em 23/10/2026, ela
suspende após **4 h** ociosa na tomada (`0x3840` = 14.400 s) e hiberna após 4 h na tomada ou
**3 h** na bateria (`0x2a30` = 10.800 s). Na suspensão, a máquina virtual do WSL2 cai e leva o
Docker Desktop junto — a causa provável das duas quedas do item 1. Sem providência, **a
campanha morreria por volta da quarta hora**. É preciso o notebook na tomada e a suspensão
desligada durante a execução: ajustando "suspender" para "nunca" na tomada, ou mantendo a
máquina acordada por recurso do próprio ambiente que dispara a campanha. As configurações de
energia são do usuário da máquina e não foram alteradas por ninguém neste trabalho.

#### Conferência imediatamente antes da primeira célula

```bash
docker version --format '{{.Server.Version}}'                  # o daemon responde
docker ps --format '{{.Names}}\t{{.Image}}'                     # apenas tcc-postgres
docker stats --no-stream --format '{{.Name}} {{.CPUPerc}}'     # CPU perto de zero
df -h .                                                        # espaço livre
```

```powershell
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE   # índice de CA: 0x00000000 = nunca
```

E as imagens devem ser as identificadas em `results/versions/imagens.txt` (seção 19):

```bash
for i in springboot django nestjs laravel aspnet; do
  printf '%-12s ' "$i"; docker image inspect "tcc-bench-$i" --format '{{.Id}}'
done
```

Um digest diferente do registrado significa que alguém reconstruiu a imagem desde 22/10, e
pede o mesmo tratamento da seção 19 — registrar a versão e reverificar D.1 e D.2 — antes
de medir.

Sobre o disco: em 22/10 havia 28 GB livres, com 95% do volume ocupado. A saída da campanha é
pequena, da ordem de megabytes, mas convém não começar com menos que isso.

#### Se uma condição falhar no meio

A retomada por célula (18.3) e o `limpar()` (seção 20) limitam o prejuízo à célula em curso.
Religa-se o que caiu, repete-se a conferência acima, e roda-se o mesmo comando de 18.1. Uma
célula medida sob carga ambiente, porém, **não** é refeita sozinha: ela grava JSON íntegro e
a retomada a considera concluída. Se a carga for notada depois, a célula precisa ser apagada
à mão, como em 18.4, e isso só é possível se alguém souber em que intervalo a carga ocorreu.
É mais um motivo para o item 2 ser cumprido do começo ao fim, e não remediado.

### 18.1 O comando

Depois dos passos 1 a 4 da sequência do README — banco de pé, framework no ar, critérios de
aceite, teste de capacidade:

```bash
RATES="81 162 243" DURATION=300s REPS=10 OUT=results/campaign ./scripts/run-experiment.sh
```

As taxas saem do teste de capacidade da seção 14 e foram reconferidas em 21/10/2026 com
`python scripts/analyze-capacity.py --dir results/capacity --p95-max 100`, que devolve
[C_min] = 325 req/s (Laravel) e os níveis 81, 162 e 243 req/s.

**23/10/2026 — as taxas mudaram.** O modo de energia passou a Desempenho Máximo e a
capacidade foi remedida nele (seção 21): [C_min] = 425 req/s, níveis **106, 212 e 318**. O
comando da campanha passa a ser

```bash
RATES="106 212 318" DURATION=300s REPS=10 OUT=results/campaign ./scripts/run-experiment.sh
```

e os 81, 162 e 243 acima ficam como registro do modo anterior. Duração, retomada e conferência
não mudam, porque não dependem da taxa. `DURATION` e `REPS` são os
valores de [D] e de repetições da seção 14.9. O `WARMUP_DURATION` não é passado: fica nos
150 s que o script traz por padrão.

**Uma divergência de semente, a confirmar.** O `ORDER_SEED` do `run-experiment.sh` vale
20260922 por padrão, enquanto o teste de capacidade correu com 20260925. São sorteios
independentes, de dois experimentos distintos, e nada no protocolo exige que coincidam — a
intercalação da seção 3.4.4 pede ordem sorteada por rodada, não a MESMA ordem do teste de
capacidade. Fica registrado para que a escolha seja deliberada e não acidental.

### 18.2 Duração

150 células: 5 frameworks × 3 níveis × 10 repetições.

| Componente | Por célula | Total |
|---|---:|---:|
| aquecimento | 150 s | 6 h 15 min |
| medição | 300 s | 12 h 30 min |
| reinício do banco e prontidão | ~5 s | ~12 min |
| `reset_db`, recriação do contêiner, `/api/health` | ~5 s | ~13 min |
| **total** | **~460 s** | **~19 h 10 min** |

A sobrecarga por célula foi medida, e não estimada: nas execuções de aquecimento de 19 e
21/10, o intervalo entre os JSONs de dois tratamentos consecutivos ficou em 607 a 610 s
contra 600 s de carga, isto é, cerca de 10 s de preparo por célula com as imagens já
construídas.

Convém rodar com as imagens já construídas. A primeira construção de cada uma não entra nessa
conta.

### 18.3 Retomada

A retomada é **por célula**, e o teste é a existência do JSON de resultado. Uma campanha
interrompida continua com o MESMO comando, sem argumento extra:

```bash
RATES="81 162 243" DURATION=300s REPS=10 OUT=results/campaign ./scripts/run-experiment.sh
```

As células já medidas são anunciadas como "já medido, pulando" e a ordem sorteada não muda,
porque o `ordem.csv` é preservado e só recebe as rodadas que ainda não constam dele. Uma
célula cujo banco caiu durante a medição teve o JSON removido pelo próprio script (seção
16.4), e por isso é refeita em lugar de pulada.

O que a retomada **não** refaz: uma célula com JSON íntegro mas registrada em
`invalidas.csv`. Essa decisão é do protocolo e não do script — ver 18.4.

### 18.4 Acompanhar o `invalidas.csv`

Toda execução com erro ou com iterações descartadas entra em `results/campaign/invalidas.csv`,
e o protocolo manda investigar cada uma e repeti-la se a causa for do ambiente. O script não
descarta nem repete nada sozinho.

```bash
cat results/campaign/invalidas.csv
```

O arquivo nasce com apenas o cabeçalho `execucao,taxa_erro,iteracoes_descartadas`. Qualquer
linha além dele pede investigação. Os rótulos de falha de ambiente —
`banco_indisponivel`, `banco_nao_reiniciou`, `banco_caiu_durante`, `falha_de_prontidao` e
`sem_resultado` — são gravados na coluna `taxa_erro`, que o cabeçalho sugere numérica; é a
convenção do script, e quem ler o arquivo com programa precisa saber (16.4).

Para repetir uma célula depois de investigar, apague o JSON dela e rode o mesmo comando:

```bash
rm results/campaign/<framework>/<framework>_<taxa>rps_rep<NN>.json
```

### 18.5 Conferir ao final que são 150 células

```bash
ls results/campaign/*/*_*rps_rep*.json | wc -l      # deve dar 150
python scripts/analyze-experiment.py results/campaign
```

A contagem de 150 é a conferência mais simples, e a que pega o caso em que uma célula ficou
para trás sem ninguém notar. O `analyze-experiment.py` destaca as execuções com erro ou
descarte sob o título de execuções a investigar antes de usar, e reporta, por framework e
nível, o coeficiente de variação entre as 10 repetições e a meia-largura do intervalo de
confiança de 95% — que são [CV] e [H] da seção 14.9, resultado a reportar e não lacuna a
preencher.

Esperado por framework: 30 JSONs, 10 em cada um dos três níveis. Por nível: 50 JSONs.

---

## 19. As imagens não estão congeladas (22/10/2026)

As cinco imagens foram reconstruídas em 22/10/2026, antes da campanha e com zero células
medidas. A reconstrução expôs uma lacuna do congelamento que convém registrar antes de o
texto afirmar reprodutibilidade.

### 19.1 A lacuna

A tag `protocolo-v3` congela `scripts/`, `k6/` e `infra/`. **Não congela as imagens**, e os
cinco Dockerfiles usam tag móvel de imagem-base:

| Framework | Imagem-base |
|---|---|
| Spring Boot | `maven:3.9-eclipse-temurin-25` (build) + `eclipse-temurin:25-jre` |
| Django | `python:3.13-slim` |
| NestJS | `node:24-alpine` (build e runtime) |
| Laravel | `php:8.5-fpm` |
| ASP.NET Core | `mcr.microsoft.com/dotnet/sdk:10.0` (build) + `dotnet/aspnet:10.0` |

Os arquivos de bloqueio — `package-lock.json`, `composer.lock`, o `pom.xml` com versões
fixas — são versionados e fixam as dependências da aplicação. O runtime e os pacotes de
sistema, não. Em consequência, **um clone construído em outra data recebe outros patches de
runtime**, e a afirmação de que o aparato é reproduzível a partir de qualquer clone, que o
comentário do `.gitattributes` toma como objetivo, vale para os scripts e não vale para o que
eles medem.

### 19.2 O que a reconstrução mudou

| Framework | Mudança |
|---|---|
| **ASP.NET Core** | runtime **10.0.12 → 10.0.13**, commit `95017c711e` → `4099f83977`. Nenhum pacote NuGet mudou. |
| Spring Boot | imagem de 596 para 575 MB **sem** mudança de versão: `openjdk 25.0.4` e `Maven 3.9.16` idênticos. |
| Laravel | reconstruída, sem mudança de versão. |
| Django | build integralmente cacheado; imagem intacta. |
| NestJS | build integralmente cacheado; imagem intacta. |

O caso do Spring Boot merece nota porque a diferença de 21 MB chegou a ser lida, aqui, como
candidata a mudança de versão. Não é: o `results/versions/springboot.txt` não mudou uma linha.
A diferença é de empacotamento de camadas. **Tamanho de imagem não é indicador de drift**, e
foi por falta de um identificador melhor que se recorreu a ele.

### 19.3 Identificação das imagens, e reverificação

Para que drift futuro seja detectável por comparação em lugar de inferência, os digests das
imagens medidas passam a ser registrados em `results/versions/imagens.txt`, com o comando que
os regenera.

A mudança de runtime do ASP.NET Core invalidou, para aquele tratamento, o argumento da seção
15.1 — de que D.1 e D.2 não precisavam ser reexecutados porque nada que eles verificam havia
mudado. Os dois foram então reverificados em 22/10/2026:

| Critério | Resultado |
|---|---|
| D.1, contrato | `contrato aspnet: 76 ok, 0 falhas` |
| D.1, registros idênticos | os cinco fingerprints idênticos, 319 bytes cada |
| D.2, consultas por requisição | 1 / 1 / 1 / 2 / 2, o contrato do Quadro C4 |
| D.2, plano da busca | `Index Scan using idx_books_title`, `Index Cond` de limites de prefixo, **sem** nó `Sort` |

O resultado mais forte não é o 76/76: é que os cinco `results/fingerprint-*.json`, reescritos
pelo `compare-fingerprints.sh`, saíram **byte a byte iguais** aos commitados em 10/09/2026. O
patch não alterou nenhum registro devolvido — nem quantidade, nem identificador, nem ordem,
inclusive no `searchAlfa`, cuja ordenação por `title` é o que evidencia tradução equivalente
do filtro de prefixo pelos cinco ORMs. Como o script roda os cinco, os outros quatro ficaram
revalidados de passagem.

O `log_statement` foi restaurado a `none` ao final, pelo próprio `verify-queries.sh`.

### 19.4 O que se faz, e o que fica declarado

Feito: o registro de versões passa a descrever o 10.0.13, que é o que a campanha vai medir;
os digests ficam gravados; e o README registra que o `--build` do passo 2 pertence à fase de
montagem, porque o laço da campanha sobe os contêineres **sem** reconstruir — o `app_up` usa
`up -d --force-recreate --no-deps`. Durante a campanha, portanto, as imagens não mudam.

Não feito, e declarado como limitação: as imagens-base **não** foram fixadas por digest. Fixá-las
exigiria alterar os Dockerfiles, em `apps/`, e nova tag. Com os digests registrados e o
`--build` fora do caminho da campanha, o risco deixa de ser drift silencioso e passa a ser
drift detectável, o que basta para medir: as 150 células usarão todas o mesmo artefato, e isso
é verificável. O que não se obtém é reprodutibilidade da construção a partir de um clone em
outra data, e essa é a limitação a declarar no texto, ao lado das demais da seção 3.6.

---

## 20. Interromper a campanha (22/10/2026)

Achado ao conferir a prontidão para a campanha, e corrigido antes da primeira célula.

### 20.1 O defeito, medido

O `run-experiment.sh` tinha apenas `trap 'stats_stop' EXIT`. Não derrubava o contêiner da
aplicação nem o do k6. É o mesmo defeito que `1540a52` corrigiu no `run-capacity.sh`, e que
ali deixou a máquina com 476% de CPU ocupada depois de o experimento ter sido mandado parar.

Exercitado em 22/10/2026 numa célula de `springboot` a 81 req/s, interrompida 15 s dentro de
uma medição de 60 s:

| Momento | k6 | aplicação |
|---|---|---|
| 15 s dentro da medição | `grafana/k6:2.2.0`, de pé | `tcc-springboot`, de pé |
| **5 s após o `kill -TERM`** | **de pé, 5,8% de CPU** | **de pé, 7,0% de CPU** |

O PostgreSQL marcava 7 a 8% ao mesmo tempo: a medição seguia inteira depois de o script ter
morrido. Importa porque a retomada por célula convida a rodar as 19 h em trechos, e a célula
seguinte começaria sob a carga da anterior.

### 20.2 A correção

Um `limpar()` espelhando o do `run-capacity.sh`, com `trap limpar EXIT INT TERM`. Uma
diferença que o espelhamento cego estragaria: o `run-experiment.sh` já tinha um trap em
`EXIT`, e **dois traps no mesmo sinal não coexistem** — o segundo substitui o primeiro. Colar
o `limpar()` sem notar isso trocaria o k6 órfão por um coletor de `docker stats` órfão. O
`stats_stop` passa a ser chamado de dentro da rotina.

### 20.3 Um efeito a conhecer antes de interromper

Com trap definido, o bash **adia** a execução dele até o comando em primeiro plano terminar.
Medido: um `kill -TERM` durante a medição não a interrompe — a célula completa, grava JSON
íntegro, e só então o `limpar()` roda. Na campanha isso significa até cerca de 460 s entre o
sinal e a parada efetiva.

É preferível assim: não resta célula meio medida, e a retomada não precisa decidir o que
fazer com ela. Mas quem interromper precisa saber que a resposta não é imediata.

O Ctrl+C num terminal percorre outro caminho: o sinal vai ao grupo de processos, o cliente
`docker run` morre de imediato, o contêiner do k6 **sobrevive ao cliente** — porque quem o
executa é o daemon — e é então que o `limpar()` o remove.

### 20.4 O que se verificou, e o que não

Verificado:

| | |
|---|---|
| o defeito existia | medido, com CPU dos dois contêineres após o sinal |
| a linha de limpeza do k6 funciona | sobe-se um contêiner k6 e a linha exata do `limpar()` o remove |
| o trap dispara em `INT` e em `TERM` | exercitado nos dois sinais |
| registrado nos três sinais | `trap limpar EXIT INT TERM`, igual ao `run-capacity.sh` |
| contêineres caem junto com o script | após o sinal, resta apenas o `tcc-postgres` |

Não verificado: a sequência completa do Ctrl+C **num terminal real**, em que o cliente `docker`
morre primeiro e o trap remove o contêiner sobrevivente. Três tentativas de simulá-la
falharam neste ambiente — o Git Bash não tem `setsid`, e a emulação de grupos de processos do
MSYS não entrega o sinal como um terminal entregaria. A correção foi então verificada por
decomposição, nas partes acima; a composição delas é o caminho do Ctrl+C, mas isso é
inferência e não medição.

---

## 21. Remedição no modo de energia Desempenho Máximo (23/10/2026)

### 21.1 Por que remedir

Ao cumprir os pré-requisitos da seção 18.0, o modo de energia do host foi trocado para
Desempenho Máximo, junto com a suspensão. O modo controla turbo e limites de potência da CPU
e, por isso, a latência e a capacidade. Rodar a campanha nele sem remedir deixaria o modelo
multicritério somar numa nota única a capacidade medida num regime de CPU e a latência e a
CPU medidas noutro, e faria a frase da seção 3.4.3 — níveis a 25%, 50% e 75% da menor
capacidade — descrever o que não foi medido. Decidiu-se manter o modo e remedir nele a
capacidade e D.3.

O estado de energia passou a ser lido do registro do Windows e gravado junto com os dados, em
`energia.txt` dentro de cada diretório de resultado: plano `Legion Balance Mode`, overlay de
corrente alternada `ded574b5-45a0-4f42-8737-46345c09c238` (Desempenho Máximo), suspensão e
hibernação em nunca, máquina na tomada. **O modo vigente nas fases anteriores não foi
registrado pelo aparato**, e não se sabe qual era.

Os scripts são os de `protocolo-v4`; só os parâmetros de linha de comando mudam.

### 21.2 Capacidade

`results/capacity-desempenho/`, com o comando da seção 14 e o `ORDER_SEED` padrão do
`run-capacity.sh`, 20260925 — a mesma ordem sorteada de 06/10. As 25 células concluíram.

| Framework | 06/10 | 23/10 | Variação | CV 06/10 | CV 23/10 |
|---|---:|---:|---:|---:|---:|
| Laravel | 325 | **425** | +31% | 8,6% | 5,5% |
| Django | 775 | 950 | +23% | 7,8% | 1,9% |
| NestJS | 1.525 | 1.700 | +11% | 9,5% | 2,9% |
| Spring Boot | 1.400 | 1.800 | +29% | 5,4% | 4,5% |
| ASP.NET Core | 1.700 | 2.600 | +53% | 18,7% | 3,2% |

[C_min] = **425 req/s** (Laravel, moda 3/5). Níveis do teste de carga fixa, arredondados para
baixo a partir de 106,25, 212,50 e 318,75: **106, 212 e 318 req/s**.

O 425 do Laravel coincide com o maior valor observado dele — 375, 400, 425, 425, 425 —,
que é a situação estrutural que a seção 12.2 apontou. Agora, porém, com maioria, de modo que a
regra de resumo se aplica. A folga do nível de 75% até a pior repetição do Laravel é de
318 → 375, 57 req/s, maior que os 31 req/s que a 12.2 considerou aceitáveis.

Deriva de sessão, pelo `analyze-capacity-deriva.py`: inclinação de **+0,099% por célula**,
r = **+0,197**. Sem deriva, como em 14.6.1. O `run-capacity.sh` não reinicia o banco por
célula, e a ausência de deriva nas duas medições é o que sustenta isso.

### 21.3 A ordem de capacidade mudou

| 06/10 | 23/10 |
|---|---|
| ASP.NET Core > **NestJS > Spring Boot** > Django > Laravel | ASP.NET Core > **Spring Boot > NestJS** > Django > Laravel |

Spring Boot e NestJS trocam de posição. Como a capacidade é critério do modelo, isto
estabelece que **a configuração de energia do host altera a ordem dos tratamentos**, e não só
os valores. É ameaça à validade externa a declarar na seção 3.6.2: o resultado depende de como
a máquina gerencia a CPU, e não apenas dos frameworks.

### 21.4 A dispersão caiu

Os CVs de Django, NestJS e ASP.NET Core caem para 1,9%, 2,9% e 3,2%. Isso enfraquece a
leitura da seção 14.6, que tratou os 18,7% do ASP.NET Core como dispersão real do tratamento.

A atribuição tem duas ressalvas. Para o ASP.NET Core, **dois fatores mudaram ao mesmo tempo**:
o modo de energia e o runtime, de 10.0.12 para 10.0.13 (seção 19), e os +53% e a queda do CV
dele não podem ser atribuídos a um só. Os outros quatro isolam melhor o fator — as imagens de
Django e NestJS são byte a byte as de 06/10, e Laravel e Spring Boot têm as mesmas versões —,
mas mesmo neles a comparação é entre Desempenho Máximo e um modo anterior desconhecido, em
datas diferentes.

### 21.5 D.3 no modo novo

`results/warmup-desempenho/`, a 212 req/s, 50% do novo [C_min], por 600 s. Evidência direta,
com as definições do `analyze-d3.py`:

| Framework | Erro | 1º (ms) | 1º / corpo | Acima de 1,5× | 1ª janela / resto |
|---|---:|---:|---:|---:|---:|
| ASP.NET Core | 0,0000% | 74,6 | 37,5× | 3 | 0,994 |
| Django | 0,0000% | 4,9 | 1,6× | 2 | 1,000 |
| Laravel | 0,0000% | 5,4 | 1,1× | 0 | 0,993 |
| NestJS | 0,0000% | 3,2 | 1,5× | 0 | 0,994 |
| Spring Boot | 0,0000% | 112,6 | 61,1× | 4 | 0,998 |

Taxa de erro nula nos cinco; transiente confinado ao primeiro intervalo; e o primeiro minuto
da janela de medição a menos de 0,7% do resto dela, contra a faixa de 0,937 a 1,120 das quatro
sessões do modo anterior. O transiente de partida do Spring Boot encolheu de 310–854 ms para
112,6 ms.

Os critérios de banda, reportados como manda a seção 17: (1) CV pior caso **100 s**, (2) ±10%
da média **40 s**, (3) mediana com piso **30 s**. É a primeira série desde 30/09 em que os três
ficam abaixo dos 150 s. Isso é coerente com a hipótese de que o ruído que os derrubava vinha em
boa parte do host, mas não muda o estatuto deles: seguem reportados, não usados como teste.

**D.3, no modo novo, é sustentado por** taxa de erro nula e transiente confinado ao primeiro
intervalo de 10 s, contra os 150 s adotados — o mesmo fundamento da seção 17.3.

**A ressalva de n.** No modo novo há **uma** série por framework. O padrão se repete nas quatro
sessões do modo anterior, o que sugere que ele é robusto entre sessões, mas aquelas foram
medidas noutro regime de CPU. Uma segunda série no modo novo tornaria a afirmação independente
de n = 1, ao custo de cerca de 51 min.

Os números desta seção para D.3 foram calculados com as funções do `analyze-d3.py`, que tem as
quatro sessões anteriores fixas no código. Para que ele as reproduza diretamente, precisaria
aceitar diretórios como argumento, o que é mudança em `scripts/`.

### 21.6 Segunda série de D.3 no modo novo (24/10/2026)

`results/warmup-desempenho-2/`, mesmas condições, com o estado de energia em `energia.txt`.
Antes dela a máquina tinha sido suspensa pelo usuário, das 02:24 às 11:30 de 24/10. Na
retomada, o Docker Desktop reiniciou e derrubou o `tcc-postgres` com código 255. Nada estava
em execução, e a série só começou depois de o banco ser religado e o ambiente conferido.

| Framework | Erro | 1º (ms) | 1º / corpo | Acima de 1,5× | 1ª janela / resto |
|---|---:|---:|---:|---:|---:|
| ASP.NET Core | 0,0000% | 79,9 | 40,4× | 2 | 0,970 |
| Django | 0,0000% | 25,0 | 8,2× | 0 | 0,993 |
| Laravel | 0,0000% | 8,2 | 1,6× | 2 | 0,992 |
| NestJS | 0,0000% | 3,3 | 1,6× | 1 | 0,989 |
| Spring Boot | 0,0000% | 149,3 | 62,9× | 0 | 0,972 |

Somadas as duas séries do modo novo: **taxa de erro nula nas 10 execuções**; nenhum intervalo
acima de 1,5× o corpo além de 0 a 4 por execução; e o primeiro minuto da medição entre
**0,970 e 1,000** do resto dela. A ressalva de n = 1 da seção 21.5 deixa de valer.

**Uma qualificação sobre o Spring Boot.** Na série 2 o transiente dele não fica só no
primeiro intervalo. Depois dos 62,9× iniciais vem uma cauda que cai de 1,30× aos 10 s para
1,03× aos 50 s, e um pico de até 1,19× entre 90 e 110 s. Aos 150 s, início da medição, ele
está em 0,92×. Nada disso passa de 1,5×, de modo que os critérios da evidência direta se
mantêm, e tudo cai dentro dos 150 s de aquecimento. Mas a formulação da seção 17.3 — de que
os 150 s são "quinze vezes a duração do único transiente observado" — depende do limiar: vale
para o transiente de ordem de grandeza, que dura um intervalo; com uma leitura mais estrita,
que conte como aquecimento qualquer coisa acima de 1,1×, o Spring Boot fica elevado até cerca
de 110 s nesta série, e a folga cai para uns 40 s. Os 150 s seguem bastando; a margem é que é
menor do que "quinze vezes".

Os critérios de banda, reportados, nas duas séries do modo novo:

| Definição | Série 1 | Série 2 |
|---|---:|---:|
| (1) CV < 2% em k = 5 | 100 s | **460 s** |
| (2) ±10% da média | 40 s | 60 s |
| (3) mediana + piso | 30 s | 40 s |

O critério do coeficiente de variação volta a variar entre sessões, de 100 para 460 s, também
no modo novo. A conclusão da seção 17.2 — de que nenhum critério de banda relativa se mostrou
estável entre sessões — se confirma no novo regime.

**D.3, no modo novo, é sustentado por** taxa de erro nula nas 10 execuções e por um aquecimento
que termina dentro dos 150 s em todas elas: o transiente de ordem de grandeza dura um
intervalo, e o resíduo abaixo de 1,5× que o Spring Boot mostra na série 2 se extingue até os
120 s.
