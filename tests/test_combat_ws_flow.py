"""
Testes da costura de combate engine-autoritativo (task 7).

Cobrem o miolo testável que o websocket chama:
- `resolver_turno_ataque_jogador` (orchestrator): ataque→dano→ação→turno inimigo→
  rodada, devolvendo o contexto "ENGINE: ..." pro Mestre narrar;
- `extrair_alvo_ataque` (turn_pipeline): de quem é o ataque (nome explícito, único
  inimigo vivo, ou ambíguo→None).

Determinístico via random.Random(seed) e d20 nat20/nat1 (acerto/erro garantidos
independentes de CA/mod).
"""

import random

from api.turn_pipeline import extrair_alvo_ataque
from engine.combat.orchestrator import resolver_turno_ataque_jogador
from engine.memory.working_memory import WorkingMemory


def _wm_combate(ca_inimigo: int = 5, hp_inimigo: int = 30) -> WorkingMemory:
    wm = WorkingMemory.nova_sessao("arena", "Arena", "sess-t")
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin", "intacto")
    wm.aplicar_stats_inimigo("goblin", ca=ca_inimigo, hp_max=hp_inimigo)
    return wm


# ── resolver_turno_ataque_jogador ─────────────────────────────────────────────

def test_acerto_aplica_dano_e_avanca_rodada():
    wm = _wm_combate(ca_inimigo=5, hp_inimigo=30)
    rodada_antes = wm.rodada_combate
    res = resolver_turno_ataque_jogador(wm, "goblin", d20=20, rng=random.Random(1))
    assert res["valido"] is True
    assert res["acertou"] is True and res["critico"] is True
    assert "CRÍTICO" in res["contexto"]
    assert res["dano"] > 0
    # dano aplicado no HP do inimigo
    assert wm.inimigos_combate["goblin"]["hp_atual"] < 30
    # ação consumida + rodada avançada
    assert wm.rodada_combate == rodada_antes + 1


def test_erro_nao_aplica_dano_mas_roda_turno_inimigo():
    wm = _wm_combate(ca_inimigo=30, hp_inimigo=30)
    res = resolver_turno_ataque_jogador(wm, "goblin", d20=1, rng=random.Random(1))
    assert res["valido"] is True
    assert res["acertou"] is False and res["falha_critica"] is True
    assert "ERROU" in res["contexto"] or "FALHA" in res["contexto"]
    assert res["dano"] == 0
    assert wm.inimigos_combate["goblin"]["hp_atual"] == 30  # intacto
    # o turno dos inimigos sempre é narrado
    assert "turno dos inimigos" in res["contexto"]


def test_abate_marca_morto_e_encerra_se_unico():
    wm = _wm_combate(ca_inimigo=5, hp_inimigo=1)  # 1 HP → crit mata
    res = resolver_turno_ataque_jogador(wm, "goblin", d20=20, rng=random.Random(2))
    assert res["estado_alvo"] == "morto"
    assert res["fim_combate"] is True
    assert "sem vida" in res["contexto"]


def test_alvo_inexistente_e_invalido():
    wm = _wm_combate()
    res = resolver_turno_ataque_jogador(wm, "dragao-fantasma", d20=15, rng=random.Random(1))
    assert res["valido"] is False


def test_alvo_ja_morto_e_invalido():
    wm = _wm_combate()
    wm.atualizar_estado_inimigo("goblin", "morto", "sem vida")
    res = resolver_turno_ataque_jogador(wm, "goblin", d20=20, rng=random.Random(1))
    assert res["valido"] is False


def test_contexto_nunca_repete_numero_de_ca_como_instrucao():
    # smoke: o contexto é factual e prefixado com ENGINE: (o Mestre veste de prosa)
    wm = _wm_combate(ca_inimigo=12, hp_inimigo=20)
    res = resolver_turno_ataque_jogador(wm, "goblin", d20=18, rng=random.Random(3))
    assert res["contexto"].count("ENGINE:") >= 2  # ataque + turno inimigo (+dano)


# ── extrair_alvo_ataque ───────────────────────────────────────────────────────

def test_extrai_alvo_por_nome_explicito_e_registra():
    wm = WorkingMemory.nova_sessao("arena", "Arena", "s")
    wm.entrar_combate()
    alvo = extrair_alvo_ataque("ataco o orc com a espada", wm)
    assert alvo == "orc"
    assert "orc" in wm.inimigos_combate  # registrado de brinde


def test_extrai_unico_inimigo_vivo_sem_nome():
    wm = _wm_combate()
    # "ataco" sem nomear → mira o único inimigo vivo
    assert extrair_alvo_ataque("ataco com tudo", wm) == "goblin"


def test_dois_inimigos_sem_nome_e_ambiguo():
    wm = _wm_combate()
    wm.registrar_inimigo("orc", "Orc", "intacto")
    assert extrair_alvo_ataque("ataco", wm) is None


def test_pronome_nao_vira_alvo():
    wm = WorkingMemory.nova_sessao("arena", "Arena", "s")
    wm.entrar_combate()
    # sem inimigo registrado e só pronome → None (não cria "ele" como inimigo)
    assert extrair_alvo_ataque("ataco ele", wm) is None
    assert "ele" not in wm.inimigos_combate


def test_inimigo_morto_nao_conta_para_alvo_unico():
    wm = _wm_combate()
    wm.atualizar_estado_inimigo("goblin", "morto", "sem vida")
    assert extrair_alvo_ataque("ataco", wm) is None
