from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PlatformType(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"


class SortOrder(str, Enum):
    VIRALITY_SCORE = "virality_score"
    VIEW_COUNT = "view_count"
    RECENT = "recent"
    ENGAGEMENT_RATE = "engagement_rate"


class DiscoveryFilter(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="Palavra-chave, hashtag ou termo de busca")
    platform: PlatformType = Field(default=PlatformType.INSTAGRAM, description="Plataforma de busca")
    limit: int = Field(default=20, ge=1, le=50, description="Quantidade máxima de resultados")
    min_views: Optional[int] = Field(default=None, ge=0, description="Filtro de visualizações mínimas")
    max_age_days: Optional[int] = Field(default=30, ge=1, le=365, description="Idade máxima do post em dias")
    sort_by: SortOrder = Field(default=SortOrder.VIRALITY_SCORE, description="Critério de ordenação")


class DiscoveryItem(BaseModel):
    id: str = Field(..., description="ID único do item na plataforma")
    platform: PlatformType = Field(..., description="Plataforma de origem")
    url: str = Field(..., description="URL direta da postagem/vídeo")
    title: str = Field(default="", description="Título ou legenda da postagem")
    description: str = Field(default="", description="Descrição completa")
    author_name: str = Field(default="", description="Nome do autor/canal")
    author_handle: str = Field(default="", description="Handle/username (@usuario)")
    author_avatar_url: Optional[str] = Field(default=None, description="URL do avatar do autor")
    published_at: Optional[str] = Field(default=None, description="Data de publicação (ISO 8601 ou timestamp)")
    published_timestamp: Optional[int] = Field(default=None, description="Timestamp de publicação em segundos")
    duration_seconds: Optional[float] = Field(default=None, description="Duração do vídeo em segundos")
    thumbnail_url: Optional[str] = Field(default=None, description="URL da miniatura/capa")
    
    # Métricas brutas
    view_count: int = Field(default=0, description="Contagem de visualizações / reproduções")
    like_count: int = Field(default=0, description="Contagem de curtidas")
    comment_count: int = Field(default=0, description="Contagem de comentários")
    share_count: int = Field(default=0, description="Contagem de compartilhamentos")
    save_count: int = Field(default=0, description="Contagem de salvamentos")
    
    # Métricas calculadas
    virality_score: float = Field(default=0.0, description="Pontuação de viralidade calculada (0 a 100)")
    engagement_rate: float = Field(default=0.0, description="Taxa de engajamento calculada")
    view_velocity: float = Field(default=0.0, description="Visualizações por hora")
    
    raw_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadados brutos da plataforma")


class DiscoveryResult(BaseModel):
    query: str
    platform: PlatformType
    total_found: int
    items: List[DiscoveryItem]
    cached: bool = False
    fetched_at: str
