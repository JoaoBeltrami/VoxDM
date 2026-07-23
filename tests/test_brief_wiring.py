"""
Testes do wiring do NarrationBrief no prompt_builder (BRIEF_ATIVO, decisão 12/07).

Por que existe: a troca da fonte do prompt (para_texto → brief) é o passo 🔴
    do roadmap engine-first — wirada atrás de kill-switch DESLIGADO (padrão
    grimdark). Estes testes provam as duas metades do contrato: flag OFF =
    zero mudança (o caminho normal segue byte-idêntico em espírito), flag ON =
    system enxuto com persona+markers+brief e SEM o dump antigo.
Dependências: pytest; monkeypatch em config.settings.
Armadilha: settings é objeto global — SEMPRE monkeypatch.setattr(settings,
    "BRIEF_ATIVO", ...), nunca atribuição direta (vaza pros outros testes).
"""

from config import settings
from engine.llm.prompt_builder import ContextoMontado, invalidar_cache, montar_mensagens
from engine.memory.working_memory import WorkingMemory

_PERSONA_FAKE = "PERSONA-DE-TESTE do Mestre " + "x" * 100


def _wm(**kw) -> WorkingMemory:
    wm = WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-brief-w", **kw)
    wm.registrar_fala("player", "Olá, taverneiro.")
    wm.registrar_fala("mestre", "O taverneiro acena.")
    wm.registrar_fala("player", "Peço uma cerveja.")
    return wm


def _contexto(wm: WorkingMemory, transcricao: str = "Peço uma cerveja.", **kw) -> ContextoMontado:
    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=kw.get("chunks_semanticos", []),
        chunks_episodicos=kw.get("chunks_episodicos", []),
        chunks_regras=kw.get("chunks_regras", []),
        relacoes_grafo=kw.get("relacoes_grafo", []),
        secrets_visiveis=[],
        transcricao_atual=transcricao,
    )


def test_flag_default_e_on_e_off_mantem_caminho_normal(monkeypatch):
    """Default promovido a ON (ADR-001, 19/07 — A/B: tokens −47%, qualidade
    não-inferior). O conftest fixa a SUITE no caminho legado via env, então o
    default de produção é guardado pelo default do CAMPO (model_fields). O
    kill-switch continua existindo: OFF restaura o para_texto de sempre."""
    assert type(settings).model_fields["BRIEF_ATIVO"].default is True
    monkeypatch.setattr(settings, "BRIEF_ATIVO", False)
    invalidar_cache()
    system = montar_mensagens(_contexto(_wm()), master_system_override=_PERSONA_FAKE)[0]["content"]
    assert "=== CENA ATUAL ===" in system
    assert "=== BRIEFING DO TURNO ===" not in system


def test_flag_on_troca_dump_pelo_brief(monkeypatch):
    monkeypatch.setattr(settings, "BRIEF_ATIVO", True)
    invalidar_cache()
    system = montar_mensagens(_contexto(_wm()), master_system_override=_PERSONA_FAKE)[0]["content"]
    assert "=== BRIEFING DO TURNO ===" in system
    assert "=== CENA ATUAL ===" not in system
    # Persona e contrato de markers acompanham o brief.
    assert _PERSONA_FAKE in system
    assert "Marcadores de Mestre Veterano" in system


def test_flag_on_rolling_summary_sempre_incluso(monkeypatch):
    monkeypatch.setattr(settings, "BRIEF_ATIVO", True)
    invalidar_cache()
    wm = _wm()
    wm.resumo_rolling = "Kael contratou o mercenário Moreno na Estrela Dourada."
    system = montar_mensagens(_contexto(wm), master_system_override=_PERSONA_FAKE)[0]["content"]
    assert "contratou o mercenário Moreno" in system


def test_flag_on_regras_srd_do_turno_entram(monkeypatch):
    """Mecânica que a engine buscou (spell detector) é fato engine-fornecido —
    acompanha o brief."""
    monkeypatch.setattr(settings, "BRIEF_ATIVO", True)
    invalidar_cache()
    ctx = _contexto(
        _wm(), transcricao="Lanço bola de fogo!",
        chunks_regras=[{"text": "Bola de Fogo: 8d6 fogo, save DES CD 15, raio 20 pés"}],
    )
    system = montar_mensagens(ctx, master_system_override=_PERSONA_FAKE)[0]["content"]
    assert "=== MECÂNICA DO TURNO (SRD) ===" in system
    assert "8d6 fogo" in system


def test_flag_on_lore_do_rag_fica_de_fora(monkeypatch):
    """A aposta LLM-fino: chunks de lore semântico NÃO acompanham o brief —
    o rolling summary carrega o contexto narrativo."""
    monkeypatch.setattr(settings, "BRIEF_ATIVO", True)
    invalidar_cache()
    ctx = _contexto(
        _wm(),
        chunks_semanticos=[{"text": "LORE-CHUNK: o Cajado de Valdrek gera um globo"}],
    )
    system = montar_mensagens(ctx, master_system_override=_PERSONA_FAKE)[0]["content"]
    assert "LORE-CHUNK" not in system


def test_flag_on_historico_de_dialogo_preservado(monkeypatch):
    monkeypatch.setattr(settings, "BRIEF_ATIVO", True)
    invalidar_cache()
    msgs = montar_mensagens(_contexto(_wm()), master_system_override=_PERSONA_FAKE)
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "Olá, taverneiro."}
    assert msgs[2] == {"role": "assistant", "content": "O taverneiro acena."}
    assert msgs[-1] == {"role": "user", "content": "Peço uma cerveja."}


def test_flag_on_system_e_bem_menor_que_o_normal(monkeypatch):
    """A tese "LLM-fino" segue de pé no turno COMUM: sem combate nem NPC, o brief
    larga o dump de RAG + a tralha acumulada do para_texto e fica bem menor.

    Nota (auditoria 22/07): o limiar antigo era 0.75 medido numa cena SOCIAL com
    8 NPCs. Aquele número refletia um brief que — indevidamente — não carregava a
    voz distinta de cada NPC (MESMICE-NPC / VOZ-DUPLA) nem o estado de combate
    (COMBATE-CEGO). Corrigido isso, numa cena social o brief carrega social.md +
    assinaturas de voz nos DOIS caminhos, então o gap ali é legitimamente menor.
    A leveza real do brief é no turno de exploração, medida aqui.
    """
    wm = _wm()  # exploração: sem NPC presente, sem combate
    wm.resumo_rolling = "resumo. " * 80
    ctx_kwargs = dict(
        chunks_semanticos=[{"text": "lore " * 120} for _ in range(4)],
        chunks_episodicos=[{"text": "memória " * 100} for _ in range(3)],
    )
    invalidar_cache()
    normal = montar_mensagens(_contexto(wm, **ctx_kwargs))[0]["content"]
    monkeypatch.setattr(settings, "BRIEF_ATIVO", True)
    invalidar_cache()
    brief = montar_mensagens(_contexto(wm, **ctx_kwargs))[0]["content"]
    assert len(brief) < len(normal) * 0.85, (
        f"brief ({len(brief)}) deveria ser bem menor que o normal ({len(normal)})"
    )


def test_flag_on_grimdark_acompanha_o_brief(monkeypatch):
    """Segurança de rota não é negociável — cena sombria injeta o fragmento
    grimdark também no modo brief."""
    monkeypatch.setattr(settings, "BRIEF_ATIVO", True)
    monkeypatch.setattr(settings, "GRIMDARK_ATIVO", True)
    invalidar_cache()
    wm = _wm()
    wm.dm_profile = "sombrio"
    system = montar_mensagens(_contexto(wm), master_system_override=_PERSONA_FAKE)[0]["content"]
    assert "=== BRIEFING DO TURNO ===" in system
    # O fragmento grimdark existe e tem conteúdo — basta um âncora estável dele.
    from engine.llm.prompt_builder import _FRAG_GRIMDARK
    frag = _FRAG_GRIMDARK.read_text(encoding="utf-8")
    ancora = frag.strip().splitlines()[0].strip("# ").strip()
    assert ancora in system


def test_flag_on_session_zero_tem_prioridade(monkeypatch):
    """Session Zero substitui TUDO — inclusive o modo brief (entrevista não
    tem cena pra briefar)."""
    monkeypatch.setattr(settings, "BRIEF_ATIVO", True)
    invalidar_cache()
    wm = _wm()
    wm.session_zero_ativa = True
    system = montar_mensagens(_contexto(wm))[0]["content"]
    assert "=== BRIEFING DO TURNO ===" not in system
