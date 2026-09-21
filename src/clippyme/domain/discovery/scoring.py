from __future__ import annotations

import math
import time
from typing import Optional
from .schemas import PlatformType


def calculate_view_velocity(views: int, published_timestamp: Optional[int], current_timestamp: Optional[int] = None) -> float:
    """Calcula a velocidade de visualizações por hora."""
    if not published_timestamp or views <= 0:
        return 0.0
    
    now = current_timestamp if current_timestamp is not None else int(time.time())
    age_seconds = max(1800, now - published_timestamp)  # Mínimo de 30 minutos
    age_hours = age_seconds / 3600.0
    return round(views / age_hours, 2)


def calculate_engagement_rate(
    platform: PlatformType,
    views: int,
    likes: int,
    comments: int,
    shares: int = 0,
    saves: int = 0,
) -> float:
    """Calcula a taxa de engajamento ponderada de acordo com a plataforma."""
    effective_views = max(views, 100)
    
    # Se o Instagram/plataforma não reportar views, estima a partir das curtidas
    if views <= 0 and likes > 0:
        effective_views = max(100, likes * 8)
    
    if platform == PlatformType.TIKTOK:
        numerator = likes + (2.5 * comments) + (4.0 * shares) + (3.0 * saves)
    elif platform == PlatformType.INSTAGRAM:
        numerator = likes + (3.0 * comments) + (4.5 * shares)
    else:  # YOUTUBE
        numerator = likes + (3.0 * comments)
        
    return round(numerator / effective_views, 4)


def calculate_freshness_decay(published_timestamp: Optional[int], half_life_hours: float = 72.0, current_timestamp: Optional[int] = None) -> float:
    """Calcula o fator de novidade usando decaimento exponencial (meia-vida padrão: 72 horas)."""
    if not published_timestamp:
        return 0.7  # Valor neutro caso a data não seja informada
    
    now = current_timestamp if current_timestamp is not None else int(time.time())
    age_hours = max(0.0, (now - published_timestamp) / 3600.0)
    
    # Constante de decaimento lambda = ln(2) / half_life
    decay_constant = math.log(2) / half_life_hours
    decay = math.exp(-decay_constant * age_hours)
    return max(0.05, min(1.0, decay))


def calculate_virality_score(
    platform: PlatformType,
    views: int,
    likes: int,
    comments: int,
    shares: int = 0,
    saves: int = 0,
    published_timestamp: Optional[int] = None,
    current_timestamp: Optional[int] = None,
) -> float:
    """
    Calcula a pontuação de viralidade (0 a 100).
    
    Combina:
    - Escala de Volume (40%): baseado em log10 de views (1 milhão de views = 1.0)
    - Taxa de Engajamento Ponderada (35%)
    - Velocidade de Visualizações (25%)
    - Modulado pelo Decaimento de Novidade (decaimento após 72h)
    """
    # 1. Escala de Volume (log10)
    if views > 0:
        volume_factor = min(1.0, math.log10(views + 1) / 6.0)
    elif likes > 0:
        volume_factor = min(1.0, math.log10(likes * 10 + 1) / 6.0)
    else:
        volume_factor = 0.0

    # 2. Engajamento
    has_engagement = (likes > 0 or comments > 0 or shares > 0 or saves > 0)
    if has_engagement:
        er = calculate_engagement_rate(platform, views, likes, comments, shares, saves)
        benchmark_er = 0.08  # 8% de benchmark de engajamento saudável
        er_ratio = min(1.5, er / benchmark_er) if benchmark_er > 0 else 0.0
    else:
        er_ratio = 0.0

    # 3. Velocidade
    has_timestamp = published_timestamp is not None and published_timestamp > 0
    if has_timestamp and views > 0:
        velocity = calculate_view_velocity(views, published_timestamp, current_timestamp)
        benchmark_velocity = 500.0  # 500 views/hora
        velocity_ratio = min(1.5, velocity / benchmark_velocity) if benchmark_velocity > 0 else 0.0
    else:
        velocity_ratio = 0.0

    # 4. Decaimento
    decay = calculate_freshness_decay(published_timestamp, 72.0, current_timestamp) if has_timestamp else 1.0

    # 5. Composição com Pesos Normalizados para Métricas Disponíveis
    w_vol = 0.40
    w_eng = 0.35 if has_engagement else 0.0
    w_vel = 0.25 if has_timestamp else 0.0
    total_weight = w_vol + w_eng + w_vel

    if total_weight > 0:
        base_score = (
            (w_vol * volume_factor)
            + (w_eng * (er_ratio / 1.5))
            + (w_vel * (velocity_ratio / 1.5))
        ) / total_weight
    else:
        base_score = 0.0

    time_modulated = base_score * (0.30 + 0.70 * decay)
    score = round(time_modulated * 100.0, 1)
    return max(0.0, min(100.0, score))
