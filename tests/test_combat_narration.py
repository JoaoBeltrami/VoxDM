"""
Testes do formatador de contexto da engine de combate (engine/combat/narration.py).

Garante que as linhas "ENGINE: ..." que o LLM narra batem com o resultado mecânico
real (acerto/erro/crit/falha, dano/estado/morte, turno dos inimigos) e que o nome
do alvo entra sem artigo (gênero-safe). Puro — sem WM, sem IO.
"""

from engine.combat.narration import (
    linha_ataque_jogador,
    linha_dano_jogador,
    linha_turno_inimigos,
)
from engine.combat.resolver import ResultadoAtaque

# ── Ataque do jogador ─────────────────────────────────────────────────────────


def test_ataque_acerto():
    r = ResultadoAtaque(acertou=True, total=19, ca_alvo=15, critico=False, falha_critica=False)
    linha = linha_ataque_jogador("Goblin", r)
    assert linha.startswith("ENGINE:")
    assert "ACERTOU" in linha and "Goblin" in linha
    assert "19" in linha and "15" in linha


def test_ataque_erro():
    r = ResultadoAtaque(acertou=False, total=11, ca_alvo=15, critico=False, falha_critica=False)
    linha = linha_ataque_jogador("Goblin", r)
    assert "ERROU" in linha and "11" in linha and "15" in linha


def test_ataque_critico():
    r = ResultadoAtaque(acertou=True, total=22, ca_alvo=15, critico=True, falha_critica=False)
    linha = linha_ataque_jogador("Goblin", r)
    assert "CRÍTICO" in linha and "natural 20" in linha


def test_ataque_falha_critica():
    r = ResultadoAtaque(acertou=False, total=3, ca_alvo=15, critico=False, falha_critica=True)
    linha = linha_ataque_jogador("Goblin", r)
    assert "FALHA CRÍTICA" in linha and "natural 1" in linha


def test_alvo_sem_artigo_genero_safe():
    """Nome do alvo nunca recebe artigo 'o '/'a ' (evita mis-gender Loba/Goblin)."""
    r = ResultadoAtaque(acertou=True, total=18, ca_alvo=13, critico=False, falha_critica=False)
    linha = linha_ataque_jogador("Loba", r)
    assert "ACERTOU Loba" in linha
    assert "ACERTOU o Loba" not in linha and "ACERTOU a Loba" not in linha


def test_alvo_vazio_usa_fallback():
    r = ResultadoAtaque(acertou=True, total=18, ca_alvo=13, critico=False, falha_critica=False)
    linha = linha_ataque_jogador("", r)
    assert "o alvo" in linha


# ── Dano do jogador ───────────────────────────────────────────────────────────


def test_dano_com_estado():
    linha = linha_dano_jogador("Goblin", 7, "cambaleando")
    assert "7 de dano" in linha and "Goblin" in linha and "cambaleando" in linha


def test_dano_morte():
    linha = linha_dano_jogador("Goblin", 12, "morto")
    assert "12 de dano" in linha and "sem vida" in linha
    assert "agora morto" not in linha  # morte tem frase própria


def test_dano_sem_estado():
    linha = linha_dano_jogador("Goblin", 4, "")
    assert "4 de dano em Goblin" in linha
    assert "agora" not in linha


def test_dano_negativo_clampa_zero():
    linha = linha_dano_jogador("Goblin", -5, "ferido")
    assert "0 de dano" in linha


# ── Turno dos inimigos ────────────────────────────────────────────────────────


def test_turno_inimigos_misto():
    res = {
        "dano_total": 5,
        "hp_jogador": 12,
        "ataques": [
            {"id": "g1", "nome": "Goblin", "acertou": True, "critico": False, "dano": 5},
            {"id": "l1", "nome": "Lobo", "acertou": False, "critico": False, "dano": 0},
        ],
    }
    linha = linha_turno_inimigos(res)
    assert "Goblin acertou" in linha and "5 de dano" in linha
    assert "Lobo errou" in linha
    assert "Seu HP: 12" in linha


def test_turno_inimigos_critico():
    res = {
        "hp_jogador": 8,
        "ataques": [{"id": "g1", "nome": "Ogro", "acertou": True, "critico": True, "dano": 14}],
    }
    linha = linha_turno_inimigos(res)
    assert "Ogro acertou crítico" in linha and "14 de dano" in linha


def test_turno_inimigos_vazio():
    linha = linha_turno_inimigos({"ataques": []})
    assert "nenhum inimigo vivo" in linha


def test_turno_inimigos_sem_hp_nao_quebra():
    res = {"ataques": [{"id": "g1", "nome": "Goblin", "acertou": False}]}
    linha = linha_turno_inimigos(res)
    assert "Goblin errou" in linha
    assert "Seu HP" not in linha


def test_turno_inimigos_fallback_id_sem_nome():
    res = {"ataques": [{"id": "guarda-2", "acertou": True, "dano": 3}]}
    linha = linha_turno_inimigos(res)
    assert "guarda-2 acertou" in linha
