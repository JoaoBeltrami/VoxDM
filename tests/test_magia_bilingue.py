"""
Magia entendida em PT-BR e em inglês, e as 19 fora do SRD ganham lastro.

Por que existe: duas decisões do Beltrami em 09/08.
    1. *"prefiro ter as magias mesmo que parecidas"* — as 19 de Xanathar's/
       Tasha's continuariam sendo PROSA mesmo com o P16 pronto. O bruxo era o
       mais atingido (5 das 19; `Hex` é a assinatura da classe).
    2. *"que o mestre entenda o nome tanto em português quanto em inglês"* — e
       a engine tinha o mesmo problema: a tabela é chaveada em INGLÊS, então
       "Bola de Fogo" não achava Fireball.
Dependências: nenhuma (tabelas puras).
Armadilha: a equivalência é APROXIMAÇÃO declarada, não igualdade. Algumas doem
    de propósito e estão marcadas no módulo — `Phantasmal Force` (nv2) cai em
    `phantasmal-killer` (nv4). É superfície de revisão, não lei.

Exemplo:
    uv run pytest tests/test_magia_bilingue.py -q
"""

from engine.magic.casting import detectar_conjuracao
from engine.magic.equivalencias import EQUIVALENCIA_SRD, equivalente_srd
from engine.magic.resolucao import mecanica_da_magia
from engine.magic.spell_list import SPELLS_POR_CLASSE

_SEM_SRD = [
    "Absorb Elements", "Arms of Hadar", "Blinding Smite", "Cloud of Daggers",
    "Conjure Barrage", "Consecrate", "Dissonant Whispers", "Erupting Earth",
    "Frostbite", "Healing Spirit", "Hex", "Phantasmal Force", "Ray of Sickness",
    "Shadow of Moil", "Snare", "Summon Beast", "Thorn Whip", "Wall of Water",
    "Wrathful Smite",
]


# ── Os dois idiomas resolvem a mesma mecânica ────────────────────────────────


def test_nome_em_portugues_acha_a_mecanica():
    """A ponte que faltava: a tabela é chaveada em INGLÊS."""
    assert mecanica_da_magia("Bola de Fogo")["nome_en"] == "Fireball"
    assert mecanica_da_magia("Curar Ferimentos")["nome_en"] == "Cure Wounds"


def test_nome_em_ingles_continua_achando():
    assert mecanica_da_magia("Fireball")["nome_en"] == "Fireball"


def test_os_dois_idiomas_dao_a_MESMA_mecanica():
    assert mecanica_da_magia("Bola de Fogo") == mecanica_da_magia("Fireball")


def test_deteccao_aceita_os_dois_idiomas():
    ficha = ["Armadura de Hex", "Curar Ferimentos", "Bola de Fogo"]
    assert detectar_conjuracao("eu uso Hex no bandido", ficha) == "Armadura de Hex"
    assert detectar_conjuracao("eu uso Armadura de Hex", ficha) == "Armadura de Hex"
    assert detectar_conjuracao("uso Cure Wounds", ficha) == "Curar Ferimentos"
    assert detectar_conjuracao("casto Fireball", ficha) == "Bola de Fogo"


def test_o_idioma_nao_afrouxa_a_regra_da_declaracao():
    """Nome em inglês sem verbo continua não sendo conjuração."""
    assert detectar_conjuracao("o hex daquele bruxo era famoso", ["Armadura de Hex"]) is None


# ── As 19 ganharam lastro ────────────────────────────────────────────────────


def test_toda_magia_fora_do_srd_tem_equivalencia():
    orfas = [n for n in _SEM_SRD if equivalente_srd(n) is None]
    assert not orfas, f"sem equivalência declarada: {orfas}"


def test_toda_equivalencia_aponta_pra_magia_que_existe():
    """Apontar pra um índice inexistente devolveria None em silêncio — a magia
    voltaria a ser prosa sem ninguém notar."""
    from engine.magic.spell_mechanics import MECANICA_MAGIA

    for origem, destino in EQUIVALENCIA_SRD.items():
        assert destino in MECANICA_MAGIA, f"{origem} → {destino} não existe no SRD"


def test_hex_finalmente_resolve():
    """A magia de assinatura do bruxo. `hunters-mark` é a equivalência mais
    limpa da tabela: marca o alvo e soma dano por ataque, mesmo nível."""
    m = mecanica_da_magia("Hex")
    assert m and m["nome_en"] == "Hunter's Mark"
    assert mecanica_da_magia("Armadura de Hex") == m


def test_nenhuma_magia_da_lista_pt_fica_sem_lastro():
    """O teste que fecha o buraco inteiro: TODA magia jogável resolve."""
    todas = {e.nome_pt for lista in SPELLS_POR_CLASSE.values() for e in lista}
    orfas = sorted(n for n in todas if mecanica_da_magia(n) is None)
    assert not orfas, f"magias sem mecânica: {orfas}"


def test_magia_do_srd_nao_passa_pela_equivalencia():
    """A equivalência é fallback — magia que já está no SRD usa a própria ficha."""
    assert equivalente_srd("Bola de Fogo") is None
    assert equivalente_srd("Fireball") is None
