"""Análise do teste de carga fixa.

    python scripts/analyze-experiment.py                         # results/campaign
    python scripts/analyze-experiment.py results/piloto-cv       # piloto de variabilidade
    python scripts/analyze-experiment.py --pares                 # + diferenças entre frameworks

Lê <dir>/<framework>/<framework>_<taxa>rps_repNN.json e .stats.csv (scripts/run-experiment.sh).

Cada execução é resumida em UM valor por métrica — p95 e média de latência, taxa obtida, erro,
iterações descartadas, CPU média e de pico, memória média e de pico — e os valores das
repetições de cada combinação framework × taxa são sintetizados por média e IC 95% baseado na
distribuição t. As diferenças entre frameworks, com --pares, são dadas como IC 95% da
diferença entre médias (Welch), e não por teste de significância.

Também reporta, por combinação:
  - o coeficiente de variação ENTRE execuções e a meia-largura relativa do IC 95% que ele
    projeta para 10 repetições: t(0,975; 9) × CV / √10 ≈ 0,715 × CV (Kalibera e Jones, 2013);
  - o intervalo EFETIVO de amostragem do docker stats, medido pelos carimbos de tempo;
  - execuções com erro ou descarte, que o protocolo manda investigar.
"""
import sys

# O console do Windows usa cp1252 e falha ao imprimir os símbolos matemáticos do relatório.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import argparse
import glob
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats_util import diferenca, meia_largura_projetada, resumo  # noqa: E402

UNIDADES = {'B': 1 / 1048576, 'KiB': 1 / 1024, 'KB': 1 / 1000 / 1.048576 * 1.024,
            'MiB': 1.0, 'MB': 1 / 1.048576, 'GiB': 1024.0, 'GB': 1000 / 1.048576}


def mib(texto):
    m = re.match(r'\s*([\d.]+)\s*([A-Za-z]+)', texto)
    if not m:
        return None
    return float(m.group(1)) * UNIDADES.get(m.group(2), float('nan'))


def ler_stats(caminho):
    if not os.path.exists(caminho):
        return None
    ts, cpu, mem = [], [], []
    for linha in io.open(caminho, encoding='utf-8'):
        partes = linha.strip().split(',')
        if len(partes) < 3:
            continue
        try:
            ts.append(int(partes[0]))
            cpu.append(float(partes[1].rstrip('%')))
            mem.append(mib(partes[2].split('/')[0]))
        except ValueError:
            continue
    if not cpu:
        return None
    intervalos = [(b - a) / 1000.0 for a, b in zip(ts, ts[1:])]
    return {
        'cpuMedia': sum(cpu) / len(cpu),
        'cpuPico': max(cpu),
        'memMedia': sum(mem) / len(mem),
        'memPico': max(mem),
        'amostras': len(cpu),
        'intervaloMedioS': sum(intervalos) / len(intervalos) if intervalos else None,
    }


def carregar(diretorio):
    execucoes = []
    for caminho in sorted(glob.glob(os.path.join(diretorio, '*', '*_rep[0-9][0-9].json'))):
        nome = os.path.basename(caminho)
        m = re.match(r'(.+)_(\d+)rps_rep(\d+)\.json$', nome)
        if not m:
            continue
        fw, taxa, rep = m.group(1), int(m.group(2)), int(m.group(3))
        try:
            row = json.load(io.open(caminho, encoding='utf-8'))['row']
        except (ValueError, KeyError):
            continue
        st = ler_stats(caminho[:-5] + '.stats.csv') or {}
        execucoes.append({
            'fw': fw, 'taxa': taxa, 'rep': rep, 'nome': nome[:-5],
            'p95': row['latencyP95Ms'], 'media': row['latencyAvgMs'],
            'obtida': row['achievedRps'], 'erro': row['errorRate'],
            'descartadas': row['droppedIterations'],
            'cpuMedia': st.get('cpuMedia'), 'cpuPico': st.get('cpuPico'),
            'memMedia': st.get('memMedia'), 'memPico': st.get('memPico'),
            'intervalo': st.get('intervaloMedioS'),
        })
    return execucoes


METRICAS = [
    ('p95', 'p95 (ms)'),
    ('media', 'média (ms)'),
    ('cpuMedia', 'CPU média (%)'),
    ('cpuPico', 'CPU pico (%)'),
    ('memMedia', 'mem. média (MiB)'),
    ('memPico', 'mem. pico (MiB)'),
    ('obtida', 'taxa obtida (req/s)'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir', nargs='?', default='results/campaign')
    ap.add_argument('--pares', action='store_true', help='IC da diferença entre frameworks')
    ap.add_argument('--n-projetado', type=int, default=10)
    args = ap.parse_args()

    ex = carregar(args.dir)
    if not ex:
        print('nenhuma execução em %s' % args.dir)
        return

    grupos = {}
    for e in ex:
        grupos.setdefault((e['taxa'], e['fw']), []).append(e)

    for taxa in sorted({t for t, _ in grupos}):
        print('=' * 100)
        print('TAXA %d req/s' % taxa)
        print('%-11s %3s  ' % ('framework', 'n') + '  '.join('%-24s' % r for _, r in METRICAS[:4]))
        for (t, fw), lista in sorted(grupos.items()):
            if t != taxa:
                continue
            celulas = []
            for chave, _ in METRICAS[:4]:
                r = resumo([e[chave] for e in lista])
                celulas.append('%9.2f ± %-7.2f cv%4.1f%%' % (r['media'], r['ic'], r['cv'] * 100)
                               if r['n'] >= 2 else '%9.2f %-16s' % (r['media'], '(n=1)'))
            print('%-11s %3d  ' % (fw, len(lista)) + '  '.join(celulas))

        print('%-11s %3s  ' % ('', '') + '  '.join('%-24s' % r for _, r in METRICAS[4:]))
        for (t, fw), lista in sorted(grupos.items()):
            if t != taxa:
                continue
            celulas = []
            for chave, _ in METRICAS[4:]:
                r = resumo([e[chave] for e in lista])
                celulas.append('%9.2f ± %-7.2f cv%4.1f%%' % (r['media'], r['ic'], r['cv'] * 100)
                               if r['n'] >= 2 else '%9.2f %-16s' % (r['media'], '(n=1)'))
            print('%-11s %3s  ' % (fw, '') + '  '.join(celulas))

    print('=' * 100)
    print('DIMENSIONAMENTO — CV entre execuções e meia-largura relativa projetada para n=%d'
          % args.n_projetado)
    print('(Kalibera e Jones, 2013: meia-largura ≈ t(0,975; n-1) × CV / √n)')
    for (taxa, fw), lista in sorted(grupos.items()):
        if len(lista) < 2:
            continue
        partes = []
        for chave in ('p95', 'cpuMedia', 'memMedia'):
            r = resumo([e[chave] for e in lista])
            if r['n'] >= 2:
                partes.append('%s: CV %.1f%% -> H %.1f%%' % (
                    chave, r['cv'] * 100, meia_largura_projetada(r['cv'], args.n_projetado) * 100))
        print('  %-11s %5d req/s  n=%d  %s' % (fw, taxa, len(lista), '   '.join(partes)))

    intervalos = [e['intervalo'] for e in ex if e['intervalo']]
    if intervalos:
        print()
        print('Intervalo efetivo de amostragem do docker stats: média %.2f s (mín %.2f, máx %.2f)'
              % (sum(intervalos) / len(intervalos), min(intervalos), max(intervalos)))

    suspeitas = [e for e in ex if e['erro'] > 0 or e['descartadas'] > 0]
    print()
    if suspeitas:
        print('EXECUÇÕES COM ERRO OU DESCARTE — investigar antes de usar (seção 3.4):')
        for e in suspeitas:
            print('  %s  erro=%.3f%%  descartadas=%d' % (e['nome'], e['erro'] * 100, e['descartadas']))
    else:
        print('Nenhuma execução com erro ou descarte.')

    if args.pares:
        print()
        print('=' * 100)
        print('DIFERENÇAS ENTRE FRAMEWORKS — IC 95% da diferença entre médias (Welch)')
        print('Intervalo contendo zero = diferença não conclusiva.')
        for taxa in sorted({t for t, _ in grupos}):
            fws = sorted(fw for t, fw in grupos if t == taxa)
            for chave in ('p95', 'cpuMedia', 'memMedia'):
                print('-- %d req/s — %s' % (taxa, chave))
                for i, a in enumerate(fws):
                    for b in fws[i + 1:]:
                        va = [e[chave] for e in grupos[(taxa, a)]]
                        vb = [e[chave] for e in grupos[(taxa, b)]]
                        d, h = diferenca(va, vb)
                        if h != h:
                            continue
                        flag = '  (não conclusiva)' if d - h <= 0 <= d + h else ''
                        print('   %-11s - %-11s  %9.2f ± %.2f%s' % (a, b, d, h, flag))


if __name__ == '__main__':
    main()
