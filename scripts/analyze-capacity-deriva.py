"""Deriva de sessão no teste de capacidade: a posição da célula afeta o resultado?

    python scripts/analyze-capacity-deriva.py --dir results/capacity

A pergunta é de validade interna. O teste de capacidade da seção 14 correu por cerca de
3 h 45 com o contêiner do PostgreSQL ativo do começo ao fim, e em 19/10/2026 mediu-se que o
tempo de vida daquele processo degrada a latência de regime (seção 15.3.6). Se a mesma
degradação atingisse o teste de capacidade, as células tardias da sessão teriam capacidade
sistematicamente menor que as iniciais, e o C_min seria artefato da ordem de execução.

O teste é simples e não exige medição nova. Cada uma das 25 células tem uma posição na
sessão, dada por (repetição - 1) x 5 + posição na rodada, que `ordem.csv` registra. A
capacidade de cada célula é comparada à MEDIANA DO PRÓPRIO FRAMEWORK, o que remove a
diferença entre tratamentos e deixa apenas o desvio atribuível à sessão. Sobre esses desvios
calculam-se a inclinação por célula e o coeficiente de correlação de Pearson contra o índice.

Deriva por envelhecimento preveria inclinação NEGATIVA e correlação apreciável. A seção 12.3
já havia reportado a ausência de efeito de rodada nos dados da seção 12; este script faz a
verificação sobre os dados da seção 14, que são os que valem.

Limite do teste: n = 25, e a dispersão entre repetições do mesmo framework é grande — o
ASP.NET Core vai de 1.500 a 2.325 req/s. O teste tem, portanto, pouca potência: ele descarta
deriva grande, não deriva pequena. E a capacidade pode ser menos sensível ao estado do banco
que a latência de regime, por ser medida onde o limite do próprio sistema domina.

As capacidades por repetição NÃO são recalculadas aqui: são lidas do analyze-capacity.py, que
é a fonte autoritativa e aplica a regra de parada da seção 14.3.
"""
import argparse
import csv
import io
import os
import re
import subprocess
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def mediana(valores):
    v = sorted(valores)
    n = len(v)
    meio = n // 2
    return v[meio] if n % 2 else (v[meio - 1] + v[meio]) / 2.0


def capacidades(diretorio, p95_max):
    """Le as capacidades por repeticao da saida do analyze-capacity.py."""
    saida = subprocess.run(
        [sys.executable, '-I', os.path.join('scripts', 'analyze-capacity.py'),
         '--dir', diretorio, '--p95-max', str(p95_max)],
        capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=RAIZ)
    if saida.returncode != 0:
        sys.stderr.write(saida.stderr)
        raise SystemExit('analyze-capacity.py falhou')
    padrao = re.compile(r'^(\w+)\s+rep(\d+)\s+(\d+) req/s')
    out = {}
    for linha in saida.stdout.splitlines():
        m = padrao.match(linha.strip())
        if m:
            out[(m.group(1), int(m.group(2)))] = int(m.group(3))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='results/capacity')
    ap.add_argument('--p95-max', type=float, default=100.0)
    args = ap.parse_args()

    cap = capacidades(args.dir, args.p95_max)
    if not cap:
        raise SystemExit('nenhuma capacidade lida do analyze-capacity.py')

    ordem_csv = os.path.join(RAIZ, args.dir, 'ordem.csv')
    if not os.path.exists(ordem_csv):
        raise SystemExit('falta %s, que da a posicao de cada celula' % ordem_csv)

    por_fw = {}
    for (fw, rep), v in cap.items():
        por_fw.setdefault(fw, []).append(v)
    med = {fw: mediana(vs) for fw, vs in por_fw.items()}

    celulas = []
    with io.open(ordem_csv, encoding='utf-8') as fh:
        for linha in csv.DictReader(fh):
            rep = int(linha['repeticao'])
            pos = int(linha['posicao'])
            fw = linha['framework']
            if (fw, rep) not in cap:
                continue
            idx = (rep - 1) * len(med) + pos
            c = cap[(fw, rep)]
            celulas.append((idx, rep, pos, fw, c, 100.0 * (c - med[fw]) / med[fw]))
    celulas.sort()

    print('Deriva de sessao no teste de capacidade — %s' % args.dir)
    print('Desvio de cada celula em relacao a mediana do proprio framework.')
    print()
    print('%6s %4s %4s  %-11s %6s %9s' % ('celula', 'rep', 'pos', 'framework', 'req/s',
                                          'desvio'))
    for idx, rep, pos, fw, c, rel in celulas:
        print('%6d %4d %4d  %-11s %6d %+8.1f%%' % (idx, rep, pos, fw, c, rel))

    n = len(celulas)
    xs = [c[0] for c in celulas]
    ys = [c[5] for c in celulas]
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    incl = sxy / sxx if sxx else 0.0
    r = sxy / ((sxx * syy) ** 0.5) if sxx and syy else 0.0

    print()
    print('celulas: %d' % n)
    print('inclinacao: %+.3f%% por celula' % incl)
    print('correlacao de Pearson: r = %+.3f' % r)
    print()
    if incl < -0.5 and r < -0.3:
        print('HA indicio de deriva negativa ao longo da sessao: investigar antes de usar.')
    else:
        print('SEM indicio de deriva ao longo da sessao. Deriva por envelhecimento preveria')
        print('inclinacao negativa e correlacao apreciavel; nao e o que se observa.')
    print('Ressalva: n = %d e a dispersao entre repeticoes e grande, de modo que o teste' % n)
    print('descarta deriva grande, e nao deriva pequena.')


if __name__ == '__main__':
    main()
