"""
Testes da heuristica _inferir_genero_por_nome em voice_registry.

Cobre os casos do modulo 'Os Filhos de Valdrek' + fallback hash.
"""

import pytest

from engine.voice.voice_registry import (
    _inferir_genero_por_nome,
    selecionar_perfil,
)


@pytest.mark.parametrize("npc_id,raca,esperado", [
    # Patronimico nordico explicito
    ("aldric-drevasson", "humano", "male"),
    ("bjorn-tharnsson", "humano", "male"),
    ("torvin-kaelsson", "humano", "male"),
    ("fael-drevasson", "humano", "male"),
    # Matronimico nordico
    ("maren-drevadottir", "humana", "female"),
    ("runa-tharnsdottir", "humana", "female"),
    ("senna-kaeldottir", "humana", "female"),
    # Sufixo PT da raca (sem patronimico)
    ("yrsa-a-curandeira", "humana", "female"),
    ("edda-a-velha", "humana", "female"),
    ("liiv", "humana", "female"),
    ("halvard-o-cinza", "goliath", ""),  # raca neutra + sem patronimico → sem inferencia
    # Casos sem sinal claro
    ("mundr", "gigante das colinas", ""),
    ("vyrmathax", "dragao", ""),
])
def test_inferir_genero_por_nome(npc_id, raca, esperado):
    from engine.voice.voice_registry import _normalizar
    raca_norm = _normalizar(raca)
    assert _inferir_genero_por_nome(npc_id, raca_norm) == esperado


def test_selecionar_perfil_usa_heuristica_quando_genero_vazio():
    """Sem gender explicito, heuristica de nome determina voz feminina."""
    perfil = selecionar_perfil("maren-drevadottir", genero="", raca="humana")
    # Voz feminina pt-BR
    assert perfil["voz"] in ("pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural")


def test_selecionar_perfil_metadata_explicita_ganha_da_heuristica():
    """Se gender vier explicito, ignora heuristica."""
    # Nome 'sson' sugere male, mas gender explicito female ganha
    perfil = selecionar_perfil("torstein-sson-trap", genero="female", raca="humano")
    assert perfil["voz"] in ("pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural")


def test_selecionar_perfil_aldric_voz_masculina():
    """Smoke test do caso real do log de 27/05."""
    perfil = selecionar_perfil("aldric-drevasson", genero="", raca="humano")
    assert perfil["voz"] == "pt-BR-AntonioNeural"


def test_selecionar_perfil_maren_voz_feminina():
    perfil = selecionar_perfil("maren-drevadottir", genero="", raca="humana")
    assert perfil["voz"] in ("pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural")
