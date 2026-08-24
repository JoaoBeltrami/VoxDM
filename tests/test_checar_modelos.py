"""
O vigia de modelo: hábito escrito não roda; script roda.

Por que existe (MODELO-DESLIGADO-1, 17/08/2026): o Groq desligou a família Llama
    de chat e o primário do projeto foi junto. O CLAUDE.md já mandava "conferir
    deprecations a cada /estado" — e isso não impediu nada, porque só existia
    como frase. `scripts/checar_modelos.py` transforma a frase em exit code.
Dependências: nenhuma — a função exercitada é PURA, sem rede.
Armadilha: o teste de "não tem literal de modelo no arquivo" tem que olhar o
    AST, não o texto. O docstring do script CITA `llama-3.1-8b-instant` para
    explicar o incidente, e um `assert "llama" not in fonte` falharia na própria
    explicação — a família de erro que já mordeu 4× neste projeto.

Exemplo:
    uv run pytest tests/test_checar_modelos.py -q
"""

import ast
import pathlib

from config import settings
from scripts.checar_modelos import comparar, modelos_configurados

_FONTE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "checar_modelos.py"


def test_acusa_modelo_que_sumiu_da_conta():
    """O caso real de 17/08: o primário deixou de existir e nada avisava."""
    configurados = {"groq-principal": "llama-3.3-70b-versatile", "groq-leve": "openai/gpt-oss-20b"}
    disponiveis = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]

    ausentes = comparar(configurados, disponiveis)

    assert ausentes == [("groq-principal", "llama-3.3-70b-versatile")]


def test_silencio_quando_esta_tudo_certo():
    configurados = {"groq-principal": "openai/gpt-oss-120b", "groq-leve": "openai/gpt-oss-20b"}
    disponiveis = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    assert comparar(configurados, disponiveis) == []


def test_slot_sem_modelo_nao_vira_falso_positivo():
    """Gemini e Ollama não têm modelo fixo em `modelo_do_slot` — devolvem "".

    Sem este guard, um slot vazio seria reportado como "modelo ausente" e o
    vigia gritaria todo dia por nada. Vigia que grita à toa é vigia desligado.
    """
    assert comparar({"gemini-flash": ""}, ["openai/gpt-oss-120b"]) == []


def test_le_o_modelo_da_mesma_fonte_que_o_router():
    """Se este script tivesse a própria lista, ela mentiria na próxima troca."""
    configurados = modelos_configurados()

    assert configurados["groq-principal"] == settings.GROQ_MODEL
    assert configurados["groq-leve"] == settings.GROQ_MODEL_FALLBACK
    assert all(configurados.values()), "slot Groq sem modelo configurado"


def test_nenhum_nome_de_modelo_escrito_a_mao_no_CODIGO():
    """A quarta cópia da configuração de modelo não pode nascer aqui.

    Olha o AST e ignora docstrings de propósito: o docstring do script cita o
    modelo desligado para explicar o incidente, e checar o TEXTO acusaria a
    própria explicação (já aconteceu 4× neste projeto).
    """
    arvore = ast.parse(_FONTE.read_text(encoding="utf-8"))

    # Constantes de string que são DOCSTRING ficam de fora: são `Expr` soltos.
    docstrings = {
        id(no.value)
        for no in ast.walk(arvore)
        if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant)
    }
    suspeitas = [
        no.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant)
        and isinstance(no.value, str)
        and id(no) not in docstrings
        and any(marca in no.value.lower() for marca in ("llama", "gpt-oss", "qwen"))
    ]

    assert not suspeitas, f"nome de modelo escrito à mão no código: {suspeitas}"
