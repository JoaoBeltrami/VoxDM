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

import re
from typing import Any

from pydantic import BaseModel, Field, model_validator

# Pattern de session_id (kebab-case) reutilizado nos validators.
_SESSION_ID_RE = re.compile(r"^[a-z0-9-]+$")


class SessaoConfig(BaseModel):
    """Parâmetros para iniciar uma nova sessão de jogo."""

    # session_id é gerado pelo SERVIDOR (UUID v4) em POST /session/start.
    # Campo aceito por compat (testes legados podem passar), mas é IGNORADO
    # na criação — o backend sempre gera novo. Frontend nunca envia em produção.
    session_id: str = Field(default="", description="Ignorado em /start — servidor gera UUID v4")
    # Campos de cena e personagem: limites de tamanho previnem abuso de recurso
    # por cliente autenticado (estouro de tokens no prompt, inflação do JSON
    # persistido em SQLite, e da URL de imagem montada com location_id).
    location_id: str = Field(default="drevamor", max_length=120)
    location_nome: str = Field(default="Drevamor", max_length=120)
    time_of_day: str = Field(default="noite", max_length=40)
    weather: str = Field(default="frio", max_length=40)
    player_hp: int = Field(default=30, ge=1, le=999)
    player_hp_max: int = Field(default=30, ge=1, le=999)
    # Personagem D&D 5e — opcionais na criação, mestre pergunta se ausentes
    player_name: str = Field(default="", max_length=80)
    player_race: str = Field(default="", max_length=60)
    player_class: str = Field(default="", max_length=60)
    player_background: str = Field(default="", max_length=80)
    # Descrição livre do personagem (opcional, max 600 chars) — passado por
    # texto pelo jogador na criação. Quando preenchido, o LLM usa pra moldar
    # a abertura: traços, segredos, motivações, aparência. NÃO substitui
    # classe/raça — é tempero narrativo. Limite previne abuso e estouro de tokens.
    player_description: str = Field(default="", max_length=600)
    player_level: int = Field(default=3, ge=1, le=20)  # personagens começam no nível 3
    # Continuação de sessão anterior — pré-popula trust_levels e quest_stages
    session_anterior_id: str | None = None
    # Voz Edge TTS escolhida pelo jogador nas Opções — restrito às vozes existentes
    tts_voice: str = Field(
        default="pt-BR-FranciscaNeural",
        pattern=(
            r"^("
            r"pt-BR-(FranciscaNeural|AntonioNeural|ThalitaMultilingualNeural)"
            r"|en-US-(GuyNeural|EricNeural|AriaNeural|JennyNeural)"
            r")$"
        ),
    )
    # Perfil de personalidade do Mestre — overlay aplicado sobre master_system.md
    # Valores: "rigoroso" | "equilibrado" | "tranquilo" | "rule_of_cool" | "sombrio"
    # "sombrio" + GRIMDARK_ATIVO=True → fragmento grimdark.md + cascata NARRATIVE_GRIM
    dm_profile: str = Field(default="equilibrado", pattern=r"^(rigoroso|equilibrado|tranquilo|rule_of_cool|sombrio)$")
    # Visibilidade das rolagens do mestre (Fase 5.7):
    # "open"        → animação + número (transparência total)
    # "result_only" → só o número sem animação (padrão)
    # "narrated"    → mestre narra sem marker, sem número visível
    roll_visibility: str = Field(default="result_only", pattern=r"^(open|result_only|narrated)$")
    # Política de morte (Pilar Perigo, 10/06):
    # "narrativo" → derrota tem custo real (captura, perda, cicatriz) mas nunca
    #               apaga o personagem; "mortal" → death saves e morte de verdade.
    death_policy: str = Field(default="narrativo", pattern=r"^(narrativo|mortal)$")
    # Modo episódio (Ritual de mesa, 10/06): mestre propõe fecho pós-clímax
    # com cliffhanger + epílogo. Default off = sessão livre.
    modo_episodio: bool = False
    # Session Zero por voz (Ritual P3, 11/06): a sessão abre como entrevista
    # de criação de personagem — o mestre pergunta, o jogador responde por voz,
    # e o marker [FICHA] fecha a criação (atributos/HP gerados pela engine).
    session_zero: bool = False
    # Atributos D&D 5e (Standard Array padrão)
    str_score: int = Field(default=10, ge=3, le=20)
    dex_score: int = Field(default=10, ge=3, le=20)
    con_score: int = Field(default=10, ge=3, le=20)
    int_score: int = Field(default=10, ge=3, le=20)
    wis_score: int = Field(default=10, ge=3, le=20)
    cha_score: int = Field(default=10, ge=3, le=20)
    # Subclasse D&D 5e — determina features especiais (Action Surge, Rage, Sneak Attack, etc.)
    player_subclass: str = Field(default="", max_length=80, description="Ex: 'Campeão', 'Ladrão', 'Escola da Evocação'")
    # Proficiências derivadas de classe + background — limites de itens previnem
    # listas gigantes que inflariam prompt e o blob persistido.
    skill_profs: list[str] = Field(default_factory=list, max_length=30)
    save_profs: list[str] = Field(default_factory=list, max_length=10)
    # Magias selecionadas na criação — lista de nomes PT-BR (truques + magias).
    # Usadas para popular SessaoAtiva.spells_conhecidas e injetar no prompt.
    player_spells: list[str] = Field(default_factory=list, max_length=80)

    @model_validator(mode="after")
    def validar_session_anterior(self) -> "SessaoConfig":
        if self.session_anterior_id and not _SESSION_ID_RE.fullmatch(self.session_anterior_id):
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
    # Identidade restaurada de sessão anterior — preenchido só quando
    # session_anterior_id foi fornecido E CharacterState.personagem_config existe.
    # O frontend usa para pular o CharacterForm e restaurar os dados do personagem.
    personagem_restaurado: dict | None = None


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


class CharacterStateSchema(BaseModel):
    """Estado persistível do personagem — usado em GET/PUT /session/{id}/character."""

    spell_slots: dict[int, dict[str, int]] = Field(default_factory=dict)
    hit_dice_current: int = 3
    hit_dice_max: int = 3
    hit_dice_type: int = 8
    death_saves_successes: int = Field(default=0, ge=0, le=3)
    death_saves_failures: int = Field(default=0, ge=0, le=3)
    death_saves_stable: bool = False
    gold: int = Field(default=0, ge=0)
    xp: int = Field(default=0, ge=0)
    inspiration: bool = False


class TokenIniciativaPayload(BaseModel):
    """Token da barra de iniciativa enviado ao frontend.

    Espelha engine.llm.types.TokenIniciativa — a engine é authority de turno.
    """
    id: str
    nome: str
    tipo: str  # "jogador" | "inimigo"
    iniciativa: int
    turno_atual: bool = False
    morto: bool = False
    hp_atual: int = 0
    hp_max: int = 0


class MensagemWS(BaseModel):
    """Envelope JSON para mensagens no canal WebSocket."""

    tipo: str  # "token" | "fim" | "erro" | "metricas" | "audio_chunk" | "recap" | "lampejo" | "dado_rolado" | "scene_image" | "cascade" | "relacao"
    conteudo: str = ""
    # Autoridade social (02/07): toast de mudança de relação decidida pela
    # engine — {"npc_id", "nome", "direcao" ("down"|"up"), "motivo"}.
    # Preenchido só em tipo="relacao"; sem números (decisão: discreto).
    relacao: dict[str, Any] | None = None
    conteudo_b64: str = ""   # bytes MP3 em base64 — preenchido em audio_chunk
    sequencia: int = 0       # índice sequencial do chunk de áudio
    # CRIT-2: audio_chunk de thinking ("Hmm...") manda narrativo=false para que
    # o useSyncTextoVoz no frontend NÃO use sua duração para calibrar o karaokê
    # reverso. Default true preserva comportamento de TTS real.
    narrativo: bool = True
    latencia_ms: int = 0
    chunks_lore: list[str] = Field(default_factory=list)
    chunks_regras: list[str] = Field(default_factory=list)
    relacoes_grafo: list[dict[str, Any]] = Field(default_factory=list)
    iteracao: int = 0
    # Estado da sessão enviado no "fim" para sincronizar o frontend
    quest_stages: dict[str, str] = Field(default_factory=dict)
    active_quest_hooks: list[str] = Field(default_factory=list)
    inventory: list[str] = Field(default_factory=list)
    # Condições ativas confirmadas pelo jogador (via sync_conditions) — persistidas
    # no backend e reenviadas no "fim" para que a CharacterSheet sobreviva a reloads.
    conditions: list[str] = Field(default_factory=list)
    location_nome: str = ""
    time_of_day: str = ""
    npcs_trust: dict[str, int] = Field(default_factory=dict)  # npc_id → trust (0-3)
    # CANON-MORTOS (12/07): presentes marcados como mortos no registro canônico —
    # o frontend mostra o retrato em grayscale (corpo na cena, não some).
    npcs_mortos: list[str] = Field(default_factory=list)
    # Mecânicas RPG — enviadas no "fim" para manter frontend sincronizado
    spell_slots: dict[int, dict[str, int]] = Field(default_factory=dict)
    hit_dice_current: int = 0
    # HP atual e máximo do jogador — enviados para manter CharacterSheet em sync
    # (ex: após level up o hp_max aumenta no backend mas o frontend não saberia).
    # None = não enviar (mensagens que não são "fim")
    player_hp: int | None = None
    player_hp_max: int | None = None
    # Bug R5-4: player_level ausente do "fim" — frontend não conseguia sincronizar
    # o nível em tempo real via turns normais (só via mensagem "level_up" separada).
    # Adicionado aqui para que o CharacterSheet sempre mostre o nível correto.
    player_level: int = 3
    gold: int = 0
    xp: int = 0
    inspiration: bool = False
    death_saves_successes: int = 0
    death_saves_failures: int = 0
    death_saves_stable: bool = False
    # Session Zero (P3): ficha criada por conversa — enviada em tipo="ficha_criada"
    ficha: dict | None = None
    # Pilar Perigo (10/06) — cicatrizes permanentes do personagem (ficha)
    cicatrizes: list[str] = Field(default_factory=list)
    # Mundo Vivo (10/06) — relógios de ameaça: id → {nome, atual, max}
    relogios: dict[str, dict] = Field(default_factory=dict)
    # Imersão P4 — crônica: timeline de eventos-chave da sessão (cap 40)
    cronica: list[str] = Field(default_factory=list)
    # Diretor de Arco (20/07) — {fase, ending_id, ending_nome, espinha:{filled,
    # segmentos,...}}. A engine sabe terminar a história; o HUD precisa mostrar.
    arco: dict = Field(default_factory=dict)
    # Estado de combate — enviado no "fim" para sincronizar CombatTracker
    em_combate: bool = False
    # inimigo_id → {nome, estado, hp_rel, ca, hp_max, hp_atual, ...} — espelha
    # working_mem.inimigos_combate. Valores MISTOS: nome/estado/hp_rel são str,
    # mas ca/hp_max/hp_atual vêm INT do bestiário (aplicar_stats_inimigo). Tipar
    # como `str` quebrava a validação do payload `fim` quando o bestiário achava
    # uma ficha real → ValidationError → WS fechava → loop infinito de reconexão
    # (playtest 27/06, inimigo "capuz"=cultist com ca=12/hp=9). `Any` aceita o mix.
    inimigos_combate: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # Rodada real de combate (incrementada por avancar_rodada()) — NÃO é o turno da sessão
    rodada_combate: int = 0
    # Rodada esperada pelo backend no momento do "fim" — permite que o frontend detecte
    # initiative drift. Se diferir do valor local antes do update, um turno se perdeu.
    rodada_esperada: int = 0
    # Últimas consequências narrativas — surfaced no frontend fora de combate
    log_consequencias: list[str] = Field(default_factory=list)
    # Barra de iniciativa — vazia fora de combate. Authority de turno = engine.
    iniciativa_ordem: list[TokenIniciativaPayload] = Field(default_factory=list)
    # Quests que avançaram neste turno — notificação ao jogador
    # Cada entrada: {quest_id, stage_id, recompensas: ["+300 XP", "Obteve: X", ...]}
    quest_avancos: list[dict[str, Any]] = Field(default_factory=list)
    # DM Feat 1: Fios Soltos — threads narrativas abertas para exibição no frontend
    # Atualizado no "fim" sempre que a lista muda. Máx 5 fios simultâneos.
    fios_soltos: list[str] = Field(default_factory=list)
    # PLAY5-QUEST: missões improvisadas pelo Mestre (fora do catálogo do módulo),
    # capturadas pelo extractor de quest. Cada item: {id, titulo, objetivo, status}.
    # Alimenta o quest log do frontend (Palco). Cap 6.
    quests_improvisadas: list[dict[str, Any]] = Field(default_factory=list)
    # Feature 3: Consequências visíveis — efeitos duradouros no mundo emitidos via
    # [CONSEQUÊNCIA: ...]. Lista circular máx 5 (working_mem.log_consequencias).
    consequencias: list[str] = Field(default_factory=list)
    # Class features — enviadas no "fim" para sincronizar os chips na ficha.
    # Mapa feature_id → {nome, disponivel, usos_max, usos_atual, restaura}.
    class_features: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # LEVELUP-SEM-ESCOLHA-1: Incrementos de Atributo que o jogador DEVE. Cada
    # item vem de `progression.escolhas_do_nivel` + o campo `nivel`. O frontend
    # abre o picker por este campo; ele persiste no SQLite, então sobrevive a
    # fechar o browser antes de escolher.
    asi_pendente: list[dict[str, Any]] = Field(default_factory=list)
    # Progressão: payload do tipo="level_up" carrega o resumo do level up
    # ({nivel_antigo, nivel_novo, hp_ganho, hp_max_novo, slots_novos, features_novas}).
    level_up: dict[str, Any] | None = None
    # Combate tático: posições relativas dos inimigos em pés (Feature posicionamento).
    # Mapa npc_id → {distancia_ft: int, cobertura: bool}. Vazio fora de combate.
    posicoes_combate: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # Movimento restante do jogador na rodada atual (em pés).
    movimento_restante_ft: int = 30
    # Movimento total por rodada (speed da raça em pés).
    movimento_total_ft: int = 30
    # Feature economia: true quando o jogador está em loja/mercado/taverna-vendedor.
    # LLM sinaliza com [MERCADO] / [FIM_MERCADO]. Frontend habilita UI de venda.
    em_mercado: bool = False
    # Feature companions/party — aliados ativos com HP/CA/atq/dano.
    # Estrutura: id → {nome, tipo, hp, hp_max, ca, atq, dano}.
    companions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # CHECK-JOGADOR-ZERO (playtest 26/07): perícia que o JOGADOR pediu pra testar,
    # detectada pela engine no texto dele. Vazio quando não há pedido aberto.
    #
    # Existe porque a UI de rolagem era função PURA da prosa do Mestre (regex sobre
    # a última fala dele), então "quero rolar Percepção" não abria nada — não havia
    # estado no backend representando "o jogador pediu". O frontend deve preferir
    # este campo ao regex: ele é determinístico e vem da mesma classificação que
    # calcula o bônus.
    check_pedido: str = ""
    # Tempo até o 1º audio_chunk sair (ms). 0 = nenhum áudio no turno. Exposto
    # aqui (e não só na telemetria) pra que benchmark/probe_check.py possa medir
    # o custo real da voz sem depender de dashboard — no playtest 26/07 o TTS era
    # 60%% do turno e ninguém tinha olhado porque não havia número pra olhar.
    primeiro_audio_ms: int = 0
    # DANO-SEM-CAUSA-1: causas das mudanças de HP do turno. Cada item:
    # {tipo: "dano"|"cura", valor, motivo, hp, hp_max}. O motivo do `[DANO]`
    # era descartado com o marcador e o jogador só via o HP cair.
    eventos_vitais: list[dict[str, Any]] = Field(default_factory=list)
    # Dado rolado pelo mestre — enviado como tipo="dado_rolado" quando roll_visibility
    # for "open" ou "result_only". Frontend exibe animação (open) ou só o número (result_only).
    dado_tipo: str = ""       # "d4", "d6", "d8", "d10", "d12", "d20", "d100"
    dado_resultado: int = 0   # valor do dado (1-max)
    # Nível de tensão narrativa atual (0–10) — calculado por pacing_nivel em WorkingMemory.
    # Frontend usa para ajustar o volume/intensidade da trilha ambiente em tempo real.
    pacing_nivel: float = 0.0
