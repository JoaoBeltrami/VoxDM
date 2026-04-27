"""
Schemas Pydantic para requests e responses da API do VoxDM.

Por que existe: define os contratos de entrada/saída para REST e WebSocket,
    garantindo validação automática e documentação OpenAPI gerada pelo FastAPI.
Dependências: pydantic v2
Armadilha: session_id deve estar em kebab-case — pattern ^[a-z0-9-]+$ validado aqui.
    Não aceitar IDs com underscores ou maiúsculas para manter consistência com o schema.

Exemplo:
    config = SessaoConfig(session_id="sess-01", location_id="aldeia-valdrek")
    cmd = ComandoJogador(texto="Eu quero falar com Fael")
    resp = RespostaMestre(texto="Fael franze o cenho...", latencia_ms=820, iteracao=1)
"""

from typing import Any

from pydantic import BaseModel, Field


class SessaoConfig(BaseModel):
    """Parâmetros para iniciar uma nova sessão de jogo."""

    session_id: str = Field(..., pattern=r"^[a-z0-9-]+$", description="ID em kebab-case")
    location_id: str = "aldeia-valdrek"
    location_nome: str = "Aldeia de Valdrek"
    time_of_day: str = "noite"
    weather: str = "frio"
    player_hp: int = Field(default=30, ge=1, le=999)
    player_hp_max: int = Field(default=30, ge=1, le=999)


class SessaoInfo(BaseModel):
    """Estado resumido de uma sessão ativa."""

    session_id: str
    location_id: str
    location_nome: str
    npcs_presentes: list[str]
    iteracoes: int
    criada_em: float


class ComandoJogador(BaseModel):
    """Comando de texto do jogador para um turno de jogo."""

    texto: str = Field(..., min_length=1, max_length=500)


class RespostaMestre(BaseModel):
    """Resposta completa do Mestre com metadados de contexto RAG e latência."""

    texto: str
    chunks_lore: list[str]
    chunks_regras: list[str]
    relacoes_grafo: list[dict[str, Any]]
    secrets_revelados: int
    latencia_ms: int
    iteracao: int


class MensagemWS(BaseModel):
    """Envelope JSON para mensagens no canal WebSocket."""

    tipo: str  # "token" | "fim" | "erro" | "metricas"
    conteudo: str = ""
    latencia_ms: int = 0
    chunks_lore: list[str] = Field(default_factory=list)
    chunks_regras: list[str] = Field(default_factory=list)
    relacoes_grafo: list[dict[str, Any]] = Field(default_factory=list)
    iteracao: int = 0
