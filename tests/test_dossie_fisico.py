"""
Camada 1-B (ADR-005, grill 23/07): NPC mostra emoção pelo corpo, não rotula.

Por que existe: a queixa "NPCs muito iguais" + o tell ranqueado como PIOR — o
    Mestre nomeava a emoção ("com uma mistura de curiosidade e desconfiança") em
    vez de mostrar pelo corpo. O dossiê gera traços distintos, mas eles só
    chegavam ao caminho legado; no BRIEF (produção) o Mestre não os via.
Dependências: nenhuma — puro sobre a WorkingMemory.
"""

from engine.llm.prompt_builder import (
    ContextoMontado,
    _montar_mensagens_brief,
)
from engine.memory.working_memory import WorkingMemory
from engine.npc.dossie import _SYSTEM_DOSSIE, aplicar_dossie, bloco_dossie
from engine.npc.identity import registrar_npc


def _wm_com_npc(tracos):
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.npcs_presentes = ["bjorn-tharnsson"]
    registrar_npc(wm, "bjorn-tharnsson", "Bjorn")
    wm.scene.npcs_apresentados = {"bjorn-tharnsson"}
    aplicar_dossie(wm, "bjorn-tharnsson", tracos)
    return wm


def test_bloco_dossie_lista_tracos_e_proibe_rotular():
    wm = _wm_com_npc(["nunca larga o copo", "fala olhando pro chão"])
    bloco = bloco_dossie(wm, wm.npcs_presentes, lambda i: "Bjorn")
    assert "nunca larga o copo" in bloco
    assert "nunca rotule" in bloco.lower() or "nunca nomeie" in bloco.lower()


def test_regra_vale_mesmo_sem_dossie_ainda():
    """Medição 24/07 (benchmark/run_tells): o dossiê nasce no 1º encontro e só
    chega ao prompt no turno SEGUINTE. Se a regra dependesse dos traços, os
    primeiros turnos com um NPC novo — quando a impressão se forma — ficariam
    sem ela, e a emoção voltava rotulada. Regra sempre; traços quando houver."""
    wm = WorkingMemory.nova_sessao("k", "K", "s")
    wm.npcs_presentes = ["mira"]
    registrar_npc(wm, "mira", "Mira")
    wm.scene.npcs_apresentados = {"mira"}
    bloco = bloco_dossie(wm, wm.npcs_presentes)
    assert "nunca rotule" in bloco.lower()
    assert "•" not in bloco          # sem traços listados — só a regra


def test_bloco_vazio_sem_npc_em_cena():
    """Cena sem ninguém não paga o bloco — custo-zero."""
    wm = WorkingMemory.nova_sessao("k", "K", "s")
    assert bloco_dossie(wm, []) == ""


def test_bloco_dossie_pula_npc_nao_apresentado():
    wm = _wm_com_npc(["nunca larga o copo"])
    wm.scene.npcs_apresentados = set()   # presente mas não apresentado
    assert bloco_dossie(wm, wm.npcs_presentes) == ""


def test_tracos_chegam_ao_prompt_do_brief():
    """O gap principal: os traços viviam só no legado. Agora no brief (produção)."""
    wm = _wm_com_npc(["aperta o cabo da faca ao mentir", "bigode espesso"])
    ctx = ContextoMontado(
        working_memory=wm, chunks_semanticos=[], chunks_episodicos=[],
        chunks_regras=[], relacoes_grafo=[], secrets_visiveis=[],
        transcricao_atual="Pergunto ao Bjorn sobre a guerra",
    )
    system = _montar_mensagens_brief(ctx)[0]["content"]
    assert "aperta o cabo da faca" in system
    assert "mostre" in system.lower() and "corpo" in system.lower()


def test_gerador_de_dossie_pede_traço_fisico_proibe_emocao_rotulada():
    assert "FÍSICO" in _SYSTEM_DOSSIE or "físic" in _SYSTEM_DOSSIE.lower()
    assert "rotular emoção" in _SYSTEM_DOSSIE.lower() or "olhar de gratidão" in _SYSTEM_DOSSIE


def test_master_system_tem_as_regras_de_show_dont_tell_e_nao_narrar_de_volta():
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "engine" / "llm" / "prompts" / "master_system.md"
    md = p.read_text(encoding="utf-8")
    # Tell B: proibido nomear a emoção
    assert "ROTULE" in md or "rotule" in md
    assert "curiosidade e desconfiança" in md   # o exemplo-tell literal
    # Tell A: não renarrar a ação do jogador
    assert "REAÇÃO do mundo" in md
    assert "entrega o aço" in md   # o exemplo-tell literal
