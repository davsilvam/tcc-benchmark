# C3 — pull requests fechados

Indicador C3 da dimensão de relevância de comunidade, conforme a seção 3.3 da monografia, que
mede o volume **fechado** numa janela de doze meses e não o número em aberto no instante da
coleta.

| | |
|---|---|
| coleta | `ColetaC3.java` (Java 17+, Search API do GitHub, `GITHUB_TOKEN` somente leitura) |
| dados | `c3-prs.csv`, um pull request por linha, 10.748 registros |
| janela | 2025-09-10T12:01:00Z a 2026-09-10T12:01:00Z, fixa |
| sha256 do CSV | `6af74e2d6c485b3092019560d6b99180370dee8aa20f01fbb0e80811002bfb87` |

A janela coincide com o instante da coleta de estrelas e forks, o que mantém os três
indicadores de comunidade referidos ao mesmo momento.

## Repositórios consultados

| Framework | Repositório |
|---|---|
| Spring Boot | `spring-projects/spring-boot` |
| Django | `django/django` |
| NestJS | `nestjs/nest` |
| Laravel | `laravel/framework` |
| ASP.NET Core | `dotnet/aspnetcore` |

## Filtros do cenário base

1. autor que não seja conta automatizada, por `user.type = Bot`;
2. intervalo de pelo menos uma hora entre abertura e fechamento (Alves Júnior et al., 2022);
3. ao menos uma revisão registrada, pelo qualificador `-review:none` da Search API.

## Colunas do CSV

| Coluna | Conteúdo |
|---|---|
| `framework` | nome do framework |
| `numero` | número do pull request no repositório |
| `criado` | instante de abertura, ISO 8601 UTC |
| `fechado` | instante de fechamento, ISO 8601 UTC |
| `integrado` | `true` se incorporado, `false` se recusado |
| `bot` | `true` se o autor é do tipo Bot |
| `com_revisao` | `true` se há ao menos uma revisão |

O CSV traz **todos** os fechados na janela, sem filtro aplicado, de modo que qualquer das
variantes abaixo é recomputável a partir dele. O filtro de intervalo mínimo deriva de `criado`
e `fechado`.

## Valores

| Framework | Bruto | Bots | Sem bot | + ≥1h | **C3 base** | C3 integrados |
|---|---:|---:|---:|---:|---:|---:|
| Laravel | 3637 | 26 | 3611 | 2944 | **50** | 31 |
| ASP.NET Core | 2707 | 1274 | 1433 | 1267 | **915** | 893 |
| Django | 1934 | 0 | 1934 | 1374 | **620** | 607 |
| NestJS | 1795 | 1416 | 379 | 325 | **0** | 0 |
| Spring Boot | 675 | 70 | 605 | 485 | **35** | 15 |

`C3 base` é o valor do cenário base: sem bot, intervalo de pelo menos uma hora e ao menos uma
revisão. `C3 integrados` restringe-o aos incorporados: é contagem de registro, e não
variante da análise de sensibilidade.

## O filtro de revisão decide o ordenamento da dimensão

| Posição | por C3 base | sem exigir revisão |
|---|---|---|
| 1º | ASP.NET Core (915) | **Laravel (2.944)** |
| 2º | Django (620) | Django (1.374) |
| 3º | Laravel (50) | **ASP.NET Core (1.267)** |
| 4º | Spring Boot (35) | Spring Boot (485) |
| 5º | NestJS (0) | NestJS (325) |

O Laravel vai do terceiro ao primeiro lugar e o ASP.NET Core do primeiro ao terceiro. Como C3
responde por um terço da dimensão de comunidade, a exigência de revisão não é detalhe de
coleta: é escolha metodológica com efeito sobre o resultado, e convém que entre na análise de
sensibilidade da seção 3.5.4 ao lado dos demais eixos.

**O NestJS fica em zero no cenário base.** Nenhuma das 1.795 linhas dele traz `com_revisao`
como `true`, inclusive entre as 379 que não são de bot. Sob normalização *max-min*, um zero
absoluto leva o tratamento ao piso do critério, e não a um valor pequeno.

## Verificação da taxa de revisão

As taxas variam muito entre os repositórios: ASP.NET Core 76%, Django 34%, Spring Boot 5,2%,
Laravel 1,4% e NestJS 0%. O zero exato do NestJS foi conferido em 14/10/2026, por três vias:

1. o pull request 17635, não automatizado e integrado, não registra revisão;
2. o pull request 17620 exibe **"No reviews"** na seção de revisores;
3. a própria consulta do script, executada na busca do GitHub, devolve zero resultados:

```
repo:nestjs/nest is:pr is:closed -review:none closed:2025-09-10..2026-09-10
→ 0 results
```

Como controle positivo, o pull request 61510 do Laravel, que a coleta marca com
`com_revisao=true`, registra duas revisões na interface. A coluna é, portanto, significativa, e
o qualificador `-review:none` funciona no repositório do NestJS.

**O zero não é defeito de coleta.** O que a coleta registra é a ausência de revisão em todos
os 1.795 pull requests fechados do NestJS na janela, inclusive nos 325 que não são de bot e
têm intervalo de pelo menos uma hora entre abertura e fechamento. Por que o projeto não
registra revisões no GitHub é pergunta que estes dados não respondem, e esta documentação não
lhe atribui causa.

## O que o indicador mede, em consequência

Com os filtros do cenário base, o indicador conta a contribuição que tem **revisão registrada
no GitHub**, e não toda a contribuição fechada. No NestJS os dois números se separam por
completo: 325 pull requests humanos com intervalo mínimo de uma hora na janela, e zero deles
contados no cenário base. Sob normalização *max-min*, isso leva o tratamento ao piso do
critério, e não a um valor pequeno.

Duas saídas, ambas defensáveis e ambas já calculadas acima: declarar na seção 3.3 que o
indicador capta contribuição *revisada*, caso em que o zero é achado a discutir no capítulo de
resultados; ou tratar a exigência de revisão como eixo da análise de sensibilidade da seção
3.5.4, ao lado dos demais.

**19/10/2026 — a segunda saída foi adotada.** O terceiro eixo da análise de sensibilidade da
seção 3.5.4 passou a recalcular o modelo suprimindo a exigência de revisão no filtro de pull
requests, ao lado da variante que troca os fechados pelos em aberto. A escolha deixa de estar
pendente; o parágrafo acima fica como registro das duas alternativas que se consideraram.
