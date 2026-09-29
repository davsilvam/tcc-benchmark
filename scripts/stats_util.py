"""Estatística mínima compartilhada pelos analisadores, sem dependências externas.

Intervalos de confiança pela distribuição t de Student, apropriada a amostras com menos de
30 observações (Georges, Buytaert e Eeckhout, 2007). Os quantis t(0,975; gl) vêm de tabela;
para graus de liberdade não inteiros — os da aproximação de Welch-Satterthwaite na diferença
entre médias —, interpola-se linearmente entre os inteiros vizinhos.
"""
import math

# t(0,975; gl) para gl = 1..30
_T975 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
         2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
         2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def t975(gl):
    if gl is None or gl < 1:
        return float('nan')
    if gl >= 30:
        # 30 -> 2,042; infinito -> 1,960
        return 1.960 + (2.042 - 1.960) * 30.0 / gl
    baixo = int(math.floor(gl))
    alto = min(baixo + 1, 30)
    if baixo == alto:
        return _T975[baixo - 1]
    f = gl - baixo
    return _T975[baixo - 1] * (1 - f) + _T975[alto - 1] * f


def resumo(valores):
    """Média, desvio-padrão amostral, CV e meia-largura do IC 95%."""
    v = [x for x in valores if x is not None and not math.isnan(x)]
    n = len(v)
    if n == 0:
        return {'n': 0, 'media': float('nan'), 'dp': float('nan'), 'cv': float('nan'),
                'ic': float('nan')}
    media = sum(v) / n
    if n < 2:
        return {'n': n, 'media': media, 'dp': float('nan'), 'cv': float('nan'),
                'ic': float('nan')}
    dp = math.sqrt(sum((x - media) ** 2 for x in v) / (n - 1))
    return {
        'n': n,
        'media': media,
        'dp': dp,
        'cv': dp / media if media else float('nan'),
        'ic': t975(n - 1) * dp / math.sqrt(n),
    }


def diferenca(a, b):
    """IC 95% da diferença entre médias (a - b), por Welch. Retorna (dif, meia-largura)."""
    ra, rb = resumo(a), resumo(b)
    if ra['n'] < 2 or rb['n'] < 2:
        return ra['media'] - rb['media'], float('nan')
    va, vb = ra['dp'] ** 2 / ra['n'], rb['dp'] ** 2 / rb['n']
    se = math.sqrt(va + vb)
    if se == 0:
        return ra['media'] - rb['media'], 0.0
    gl = (va + vb) ** 2 / (va ** 2 / (ra['n'] - 1) + vb ** 2 / (rb['n'] - 1))
    return ra['media'] - rb['media'], t975(gl) * se


def meia_largura_projetada(cv, n):
    """Meia-largura relativa do IC 95% esperada com n repetições e um dado CV."""
    return t975(n - 1) * cv / math.sqrt(n)
