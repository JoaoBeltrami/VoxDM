"""
P16 passo 1 — a tabela mecânica de magias existe, é local, e o buraco tem NOME.

Por que existe: ADR-007 decidiu que resolução de magia não pode depender de rede
    — a única fonte estruturada era o Qdrant, e `buscar_dados_magia` falha CALADA
    por design. A tabela é artefato de build gerado do 5e-database.
Dependências: nenhuma (dado estático).
Armadilha: o valor deste arquivo não é provar que a tabela está cheia — é impedir
    que ela fique VAZIA EM SILÊNCIO. A lição do BESTIARIO-CR-ERRADO-1 é que uma
    lenda pagando preço de bandido não crasha, não loga erro, e só aparece como
    sensação. Aqui, magia sem entrada mecânica falharia do mesmo jeito.

Exemplo:
    uv run pytest tests/test_spell_mechanics.py -q
"""

from engine.magic.spell_list import SPELLS_POR_CLASSE
from engine.magic.spell_mechanics import MECANICA_MAGIA, POR_NOME_EN

# O SRD 5.1 remove os nomes próprios de mago das magias clássicas. A lista PT-BR
# usa o nome comercial; a tabela usa o do SRD. São a MESMA magia.
ALIASES_SRD: dict[str, str] = {
    "bigby's hand": "arcane hand",
    "melf's acid arrow": "acid arrow",
}

# Magias da lista PT-BR que NÃO existem no SRD 2014 (vêm de Xanathar's/Tasha's).
# Congelado de propósito: o teste falha se a lista CRESCER — magia nova sem
# lastro mecânico é exatamente o que este arquivo existe pra pegar.
#
# ⚠️ CONTEÚDO, não engenharia: o projeto só usa SRD aberto (decisão travada de
# copyright). Que estas 19 estejam em `spell_list.py` é decisão do Beltrami —
# ou saem, ou ficam sabidamente sem resolução mecânica.
SEM_LASTRO_SRD: frozenset[str] = frozenset({
    "Absorb Elements", "Arms of Hadar", "Blinding Smite", "Cloud of Daggers",
    "Conjure Barrage", "Consecrate", "Dissonant Whispers", "Erupting Earth",
    "Frostbite", "Healing Spirit", "Hex", "Phantasmal Force", "Ray of Sickness",
    "Shadow of Moil", "Snare", "Summon Beast", "Thorn Whip", "Wall of Water",
    "Wrathful Smite",
})


def _indice_de(nome_en: str) -> str | None:
    chave = nome_en.lower()
    return POR_NOME_EN.get(ALIASES_SRD.get(chave, chave))


def _todas_pt() -> set[str]:
    return {e.nome_en for lista in SPELLS_POR_CLASSE.values() for e in lista}


# ── A tabela existe e é local ────────────────────────────────────────────────


def test_tabela_tem_o_srd_inteiro():
    assert len(MECANICA_MAGIA) > 300


def test_a_tabela_nao_depende_de_rede():
    """O ponto inteiro do ADR-007: o número que a engine usa é local.

    Checa o CÓDIGO via AST, não o texto — o docstring do módulo MENCIONA o Qdrant
    justamente pra dizer que ele não entra no caminho do número, e um assert
    sobre a string acusaria a própria explicação. (Terceira vez que esta
    armadilha aparece nesta rodada; está no CLAUDE.md.)
    """
    import ast

    import engine.magic.spell_mechanics as mod

    arvore = ast.parse(open(mod.__file__, encoding="utf-8").read())
    proibidos = {"httpx", "requests", "qdrant_client", "aiohttp", "urllib"}
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for a in no.names:
                assert a.name.split(".")[0] not in proibidos, a.name
        elif isinstance(no, ast.ImportFrom):
            assert (no.module or "").split(".")[0] not in proibidos, no.module
        # nada assíncrono: dado estático não espera por ninguém
        assert not isinstance(no, (ast.AsyncFunctionDef, ast.Await))


# ── Cobertura: o buraco tem nome ─────────────────────────────────────────────


def test_toda_magia_pt_br_tem_lastro_ou_esta_na_lista_de_excecoes():
    """O teste obrigatório do P16 passo 1.

    Falha nomeando exatamente quais magias ficaram sem entrada — nunca um
    "algumas não foram encontradas".
    """
    orfas = sorted(
        nome for nome in _todas_pt()
        if _indice_de(nome) is None and nome not in SEM_LASTRO_SRD
    )
    assert not orfas, (
        "Magias na lista PT-BR sem entrada na tabela mecânica e fora da lista de "
        f"exceções conhecidas: {orfas}. Ou entram como alias do SRD, ou entram em "
        "SEM_LASTRO_SRD com a razão — nunca ficam órfãs em silêncio."
    )


def test_as_excecoes_ganharam_equivalencia():
    """09/08: as 19 deixaram de ser débito.

    Decisão do Beltrami — "prefiro ter as magias mesmo que parecidas". Elas
    continuam fora do SRD 2014 (por isso seguem nesta lista), mas agora
    EMPRESTAM mecânica de uma magia equivalente, e o teste passou a exigir isso
    em vez de só congelar o buraco. Ver engine/magic/equivalencias.py.
    """
    from engine.magic.equivalencias import equivalente_srd

    assert len(SEM_LASTRO_SRD) == 19
    sem_mapa = sorted(n for n in SEM_LASTRO_SRD if equivalente_srd(n) is None)
    assert not sem_mapa, f"fora do SRD e sem equivalência: {sem_mapa}"


def test_os_aliases_realmente_resolvem():
    for comercial in ALIASES_SRD:
        assert _indice_de(comercial) is not None, comercial


def test_a_maioria_das_magias_pt_br_tem_lastro():
    """Sanidade da junção: se o casamento quebrar, isto cai de ~87% pra zero."""
    todas = _todas_pt()
    com_lastro = [n for n in todas if _indice_de(n) is not None]
    assert len(com_lastro) / len(todas) > 0.8


# ── Os campos que a resolução vai consumir ───────────────────────────────────


def test_vocabulario_de_resolucao_e_fechado():
    assert {v["resolucao"] for v in MECANICA_MAGIA.values()} <= {
        "ataque", "resistencia", "nenhum"
    }


def test_magia_de_ataque_conhecida():
    """Fire Bolt: o conjurador rola o ataque (decisão 3 do ADR-007)."""
    m = MECANICA_MAGIA["fire-bolt"]
    assert m["resolucao"] == "ataque"
    assert m["dano"]["tipo"] == "Fire"
    assert m["dano"]["escala_por"] == "nivel_personagem"   # truque não gasta slot


def test_magia_de_resistencia_conhecida():
    """Bola de Fogo: o ALVO resiste, e metade do dano passa em sucesso."""
    m = MECANICA_MAGIA["fireball"]
    assert m["resolucao"] == "resistencia"
    assert m["save_atributo"] == "DEX"
    assert m["save_sucesso"] == "half"
    assert m["dano"]["por"]["3"] == "8d6"
    assert m["dano"]["escala_por"] == "slot"


def test_magia_de_cura_conhecida():
    """Curar Ferimentos: é daqui que sai o número que hoje o LLM inventa."""
    m = MECANICA_MAGIA["cure-wounds"]
    assert m["cura"]["1"].startswith("1d8")
    assert not m["dano"]


def test_concentracao_e_apenas_registrada():
    """O ADR deixou concentração FORA do escopo. O campo existe como dado, mas
    nada o consome ainda — registrar o débito é diferente de implementá-lo."""
    assert MECANICA_MAGIA["bless"]["concentracao"] is True
