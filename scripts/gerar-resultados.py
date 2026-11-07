"""Tabelas e figuras do Capítulo 4, reproduzíveis a partir dos dados versionados.

    python scripts/gerar-resultados.py
    python scripts/gerar-resultados.py --saida /outro/diretorio
    python scripts/gerar-resultados.py --comunidade caminho/estrelas-forks.csv

SOMENTE LEITURA sobre results/campaign, results/capacity-desempenho, results/comunidade e
results/sloc. Escreve apenas em --saida (padrão results/analise/): tabelas em CSV e figuras
em PNG. As figuras exigem matplotlib; sem ele, as tabelas são geradas e as figuras, puladas.

As definições não são reimplementadas aqui quando já existem num analisador versionado:
  - a leitura das execuções e do docker stats vem de scripts/analyze-experiment.py;
  - a capacidade por repetição (último patamar antes da violação confirmada, com descarte e
    erro terminais) e o resumo por moda de maioria ou mediana vêm de
    scripts/analyze-capacity.py;
  - o IC 95% pela t de Student vem de scripts/stats_util.py.

DADOS DE COMUNIDADE. Estrelas, forks e o número de pull requests em aberto NÃO estão no
repositório: results/comunidade traz apenas os pull requests fechados que compõem C3. O
script os lê de um CSV informado em --comunidade (padrão results/comunidade/estrelas-forks.csv),
com o cabeçalho

    framework,estrelas,forks,prs_abertos

e framework em springboot, django, nestjs, laravel, aspnet. prs_abertos é opcional; sem ele,
a variante "C3 por PRs abertos" é omitida. Sem o arquivo, o script gera tudo o que não depende
da dimensão de comunidade e avisa o que deixou de gerar.

NORMALIZAÇÕES (Vafaei, Ribeiro e Camarinha-Matos, 2022, Tabela 1), com r o valor bruto:

    técnica    benefício (maior é melhor)    custo (menor é melhor)
    max-min    (r - min) / (max - min)       (max - r) / (max - min)
    máximo     r / max                       1 - r / max
    soma       r / Σr                        (1/r) / Σ(1/r)
    vetorial   r / √Σr²                      1 - r / √Σr²

MODELO SAW. Três dimensões de peso igual (1/3):
  desempenho   = média de [p95 (custo), capacidade (benefício), recursos], com
                 recursos = ½ CPU média (custo) + ½ memória média (custo), a 212 req/s;
  produtividade = SLOC-A (custo);
  comunidade   = média de [estrelas, forks, C3], todos benefício.

SENSIBILIDADE. Cada configuração muda UM eixo em relação ao cenário base e é comparada a ele
pelo τ de Kendall na versão tau-a: (concordantes − discordantes) / [n(n−1)/2], com pares
empatados contando zero.
"""
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import argparse
import csv
import datetime
import glob
import importlib.util
import io
import math
import os
import re

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
from stats_util import resumo  # noqa: E402


def _importar(nome_arquivo, nome_modulo):
    spec = importlib.util.spec_from_file_location(nome_modulo, os.path.join(AQUI, nome_arquivo))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


experimento = _importar('analyze-experiment.py', 'analyze_experiment')
capacidade_mod = _importar('analyze-capacity.py', 'analyze_capacity')

# Ordem fixa: a cor e a posição nas tabelas seguem o framework, nunca o resultado.
FRAMEWORKS = ['springboot', 'django', 'nestjs', 'laravel', 'aspnet']
ROTULO = {'springboot': 'Spring Boot', 'django': 'Django', 'nestjs': 'NestJS',
          'laravel': 'Laravel', 'aspnet': 'ASP.NET Core'}
COR = {'springboot': '#2a78d6', 'django': '#eb6834', 'nestjs': '#1baf7a',
       'laravel': '#eda100', 'aspnet': '#e87ba4'}
COR_DIM = {'desempenho': '#2a78d6', 'produtividade': '#eb6834', 'comunidade': '#1baf7a'}

TAXA_BASE = 212
TETO_BASE = 100.0                      # p95_max de results/capacity-desempenho/parametros.txt
TETOS = [25, 50, 75, 100, 150, 200, 300, 500]
DIMENSOES = ['desempenho', 'produtividade', 'comunidade']
PESOS_BASE = {d: 1 / 3 for d in DIMENSOES}


# --------------------------------------------------------------------------- leitura

def ler_campanha(diretorio):
    ex = experimento.carregar(diretorio)
    if len(ex) != 150:
        print('AVISO: %d execuções em %s (esperadas 150)' % (len(ex), diretorio))
    return ex


def ler_capacidade(diretorio):
    """{fw: [(rep, patamares)]}, excluídas as execuções sem medição, como no analisador."""
    por_fw = {}
    for caminho in sorted(glob.glob(os.path.join(diretorio, '*_rep[0-9][0-9].csv'))):
        m = re.match(r'(.+)_rep(\d+)\.csv$', os.path.basename(caminho))
        fw, rep = m.group(1), int(m.group(2))
        pats, motivo, _ = capacidade_mod.ler(caminho)
        if not pats or motivo == 'k6_sem_resultado':
            print('AVISO: %s rep%02d sem medição, excluída' % (fw, rep))
            continue
        por_fw.setdefault(fw, []).append((rep, pats))
    return por_fw


def capacidades(por_fw, teto):
    """{fw: (lista por repetição, resumo)} com o teto de p95 dado."""
    saida = {}
    for fw, reps in por_fw.items():
        valores = [capacidade_mod.capacidade(pats, teto)[1] for _, pats in sorted(reps)]
        saida[fw] = (valores, capacidade_mod.resumir_patamares(valores))
    return saida


def ler_sloc(diretorio, corpus):
    saida = {}
    for fw in FRAMEWORKS:
        caminho = os.path.join(diretorio, 'sloc-%s-%s.txt' % (corpus, fw))
        for linha in io.open(caminho, encoding='utf-8'):
            if linha.startswith('SUM:'):
                saida[fw] = int(linha.split()[-1])
    return saida


NOME_C3 = {'Spring Boot': 'springboot', 'Django': 'django', 'NestJS': 'nestjs',
           'Laravel': 'laravel', 'ASP.NET Core': 'aspnet'}


def ler_c3(caminho):
    """C3 base (sem bot, >= 1 h, com revisão) e sem exigir revisão, do CSV de PRs fechados."""
    base = {fw: 0 for fw in FRAMEWORKS}
    sem_revisao = {fw: 0 for fw in FRAMEWORKS}
    uma_hora = datetime.timedelta(hours=1)
    with io.open(caminho, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['bot'] == 'true':
                continue
            criado = datetime.datetime.strptime(r['criado'], '%Y-%m-%dT%H:%M:%SZ')
            fechado = datetime.datetime.strptime(r['fechado'], '%Y-%m-%dT%H:%M:%SZ')
            if fechado - criado < uma_hora:
                continue
            fw = NOME_C3[r['framework']]
            sem_revisao[fw] += 1
            if r['com_revisao'] == 'true':
                base[fw] += 1
    return base, sem_revisao


def ler_comunidade_extra(caminho):
    if not os.path.exists(caminho):
        return None
    saida = {}
    with io.open(caminho, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            fw = r['framework'].strip()
            saida[fw] = {
                'estrelas': float(r['estrelas']),
                'forks': float(r['forks']),
                'prs_abertos': float(r['prs_abertos']) if r.get('prs_abertos') else None,
            }
    faltam = [fw for fw in FRAMEWORKS if fw not in saida]
    if faltam:
        sys.exit('erro: %s não traz %s' % (caminho, ', '.join(faltam)))
    return saida


# --------------------------------------------------------------------------- modelo

def normalizar(valores, beneficio, tecnica):
    fws = list(valores)
    v = [valores[fw] for fw in fws]
    if tecnica == 'max-min':
        lo, hi = min(v), max(v)
        if hi == lo:
            n = [1.0] * len(v)
        elif beneficio:
            n = [(x - lo) / (hi - lo) for x in v]
        else:
            n = [(hi - x) / (hi - lo) for x in v]
    elif tecnica == 'maximo':
        hi = max(v)
        n = [x / hi for x in v] if beneficio else [1 - x / hi for x in v]
    elif tecnica == 'soma':
        if beneficio:
            s = sum(v)
            n = [x / s for x in v]
        else:
            # (1/r) / Σ(1/r) não admite r = 0; um critério de custo nulo não ocorre nestes dados.
            s = sum(1 / x for x in v)
            n = [(1 / x) / s for x in v]
    elif tecnica == 'vetorial':
        s = math.sqrt(sum(x * x for x in v))
        n = [x / s for x in v] if beneficio else [1 - x / s for x in v]
    else:
        raise ValueError(tecnica)
    return dict(zip(fws, n))


def saw(criterios, pesos=PESOS_BASE, tecnica='max-min'):
    """criterios: dicionários {fw: valor bruto}. Devolve normalizados, dimensões e nota."""
    N = {nome: normalizar(criterios[nome], benef, tecnica)
         for nome, benef in (('p95', False), ('capacidade', True), ('cpu', False),
                             ('memoria', False), ('sloc', False), ('estrelas', True),
                             ('forks', True), ('c3', True))}
    dims = {}
    for fw in FRAMEWORKS:
        recursos = 0.5 * N['cpu'][fw] + 0.5 * N['memoria'][fw]
        dims[fw] = {
            'recursos': recursos,
            'desempenho': (N['p95'][fw] + N['capacidade'][fw] + recursos) / 3,
            'produtividade': N['sloc'][fw],
            'comunidade': (N['estrelas'][fw] + N['forks'][fw] + N['c3'][fw]) / 3,
        }
        dims[fw]['saw'] = sum(pesos[d] * dims[fw][d] for d in DIMENSOES)
    return N, dims


def ordenar(dims):
    return sorted(FRAMEWORKS, key=lambda fw: -dims[fw]['saw'])


def kendall_tau_a(ordem_a, ordem_b):
    pos_a = {fw: i for i, fw in enumerate(ordem_a)}
    pos_b = {fw: i for i, fw in enumerate(ordem_b)}
    fws = list(pos_a)
    conc = disc = 0
    for i in range(len(fws)):
        for j in range(i + 1, len(fws)):
            s = (pos_a[fws[i]] - pos_a[fws[j]]) * (pos_b[fws[i]] - pos_b[fws[j]])
            if s > 0:
                conc += 1
            elif s < 0:
                disc += 1
    n = len(fws)
    return (conc - disc) / (n * (n - 1) / 2)


def cruzamento_peso_desempenho(dims, a, b):
    """Peso w do desempenho em que a e b empatam, com as outras duas dimensões a (1-w)/2."""
    da = dims[a]['desempenho'] - dims[b]['desempenho']
    ra = (dims[a]['produtividade'] + dims[a]['comunidade']
          - dims[b]['produtividade'] - dims[b]['comunidade']) / 2
    # nota_a - nota_b = w·da + (1-w)·ra = 0
    if da == ra:
        return None
    return ra / (ra - da)


# --------------------------------------------------------------------------- saída

def _mostrar(caminho):
    rel = os.path.relpath(os.path.abspath(caminho), RAIZ)
    return caminho if rel.startswith('..') else rel


def escrever_csv(caminho, cabecalho, linhas):
    with io.open(caminho, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(cabecalho)
        for linha in linhas:
            w.writerow(['%.6g' % c if isinstance(c, float) else c for c in linha])
    print('  gravado %s' % _mostrar(caminho))


def medias_por_taxa(execucoes):
    """{taxa: {fw: {métrica: resumo}}}"""
    grupos = {}
    for e in execucoes:
        grupos.setdefault(e['taxa'], {}).setdefault(e['fw'], []).append(e)
    saida = {}
    for taxa, por_fw in grupos.items():
        saida[taxa] = {}
        for fw, lista in por_fw.items():
            saida[taxa][fw] = {m: resumo([e[m] for e in lista])
                               for m in ('p95', 'media', 'cpuMedia', 'memMedia')}
    return saida


def figuras(saida, m212, cap_base, dims_base, configs):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('AVISO: matplotlib não instalado; figuras não geradas')
        return []

    plt.rcParams.update({
        'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
        'axes.edgecolor': '#52514e', 'axes.labelcolor': '#0b0b0b', 'xtick.color': '#52514e',
        'ytick.color': '#52514e', 'axes.grid': True, 'grid.color': '#e4e3df',
        'grid.linewidth': 0.6, 'axes.axisbelow': True, 'figure.facecolor': 'white',
        'axes.facecolor': 'white', 'savefig.dpi': 200, 'savefig.bbox': 'tight',
    })
    gerados = []

    def salvar(fig, nome):
        caminho = os.path.join(saida, nome)
        fig.savefig(caminho)
        plt.close(fig)
        print('  gravado %s' % _mostrar(caminho))
        gerados.append(caminho)

    ordem_p95 = sorted(FRAMEWORKS, key=lambda fw: m212[fw]['p95']['media'])

    # 1. p95 com IC 95%
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for i, fw in enumerate(ordem_p95):
        r = m212[fw]['p95']
        ax.barh(i, r['media'], color=COR[fw], height=0.55)
        ax.errorbar(r['media'], i, xerr=r['ic'], fmt='none', ecolor='#0b0b0b', capsize=4,
                    linewidth=1.2)
        ax.text(r['media'] + r['ic'] + 0.12, i, '%.2f ± %.2f' % (r['media'], r['ic']),
                va='center', fontsize=9, color='#0b0b0b')
    ax.set_yticks(range(len(ordem_p95)), [ROTULO[fw] for fw in ordem_p95])
    ax.invert_yaxis()
    ax.set_xlabel('latência p95 (ms), média de 10 repetições e IC 95%')
    ax.set_title('Latência p95 a %d req/s' % TAXA_BASE, loc='left', fontsize=11)
    ax.grid(axis='y', visible=False)
    ax.set_xlim(0, max(m212[fw]['p95']['media'] for fw in FRAMEWORKS) * 1.3)
    salvar(fig, 'fig1-latencia-p95.png')

    # 2. capacidade com as 5 repetições
    ordem_cap = sorted(FRAMEWORKS, key=lambda fw: -cap_base[fw][1]['valor'])
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for i, fw in enumerate(ordem_cap):
        valores, r = cap_base[fw]
        ax.barh(i, r['valor'], color=COR[fw], height=0.55, alpha=0.35)
        # repetições coincidentes ficam lado a lado na vertical, para não se esconderem
        vistos = {}
        for v in valores:
            k = vistos.get(v, 0)
            vistos[v] = k + 1
            ax.plot(v, i - 0.18 + 0.09 * k, 'o', color=COR[fw], markersize=6,
                    markeredgecolor='white', markeredgewidth=1)
        ax.text(max(valores) + 70, i, '%d (%s)' % (r['valor'], r['criterio']), va='center',
                fontsize=9, color='#0b0b0b')
    ax.set_yticks(range(len(ordem_cap)), [ROTULO[fw] for fw in ordem_cap])
    ax.invert_yaxis()
    ax.set_xlabel('capacidade utilizável (req/s); barra = resumo, pontos = repetições')
    ax.set_title('Capacidade (p95 < %g ms, 5 repetições)' % TETO_BASE, loc='left', fontsize=11)
    ax.grid(axis='y', visible=False)
    ax.set_xlim(0, max(max(v) for v, _ in cap_base.values()) * 1.25)
    salvar(fig, 'fig2-capacidade.png')

    # 3. CPU e memória lado a lado — dois gráficos, uma escala cada
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.8, 3.4), sharey=True)
    for ax, chave, rotulo in ((a1, 'cpuMedia', 'CPU média (%)'),
                              (a2, 'memMedia', 'memória média (MiB)')):
        for i, fw in enumerate(FRAMEWORKS):
            r = m212[fw][chave]
            ax.barh(i, r['media'], color=COR[fw], height=0.55)
            ax.errorbar(r['media'], i, xerr=r['ic'], fmt='none', ecolor='#0b0b0b', capsize=3,
                        linewidth=1)
            ax.text(r['media'] + r['ic'], i, '  %.1f' % r['media'], va='center', fontsize=9)
        ax.set_xlabel(rotulo)
        ax.grid(axis='y', visible=False)
        ax.set_xlim(0, max(m212[fw][chave]['media'] for fw in FRAMEWORKS) * 1.25)
    a1.set_yticks(range(len(FRAMEWORKS)), [ROTULO[fw] for fw in FRAMEWORKS])
    a1.invert_yaxis()
    fig.suptitle('Recursos a %d req/s (média de 10 repetições e IC 95%%)' % TAXA_BASE,
                 x=0.02, ha='left', fontsize=11)
    salvar(fig, 'fig3-cpu-memoria.png')

    if dims_base is None:
        print('AVISO: figuras 4 e 5 dependem da dimensão de comunidade; não geradas')
        return gerados

    # 4. SAW empilhado por dimensão (contribuição ponderada, 1/3 cada)
    ordem_saw = ordenar(dims_base)
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    for i, fw in enumerate(ordem_saw):
        esquerda = 0.0
        for d in DIMENSOES:
            largura = PESOS_BASE[d] * dims_base[fw][d]
            ax.barh(i, largura, left=esquerda, color=COR_DIM[d], height=0.55,
                    edgecolor='white', linewidth=2, label=d if i == 0 else None)
            esquerda += largura
        ax.text(esquerda + 0.01, i, '%.3f' % dims_base[fw]['saw'], va='center', fontsize=9)
    ax.set_yticks(range(len(ordem_saw)), [ROTULO[fw] for fw in ordem_saw])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel('nota SAW (soma das contribuições ponderadas das dimensões)')
    ax.set_title('Modelo SAW — cenário base', loc='left', fontsize=11)
    ax.grid(axis='y', visible=False)
    ax.legend(loc='lower right', frameon=False, fontsize=9)
    salvar(fig, 'fig4-saw-dimensoes.png')

    # 5. mapa de posição por configuração
    nomes = [c['nome'] for c in configs]
    fig, ax = plt.subplots(figsize=(6.4, 0.32 * len(nomes) + 1.4))
    for j, c in enumerate(configs):
        for fw in FRAMEWORKS:
            pos = c['ordem'].index(fw) + 1
            ax.add_patch(plt.Rectangle((FRAMEWORKS.index(fw) - 0.5 + 0.03, j - 0.5 + 0.03),
                                       0.94, 0.94, color=plt.cm.Blues(1.05 - pos * 0.18),
                                       linewidth=0))
            ax.text(FRAMEWORKS.index(fw), j, str(pos), ha='center', va='center', fontsize=8,
                    color='white' if pos <= 2 else '#0b0b0b')
        ax.text(len(FRAMEWORKS) - 0.35, j, 'τ = %.1f' % c['tau'], va='center', fontsize=8,
                color='#52514e')
    ax.set_xlim(-0.5, len(FRAMEWORKS) + 0.4)
    ax.set_ylim(len(nomes) - 0.5, -0.5)
    ax.set_xticks(range(len(FRAMEWORKS)), [ROTULO[fw] for fw in FRAMEWORKS], fontsize=9)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(nomes)), nomes, fontsize=8)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title('Posição no ordenamento SAW por configuração (1 = melhor)', loc='left',
                 fontsize=11, pad=24)
    salvar(fig, 'fig5-mapa-posicoes.png')
    return gerados


# --------------------------------------------------------------------------- principal

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campanha', default=os.path.join(RAIZ, 'results', 'campaign'))
    ap.add_argument('--capacidade', default=os.path.join(RAIZ, 'results', 'capacity-desempenho'))
    ap.add_argument('--sloc', default=os.path.join(RAIZ, 'results', 'sloc'))
    ap.add_argument('--c3', default=os.path.join(RAIZ, 'results', 'comunidade', 'c3-prs.csv'))
    ap.add_argument('--comunidade',
                    default=os.path.join(RAIZ, 'results', 'comunidade', 'estrelas-forks.csv'))
    ap.add_argument('--saida', default=os.path.join(RAIZ, 'results', 'analise'))
    args = ap.parse_args()

    os.makedirs(args.saida, exist_ok=True)
    print('saída em %s' % _mostrar(args.saida))

    # -- carga fixa
    ex = ler_campanha(args.campanha)
    invalidas = [e['nome'] for e in ex if e['erro'] > 0 or e['descartadas'] > 0]
    print('execuções: %d; com erro ou descarte: %d' % (len(ex), len(invalidas)))
    m = medias_por_taxa(ex)
    linhas = []
    for taxa in sorted(m):
        for fw in FRAMEWORKS:
            r = m[taxa][fw]
            linha = [taxa, ROTULO[fw], r['p95']['n']]
            for chave in ('p95', 'media', 'cpuMedia', 'memMedia'):
                linha += [r[chave]['media'], r[chave]['ic'], r[chave]['cv']]
            linhas.append(linha)
    cab = ['taxa_rps', 'framework', 'n']
    for chave in ('p95_ms', 'lat_media_ms', 'cpu_pct', 'mem_mib'):
        cab += [chave, chave + '_ic95', chave + '_cv']
    escrever_csv(os.path.join(args.saida, 'tabela-carga-fixa.csv'), cab, linhas)
    escrever_csv(os.path.join(args.saida, 'tabela-212rps.csv'), cab,
                 [l for l in linhas if l[0] == TAXA_BASE])

    # -- capacidade
    por_fw = ler_capacidade(args.capacidade)
    cap_base = capacidades(por_fw, TETO_BASE)
    n_reps = max(len(v) for v, _ in cap_base.values())
    escrever_csv(
        os.path.join(args.saida, 'tabela-capacidade.csv'),
        ['framework'] + ['rep%02d' % (i + 1) for i in range(n_reps)] + ['resumo', 'criterio'],
        [[ROTULO[fw]] + cap_base[fw][0] + [cap_base[fw][1]['valor'], cap_base[fw][1]['criterio']]
         for fw in FRAMEWORKS])

    # -- produtividade e comunidade
    sloc_a, sloc_b = ler_sloc(args.sloc, 'a'), ler_sloc(args.sloc, 'b')
    c3_base, c3_sem_rev = ler_c3(args.c3)
    print('C3 base: %s' % ', '.join('%s %d' % (ROTULO[fw], c3_base[fw]) for fw in FRAMEWORKS))
    extra = ler_comunidade_extra(args.comunidade)

    def criterios(taxa=TAXA_BASE, lat='p95', teto=TETO_BASE, sloc=sloc_a, c3=c3_base):
        cap = cap_base if teto == TETO_BASE else capacidades(por_fw, teto)
        return {
            'p95': {fw: m[taxa][fw][lat]['media'] for fw in FRAMEWORKS},
            'capacidade': {fw: cap[fw][1]['valor'] for fw in FRAMEWORKS},
            'cpu': {fw: m[taxa][fw]['cpuMedia']['media'] for fw in FRAMEWORKS},
            'memoria': {fw: m[taxa][fw]['memMedia']['media'] for fw in FRAMEWORKS},
            'sloc': dict(sloc),
            'estrelas': {fw: extra[fw]['estrelas'] for fw in FRAMEWORKS} if extra else None,
            'forks': {fw: extra[fw]['forks'] for fw in FRAMEWORKS} if extra else None,
            'c3': dict(c3),
        }

    escrever_csv(
        os.path.join(args.saida, 'tabela-criterios-brutos.csv'),
        ['framework', 'p95_ms', 'capacidade_rps', 'cpu_pct', 'mem_mib', 'sloc_a', 'sloc_b',
         'estrelas', 'forks', 'c3_base', 'c3_sem_revisao', 'prs_abertos'],
        [[ROTULO[fw], m[TAXA_BASE][fw]['p95']['media'], cap_base[fw][1]['valor'],
          m[TAXA_BASE][fw]['cpuMedia']['media'], m[TAXA_BASE][fw]['memMedia']['media'],
          sloc_a[fw], sloc_b[fw],
          extra[fw]['estrelas'] if extra else '', extra[fw]['forks'] if extra else '',
          c3_base[fw], c3_sem_rev[fw],
          (extra[fw]['prs_abertos'] if extra and extra[fw]['prs_abertos'] is not None else '')]
         for fw in FRAMEWORKS])

    if extra is None:
        print()
        print('AVISO: %s não existe. Estrelas, forks e PRs em aberto não estão no repositório;'
              % os.path.relpath(args.comunidade, RAIZ))
        print('       o modelo SAW, a sensibilidade e as figuras 4 e 5 NÃO foram gerados.')
        figuras(args.saida, m[TAXA_BASE], cap_base, None, [])
        return

    # -- SAW base
    crit_base = criterios()
    N, dims_base = saw(crit_base)
    ordem_base = ordenar(dims_base)
    escrever_csv(
        os.path.join(args.saida, 'tabela-saw.csv'),
        ['posicao', 'framework', 'n_p95', 'n_capacidade', 'n_cpu', 'n_memoria', 'recursos',
         'desempenho', 'n_sloc', 'produtividade', 'n_estrelas', 'n_forks', 'n_c3',
         'comunidade', 'saw'],
        [[i + 1, ROTULO[fw], N['p95'][fw], N['capacidade'][fw], N['cpu'][fw],
          N['memoria'][fw], dims_base[fw]['recursos'], dims_base[fw]['desempenho'],
          N['sloc'][fw], dims_base[fw]['produtividade'], N['estrelas'][fw], N['forks'][fw],
          N['c3'][fw], dims_base[fw]['comunidade'], dims_base[fw]['saw']]
         for i, fw in enumerate(ordem_base)])

    # -- sensibilidade
    configs = [('base', crit_base, PESOS_BASE, 'max-min')]
    for d in DIMENSOES:
        pesos = {x: (0.50 if x == d else 0.25) for x in DIMENSOES}
        configs.append(('peso %s 0,50' % d, crit_base, pesos, 'max-min'))
    # As normalizações alternativas NÃO integram as 18 configurações da sensibilidade: são
    # verificação à parte da escolha da técnica, reportada em tabela própria e fora da
    # contagem de 1º lugar, do τ mínimo e da figura 5.
    normalizacoes = [('normalização %s' % tec, crit_base, PESOS_BASE, tec)
                     for tec in ('maximo', 'soma', 'vetorial')]
    configs.append(('C3 sem exigir revisão', criterios(c3=c3_sem_rev), PESOS_BASE, 'max-min'))
    if all(extra[fw]['prs_abertos'] is not None for fw in FRAMEWORKS):
        configs.append(('C3 por PRs abertos',
                        criterios(c3={fw: extra[fw]['prs_abertos'] for fw in FRAMEWORKS}),
                        PESOS_BASE, 'max-min'))
    else:
        print('AVISO: prs_abertos ausente em %s; variante "C3 por PRs abertos" omitida'
              % os.path.relpath(args.comunidade, RAIZ))
    configs.append(('SLOC-B', criterios(sloc=sloc_b), PESOS_BASE, 'max-min'))
    for taxa in (106, 318):
        configs.append(('carga %d req/s' % taxa, criterios(taxa=taxa), PESOS_BASE, 'max-min'))
    configs.append(('latência média', criterios(lat='media'), PESOS_BASE, 'max-min'))
    for teto in TETOS:
        configs.append(('teto p95 %d ms' % teto, criterios(teto=float(teto)), PESOS_BASE,
                        'max-min'))

    def avaliar(lista):
        saida = []
        for nome, crit, pesos, tec in lista:
            _, dims = saw(crit, pesos, tec)
            ordem = ordenar(dims)
            saida.append({'nome': nome, 'dims': dims, 'ordem': ordem,
                          'tau': kendall_tau_a(ordem_base, ordem), 'crit': crit})
        return saida

    def gravar_ordenamentos(nome_arquivo, lista):
        escrever_csv(
            os.path.join(args.saida, nome_arquivo),
            ['configuracao', 'tau_a'] + ['pos_' + fw for fw in FRAMEWORKS]
            + ['saw_' + fw for fw in FRAMEWORKS] + ['ordenamento'],
            [[r['nome'], r['tau']] + [r['ordem'].index(fw) + 1 for fw in FRAMEWORKS]
             + [r['dims'][fw]['saw'] for fw in FRAMEWORKS]
             + [' > '.join(ROTULO[fw] for fw in r['ordem'])] for r in lista])

    resultados = avaliar(configs)
    res_normalizacoes = avaliar(normalizacoes)
    gravar_ordenamentos('tabela-sensibilidade.csv', resultados)
    gravar_ordenamentos('tabela-normalizacoes.csv', res_normalizacoes)

    escrever_csv(
        os.path.join(args.saida, 'tabela-capacidade-por-teto.csv'),
        ['teto_ms'] + [ROTULO[fw] for fw in FRAMEWORKS],
        [[teto] + [capacidades(por_fw, float(teto))[fw][1]['valor'] for fw in FRAMEWORKS]
         for teto in TETOS])

    # -- resumo no console
    print()
    print('SAW base: ' + '  '.join('%s %.3f' % (ROTULO[fw], dims_base[fw]['saw'])
                                   for fw in ordem_base))
    print('configurações: %d (base + %d)' % (len(resultados), len(resultados) - 1))
    primeiros = {}
    for r in resultados:
        primeiros[r['ordem'][0]] = primeiros.get(r['ordem'][0], 0) + 1
    print('1º lugar: ' + ', '.join('%s em %d' % (ROTULO[fw], n) for fw, n in
                                   sorted(primeiros.items(), key=lambda x: -x[1])))
    pior = min(resultados, key=lambda r: r['tau'])
    print('τ mínimo = %.1f (%s)' % (pior['tau'], pior['nome']))
    print('normalizações, à parte: ' + '; '.join(
        '%s τ = %.1f, 1º %s' % (r['nome'], r['tau'], ROTULO[r['ordem'][0]])
        for r in res_normalizacoes))
    w = cruzamento_peso_desempenho(dims_base, 'aspnet', 'django')
    print('ASP.NET Core e Django empatam com peso de desempenho w = %.4f '
          '(produtividade e comunidade a (1-w)/2 cada)' % w)

    figuras(args.saida, m[TAXA_BASE], cap_base, dims_base, resultados)


if __name__ == '__main__':
    main()
