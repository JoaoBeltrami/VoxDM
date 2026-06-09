"""Testes do marker [CENA: local-id|Nome|hora] — atualização de cena ao vivo.

Por que existe: bug CENA-1 (varredura 08/06) — durante o jogo ao vivo, o estado
de cena (location_id/nome, time_of_day, npcs_presentes) congelava no valor da
criação da sessão. Sem um canal para o LLM declarar mudança de local, os NPCs
iniciais "perseguiam" o jogador pelo mapa e o gating de NARRATIVE_LIGHT nunca
disparava (npcs_presentes nunca esvaziava). O marker [CENA] dá esse canal.

Dependências: pytest, pytest-asyncio (parte de re-inferência).
Armadilha: a parte SYNC (aplicar local/hora) roda em aplicar_pos_turno; a parte
ASYNC (re-inferir NPCs no Neo4j) roda em reinferir_npcs_se_mudou_cena, chamada
pelo caller (WS/REST) após o pipeline. O flag cena_mudou_local liga as duas.
"""

import pytest

from api.turn_pipeline import (
    _RE_CENA,
    aplicar_pos_turno,
    reinferir_npcs_se_mudou_cena,
)
from engine.memory.quest_detector import strip_marcadores
from engine.memory.working_memory import WorkingMemory


def _wm() -> WorkingMemory:
    """WM numa vila, fora de combate, com NPCs iniciais."""
    wm = WorkingMemory.nova_sessao("taverna-javali", "Taverna do Javali", "sess-test")
    wm.npcs_presentes = ["aldric", "maren"]
    wm.npcs_apresentados = {"aldric", "maren"}
    return wm


# ── Regex ────────────────────────────────────────────────────────────────────


def test_regex_formato_completo():
    m = _RE_CENA.search("[CENA: mina-abandonada|Mina Abandonada|noite]")
    assert m is not None
    assert m.group(1) == "mina-abandonada"
    assert m.group(2) == "Mina Abandonada"
    assert m.group(3) == "noite"


def test_regex_sem_hora():
    m = _RE_CENA.search("[CENA: floresta-negra|Floresta Negra]")
    assert m is not None
    assert m.group(1) == "floresta-negra"
    assert m.group(2) == "Floresta Negra"
    assert m.group(3) is None


def test_regex_case_insensitive():
    assert _RE_CENA.search("[cena: cripta|Cripta|madrugada]") is not None


def test_regex_no_meio_da_narrativa():
    texto = (
        "Você empurra a porta pesada e desce os degraus de pedra. "
        "[CENA: mina-abandonada|Mina Abandonada|noite] "
        "O cheiro de mofo e enxofre toma o ar."
    )
    m = _RE_CENA.search(texto)
    assert m is not None
    assert m.group(1) == "mina-abandonada"


# ── SceneState.aplicar_cena / consumir_cena_mudou ─────────────────────────────


def test_aplicar_cena_muda_local_seta_flag():
    wm = _wm()
    mudou = wm.scene.aplicar_cena("mina-abandonada", "Mina Abandonada", "noite")
    assert mudou is True
    assert wm.location_id == "mina-abandonada"
    assert wm.location_nome == "Mina Abandonada"
    assert wm.time_of_day == "noite"
    assert wm.scene.cena_mudou_local is True


def test_aplicar_cena_mesmo_local_so_atualiza_hora():
    wm = _wm()
    # Mesmo local (id igual), só anoiteceu — não deve sinalizar re-inferência.
    mudou = wm.scene.aplicar_cena("taverna-javali", "Taverna do Javali", "madrugada")
    assert mudou is False
    assert wm.time_of_day == "madrugada"
    assert wm.scene.cena_mudou_local is False


def test_aplicar_cena_id_vazio_e_noop():
    wm = _wm()
    assert wm.scene.aplicar_cena("", "Nada", "dia") is False
    assert wm.location_id == "taverna-javali"


def test_consumir_cena_mudou_e_one_shot():
    wm = _wm()
    wm.scene.aplicar_cena("cripta", "Cripta")
    assert wm.scene.consumir_cena_mudou() is True
    # Segunda leitura já vem False (resetado)
    assert wm.scene.consumir_cena_mudou() is False


# ── Integração com aplicar_pos_turno ──────────────────────────────────────────


def test_pos_turno_aplica_cena_do_marker():
    wm = _wm()
    aplicar_pos_turno(
        wm,
        "Vou descer para a mina.",
        "Você desce os degraus úmidos. [CENA: mina-abandonada|Mina Abandonada|noite] "
        "A escuridão engole a luz da tocha.",
    )
    assert wm.location_id == "mina-abandonada"
    assert wm.location_nome == "Mina Abandonada"
    assert wm.time_of_day == "noite"
    assert wm.scene.cena_mudou_local is True  # sinalizado p/ re-inferência


def test_pos_turno_mudar_local_encerra_combate():
    wm = _wm()
    wm.entrar_combate()
    assert wm.em_combate
    aplicar_pos_turno(
        wm,
        "Fujo escada acima.",
        "Você dispara pelas escadas e fecha a porta atrás de si. "
        "[CENA: salao-superior|Salão Superior|noite] O barulho fica para trás.",
    )
    assert not wm.em_combate  # encontro ficou para trás
    assert wm.location_id == "salao-superior"


def test_pos_turno_mesmo_local_nao_encerra_combate():
    wm = _wm()
    wm.entrar_combate()
    aplicar_pos_turno(
        wm,
        "ataco o goblin",
        "O golpe acerta. [CENA: taverna-javali|Taverna do Javali|noite] O goblin recua.",
    )
    # Mesmo local → combate continua
    assert wm.em_combate


def test_cena_removido_do_texto_de_voz():
    """Marker [CENA] não pode chegar ao TTS."""
    texto = "Você entra na cripta. [CENA: cripta|Cripta|madrugada] O frio sobe pelos pés."
    limpo = strip_marcadores(texto)
    assert "[CENA" not in limpo
    assert "cripta|" not in limpo
    assert "Você entra na cripta." in limpo
    assert "O frio sobe pelos pés." in limpo


# ── reinferir_npcs_se_mudou_cena (parte async) ────────────────────────────────


class _FakeContextBuilder:
    """Stub que registra a chamada e devolve NPCs fixos do novo local."""

    def __init__(self, npcs: list[str] | None = None, *, falha: bool = False):
        self._npcs = npcs or []
        self._falha = falha
        self.chamado_com: str | None = None

    async def inferir_npcs_presentes(self, location_id: str) -> list[str]:
        self.chamado_com = location_id
        if self._falha:
            raise RuntimeError("neo4j offline")
        return self._npcs


@pytest.mark.asyncio
async def test_reinferir_atualiza_npcs_quando_cena_mudou():
    wm = _wm()
    wm.scene.aplicar_cena("mina-abandonada", "Mina Abandonada", "noite")
    cb = _FakeContextBuilder(["kael-mineiro"])
    await reinferir_npcs_se_mudou_cena(wm, cb)
    assert cb.chamado_com == "mina-abandonada"
    assert wm.npcs_presentes == ["kael-mineiro"]  # NPCs antigos não perseguem mais
    assert wm.scene.cena_mudou_local is False  # flag consumido


@pytest.mark.asyncio
async def test_reinferir_noop_sem_mudanca_de_cena():
    wm = _wm()
    cb = _FakeContextBuilder(["nao-deveria-aparecer"])
    await reinferir_npcs_se_mudou_cena(wm, cb)
    assert cb.chamado_com is None  # Neo4j não foi tocado
    assert wm.npcs_presentes == ["aldric", "maren"]  # inalterado


@pytest.mark.asyncio
async def test_reinferir_silencioso_com_neo4j_offline():
    wm = _wm()
    wm.scene.aplicar_cena("mina-abandonada", "Mina Abandonada")
    cb = _FakeContextBuilder(falha=True)
    # Não deve levantar — degradação graciosa (mantém NPCs antigos).
    await reinferir_npcs_se_mudou_cena(wm, cb)
    assert wm.npcs_presentes == ["aldric", "maren"]
    assert wm.scene.cena_mudou_local is False  # flag consumido mesmo em falha
