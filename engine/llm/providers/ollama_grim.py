"""
Provider Ollama-Grim — modelo uncensored como garantia de último recurso.

Por que existe: o OllamaProvider normal usa llama3.1:8b que tem safety training.
    Em cenas de fantasia sombria (massacre, tortura, horror), esse modelo amarelea.
    Este provider aponta para OLLAMA_MODEL_GRIM (ex: dolphin-mistral) que é um
    modelo abliterated/uncensored — sem filtros de conteúdo.
Dependências: OllamaProvider (herança), config (OLLAMA_MODEL_GRIM, GRIMDARK_ATIVO).
Armadilha: só está disponível quando GRIMDARK_ATIVO=True. O modelo PRECISA ser
    puxado manualmente: `ollama pull dolphin-mistral`. Falha silenciosa de
    conexão se o modelo não estiver baixado.

Exemplo:
    # No .env:
    # OLLAMA_MODEL_GRIM=dolphin-mistral
    # GRIMDARK_ATIVO=true
    provider = OllamaGrimProvider()
    assert provider.disponivel  # True quando settings acima configurados
"""

from __future__ import annotations

import structlog

from config import settings
from engine.llm.providers.ollama import OllamaProvider

log = structlog.get_logger(__name__)


class OllamaGrimProvider(OllamaProvider):
    """Provider Ollama uncensored — último recurso pra cenas de ficção sombria.

    Herda toda a lógica de HTTP/streaming do OllamaProvider, só troca o modelo
    e o keep_alive (episódico — descarrega VRAM entre cenas sombrias para
    não competir com Whisper na RTX 2060).
    """

    nome = "ollama-grim"

    def __init__(self) -> None:
        super().__init__()
        # Sobrescreve os campos relevantes do parent
        self._modelo = settings.OLLAMA_MODEL_GRIM
        # keep_alive curto: cenas sombrias são beats dramáticos esporádicos,
        # não turnos consecutivos. 5m libera VRAM para Whisper entre cenas.
        self._keep_alive = "5m"

    @property
    def disponivel(self) -> bool:
        """Só disponível quando GRIMDARK_ATIVO=True e modelo configurado."""
        return bool(settings.GRIMDARK_ATIVO and settings.OLLAMA_MODEL_GRIM)
