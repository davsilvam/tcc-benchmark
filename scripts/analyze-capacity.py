"""Análise do teste de capacidade.

    python scripts/analyze-capacity.py                       # curva latência × taxa
    python scripts/analyze-capacity.py --p95-max 100         # + capacidade com teto X = 100 ms
    python scripts/analyze-capacity.py --dir results/capacity

Lê results/capacity/<framework>_repNN.csv (scripts/run-capacity.sh) e produz:

1. A CURVA latência × taxa de cada framework, com a latência de base (p95 mediano dos três
   primeiros patamares) e as taxas em que o p95 ultrapassa 2, 3 e 5 vezes essa base. É o
   dado que sustenta a derivação do teto X a partir do joelho da curva. Este script NÃO
   escolhe X: mostra onde a curva se dobra.

2. Com --p95-max, a CAPACIDADE UTILIZÁVEL de cada repetição — o maior patamar que satisfaz
   simultaneamente p95 < X, erro < 1% e nenhuma iteração descartada —, a média entre
   repetições com IC 95%, a menor capacidade C_min e os três níveis do teste de carga fixa.

Sobre a definição. "O maior patamar que satisfaz" e "o último patamar antes da primeira
violação" coincidem quando a curva é monótona. Se não coincidirem — um patamar viola e um
mais alto volta a satisfazer —, o script aponta a discrepância em vez de escolher uma
leitura em silêncio.
"""
import sys

# O console do Windows usa cp1252 e falha ao imprimir os símbolos matemáticos do relatório.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import argparse
import glob
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats_util import resumo  # noqa: E402

CAMPOS = ['rate_target', 'achieved_rps', 'p95_ms', 'avg_ms', 'error_rate', 'dropped',
          'vus_max_used', 'estagio']


def ler(caminho):
    linhas, motivo, livros = [], None, None
    for linha in io.open(caminho, encoding='utf-8'):
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith('#'):
            if 'motivo=' in linha:
                motivo = linha.split('motivo=', 1)[-1]
            if 'livros_ao_final=' in linha:
                livros = linha.split('livros_ao_final=', 1)[-1].split()[0]
            continue
        if linha.startswith('rate_target'):
            continue
        v = linha.split(',')
        d = dict(zip(CAMPOS, v))
        linhas.append({
            'rate': int(d['rate_target']),
            'achieved': float(d['achieved_rps']),
            'p95': float(d['p95_ms']),
            'avg': float(d['avg_ms']),
            'erro': float(d['error_rate']),
            'descartadas': int(d['dropped']),
            # Arquivos anteriores ao estágio fino (piloto de 25/09/2026) não têm a coluna.
            'estagio': d.get('estagio', 'grosso'),
        })
    # O estágio fino acrescenta patamares de taxa MENOR que a do patamar violado, então o
    # arquivo não vem em ordem crescente. A definição de capacidade — tanto "o maior patamar que
    # satisfaz" quanto "o último antes da primeira violação" — só faz sentido sobre a sequência
    # ordenada por taxa. Ordenar aqui deixa ambas as leituras bem definidas e não altera nada
    # nos arquivos de passo único, que já estão em ordem.
    linhas.sort(key=lambda r: r['rate'])
    return linhas, motivo, livros


def satisfaz(p, x):
    return p['p95'] < x and p['erro'] < 0.01 and p['descartadas'] == 0


def capacidade(patamares, x):
    """Capacidade pela primeira violação CONFIRMADA: dois patamares consecutivos violando.

    Uma violação isolada é tratada como transitória e a varredura prossegue. Sem isso, o
    critério mede, para um framework com transitórios esporádicos, a taxa em que o primeiro
    deles calha de cruzar o teto, e não a capacidade: no teste de 30/09/2026 o NestJS parava
    com p95 de 101 ms e ZERO iterações descartadas, voltando a 8 ms no patamar seguinte,
    enquanto os outros quatro paravam com milhares de descartes e latência cem vezes maior.

    Quando o arquivo termina numa violação sem patamar posterior, ela é tratada como parada,
    e não como transitória: é o que ocorre nos arquivos anteriores a esta regra, em que a
    varredura parava na primeira violação, e presumir o contrário inventaria capacidade.

    Devolve (maior patamar que satisfaz, último antes da violação confirmada, transitórios).
    """
    ok = [p['rate'] for p in patamares if satisfaz(p, x)]
    maior = max(ok) if ok else None
    ultimo = None
    transitorios = []
    i, n = 0, len(patamares)
    while i < n:
        if satisfaz(patamares[i], x):
            ultimo = patamares[i]['rate']
            i += 1
            continue
        if i + 1 >= n or not satisfaz(patamares[i + 1], x):
            break
        transitorios.append(patamares[i]['rate'])
        i += 1
    return maior, ultimo, transitorios


def resumir_patamares(valores):
    """Patamar modal entre as repeticoes; na ausencia de moda, a mediana.

    A secao 3.4.2 da monografia descarta a media aritmetica: a capacidade so assume valores
    discretos, multiplos do passo fino, e uma media sugeriria resolucao superior a do
    instrumento. A moda exige um valor mais frequente que todos os outros; com N_A impar e
    repeticoes todas distintas nao ha moda, e a mediana cai sempre sobre um patamar observado.
    """
    v = sorted(x for x in valores if x is not None)
    if not v:
        return {'valor': None, 'criterio': '-', 'n': 0, 'min': None, 'max': None}
    contagem = {}
    for x in v:
        contagem[x] = contagem.get(x, 0) + 1
    mais = max(contagem.values())
    modas = [x for x, c in contagem.items() if c == mais]
    # A moda exige MAIORIA das repeticoes, nao apenas ser o valor mais frequente. Com
    # N_A = 5 e resolucao de 25 req/s, um valor que aparece 2 vezes entre 5 quase nao e
    # evidencia sobre os que aparecem 1 vez, e no teste formal de 30/09/2026 essa moda fraca
    # caiu sobre o MAIOR valor observado do Laravel (350, numa faixa de 275 a 350) — o
    # framework que define o C_min e, com ele, os tres niveis da campanha.
    # mais >= 2 porque uma observacao unica satisfaz 'maioria' trivialmente e sairia
    # rotulada como moda, o que e falso: com n = 1 nao ha valor mais frequente.
    if mais >= 2 and mais * 2 > len(v) and len(modas) == 1:
        valor, criterio = modas[0], 'moda'
    else:
        valor, criterio = v[len(v) // 2], 'mediana'
    return {'valor': valor, 'criterio': criterio, 'n': len(v), 'min': v[0], 'max': v[-1]}


def joelho(patamares):
    if not patamares:
        return None, {}
    base_lista = sorted(p['p95'] for p in patamares[:3])
    base = base_lista[len(base_lista) // 2]
    marcos = {}
    for fator in (2, 3, 5):
        marcos[fator] = next((p['rate'] for p in patamares if p['p95'] > fator * base), None)
    return base, marcos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='results/capacity')
    ap.add_argument('--p95-max', type=float, default=None, help='teto X do p95, em ms')
    args = ap.parse_args()

    arquivos = sorted(glob.glob(os.path.join(args.dir, '*_rep[0-9][0-9].csv')))
    if not arquivos:
        print('nenhum resultado em %s' % args.dir)
        return

    por_fw = {}
    for a in arquivos:
        m = re.match(r'(.+)_rep(\d+)\.csv$', os.path.basename(a))
        fw, rep = m.group(1), int(m.group(2))
        patamares, motivo, livros = ler(a)
        por_fw.setdefault(fw, []).append((rep, patamares, motivo, livros))

    print('=== curva latência × taxa (p95 em ms) ===')
    for fw, reps in sorted(por_fw.items()):
        for rep, pats, motivo, livros in reps:
            base, marcos = joelho(pats)
            print('%-11s rep%02d  parada=%-14s livros ao final=%s' % (fw, rep, motivo, livros))
            if base is not None:
                txt = '  '.join('%dx base: %s' % (f, ('%d req/s' % r) if r else 'não atingido')
                                for f, r in marcos.items())
                print('            p95 de base %.1f ms   %s' % (base, txt))
            print('            ' + '  '.join('%d:%.0f' % (p['rate'], p['p95']) for p in pats))

    if args.p95_max is None:
        print()
        print('Informe --p95-max X para calcular a capacidade utilizável e C_min.')
        return

    x = args.p95_max
    print()
    print('=== capacidade utilizável (p95 < %g ms, erro < 1%%, sem descarte) ===' % x)
    medias = {}
    for fw, reps in sorted(por_fw.items()):
        valores = []
        for rep, pats, motivo, _ in reps:
            # Execução sem medição válida não é dado. O run-capacity.sh marca o CSV, mas um
            # arquivo truncado por outra razão também cai aqui: sem patamares não há o que
            # resumir, e incluí-la como zero ou como "abaixo de START" inventaria resultado.
            if not pats or motivo == 'k6_sem_resultado':
                print('%-11s rep%02d  SEM MEDIÇÃO (%s) — excluída do resumo'
                      % (fw, rep, motivo or 'nenhum patamar no arquivo'))
                continue
            maior, ultimo, transitorios = capacidade(pats, x)
            # A seção 3.4.2 define a capacidade como o ÚLTIMO patamar antes da primeira
            # violação, e não o maior que satisfaz: a varredura é cumulativa, de modo que a
            # passagem por um patamar violado integra o percurso até os seguintes, e um
            # framework que volta a satisfazer as condições acima dele não sustentou a faixa.
            # As duas leituras divergem ao reanalisar uma curva com teto MAIS APERTADO que o
            # usado na coleta, que é justamente o sexto eixo de sensibilidade (seção 3.5.4).
            valores.append(ultimo)
            aviso = ''
            if transitorios:
                aviso += '  [%d transitório(s) ignorado(s): %s req/s]' % (
                    len(transitorios), ', '.join(str(t) for t in transitorios))
            if maior != ultimo:
                aviso += '  (curva não monótona: maior patamar que satisfaz = %s, descartado)' % maior
            if pats and ultimo == pats[-1]['rate'] and motivo == 'max_rate':
                aviso += '  ATENÇÃO: atingiu MAX_RATE sem violar; capacidade é limite inferior'
            print('%-11s rep%02d  %s req/s%s' % (fw, rep, ultimo, aviso))
        r = resumir_patamares(valores)
        medias[fw] = r['valor']
        if r['valor'] is None:
            print('%-11s sem repetição válida' % fw)
        else:
            print('%-11s %s %s req/s  (n=%d, observado de %s a %s)' % (
                fw, r['criterio'], r['valor'], r['n'], r['min'], r['max']))

    validos = {fw: m for fw, m in medias.items() if m is not None}
    if validos:
        fw_min = min(validos, key=validos.get)
        c_min = validos[fw_min]
        print()
        print('C_min = %d req/s (%s)' % (c_min, fw_min))
        for frac in (0.25, 0.50, 0.75):
            exato = frac * c_min
            # O k6 le RATE com parseInt: a taxa tem de ser inteira. Arredonda-se para baixo,
            # o que mantem o nivel do lado conservador do limite.
            print('  %2d%% de C_min = %8.2f req/s  ->  usar RATE=%d' % (
                int(frac * 100), exato, int(exato)))


if __name__ == '__main__':
    main()
