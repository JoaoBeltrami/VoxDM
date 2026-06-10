"""
Testes de segurança para os prompts do mestre.

Garantem que master_system.md e dice.md carregam corretamente e que
prompt_builder.py não quebra em cenários de arquivo ausente ou corrompido.
"""

import os

os.environ.setdefault("GROQ_API_KEY",    "test-key")
os.environ.setdefault("QDRANT_URL",      "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY",  "test")
os.environ.setdefault("NEO4J_URI",       "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER",      "neo4j")
os.environ.setdefault("NEO4J_PASSWORD",  "test")


import pytest

from engine.llm.prompt_builder import (
    _COMBAT_PATH,
    _DICE_PATH,
    _MASTER_SYSTEM_PATH,
    _PROMPT_MIN_CHARS,
    _RE_COMBATE,
    _RE_ROLAGEM,
    _SAVES_PATH,
    ContextoMontado,
    _carregar_combat,
    _carregar_dice,
    _carregar_master_system,
    _carregar_saves,
    invalidar_cache,
    montar_mensagens,
    validar_master_system,
)
from engine.memory.working_memory import WorkingMemory

# ── Fixtures ────────────────────────────────────────────────────────────────

def _contexto_minimo(transcricao: str = "Eu olho ao redor") -> ContextoMontado:
    """Cria um ContextoMontado mínimo para testes."""
    wm = WorkingMemory.nova_sessao(
        location_id="tharnvik",
        location_nome="Tharnvik",
        session_id="test-session",
    )
    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual=transcricao,
    )


# ── Testes: arquivos existem e têm conteúdo mínimo ────────────────────────

def test_master_system_existe():
    assert _MASTER_SYSTEM_PATH.exists(), "master_system.md não encontrado"


def test_master_system_tem_conteudo_minimo():
    conteudo = _MASTER_SYSTEM_PATH.read_text(encoding="utf-8")
    assert len(conteudo) >= _PROMPT_MIN_CHARS


def test_master_system_menciona_voz():
    conteudo = _MASTER_SYSTEM_PATH.read_text(encoding="utf-8")
    assert "voz" in conteudo.lower() or "falada" in conteudo.lower()


def test_master_system_menciona_rolagem():
    conteudo = _MASTER_SYSTEM_PATH.read_text(encoding="utf-8")
    assert "[Rolagem:" in conteudo, "master_system.md deve referenciar o formato [Rolagem:]"


def test_dice_md_existe():
    assert _DICE_PATH.exists(), "dice.md não encontrado"


def test_dice_md_tem_conteudo_minimo():
    conteudo = _DICE_PATH.read_text(encoding="utf-8")
    assert len(conteudo) >= _PROMPT_MIN_CHARS


def test_dice_md_menciona_d20():
    conteudo = _DICE_PATH.read_text(encoding="utf-8")
    assert "d20" in conteudo


def test_dice_md_menciona_critico():
    conteudo = _DICE_PATH.read_text(encoding="utf-8")
    assert "20" in conteudo and ("crítico" in conteudo.lower() or "critico" in conteudo.lower())


def test_dice_md_proibe_expor_numero():
    conteudo = _DICE_PATH.read_text(encoding="utf-8")
    assert "nunca" in conteudo.lower()


# ── Testes: validar_master_system ─────────────────────────────────────────

def test_validar_master_system_ok():
    ok, msg = validar_master_system()
    assert ok, f"validar_master_system retornou erro: {msg}"
    assert msg == "ok"


def test_validar_master_system_ausente(tmp_path, monkeypatch):
    ausente = tmp_path / "inexistente.md"
    monkeypatch.setattr("engine.llm.prompt_builder._MASTER_SYSTEM_PATH", ausente)
    ok, msg = validar_master_system()
    assert not ok
    assert "ausente" in msg.lower() or "inexistente" in msg.lower() or "Arquivo" in msg


def test_validar_master_system_muito_curto(tmp_path, monkeypatch):
    curto = tmp_path / "curto.md"
    curto.write_text("curto", encoding="utf-8")
    monkeypatch.setattr("engine.llm.prompt_builder._MASTER_SYSTEM_PATH", curto)
    ok, msg = validar_master_system()
    assert not ok
    assert "curto" in msg.lower()


# ── Testes: regex de detecção de rolagem ──────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [
    ("[Rolagem: d20 = 17]", True),
    ("[Rolagem: d6 = 3]", True),
    ("[Rolagem: d100 = 45]", True),
    ("[Rolagem: d20 = 1 — FALHA CRÍTICA!]", True),   # formato com sufixo
    ("[Rolagem: D20 = 17]", True),                    # case insensitive
    ("Eu ataco com minha espada", False),
    ("", False),
    ("[Rolagem:]", False),                             # sem valor
    ("[Rolagem: d20]", False),                         # sem = Y
])
def test_regex_rolagem(texto: str, esperado: bool):
    assert bool(_RE_ROLAGEM.search(texto)) == esperado


# ── Testes: carregamento com cache ────────────────────────────────────────

def test_carregar_master_system_retorna_string():
    invalidar_cache()
    conteudo = _carregar_master_system()
    assert isinstance(conteudo, str)
    assert len(conteudo) > 0


def test_carregar_master_system_usa_cache():
    invalidar_cache()
    primeira = _carregar_master_system()
    segunda = _carregar_master_system()
    assert primeira is segunda   # mesmo objeto — cache hit


def test_carregar_master_system_fallback_quando_ausente(tmp_path, monkeypatch):
    ausente = tmp_path / "inexistente.md"
    monkeypatch.setattr("engine.llm.prompt_builder._MASTER_SYSTEM_PATH", ausente)
    invalidar_cache()
    conteudo = _carregar_master_system()
    assert "VoxDM" in conteudo   # fallback sempre menciona VoxDM


def test_carregar_dice_retorna_string():
    invalidar_cache()
    conteudo = _carregar_dice()
    assert conteudo is not None
    assert len(conteudo) > 0


def test_invalidar_cache_reseta_ambos():
    """invalidar_cache() limpa o dict de caches — próxima chamada relê do disco."""
    _carregar_master_system()
    _carregar_dice()
    import engine.llm.prompt_builder as pb
    assert len(pb._cache_prompts) >= 1  # pelo menos um path foi cacheado
    invalidar_cache()
    assert pb._cache_prompts == {}


# ── Testes: montar_mensagens com rolagem ─────────────────────────────────

def test_montar_mensagens_sem_rolagem_nao_injeta_dice():
    invalidar_cache()
    contexto = _contexto_minimo("Eu olho ao redor")
    mensagens = montar_mensagens(contexto)
    system = mensagens[0]["content"]
    # "Escala de narração" existe APENAS no dice.md — não deve aparecer sem rolagem
    assert "escala de narração" not in system.lower()


def test_montar_mensagens_com_rolagem_injeta_dice():
    invalidar_cache()
    contexto = _contexto_minimo("[Rolagem: d20 = 17]")
    mensagens = montar_mensagens(contexto)
    system = mensagens[0]["content"]
    # dice.md deve ter sido injetado — "fumble" é uma das palavras exclusivas do arquivo
    assert "fumble" in system.lower() or "d20" in system


def test_montar_mensagens_com_critico_injeta_dice():
    invalidar_cache()
    contexto = _contexto_minimo("[Rolagem: d20 = 20 — CRÍTICO!]")
    mensagens = montar_mensagens(contexto)
    system = mensagens[0]["content"]
    assert len(system) > 500   # sistema com dice.md deve ser substancialmente maior


def test_montar_mensagens_estrutura_basica():
    invalidar_cache()
    contexto = _contexto_minimo("Eu examino a porta")
    mensagens = montar_mensagens(contexto)
    assert mensagens[0]["role"] == "system"
    assert mensagens[-1]["role"] == "user"
    assert mensagens[-1]["content"] == "Eu examino a porta"


def test_montar_mensagens_nao_quebra_com_override():
    invalidar_cache()
    contexto = _contexto_minimo()
    mensagens = montar_mensagens(contexto, master_system_override="Sistema teste.")
    assert mensagens[0]["content"].startswith("Sistema teste.")


def test_montar_mensagens_dice_nao_injetado_quando_arquivo_ausente(tmp_path, monkeypatch):
    ausente = tmp_path / "dice_ausente.md"
    monkeypatch.setattr("engine.llm.prompt_builder._DICE_PATH", ausente)
    invalidar_cache()
    contexto = _contexto_minimo("[Rolagem: d20 = 5]")
    # Não deve levantar exceção — apenas não injeta
    mensagens = montar_mensagens(contexto)
    assert mensagens[0]["role"] == "system"


# ── Testes: combat.md ────────────────────────────────────────────────────────

def test_combat_md_existe():
    assert _COMBAT_PATH.exists(), "combat.md não encontrado"


def test_combat_md_tem_conteudo_minimo():
    conteudo = _COMBAT_PATH.read_text(encoding="utf-8")
    assert len(conteudo) >= _PROMPT_MIN_CHARS


def test_combat_md_menciona_lente_de_classe():
    conteudo = _COMBAT_PATH.read_text(encoding="utf-8")
    assert "guerreiro" in conteudo.lower() or "ladino" in conteudo.lower()


def test_combat_md_menciona_critico():
    conteudo = _COMBAT_PATH.read_text(encoding="utf-8")
    assert "20" in conteudo or "crítico" in conteudo.lower()


def test_carregar_combat_retorna_string():
    invalidar_cache()
    conteudo = _carregar_combat()
    assert conteudo is not None
    assert len(conteudo) > 0


def test_invalidar_cache_reseta_combat():
    """invalidar_cache() limpa também o cache de combat.md."""
    _carregar_combat()
    import engine.llm.prompt_builder as pb
    cache_antes = dict(pb._cache_prompts)
    assert any("combat" in str(p) for p in cache_antes.keys())
    invalidar_cache()
    assert pb._cache_prompts == {}


def test_hot_reload_relê_quando_mtime_muda(tmp_path):
    """Hot reload: edita o .md em disco e a próxima chamada pega a versão nova."""
    import engine.llm.prompt_builder as pb

    fake = tmp_path / "fake_prompt.md"
    fake.write_text("conteúdo inicial " * 20, encoding="utf-8")  # > 100 chars

    # Primeira leitura — cacheia
    v1 = pb._ler_prompt(fake)
    assert v1 is not None and "inicial" in v1

    # Reescreve com mtime diferente (Windows tem granularidade alta, então
    # usar os.utime explicitamente garante mtime distinto sem depender de sleep)
    import os
    fake.write_text("conteúdo NOVO " * 20, encoding="utf-8")
    futuro = fake.stat().st_mtime + 5
    os.utime(fake, (futuro, futuro))

    # Segunda leitura — deve pegar versão nova
    v2 = pb._ler_prompt(fake)
    assert v2 is not None and "NOVO" in v2 and "inicial" not in v2


def test_hot_reload_retorna_none_quando_arquivo_some(tmp_path):
    """Hot reload: se o arquivo é deletado, próxima leitura retorna None."""
    import engine.llm.prompt_builder as pb

    fake = tmp_path / "ephemeral.md"
    fake.write_text("conteúdo " * 30, encoding="utf-8")
    assert pb._ler_prompt(fake) is not None

    fake.unlink()
    assert pb._ler_prompt(fake) is None


# ── Testes: regex de detecção de combate ─────────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [
    # ── Nível 1: sempre combate ────────────────────────────────────────────────
    ("ataco o inimigo com minha espada", True),
    ("golpeio o guarda na cabeça", True),
    # Bug R4-2: "lanço" sem alvo NÃO é combate (ritual, corda, etc. são falsos positivos)
    # "lanço" COM alvo explícito (no/na/contra/sobre) É combate
    ("lanço um feitiço de fogo", False),          # sem alvo → não combate
    ("lanço bola de fogo no goblin", True),       # com alvo → combate
    ("lanço raio contra o guardião", True),       # com alvo → combate
    ("lancei veneno sobre o guarda", True),       # com alvo → combate
    ("lanço um ritual de identificação", False),  # sem alvo → não combate
    ("ativo minha espada mágica", True),
    ("luto contra os dois ao mesmo tempo", True),
    ("disparo uma flecha", True),
    ("conjuro Bola de Fogo", True),
    ("esquivo do golpe", True),
    # ── Nível 2: cortar — com alvo ou arma ────────────────────────────────────
    ("corto o goblin com minha espada", True),
    ("corto com minha espada", True),
    ("cortei ele de um golpe", True),
    # ── Nível 2: cortar — mundano (sem alvo singular ou arma) ─────────────────
    ("corto as folhas no meu caminho", False),   # plural "as" → sem combate
    ("corto galhos para montar acampamento", False),  # sem artigo → sem combate
    # ── Nível 2: empurrar, agarrar, derrubar ──────────────────────────────────
    ("empurro o guarda para longe", True),
    ("agarrei o bandido pelo pescoço", True),
    ("derrubei o orc no chão", True),
    ("empurrei ela com força", True),
    # ── Fix 5: desembainhar — todas as conjugações ────────────────────────────
    ("desembainho minha espada lentamente", True),
    ("ela desembainha a adaga", True),
    ("desembainhou a espada antes de atacar", True),
    ("vou desembainhar minha espada", True),
    # ── Fix COMBATE-VERB-1 (26/05): "uso X em/contra/no Y" — análogo ao lançar ──
    ("uso chama sagrada nele", True),
    ("uso bola de fogo contra o orc", True),
    ("usei minha habilidade especial sobre o líder", True),
    ("uso a corda", False),                       # sem alvo → não combate
    ("uso o cajado para abrir a porta", False),   # propósito, não ataque
    # ── Fix COMBATE-VERB-1: declarações explícitas de combate ─────────────────
    ("estamos em combate agora", True),
    ("entrei em combate com o guarda", True),
    ("iniciei o combate", True),
    ("começou o combate", True),
    # ── Não combate ────────────────────────────────────────────────────────────
    ("eu falo com o ferreiro", False),
    ("olho ao redor da sala", False),
    ("examino a porta", False),
    ("", False),
])
def test_regex_combate(texto: str, esperado: bool):
    assert bool(_RE_COMBATE.search(texto)) == esperado


def test_montar_mensagens_com_acao_combate_injeta_combat_md():
    invalidar_cache()
    contexto = _contexto_minimo("ataco o goblin com minha espada")
    mensagens = montar_mensagens(contexto)
    system = mensagens[0]["content"]
    # "lente de classe" ou "teatro da mente" são exclusivos do combat.md
    assert "teatro da mente" in system.lower() or "lente" in system.lower()


def test_montar_mensagens_sem_combate_nao_injeta_combat_md():
    invalidar_cache()
    contexto = _contexto_minimo("eu falo com o ferreiro sobre o martelo")
    mensagens = montar_mensagens(contexto)
    system = mensagens[0]["content"]
    assert "teatro da mente" not in system.lower()


def test_montar_mensagens_em_combate_ativo_injeta_combat_md():
    invalidar_cache()
    wm = WorkingMemory.nova_sessao(
        location_id="tharnvik",
        location_nome="Tharnvik",
        session_id="test-session",
    )
    wm.entrar_combate()
    # Texto neutro — mas em_combate=True deve forçar injeção
    contexto = ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual="o que faço agora?",
    )
    mensagens = montar_mensagens(contexto)
    system = mensagens[0]["content"]
    assert "teatro da mente" in system.lower() or "lente" in system.lower()


# ── Testes: saves.md ─────────────────────────────────────────────────────────

def test_saves_md_existe():
    assert _SAVES_PATH.exists(), "saves.md não encontrado"


def test_saves_md_tem_conteudo_minimo():
    conteudo = _SAVES_PATH.read_text(encoding="utf-8")
    assert len(conteudo) >= _PROMPT_MIN_CHARS


def test_saves_md_cobre_seis_atributos():
    conteudo = _SAVES_PATH.read_text(encoding="utf-8").lower()
    for atrib in ["força", "destreza", "constituição", "inteligência", "sabedoria", "carisma"]:
        assert atrib in conteudo, f"saves.md não menciona '{atrib}'"


def test_saves_md_menciona_sequencia_rolagem():
    conteudo = _SAVES_PATH.read_text(encoding="utf-8")
    assert "Rolagem" in conteudo, "saves.md deve referenciar o formato [Rolagem:]"


def test_carregar_saves_retorna_string():
    invalidar_cache()
    conteudo = _carregar_saves()
    assert conteudo is not None
    assert len(conteudo) > 0


def test_invalidar_cache_reseta_saves():
    """invalidar_cache() limpa o cache de saves.md."""
    _carregar_saves()
    import engine.llm.prompt_builder as pb
    cache_antes = dict(pb._cache_prompts)
    assert any("saves" in str(p) for p in cache_antes.keys())
    invalidar_cache()
    assert pb._cache_prompts == {}


def test_montar_mensagens_em_combate_ativo_injeta_saves():
    invalidar_cache()
    wm = WorkingMemory.nova_sessao(
        location_id="tharnvik",
        location_nome="Tharnvik",
        session_id="test-session",
    )
    wm.entrar_combate()
    contexto = ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual="o que faço agora?",
    )
    mensagens = montar_mensagens(contexto)
    system = mensagens[0]["content"]
    # saves.md contém "salvaguarda" ou pelo menos um dos atributos com contexto de saves
    assert "salvaguarda" in system.lower() or "constituição" in system.lower()


def test_montar_mensagens_acao_combate_injeta_saves():
    invalidar_cache()
    contexto = _contexto_minimo("ataco o goblin com minha espada")
    mensagens = montar_mensagens(contexto)
    system = mensagens[0]["content"]
    assert "salvaguarda" in system.lower() or "constituição" in system.lower()


def test_montar_mensagens_fora_combate_nao_injeta_saves():
    invalidar_cache()
    contexto = _contexto_minimo("eu falo com o ferreiro sobre o martelo")
    mensagens = montar_mensagens(contexto)
    system = mensagens[0]["content"]
    # saves.md não deve aparecer em contexto puramente social
    assert "salvaguarda" not in system.lower()


# ── Testes de budget de tokens ────────────────────────────────────────────────
# Garante que os prompts comprimidos não excedam os tetos de tamanho.
# Qualquer editor que inflar os .md além do teto vai ver esses testes quebrarem.

def test_combat_md_dentro_do_budget():
    """combat.md comprimido: máx 5 000 chars (~1 430 tokens).

    O budget é: turno de combate ≤ 6 000 TPM no Groq 70B free tier.
    combat.md estava em 12 018 chars (3 434 tok) — estava consumindo 57% do TPM
    sozinho. Após compressão ficou em ~3 700 chars (~1 055 tok).
    Teto aqui é 5 000 chars para dar margem a edições futuras sem travar sessão.
    """
    conteudo = _COMBAT_PATH.read_text(encoding="utf-8")
    assert len(conteudo) <= 5_000, (
        f"combat.md com {len(conteudo)} chars excede teto de 5 000 chars — "
        "o turno de combate vai cascatear para 8B toda vez"
    )


def test_saves_md_dentro_do_budget():
    """saves.md comprimido: máx 2 000 chars (~571 tokens)."""
    saves_path = _COMBAT_PATH.parent / "saves.md"
    conteudo = saves_path.read_text(encoding="utf-8")
    assert len(conteudo) <= 2_000, (
        f"saves.md com {len(conteudo)} chars excede teto de 2 000 chars"
    )


def test_master_system_dentro_do_budget():
    """master_system.md: máx 11 500 chars (~3 285 tokens).

    Histórico:
    - 10 500 antes dos marcadores ANCORA/VOZ/AFETO
    - 11 000 após (margem pra mexer)
    - 11 500 após (27/05) inclusão da voz dupla refinada + regra NPC progressivo
      — ambas resolveram feedback de jogo, valem o custo de tokens.

    Acima de 11 500: pausar, justificar, e considerar gating condicional
    (injetar só quando relevante) em vez de adicionar.
    """
    conteudo = _MASTER_SYSTEM_PATH.read_text(encoding="utf-8")
    assert len(conteudo) <= 11_500, (
        f"master_system.md com {len(conteudo)} chars excede teto de 11 500 chars — "
        "injeta >3 285 tokens em todo turno; comprimir ou gating condicional"
    )


def test_prompt_combate_dentro_do_budget_de_tokens():
    """Prompt de combate completo deve ficar abaixo de 18 800 chars (~5 370 tokens).

    Budget alvo: turno de combate (system + user) ≤ 6 000 TPM @ 1 turn/min
    no Groq 70B. Teto 18 800 (master ~10 150 — instruções [CENA], OOC-vocativo e
    NPC-react do teste ao vivo 09/06 — + combat ~3 530 + markers_frag ~2 240 com
    [FEATURE_GASTA] e doc anti-"srd" do [INIMIGO] + saves ~1 400 + wm ~500 +
    lembrete ~180). Continua 1 200 chars abaixo do guard de runtime (20 000).
    Subir este teto de novo exige cortar gordura em vez de empilhar instrução.
    """
    invalidar_cache()
    wm = WorkingMemory.nova_sessao(
        location_id="dungeon",
        location_nome="Dungeon",
        session_id="test-budget",
        player_class="Guerreiro",
    )
    wm.entrar_combate()
    # Adiciona 3 inimigos para simular combate real
    wm.registrar_inimigo("goblin-1", "Goblin", "ferido")
    wm.registrar_inimigo("goblin-2", "Goblin Arqueiro", "intacto")
    wm.registrar_inimigo("orc-lider", "Orc Líder", "intacto")
    # DM features populadas
    wm.fios_soltos = ["O ferreiro sabe algo sobre Valdrek", "A guarda suspeita do jogador"]
    wm.agenda_npcs = {"orc-lider": "planeja recuar se perder mais de metade dos guerreiros"}

    contexto = ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual="ataco o orc líder com minha espada",
    )
    mensagens = montar_mensagens(contexto)
    system = mensagens[0]["content"]
    assert len(system) <= 18_800, (
        f"System prompt de combate com {len(system)} chars excede teto de 18 800 — "
        f"turn total estimado: ~{(len(system)/3.5 + 400):.0f} tokens"
    )
