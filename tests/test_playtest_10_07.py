"""
Testes dos fixes do playtest 10/07 (sess-cc69c30f7c4f, 16 iterações, ~25min).

Primeiro playtest 100% autônomo (Claude jogou via browser nativo, digitando no
lugar de voz). Validou o PRIMEIRO dano real da engine de combate (28→22 HP) e o
grimdark ao vivo (Camadas 1-3). Achou 1 bug novo de causa-raiz:

- ALVO-INSTRUMENTO-1: "Quebro a caneca na cabeça do grandão" registrou "caneca"
  (o instrumento do golpe) como inimigo em vez de "grandão" (o alvo real) — o
  objeto direto do verbo vinha antes do possessivo nomeado do corpo atingido.

Dependências: pytest.
"""

from engine.memory.working_memory import WorkingMemory


def _wm(**kw) -> WorkingMemory:
    return WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-test", **kw)


# ══ ALVO-INSTRUMENTO-1: possessivo nomeado de corpo vence objeto direto ═══════


def test_alvo_instrumento_frase_real_da_sessao():
    """A frase real do playtest: instrumento (caneca) não pode virar inimigo."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.entrar_combate()
    alvo = extrair_alvo_ataque("Quebro a caneca na cabeça do grandão.", wm)
    assert alvo == "grandao"
    assert "grandao" in wm.inimigos_combate
    assert "caneca" not in wm.inimigos_combate


def test_alvo_instrumento_prefere_npc_ja_presente():
    """Quando o possuidor nomeado já é um NPC presente, resolve_falado ancora
    nele em vez de criar um id solto novo."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["grandao-barba-densa"]
    wm.entrar_combate()
    alvo = extrair_alvo_ataque("Quebro a garrafa na cabeça do grandão.", wm)
    assert alvo == "grandao-barba-densa"


def test_alvo_instrumento_outras_partes_do_corpo():
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.entrar_combate()
    assert extrair_alvo_ataque("Acerto a garrafa no rosto do bandido", wm) == "bandido"

    wm2 = _wm()
    wm2.entrar_combate()
    assert extrair_alvo_ataque("Bato a tocha nas costas do ladrão", wm2) == "ladrao"


def test_alvo_instrumento_nao_interfere_com_ataque_direto_normal():
    """Sem parte-do-corpo-possessiva na frase, o objeto direto clássico segue
    intocado — não é regressão do FUNC-1."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.entrar_combate()
    assert extrair_alvo_ataque("Ataco o goblin", wm) == "goblin"


def test_alvo_instrumento_nao_interfere_com_pronome_ja_coberto():
    """'na cabeça com ele' (sem 'do/da NOME') não deve casar com o novo regex —
    continua caindo no caminho de pronome já validado no FUNC-1."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["guarda"]
    wm.entrar_combate()
    texto = "Eu vou pegar o copo que tiver perto da mesa, quebrar ele na cabeça com ele"
    assert extrair_alvo_ataque(texto, wm) == "guarda"


def test_alvo_instrumento_possuidor_pronome_nao_casa():
    """'na cabeça dele' (pronome, não nome) não deve ser capturado pelo regex
    novo — 'dele' não bate em d[oa]s? (só do/da/dos/das)."""
    from api.turn_pipeline import _RE_ALVO_POSSESSIVO_CORPO, extrair_alvo_ataque

    assert _RE_ALVO_POSSESSIVO_CORPO.search("na cabeca dele") is None

    wm = _wm()
    wm.npcs_presentes = []
    wm.entrar_combate()
    assert extrair_alvo_ataque("Bato na cabeça dele com a garrafa", wm) is None
