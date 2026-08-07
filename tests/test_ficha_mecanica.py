"""
FICHA-MECANICA (07/08): número pra engine, porte pro Mestre.

Por que existe: a ficha SRD inteira ia pro prompt em todo turno de combate (até
    3, ~55 palavras cada) — uma TABELA num lugar onde o Mestre nem pode citar
    número. Estes testes travam as duas pontas: (a) o prompt não carrega mais
    números de ficha, (b) todo inimigo termina ancorado num statblock REAL antes
    do genérico, e o texto dessa âncora é parseável pela própria engine.
Dependências: nenhuma (tudo puro, sem I/O).
Armadilha: o teste de parseabilidade é o que impede `_ficha_texto` e
    `parse_ficha` de derivarem em silêncio — foi assim que Vyrmathax pegou uma
    ficha de warlock e o combate parou de doer.

Exemplo:
    uv run pytest tests/test_ficha_mecanica.py -q
"""

import re

from engine.combat.npc_statblocks import STATBLOCKS_SRD, ancorar_no_srd
from engine.combat.stats import descritor_de_inimigo, parse_ficha, stats_inimigo
from engine.state.combat import CombatState

_FICHA_BERSERKER = (
    "Berserker — CR 2 (450 XP). CA 13 | PV 67. Ataques: Machadão +5 (1d12+3)"
)
_FICHA_PLEBEU = "Plebeu — CR 0 (10 XP). CA 10 | PV 4. Ataques: Clava +2 (1d4)"

# Formato REAL devolvido pelo Qdrant (voxdm_bestiary) — é esta que ia inteira
# pro prompt, até 3 por turno de combate.
_FICHA_QDRANT = (
    "Berserker — Médio humanoide (qualquer raça), caótico neutro. CR 2 (450 XP). "
    "CA 13 (peles) | PV 67 (9d8+27). Deslocamento 30 ft. "
    "FOR 16 (+3) DES 12 (+1) CON 17 (+3) INT 9 (-1) SAB 11 (+0) CAR 9 (-1). "
    "Sentidos: Percepção passiva 10. Idiomas: qualquer um. "
    "Frenesi Insano: no início do turno, ganha vantagem em jogadas de ataque "
    "corpo a corpo durante o turno e ataques contra ele têm vantagem até o "
    "próximo turno. Ataques: Machadão +5 (1d12+3 cortante)."
)


# ── Descritor: o que o Mestre lê ─────────────────────────────────────────────


def test_descritor_nao_carrega_numero_nenhum():
    """O master_system proíbe citar número — então número não entra no prompt."""
    desc = descritor_de_inimigo("Berserker", stats_inimigo(_FICHA_BERSERKER))
    assert not re.search(r"\d", desc), f"descritor vazou número: {desc}"


def test_descritor_distingue_ameaca_de_lacaio():
    """Berserker e plebeu não podem ler igual — era o sintoma do combate fácil."""
    forte = descritor_de_inimigo("Berserker", stats_inimigo(_FICHA_BERSERKER))
    fraco = descritor_de_inimigo("Plebeu", stats_inimigo(_FICHA_PLEBEU))
    assert forte != fraco
    assert "monstruoso" in forte or "coriáceo" in forte
    assert "frágil" in fraco


def test_descritor_e_muito_menor_que_a_ficha_do_bestiario():
    """A economia é o ponto: o prompt bateu 24 558 chars com fichas inteiras.

    Compara com a ficha do QDRANT (a que inchava o prompt), não com a compacta
    do statblock estático — contra a compacta o corte é de ~40%, contra a real
    é de ~85%.
    """
    desc = descritor_de_inimigo("Berserker", stats_inimigo(_FICHA_BERSERKER))
    assert len(desc) < len(_FICHA_QDRANT) / 4
    # e mesmo contra a compacta ainda encolhe
    assert len(desc) < len(_FICHA_BERSERKER)


def test_descritor_sem_nome_nao_quebra():
    assert descritor_de_inimigo("", stats_inimigo("")).startswith("inimigo")


# ── to_prompt: a ficha saiu do prompt de verdade ─────────────────────────────


def _combate_com_berserker() -> CombatState:
    combat = CombatState()
    combat.entrar()
    combat.registrar_inimigo("bjorn", "Bjorn")
    combat.inimigos_combate["bjorn"]["ficha"] = _FICHA_BERSERKER
    return combat


def test_prompt_de_combate_nao_injeta_mais_a_ficha():
    prompt = _combate_com_berserker().to_prompt()
    assert "CA 13" not in prompt
    assert "PV 67" not in prompt
    assert "1d12" not in prompt


def test_prompt_de_combate_traz_o_porte():
    prompt = _combate_com_berserker().to_prompt()
    assert "Porte:" in prompt
    assert "Bjorn" in prompt


def test_inimigo_morto_nao_entra_no_porte():
    combat = _combate_com_berserker()
    combat.atualizar_estado_inimigo("bjorn", "morto")
    assert "Porte:" not in combat.to_prompt()


def test_porte_dedup_por_tipo():
    """5 goblins = 1 linha de porte (dedup por srd_index)."""
    combat = CombatState()
    combat.entrar()
    for i in range(5):
        iid = f"goblin-{i}"
        combat.registrar_inimigo(iid, "Goblin")
        combat.inimigos_combate[iid]["ficha"] = _FICHA_PLEBEU
        combat.inimigos_combate[iid]["srd_index"] = "goblin"
    linha = [ln for ln in combat.to_prompt().splitlines() if ln.startswith("Porte:")]
    assert len(linha) == 1
    assert linha[0].count("—") == 1


# ── Âncora SRD: o último elo antes do genérico ───────────────────────────────


def test_ancora_por_indice_srd():
    assert "Berserker" in (ancorar_no_srd(srd_index="berserker") or "")


def test_ancora_por_nome_pt_br_com_acento():
    """O Mestre narra em português: o inimigo chega como 'Acólito', não 'acolyte'."""
    assert "Acólito" in (ancorar_no_srd(nome="Acólito") or "")


def test_ancora_ignora_criatura_desconhecida():
    """Vyrmathax não é SRD — tem que cair no genérico (e no warning), não num chute."""
    assert ancorar_no_srd(nome="Vyrmathax", srd_index="") is None


def test_ancora_vazia_nao_quebra():
    assert ancorar_no_srd() is None


def test_toda_ancora_srd_e_parseavel_pela_engine():
    """Teste que amarra os dois lados: `_ficha_texto` gera, `parse_ficha` lê.

    Sem isto, mudar o formato do statblock quebraria o combate em SILÊNCIO — o
    parse voltaria None e o inimigo cairia no default CR 1/8 sem avisar.
    """
    for chave, campos in STATBLOCKS_SRD.items():
        ficha = ancorar_no_srd(srd_index=chave)
        assert ficha, f"{chave} não ancorou"
        stats = parse_ficha(ficha)
        assert stats is not None, f"{chave} gerou ficha não-parseável: {ficha}"
        assert stats.ca == int(campos["ca"]), chave
        assert stats.hp_max == int(campos["hp"]), chave
        assert stats.atk_bonus == int(campos["atk"]), chave
        assert stats.dano_dado == str(campos["dano"]), chave
