"""Testes do CANON-MORTOS-2 — reconciliação de abates pendentes (A/B 17/07).

Por que existe: no A/B do BRIEF_ATIVO a engine matou `homem-da-lanca` (fim=True)
mas a flag `morto` nunca chegou ao npc_registro — o kill roda PRÉ-LLM e o
combatente só virou conhecido-da-cena na extração/[NPC] do pós-turno; o
`marcar_morto` conservador devolvia None e o abate se perdia (corpo sumia do
canon). O fix: fila transiente `mortos_pendentes` na facade + drenagem no fim
do aplicar_pos_turno (step 17c), quando o registro já existe.

Dependências: pytest.
Armadilha: `mortos_pendentes` é TRANSIENTE — não persiste em dm_state nem entra
em prompt; um teste que assuma sobrevivência a checkpoint está errado.

Exemplo:
    wm.atualizar_estado_inimigo("x", "morto")  # cena não conhece "x"
    # → wm.mortos_pendentes == ["x"]; aplicar_pos_turno com [NPC: x|X] marca.
"""

from api.turn_pipeline import aplicar_pos_turno
from engine.memory.working_memory import WorkingMemory
from engine.npc.identity import esta_morto, registrar_npc


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao("estrada-norte", "Estrada Norte", "sess-test")


# ── Captura na facade (_marcar_npc_morto) ────────────────────────────────────


def test_kill_de_desconhecido_vai_pra_pendentes():
    wm = _wm()
    wm.entrar_combate()
    wm.atualizar_estado_inimigo("homem-da-lanca", "morto")
    # Cena não conhece o id → marcar_morto conservador falhou → pendente
    assert "homem-da-lanca" in wm.mortos_pendentes
    assert not esta_morto(wm, "homem-da-lanca")


def test_kill_de_conhecido_marca_na_hora_sem_pendencia():
    wm = _wm()
    registrar_npc(wm, "ryker", "Ryker")
    wm.entrar_combate()
    wm.atualizar_estado_inimigo("ryker", "morto")
    assert esta_morto(wm, "ryker")
    assert wm.mortos_pendentes == []


def test_kill_duplicado_de_desconhecido_nao_duplica_pendencia():
    wm = _wm()
    wm.entrar_combate()
    wm.atualizar_estado_inimigo("goblin-x", "morto")
    wm.atualizar_estado_inimigo("goblin-x", "morto")
    assert wm.mortos_pendentes.count("goblin-x") == 1


# ── Drenagem no aplicar_pos_turno (step 17c) ─────────────────────────────────


def test_reconciliacao_marca_apos_registro_via_marker_npc():
    """Cenário exato do A/B: kill pré-LLM de desconhecido + [NPC] no pós-turno."""
    wm = _wm()
    wm.entrar_combate()
    wm.atualizar_estado_inimigo("homem-da-lanca", "morto")
    wm.sair_combate()  # engine fecha o combate na hora do fim (como no WS)
    assert not esta_morto(wm, "homem-da-lanca")

    aplicar_pos_turno(
        wm,
        "Ataco o homem da lança.",
        "A lâmina o derruba; ele não se move mais. "
        "[NPC: homem-da-lanca|Homem da Lança]",
    )
    assert esta_morto(wm, "homem-da-lanca")
    assert wm.mortos_pendentes == []


def test_reconciliacao_descarta_quem_continua_desconhecido():
    wm = _wm()
    wm.entrar_combate()
    wm.atualizar_estado_inimigo("vulto-sem-nome", "morto")
    wm.sair_combate()

    aplicar_pos_turno(wm, "Sigo em frente.", "A estrada continua vazia e fria.")
    # Continua desconhecido → descartado sem crash, fila limpa (não cresce sem teto)
    assert wm.mortos_pendentes == []
    assert not esta_morto(wm, "vulto-sem-nome")


def test_reconciliacao_marca_quando_ja_estava_em_presentes():
    """Extração de alvo pode ter posto o id em npcs_presentes sem registro —
    a drenagem também cobre esse caminho (conhecido via presença)."""
    wm = _wm()
    wm.entrar_combate()
    wm.atualizar_estado_inimigo("batedor", "morto")
    wm.sair_combate()
    wm.npcs_presentes.append("batedor")

    aplicar_pos_turno(wm, "Confiro o corpo.", "O batedor está imóvel no chão.")
    assert esta_morto(wm, "batedor")
    assert wm.mortos_pendentes == []
