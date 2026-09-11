"""Análise das séries do critério de aceite 8.3.

    python scripts/analyze-warmup.py results/warmup/*.json

Lê as séries gravadas por scripts/verify-warmup.sh e responde a pergunta da seção 8.3:
a latência estabiliza, e em quanto tempo?

Sobre o critério. Exigir que TODO intervalo posterior fique dentro de uma faixa estreita
confunde ruído com aquecimento: uma única oscilação tardia — coleta de lixo, escalonamento
do host — reprova uma série que já entrou em regime há muito tempo. O que se reporta aqui é:

  entrada em regime   primeiro intervalo cuja média cai dentro de ±TOL do regime estável
  dispersão na cauda  maior desvio observado DEPOIS desse ponto, que mede o ruído de fundo
                      e permite julgar se a entrada foi real ou acidental
  custo do aquecimento excesso de latência acumulado antes da entrada, em relação ao que a
                      mesma carga custaria em regime

O regime estável é a média dos últimos 30% dos intervalos.
"""
import glob
import io
import json
import sys

TOL = 0.10


def analisar(caminho):
    d = json.load(io.open(caminho, encoding='utf-8'))
    serie = d.get('series') or []
    if not serie:
        return None

    lat = [b['latencyAvgMs'] for b in serie]
    passo = d.get('bucketSeconds', 10)

    corte = max(1, int(len(lat) * 0.7))
    estavel = sum(lat[corte:]) / len(lat[corte:])

    entrada = None
    for i, v in enumerate(lat):
        if abs(v - estavel) <= TOL * estavel:
            entrada = i
            break

    if entrada is None:
        cauda = 0.0
        custo = None
    else:
        posteriores = lat[entrada:]
        cauda = max(abs(v - estavel) / estavel for v in posteriores)
        # excesso acumulado antes da entrada, em segundos-equivalentes de latência
        custo = sum(max(0.0, v - estavel) for v in lat[:entrada]) / estavel * passo

    return {
        'framework': caminho.replace('\\', '/').split('/')[-1].replace('.json', ''),
        'passo': passo,
        'primeiro': lat[0],
        'estavel': estavel,
        'excessoPrimeiro': lat[0] / estavel - 1,
        'entradaSegundos': None if entrada is None else entrada * passo,
        'dispersaoCauda': cauda,
        'custoAquecimentoSegundos': custo,
        'erro': d.get('errorRate', 0) or 0,
        'serie': lat,
    }


def main(padroes):
    caminhos = []
    for p in padroes:
        caminhos.extend(sorted(glob.glob(p)))
    caminhos = [c for c in caminhos if not c.replace('\\', '/').split('/')[-1].startswith('_')]

    linhas = [a for a in (analisar(c) for c in caminhos) if a]
    if not linhas:
        print('nenhuma série encontrada')
        return

    print('%-12s %10s %10s %12s %12s %10s' %
          ('framework', '1º (ms)', 'regime', 'entrada', 'disp. cauda', 'erro'))
    print('%-12s %10s %10s %12s %12s %10s' %
          ('-' * 12, '-' * 10, '-' * 10, '-' * 12, '-' * 12, '-' * 10))
    for a in linhas:
        entrada = 'não entrou' if a['entradaSegundos'] is None else '%d s' % a['entradaSegundos']
        print('%-12s %10.1f %10.1f %12s %11.0f%% %9.4f%%' %
              (a['framework'], a['primeiro'], a['estavel'], entrada,
               a['dispersaoCauda'] * 100, a['erro'] * 100))

    print()
    entradas = [a['entradaSegundos'] for a in linhas if a['entradaSegundos'] is not None]
    if entradas:
        pior = max(entradas)
        print('Entrada em regime mais tardia: %d s.' % pior)
        print('Período de aquecimento sugerido, com margem: %d s.'
              % (int((pior * 1.5 + 29) // 30) * 30))
    faltam = [a['framework'] for a in linhas if a['entradaSegundos'] is None]
    if faltam:
        print('Sem entrada em regime dentro da janela: %s' % ', '.join(faltam))
    ruidosos = [a['framework'] for a in linhas if a['dispersaoCauda'] > 0.25]
    if ruidosos:
        print('Dispersão de cauda acima de 25%% (leitura da entrada é frágil): %s'
              % ', '.join(ruidosos))
    com_erro = [a['framework'] for a in linhas if a['erro'] > 0]
    print('Taxa de erro nula em todos: %s' % ('NÃO — ' + ', '.join(com_erro) if com_erro else 'SIM'))

    print()
    for a in linhas:
        print('%-12s %s' % (a['framework'],
                            ' '.join('%.0f' % v for v in a['serie'])))


if __name__ == '__main__':
    main(sys.argv[1:] or ['results/warmup/*.json'])
