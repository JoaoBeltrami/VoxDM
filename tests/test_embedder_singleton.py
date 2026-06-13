"""
Testes do singleton process-wide do Embedder (ingestor/embedder.py).

Regressão do teste ao vivo #4 (13/06): o SentenceTransformer recarregava (~3s de
stall) no meio da sessão porque cada QdrantMemoryClient (context_builder,
bestiário, session_writer…) criava um Embedder com seu PRÓPRIO modelo. O fix é um
singleton de módulo — o modelo carrega uma única vez por processo. Estes testes
usam um SentenceTransformer falso (sem baixar/carregar os ~90MB reais).
"""

from typing import Any

import numpy as np
import pytest

import ingestor.embedder as emb_mod
from ingestor.embedder import Embedder


class _FakeModel:
    """SentenceTransformer falso — conta instanciações e devolve vetores zerados."""

    instancias = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _FakeModel.instancias += 1

    def encode(self, textos: list[str], **kwargs: Any) -> np.ndarray:
        return np.zeros((len(textos), emb_mod.VECTOR_SIZE), dtype=np.float32)


@pytest.fixture
def fake_st(monkeypatch: pytest.MonkeyPatch):
    """Reseta o singleton global e troca SentenceTransformer pelo falso."""
    _FakeModel.instancias = 0
    monkeypatch.setattr(emb_mod, "_modelo_global", None)
    monkeypatch.setattr(emb_mod, "_device_global", "desconhecido")
    monkeypatch.setattr(emb_mod, "SentenceTransformer", _FakeModel)
    yield
    # monkeypatch restaura _modelo_global/_device_global/SentenceTransformer ao sair


def test_modelo_carrega_uma_vez_entre_instancias(fake_st):
    """Várias instâncias de Embedder compartilham UM modelo — carregado 1×."""
    e1 = Embedder()
    e2 = Embedder()
    e3 = Embedder()
    e1.gerar(["a"])
    e2.gerar(["b"])
    e3.gerar(["c"])
    e1.gerar(["d"])
    assert _FakeModel.instancias == 1  # singleton process-wide


def test_device_propagado_para_instancia(fake_st):
    """Após o load, a instância reflete o device do modelo global (CUDA tentado 1º)."""
    e = Embedder()
    e.gerar(["x"])
    assert e.device == "cuda"  # _FakeModel não levanta no device="cuda"


def test_gerar_sem_textos_nao_carrega_modelo(fake_st):
    """Lista vazia retorna cedo sem instanciar o modelo (atalho de performance)."""
    e = Embedder()
    out = e.gerar([])
    assert out.shape == (0, emb_mod.VECTOR_SIZE)
    assert _FakeModel.instancias == 0
