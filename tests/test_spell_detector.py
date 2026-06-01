"""Testes para engine/magic/spell_detector.py."""

import pytest

from engine.magic.spell_detector import (
    _RE_CASTING,
    extrair_nome_magia,
    formatar_bloco_magia,
)

# ── Testes do regex _RE_CASTING ───────────────────────────────────────────────

def test_extrair_nome_corta_stopwords_alvo():
    """Bug #15: 'lanço meu olhar para o orc' não vira nome de magia."""
    nome = extrair_nome_magia("Lanço meu olhar para o orc")
    # "meu" é stopword → nome resulta vazio (<3 chars) → None
    assert nome is None


def test_extrair_nome_corta_em_preposicao():
    """Bug #15: 'lanço bola de fogo no grupo' → 'Bola de Fogo'."""
    nome = extrair_nome_magia("Lanço Bola de Fogo no grupo")
    assert nome is not None
    assert nome.lower() == "bola de fogo"


def test_extrair_nome_preserva_de_no_meio():
    """'Bola de Fogo' precisa preservar 'de' — não pode ser stopword."""
    nome = extrair_nome_magia("Conjuro Bola de Fogo")
    assert nome is not None
    assert "de" in nome.lower()


def test_re_casting_detecta_lanco():
    assert _RE_CASTING.search("Lanço Bola de Fogo!")


def test_re_casting_detecta_conjuro():
    assert _RE_CASTING.search("Conjuro Missil Mágico")


def test_re_casting_detecta_uso_a_magia():
    assert _RE_CASTING.search("Uso a magia de cura no aliado")


def test_re_casting_detecta_casto():
    assert _RE_CASTING.search("Casto Escudo de Fé sobre mim")


def test_re_casting_nao_dispara_sem_magia():
    assert not _RE_CASTING.search("Ataco o goblin com minha espada")


def test_re_casting_nao_dispara_em_dialogo_comum():
    assert not _RE_CASTING.search("Pergunto ao ferreiro sobre as ruínas")


def test_re_casting_case_insensitive():
    assert _RE_CASTING.search("LANÇO FIREBALL")
    assert _RE_CASTING.search("conjuro missil mágico")


# ── Testes de extrair_nome_magia ──────────────────────────────────────────────

def test_extrair_nome_lanco():
    nome = extrair_nome_magia("Lanço Bola de Fogo no grupo")
    assert nome is not None
    assert "Bola de Fogo" in nome


def test_extrair_nome_conjuro():
    nome = extrair_nome_magia("Conjuro Missil Mágico")
    assert nome is not None
    assert len(nome) > 2


def test_extrair_nome_sem_casting_retorna_none():
    assert extrair_nome_magia("Ataco o goblin") is None


def test_extrair_nome_dialogo_retorna_none():
    assert extrair_nome_magia("Pergunto ao NPC sobre a quest") is None


def test_extrair_nome_strip_pontuacao():
    nome = extrair_nome_magia("Lanço Bola de Fogo!")
    assert nome is not None
    # Nome não deve terminar com pontuação
    assert nome[-1] not in ".!,?"


def test_extrair_nome_minimo_3_chars():
    # "lanço o" → artigo isolado, deve retornar None
    resultado = extrair_nome_magia("lanço o")
    # Se retornar algo, deve ter pelo menos 3 chars
    if resultado is not None:
        assert len(resultado) >= 3


# ── Testes de formatar_bloco_magia ────────────────────────────────────────────

def test_formatar_bloco_magia_campos_basicos():
    dados = {"nome": "Fireball", "nivel": 3, "escola": "Evocação"}
    bloco = formatar_bloco_magia(dados)
    assert "Fireball" in bloco
    assert "3" in bloco


def test_formatar_bloco_magia_com_dano():
    dados = {"nome": "Fireball", "nivel": 3, "dano": "8d6 fogo", "cd_save": "DES DC 14"}
    bloco = formatar_bloco_magia(dados)
    assert "8d6" in bloco
    assert "DES" in bloco


def test_formatar_bloco_magia_sem_nivel_usa_truque():
    dados = {"nome": "Prestidigitação", "nivel": 0}
    bloco = formatar_bloco_magia(dados)
    assert "truque" in bloco.lower()


def test_formatar_bloco_magia_omite_campos_ausentes():
    dados = {"nome": "Missil Mágico", "nivel": 1}
    bloco = formatar_bloco_magia(dados)
    # Sem dano nem save: não deve ter "|" extras soltos
    assert "Missil Mágico" in bloco
    assert "nível 1" in bloco


def test_formatar_bloco_magia_todos_os_campos():
    dados = {
        "nome": "Fireball",
        "nivel": 3,
        "escola": "Evocação",
        "alcance": "150ft",
        "duracao": "Instantânea",
        "dano": "8d6 fogo",
        "cd_save": "DES DC 14",
    }
    bloco = formatar_bloco_magia(dados)
    assert "Fireball" in bloco
    assert "150ft" in bloco
    assert "8d6" in bloco
    assert "DES DC 14" in bloco
    assert "Instantânea" in bloco


def test_formatar_bloco_magia_prefixo_icone():
    dados = {"nome": "Cura", "nivel": 1}
    bloco = formatar_bloco_magia(dados)
    assert bloco.startswith("⚡ MAGIA:")
