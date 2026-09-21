from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List
from .schemas import DiscoveryFilter, DiscoveryItem, PlatformType


class DiscoveryProvider(ABC):
    """Interface base abstrata para provedores de busca e descoberta de vídeos."""

    @property
    @abstractmethod
    def platform(self) -> PlatformType:
        """Identificador da plataforma associada a este provedor."""
        pass

    @abstractmethod
    async def search(self, filter_params: DiscoveryFilter) -> List[DiscoveryItem]:
        """
        Executa a busca por termo, hashtag ou explorador na plataforma
        e retorna uma lista de DiscoveryItem preenchidos e pontuados.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Verifica a disponibilidade da plataforma e validade das credenciais/cookies."""
        pass
