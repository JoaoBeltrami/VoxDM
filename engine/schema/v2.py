"""
VoxDM Schema v2 — modelo Pydantic do formato de módulo (Frente B1 do NEXT LEVEL).

Por que existe: o v1.2 é JSON livre, validado só estruturalmente por
    ingestor/parser.py. O v2 é a EVOLUÇÃO declarativa — o formato que outros
    criadores vão escrever — com as peças que faltavam pra um mundo vivo dirigido
    por dados (não por improviso do LLM): grafo de mapa navegável, encounter
    tables, NPCs com appearance/voice/agenda/portrait nativos, secrets com
    gatilho machine-readable, fronts/relógios autorais, loot tables e canon
    protegido. É FORWARD-COMPATÍVEL: um módulo v1.2 valida como v2 (os campos
    novos são opcionais e `extra="allow"` preserva seções existentes), então a
    adoção é incremental.
Dependências: pydantic v2.
Armadilha: NÃO é consumido pelo runtime ainda — é a costura do formato. A
    ingestão (ingestor/) continua lendo v1.2; migrar o pipeline pra ler v2 nativo
    é passo seguinte (B2). Validar aqui só garante que um módulo está bem-formado.

Exemplo:
    from engine.schema.v2 import validar_modulo
    modulo = validar_modulo(dados_json)   # ModuloV2 | ValidationError
    for loc in modulo.locations:
        for con in loc.connections:
            ...  # grafo de mapa navegável
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "2.0"

# Política comum: aceitar campos extras (forward-compat com v1.2 e tolerância a
# campos autorais não modelados) em vez de rejeitar — um módulo não quebra a
# validação por trazer uma chave a mais.
_Config = ConfigDict(extra="allow")


# ── Mundo: locais e grafo de mapa ───────────────────────────────────────────────

class Connection(BaseModel):
    """Aresta navegável entre locais (grafo de mapa)."""

    model_config = _Config
    to: str = Field(description="id do local de destino")
    via: str | None = Field(default=None, description="rota/passagem (ex: 'trilha da garganta')")
    distance: str | None = Field(default=None, description="distância narrativa (ex: 'meio dia a pé')")
    locked: bool = Field(default=False, description="passagem bloqueada por padrão")


class LocationV2(BaseModel):
    model_config = _Config
    id: str
    name: str
    description: str = ""
    connections: list[Connection] = Field(default_factory=list)
    encounter_table: str | None = Field(default=None, description="id de uma EncounterTable ativa aqui")

    @field_validator("connections", mode="before")
    @classmethod
    def _normalizar_connections(cls, v: Any) -> Any:
        """Forward-compat v1.2: connections como list[str] (só ids de destino)
        vira list[Connection(to=id)]. v2 já traz objetos completos."""
        if isinstance(v, list):
            return [{"to": item} if isinstance(item, str) else item for item in v]
        return v


# ── NPCs com presença nativa (alimenta retrato, voz, iniciativa de agenda) ───────

class NpcVoice(BaseModel):
    """Assinatura de voz do NPC (alimenta o marcador [VOZ] / voice_manager)."""

    model_config = _Config
    pitch: str | None = Field(default=None, description="ajuste de tom Edge TTS (ex: '-3Hz')")
    rate: str | None = Field(default=None, description="ajuste de ritmo (ex: '-10%')")
    style: str | None = Field(default=None, description="descrição curta do timbre/entonação")


class NpcV2(BaseModel):
    model_config = _Config
    id: str
    name: str
    role: str | None = None
    personality: str | None = None
    knowledge: list[str] = Field(default_factory=list)
    speech_style: str | None = None
    # Novos no v2 — nativos, não inferidos:
    appearance: str | None = Field(default=None, description="aparência física p/ narração e retrato")
    voice: NpcVoice | None = Field(default=None, description="assinatura de voz TTS")
    agenda: str | None = Field(default=None, description="plano/objetivo de fundo (mundo vivo)")
    portrait_hint: str | None = Field(default=None, description="prompt curto p/ retrato gerado")


# ── Secrets com gatilho machine-readable (já existia no v1.2; formalizado) ───────

class TriggerCondition(BaseModel):
    model_config = _Config
    operator: Literal["AND", "OR"] = "AND"
    conditions: list[dict[str, Any]] = Field(default_factory=list)


class SecretV2(BaseModel):
    model_config = _Config
    id: str
    content: str
    lie_content: str | None = None
    known_by: list[str] = Field(default_factory=list)
    min_trust_level: int = 0
    trigger_condition: TriggerCondition | None = None


# ── Encounter tables ─────────────────────────────────────────────────────────────

class EncounterEntry(BaseModel):
    model_config = _Config
    description: str
    weight: int = Field(default=1, ge=1, description="peso relativo no sorteio")
    enemies: list[str] = Field(default_factory=list, description="srd_index dos monstros (bestiário)")


class EncounterTable(BaseModel):
    model_config = _Config
    id: str
    location: str | None = None
    entries: list[EncounterEntry] = Field(default_factory=list)


# ── Fronts / relógios autorais (mundo vivo dirigido por dados) ───────────────────

class Front(BaseModel):
    """Relógio de ameaça pré-definido pelo autor (ex: 'a horda chega' em 6 passos)."""

    model_config = _Config
    id: str
    name: str
    segments: int = Field(ge=1, description="total de passos do relógio")
    filled: int = Field(default=0, ge=0, description="passos já preenchidos no início")
    advances_on: str | None = Field(default=None, description="condição narrativa que avança o relógio")


# ── Loot tables ──────────────────────────────────────────────────────────────────

class LootEntry(BaseModel):
    model_config = _Config
    item: str
    weight: int = Field(default=1, ge=1)
    gold: str | None = Field(default=None, description="ouro associado (ex: '2d6')")


class LootTable(BaseModel):
    model_config = _Config
    id: str
    entries: list[LootEntry] = Field(default_factory=list)


# ── Canon protegido (mortos continuam mortos; verdades imutáveis) ────────────────

class CanonFact(BaseModel):
    model_config = _Config
    fact: str
    immutable: bool = Field(default=True, description="o Mestre não pode contradizer/reverter")


# ── Raiz ─────────────────────────────────────────────────────────────────────────

class ModuloV2(BaseModel):
    """Módulo VoxDM v2. Forward-compatível com v1.2 (campos novos opcionais)."""

    model_config = _Config

    # Seções existentes do v1.2 ficam soltas (extra="allow") exceto as que o v2
    # formaliza/enriquece. `_meta` (com underscore) entra via alias.
    meta: dict[str, Any] | None = Field(default=None, alias="_meta")
    module: dict[str, Any] | None = None

    locations: list[LocationV2] = Field(default_factory=list)
    npcs: list[NpcV2] = Field(default_factory=list)
    secrets: list[SecretV2] = Field(default_factory=list)

    # Novidades do v2:
    encounter_tables: list[EncounterTable] = Field(default_factory=list)
    fronts: list[Front] = Field(default_factory=list)
    loot_tables: list[LootTable] = Field(default_factory=list)
    canon: list[CanonFact] = Field(default_factory=list)

    def schema_version(self) -> str:
        """Versão declarada em _meta.schema_version, ou o default v2."""
        if self.meta and isinstance(self.meta, dict):
            return str(self.meta.get("schema_version", SCHEMA_VERSION))
        return SCHEMA_VERSION


def validar_modulo(dados: dict[str, Any]) -> ModuloV2:
    """Valida um dict de módulo contra o Schema v2.

    Aceita também módulos v1.2 (forward-compat). Lança pydantic.ValidationError
    com mensagem clara se a estrutura estiver malformada (ex: location sem id,
    secret sem content, encounter weight < 1).
    """
    return ModuloV2.model_validate(dados)
