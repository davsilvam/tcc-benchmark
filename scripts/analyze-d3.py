"""Evidência direta do critério de aceite D.3, sobre todas as sessões medidas.

    python scripts/analyze-d3.py

Este script existe porque a conclusão de D.3 deixou de se apoiar em critério de banda. As
três definições de entrada em regime do analyze-warmup.py seguem sendo reportadas, mas
nenhuma delas se mostrou estável entre sessões neste aparato: a de coeficiente de variação
deu 90, 200, 550 e 370 s nas quatro sessões; a de ±10% sobre a média deu 50, 130, "não
entrou" e 110 s; a de mediana com persistência deu 80, 70, 220 e 40 s, e a versão dela com
piso absoluto passa no valor mas atribui ao Spring Boot uma entrada que não descreve
estabilização (seção 16.6 de docs/versoes-e-configuracao.md).

O que se reporta aqui são as quatro grandezas que NÃO dependem de banda, nem de supor que os
últimos 30% da série representem o estado estacionário:

  erro                 taxa de erro da execução. D.3 exige nula.
  1º / corpo           latência do primeiro intervalo sobre a mediana do CORPO. Mede o
                       tamanho do transiente de partida.
  acima de 1,5x        quantos intervalos, do 2º em diante, passam de 1,5x a mediana do
                       corpo. Mede se há transiente DEPOIS do primeiro intervalo.
  1ª janela / resto    mediana de [150, 210) s sobre a mediana de [210, 450) s. É o primeiro
                       minuto da janela de medição contra o resto dela: se o aquecimento de
                       150 s bastou, a razão fica em torno de 1.

DEFINIÇÃO DE CORPO, e uma divergência que ela resolve. Corpo são os intervalos de índice 1 a
41 inclusive — isto é, de 10 s a 410 s —, excluídos o primeiro intervalo, que é o transiente
que se quer medir, e os últimos 30% da série, que as seções 16.3, 16.5 e 16.6 mostraram
sujeitos a rajada tardia, pico isolado e elevação da cauda sobre o corpo. Tomar o corpo como
TODOS os intervalos do 2º ao último, como se fez num relato preliminar, inclui essa cauda
contaminada na referência e desloca as razões: o máximo de 1º/corpo cai de 307x para 303x e o
mínimo sobe de 1,1x para 1,0x. A definição adotada é a de 1 a 41, por não depender do trecho
que se sabe contaminado.
"""
import glob
import io
import json
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Sessões em ordem cronológica, com a data em que foram medidas.
SESSOES = (
    ('results/warmup-aberto', '30/09'),
    ('results/warmup-protocolo-v3', '19/10'),
    ('results/warmup-d3-serie2', '21/10 a'),
    ('results/warmup-d3-serie3', '21/10 b'),
)

CORPO_DE, CORPO_ATE = 1, 41          # inclusive, em índices de intervalo
LIMIAR_TRANSIENTE = 1.5              # multiplo da mediana do corpo
JANELA_1 = (150, 210)                # primeiro minuto da janela de medicao, em s
JANELA_2 = (210, 450)                # o resto da janela de medicao, em s


def mediana(valores):
    v = sorted(valores)
    n = len(v)
    if not n:
        return 0.0
    meio = n // 2
    return v[meio] if n % 2 else (v[meio - 1] + v[meio]) / 2.0


def mediana_entre(serie, de, ate):
    """Mediana dos intervalos cujo instante inicial esta em [de, ate)."""
    vs = [b['latencyAvgMs'] for b in serie if de <= b['fromSeconds'] < ate]
    return mediana(vs) if vs else None


def analisar(caminho):
    d = json.load(io.open(caminho, encoding='utf-8'))
    serie = d.get('series') or []
    if not serie:
        return None
    lat = [b['latencyAvgMs'] for b in serie]
    corpo = lat[CORPO_DE:CORPO_ATE + 1]
    if not corpo:
        return None
    med = mediana(corpo)
    acima = [i for i, v in enumerate(lat[1:], start=1) if v > LIMIAR_TRANSIENTE * med]
    j1 = mediana_entre(serie, *JANELA_1)
    j2 = mediana_entre(serie, *JANELA_2)
    return {
        'framework': os.path.basename(caminho).replace('.json', ''),
        'erro': d.get('errorRate', 0) or 0,
        'primeiro': lat[0],
        'medianaCorpo': med,
        'razaoPrimeiro': lat[0] / med if med else None,
        'acima': acima,
        'razaoJanelas': (j1 / j2) if (j1 and j2) else None,
        'intervalos': len(lat),
    }


def main():
    print('Evidência direta de D.3 — grandezas independentes de critério de banda.')
    print('Corpo = mediana dos intervalos %d a %d (de %d s a %d s).'
          % (CORPO_DE, CORPO_ATE, CORPO_DE * 10, CORPO_ATE * 10))
    print('1ª janela / resto = mediana[%d, %d) / mediana[%d, %d) s.'
          % (JANELA_1[0], JANELA_1[1], JANELA_2[0], JANELA_2[1]))
    print()
    cab = ('%-10s %-11s %9s %10s %12s %14s %9s'
           % ('sessão', 'framework', 'erro', '1º (ms)', '1º / corpo', 'acima de 1,5x',
              '1ª/resto'))
    print(cab)
    print('-' * len(cab))

    todas = []
    for pasta, data in SESSOES:
        arquivos = sorted(glob.glob(os.path.join(pasta, '*.json')))
        if not arquivos:
            print('%-10s (sem séries em %s)' % (data, pasta))
            continue
        for caminho in arquivos:
            a = analisar(caminho)
            if not a:
                continue
            a['sessao'] = data
            a['pasta'] = pasta
            todas.append(a)
            print('%-10s %-11s %8.4f%% %10.1f %11.1fx %14d %8.3f'
                  % (data, a['framework'], a['erro'] * 100, a['primeiro'],
                     a['razaoPrimeiro'], len(a['acima']),
                     a['razaoJanelas'] if a['razaoJanelas'] else float('nan')))

    if not todas:
        print('nenhuma série encontrada')
        return

    print()
    print('=== agregado sobre %d execuções, em %d sessões ==='
          % (len(todas), len({a['sessao'] for a in todas})))
    com_erro = [a for a in todas if a['erro'] > 0]
    print('taxa de erro nula: %s'
          % ('SIM, nas %d execuções' % len(todas) if not com_erro
             else 'NÃO — %s' % ', '.join('%s/%s' % (a['sessao'], a['framework'])
                                         for a in com_erro)))

    por_fw = {}
    for a in todas:
        por_fw.setdefault(a['framework'], []).append(a)
    print()
    print('%-11s %18s %16s %16s' % ('framework', '1º / corpo', 'acima de 1,5x',
                                    '1ª janela / resto'))
    for fw in sorted(por_fw):
        rs = [a['razaoPrimeiro'] for a in por_fw[fw]]
        ac = [len(a['acima']) for a in por_fw[fw]]
        js = [a['razaoJanelas'] for a in por_fw[fw] if a['razaoJanelas']]
        print('%-11s %8.1fx a %5.1fx %7d a %6d %7.3f a %6.3f'
              % (fw, min(rs), max(rs), min(ac), max(ac), min(js), max(js)))

    rs = [a['razaoPrimeiro'] for a in todas]
    ac = [len(a['acima']) for a in todas]
    js = [a['razaoJanelas'] for a in todas if a['razaoJanelas']]
    print()
    print('1º intervalo sobre a mediana do corpo: de %.1fx a %.1fx' % (min(rs), max(rs)))
    print('intervalos acima de 1,5x o corpo, do 2º em diante: de %d a %d por execução'
          % (min(ac), max(ac)))
    print('1ª janela de medição sobre o resto dela: de %.3f a %.3f' % (min(js), max(js)))
    print()
    print('D.3 é sustentado por: taxa de erro nula e transiente confinado ao primeiro')
    print('intervalo de 10 s, contra 150 s de aquecimento adotados.')


if __name__ == '__main__':
    main()
