"""
Testes do repetition guard SENSORIAL — REPETICAO-FRIO (23/06).

Garante que imagens de clima/ambiente que o Mestre usa ("frio cortante da
noite") são detectadas, acumuladas com cap/dedup e injetadas no prompt como
"AMBIENTAÇÃO JÁ DESCRITA" pra ele variar. Espelha o mecanismo de fatos_ancora.
"""

import pytest

from api.turn_pipeline import aplicar_pos_turno, extrair_imagens_ambiente
from engine.llm.prompt_builder import (
    ContextoMontado,
    invalidar_cache,
    montar_mensagens,
)
from engine.memory.working_memory import WorkingMemory


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao("vila", "Vila", "sess-amb")


def _contexto(wm: WorkingMemory) -> ContextoMontado:
    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual="Eu olho ao redor",
    )


# ── extrair_imagens_ambiente ────────────────────────────────────────────────

def test_extrai_imagem_de_frio():
    out = extrair_imagens_ambiente("O frio cortante da noite morde a pele.")
    assert out == ["O frio cortante da noite morde a pele"]


@pytest.mark.parametrize("frase", [
    "O cheiro de sal e peixe enche o ar.",
    "Uma névoa densa cobre o porto.",
    "O vento gelado uiva entre as árvores.",
    "O silêncio pesa na sala escura.",
])
def test_extrai_varias_imagens_sensoriais(frase):
    assert extrair_imagens_ambiente(frase), f"não detectou ambiente em: {frase}"


def test_ignora_frase_sem_keyword_ambiente():
    assert extrair_imagens_ambiente("Aldric saca a espada e avança contra o orc.") == []


def test_ignora_frase_longa_de_acao():
    # > 12 palavras → provavelmente ação/diálogo, não imagem de ambiente curta.
    longa = (
        "O frio estava presente quando ele decidiu correr pela ponte velha "
        "perseguindo o ladrão que havia roubado a bolsa da velha senhora ali"
    )
    assert extrair_imagens_ambiente(longa) == []


def test_dedup_de_imagem_repetida_na_mesma_narracao():
    texto = "O frio cortante da noite. Ele anda. O frio cortante da noite."
    assert extrair_imagens_ambiente(texto) == ["O frio cortante da noite"]


def test_separa_por_pontuacao_forte():
    texto = "O frio morde. O cheiro de mofo sobe das tábuas."
    out = extrair_imagens_ambiente(texto)
    assert len(out) == 2


# ── registrar_ambiente (cap + dedup) ────────────────────────────────────────

def test_registrar_ambiente_dedup():
    wm = _wm()
    assert wm.registrar_ambiente("frio cortante") is True
    assert wm.registrar_ambiente("frio cortante") is False
    assert wm.ambiente_recente == ["frio cortante"]


def test_registrar_ambiente_cap_rolling():
    wm = _wm()
    for i in range(8):
        wm.registrar_ambiente(f"imagem {i}")
    # _MAX_AMBIENTE = 4 — só as mais recentes sobrevivem
    assert len(wm.ambiente_recente) == 4
    assert wm.ambiente_recente == ["imagem 4", "imagem 5", "imagem 6", "imagem 7"]


# ── integração: aplicar_pos_turno registra o ambiente ───────────────────────

def test_pos_turno_registra_ambiente():
    wm = _wm()
    aplicar_pos_turno(wm, "", "O frio cortante da noite morde. Você avança.")
    assert any("frio cortante" in a.lower() for a in wm.ambiente_recente)


def test_pos_turno_sem_ambiente_nao_registra():
    wm = _wm()
    aplicar_pos_turno(wm, "", "Aldric assente e te entrega a carta.")
    assert wm.ambiente_recente == []


# ── injeção no prompt ───────────────────────────────────────────────────────

def test_injeta_ambientacao_ja_descrita():
    invalidar_cache()
    wm = _wm()
    wm.registrar_ambiente("o frio cortante da noite")
    system = montar_mensagens(_contexto(wm))[0]["content"]
    # Header único da SEÇÃO injetada (o texto da regra no master_system.md também
    # menciona a frase, então casamos o marcador "===" pra não confundir).
    assert "=== AMBIENTAÇÃO JÁ DESCRITA" in system
    assert "o frio cortante da noite" in system


def test_sem_ambiente_nao_injeta_secao():
    invalidar_cache()
    wm = _wm()
    system = montar_mensagens(_contexto(wm))[0]["content"]
    assert "=== AMBIENTAÇÃO JÁ DESCRITA" not in system


# ── instrução na seção dinâmica (não no master sempre-presente — dieta) ──────

def test_secao_ambiente_carrega_instrucao_de_variar():
    # A instrução anti-repetição vive na SEÇÃO injetada (custo zero quando não há
    # repetição) — não no master_system.md sempre-presente, pra respeitar o budget.
    invalidar_cache()
    wm = _wm()
    wm.registrar_ambiente("o frio cortante da noite")
    system = montar_mensagens(_contexto(wm))[0]["content"]
    assert "varie a descrição ou apenas avance" in system.lower()
