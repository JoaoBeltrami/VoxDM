"""
Schemas Pydantic para requests e responses da API do VoxDM.

Por que existe: define os contratos de entrada/saída para REST e WebSocket,
    garantindo validação automática e documentação OpenAPI gerada pelo FastAPI.
Dependências: pydantic v2
Armadilha: session_id deve estar em kebab-case — pattern ^[a-z0-9-]+$ validado aqui.
    Não aceitar IDs com underscores ou maiúsculas para manter consistência com o schema.

Exemplo:
    config = SessaoConfig(session_id="sess-01", location_id="tharnvik")
    cmd = ComandoJogador(texto="Eu quero falar com Fael")
    resp = RespostaMestre(texto="Fael franze o cenho...", latencia_ms=820, iteracao=1)
"""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class SessaoConfig(BaseModel):
    """Parâmetros para iniciar uma nova sessão de jogo."""

    session_id: str = Field(..., pattern=r"^[a-z0-9-]+$", description="ID em kebab-case")
    location_id: str = "drevamor"
    location_nome: str = "Drevamor"
    time_of_day: str = "noite"
    weather: str = "frio"
    player_hp: int = Field(default=30, ge=1, le=999)
    player_hp_max: int = Field(default=30, ge=1, le=999)
    # Personagem D&D 5e — opcionais na criação, mestre pergunta se ausentes
    player_name: str = ""
    player_race: str = ""
    player_class: str = ""
    player_background: str = ""
    player_level: int = Field(default=3, ge=1, le=20)  # personagens começam no nível 3
    # Continuação de sessão anterior — pré-popula trust_levels e quest_stages
    session_anterior_id: str | None = None
    # Voz Edge TTS escolhida pelo jogador nas Opções
    tts_voice: str = "pt-BR-FranciscaNeural"
    # Atributos D&D 5e (Standard Array padrão)
    str_score: int = Field(default=10, ge=3, le=20)
    dex_score: int = Field(default=10, ge=3, le=20)
    con_score: int = Field(default=10, ge=3, le=20)
    int_score: int = Field(default=10, ge=3, le=20)
    wis_score: int = Field(default=10, ge=3, le=20)
    cha_score: int = Field(default=10, ge=3, le=20)
    # Proficiências derivadas de classe + background
    skill_profs: list[str] = Field(default_factory=list)
    save_profs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validar_session_anterior(self) -> "SessaoConfig":
        if self.session_anterior_id and not __import__("re").fullmatch(
            r"[a-z0-9-]+", self.session_anterior_id
        ):
            raise ValueError("session_anterior_id deve estar em kebab-case")
        return self


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


class SessaoListaItem(BaseModel):
    """Item de uma sessão disponível para carregar."""

    session_id: str
    timestamp: float
    location_final: str
    npcs_mencionados: list[str]
    resumo_curto: str  # Primeiros 200 chars do resumo narrativo


class TranscricaoResponse(BaseModel):
    """Resultado da transcrição de áudio via Faster-Whisper."""

    texto: str
    idioma: str


class MensagemWS(BaseModel):
    """Envelope JSON para mensagens no canal WebSocket."""

    tipo: str  # "token" | "fim" | "erro" | "metricas" | "audio_chunk"
    conteudo: str = ""
    conteudo_b64: str = ""   # bytes MP3 em base64 — preenchido em audio_chunk
    sequencia: int = 0       # índice sequencial do chunk de áudio
    latencia_ms: int = 0
    chunks_lore: list[str] = Field(default_factory=list)
    chunks_regras: list[str] = Field(default_factory=list)
    relacoes_grafo: list[dict[str, Any]] = Field(default_factory=list)
    iteracao: int = 0
    # Estado da sessão enviado no "fim" para sincronizar o frontend
    quest_stages: dict[str, str] = Field(default_factory=dict)
    active_quest_hooks: list[str] = Field(default_factory=list)
    inventory: list[str] = Field(default_factory=list)
    location_nome: str = ""
    time_of_day: str = ""
    npcs_trust: dict[str, int] = Field(default_factory=dict)  # npc_id → trust (0-3)
