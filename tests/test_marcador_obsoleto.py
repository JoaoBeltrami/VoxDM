"""
Bloco 3 — marcador migrado pra engine morre no PROCESSAMENTO, não no strip.

Por que existe: a regra de migração do Bloco 3, como escrita na fila, manda
    tirar o nome de `NOMES_MARCADORES` quando a engine assume a decisão. Seguir
    isso ao pé da letra QUEBRA A VOZ — `RE_STRIP_MARCADORES` é DERIVADO daquela
    tupla e é o único strip do TTS. O nome removido de lá deixaria de ser limpo
    do texto e o jogador passaria a OUVIR "colchete RELOGIO_AVANCA dois pontos
    guerra-das-vilas". Este arquivo trava as duas metades da migração.
Dependências: nenhuma (regex e tuplas puras).
Armadilha: o teste do strip precisa usar o marcador OBSOLETO de verdade, não um
    canônico — senão passa por acidente e não prova nada.

Exemplo:
    uv run pytest tests/test_marcador_obsoleto.py -q
"""

from engine.markers import (
    NOMES_MARCADORES,
    NOMES_OBSOLETOS,
    RE_STRIP_MARCADORES,
    e_obsoleto,
)

# ── As duas tuplas são disjuntas ─────────────────────────────────────────────


def test_obsoleto_sai_da_lista_canonica():
    assert not (set(NOMES_MARCADORES) & set(NOMES_OBSOLETOS)), (
        "um nome não pode ser canônico E obsoleto — o handler voltaria a rodar"
    )


def test_relogio_avanca_esta_obsoleto():
    assert e_obsoleto("RELOGIO_AVANCA")
    assert "RELOGIO_AVANCA" not in NOMES_MARCADORES


def test_relogio_simples_continua_canonico():
    """`[RELOGIO: id|nome]` responde 'o que isso significa' (o Mestre percebeu
    que uma ameaça importa) — é o que o LLM AINDA pode decidir pelo ADR-006.
    Só o `_AVANCA` (quanto) saiu."""
    assert "RELOGIO" in NOMES_MARCADORES
    assert not e_obsoleto("RELOGIO")


def test_e_obsoleto_ignora_caixa_e_espaco():
    assert e_obsoleto("  relogio_avanca ")


def test_marcador_canonico_nao_e_obsoleto():
    for nome in ("FIO", "DANO", "CENA", "NPC"):
        assert not e_obsoleto(nome)


# ── O strip continua limpando (a metade que a fila esqueceu) ─────────────────


def test_marcador_obsoleto_continua_sendo_limpo_do_texto():
    """A prova de que a voz não quebrou. Se este teste falhar, o jogador OUVE
    o marcador."""
    texto = "A guerra se aproxima. [RELOGIO_AVANCA: guerra-das-vilas] O sino toca."
    limpo = RE_STRIP_MARCADORES.sub("", texto)
    assert "RELOGIO_AVANCA" not in limpo
    assert "[" not in limpo and "]" not in limpo
    assert "A guerra se aproxima." in limpo
    assert "O sino toca." in limpo


def test_todo_obsoleto_e_limpo_do_texto():
    """Vale pra tupla inteira, não só pro primeiro — os próximos itens do
    Bloco 3 entram aqui e o teste passa a cobri-los sozinho."""
    for nome in NOMES_OBSOLETOS:
        limpo = RE_STRIP_MARCADORES.sub("", f"antes [{nome}: alvo-qualquer] depois")
        assert nome not in limpo, nome
        assert "[" not in limpo and "]" not in limpo, nome
        # a prosa em volta sobrevive intacta
        assert limpo.split() == ["antes", "depois"], nome


# ── O processamento morreu ───────────────────────────────────────────────────


def test_marcador_obsoleto_nao_move_mais_o_relogio():
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.narrative.criar_relogio("guerra", "Guerra das Vilas", segmentos=6)

    aplicar_pos_turno(wm, "olho o horizonte", "Tensão. [RELOGIO_AVANCA: guerra]")

    assert wm.narrative.relogios["guerra"]["atual"] == 0, (
        "o LLM voltou a mover o relógio — o handler deveria estar morto"
    )


def test_o_prompt_parou_de_pedir_o_obsoleto():
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    for md in (raiz / "engine/llm/prompts").rglob("*.md"):
        texto = md.read_text(encoding="utf-8")
        for nome in NOMES_OBSOLETOS:
            assert f"[{nome}" not in texto, f"{md.name} ainda pede [{nome}]"
