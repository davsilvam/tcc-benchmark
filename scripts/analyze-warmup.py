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
import sys

# O console do Windows usa cp1252 e falha ao imprimir os símbolos matemáticos do relatório.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import glob
import io
import json
import sys

TOL = 0.10


# Par adotado, calibrado na reconfirmação de 30/09/2026 a 162 req/s (seção 13 de
# docs/versoes-e-configuracao.md). O limiar de 2% é o que Georges, Buytaert e Eeckhout (2007)
# adotam na própria avaliação — a seção 4.2 deles define o regime pelo CoV de k iterações
# abaixo de "0.01 or 0.02". O k, porém, não é transportável: lá cada medição é uma iteração de
# benchmark dentro de uma invocação da máquina virtual; aqui é um intervalo de 10 s que já
# agrega mais de mil requisições. O k = 10 deles é inatingível a 2% neste aparato, e não por
# instabilidade: com latência de regime entre 2,5 e 5,9 ms, um único transitório — o Spring
# Boot tem um pico isolado de 16 ms — contamina dez janelas consecutivas. k = 5 é a maior
# janela em que os cinco frameworks atingem 2%, com pior caso de 90 s.
CV_MAX = 0.02
K_ADOTADO = 5
# As demais janelas ficam no relatório para comparação, e para que a escolha de K_ADOTADO
# seja verificável em vez de asseverada.
JANELAS = (3, 5, 6, 10)


def coef_var(valores):
    n = len(valores)
    if n < 2:
        return float('inf')
    media = sum(valores) / n
    if media == 0:
        return float('inf')
    dp = (sum((v - media) ** 2 for v in valores) / (n - 1)) ** 0.5
    return dp / media


def janela_estavel(lat, k, passo):
    """Primeiro instante (s) a partir do qual o CV de k intervalos fica abaixo de CV_MAX,
    e a fração de janelas subsequentes que também ficam."""
    if len(lat) < k:
        return {'inicio': None, 'fracao': 0.0}
    cvs = [coef_var(lat[i:i + k]) for i in range(len(lat) - k + 1)]
    inicio = next((i for i, c in enumerate(cvs) if c < CV_MAX), None)
    if inicio is None:
        return {'inicio': None, 'fracao': 0.0}
    posteriores = cvs[inicio:]
    return {
        'inicio': (inicio + k - 1) * passo,
        'fracao': sum(1 for c in posteriores if c < CV_MAX) / len(posteriores),
    }



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

    # Critério de Georges, Buytaert e Eeckhout (2007): considera-se atingido o regime
    # estável quando o coeficiente de variação da latência média, sobre uma janela de k
    # intervalos consecutivos, cai abaixo de CV_MAX. O k não é escolhido aqui: o resultado
    # é dado para vários valores, e a escolha fica registrada na monografia.
    cv_janela = {}
    for k in JANELAS:
        cv_janela[k] = janela_estavel(lat, k, passo)

    return {
        'cvJanela': cv_janela,
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
    print('Regime estável pelo critério do coeficiente de variação (CV < %.0f%% numa janela'
          % (CV_MAX * 100))
    print('de k intervalos de %d s) — Georges, Buytaert e Eeckhout (2007):' % linhas[0]['passo'])
    print('%-12s ' % 'framework'
          + '  '.join('%-24s' % ('k=%d%s' % (k, ' (adotado)' if k == K_ADOTADO else ''))
                      for k in JANELAS))
    for a in linhas:
        celulas = []
        for k in JANELAS:
            j = a['cvJanela'][k]
            celulas.append('%-24s' % (
                'não atingido' if j['inicio'] is None
                else '%d s (%.0f%% das janelas)' % (j['inicio'], j['fracao'] * 100)))
        print('%-12s ' % a['framework'] + '  '.join(celulas))

    adotados = [a['cvJanela'][K_ADOTADO]['inicio'] for a in linhas]
    print()
    if any(x is None for x in adotados):
        faltam = [a['framework'] for a in linhas if a['cvJanela'][K_ADOTADO]['inicio'] is None]
        print('PAR ADOTADO (k=%d, %.0f%%): NÃO atingido por %s — recalibrar.'
              % (K_ADOTADO, CV_MAX * 100, ', '.join(faltam)))
    else:
        pior = max(adotados)
        print('Par adotado (k=%d, CV < %.0f%%): pior caso %d s.'
              % (K_ADOTADO, CV_MAX * 100, pior))

    print()
    for a in linhas:
        print('%-12s %s' % (a['framework'],
                            ' '.join('%.0f' % v for v in a['serie'])))


if __name__ == '__main__':
    main(sys.argv[1:] or ['results/warmup/*.json'])
