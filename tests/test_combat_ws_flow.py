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

from api.turn_pipeline import (
    aliados_presentes_para_hostil,
    deve_auto_registrar_generico,
    extrair_alvo_ataque,
    extrair_d20_jogador,
)
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


# ── ALVO-FANTASMA-1 (playtest 29/06) — atacar NPC presente nomeado ─────────────

def test_alvo_fantasma_npc_presente_vence_generico():
    # O bug exato: jogador ataca "aldric" (NPC presente), mas existe um "oponente-1"
    # genérico registrado → antes o engine mirava o fantasma. Agora mira aldric.
    wm = WorkingMemory.nova_sessao("vila", "Vila", "s")
    wm.entrar_combate()
    wm.npcs_presentes = ["aldric-drevasson", "maren-drevadottir"]
    wm.registrar_inimigo("oponente-1", "Oponente", "intacto")
    alvo = extrair_alvo_ataque("vou tentar cortar a cabeça de aldric com a espada", wm)
    assert alvo == "aldric-drevasson"
    assert "aldric-drevasson" in wm.inimigos_combate  # NPC virou combatente


def test_parte_do_corpo_com_verbo_nao_vira_alvo():
    # "ataco a cabeça de aldric" — "ataco" casa o regex e pega "cabeça"; é parte do
    # corpo (descartada) → cai no scan de NPC presente → aldric.
    wm = WorkingMemory.nova_sessao("vila", "Vila", "s")
    wm.entrar_combate()
    wm.npcs_presentes = ["aldric-drevasson"]
    assert extrair_alvo_ataque("ataco a cabeça de aldric", wm) == "aldric-drevasson"
    assert "cabeca" not in wm.inimigos_combate


def test_parte_do_corpo_sem_npc_cai_no_unico_inimigo():
    wm = _wm_combate()  # só "goblin" registrado, sem npcs_presentes
    assert extrair_alvo_ataque("ataco a cabeça dele", wm) == "goblin"
    assert "cabeca" not in wm.inimigos_combate


def test_ataca_npc_presente_sem_artigo():
    # "ataco osmund" (sem artigo) não casa o regex → scan acha o NPC presente.
    wm = WorkingMemory.nova_sessao("vila", "Vila", "s")
    wm.entrar_combate()
    wm.npcs_presentes = ["osmund-o-exilado"]
    assert extrair_alvo_ataque("ataco osmund agora", wm) == "osmund-o-exilado"


# ── extrair_d20_jogador — playtest 30/06 (iniciativa "comeu" a pendência) ──────

def test_d20_formato_simples_toolbar():
    assert extrair_d20_jogador("[Rolagem: d20 = 18]") == 18


def test_d20_formato_simples_com_sufixo_vantagem():
    assert extrair_d20_jogador("[Rolagem: d20 = 18 — VANTAGEM]") == 18


def test_d20_formato_simples_falha_critica():
    assert extrair_d20_jogador("[Rolagem: d20 = 1 — FALHA CRÍTICA!]") == 1


def test_d20_formato_rico_chip_contextual_subtrai_modificador():
    # O bug exato do playtest: chip contextual de "Iniciativa" manda o TOTAL já
    # somado ao modificador — o bruto precisa ser recuperado (total - mod).
    assert extrair_d20_jogador("[Rolagem: Iniciativa (+3) d20+3 = 9]") == 6


def test_d20_formato_rico_modificador_negativo():
    assert extrair_d20_jogador("[Rolagem: Furtividade (-1) d20-1 = 5]") == 6


def test_d20_formato_rico_com_vs_cd_e_critico():
    texto = "[Rolagem: Persuasão (+5) d20+5 = 25 vs CD 15 — CRÍTICO!]"
    assert extrair_d20_jogador(texto) == 20


def test_d20_dano_nao_e_confundido_com_d20():
    # Dado de dano (ex: d8) não é uma rolagem de d20 — None, não vaza pro resolver.
    assert extrair_d20_jogador("[Rolagem: d8 = 5]") is None


def test_d20_sem_rolagem_no_texto():
    assert extrair_d20_jogador("Eu ataco o goblin com a espada.") is None


# ── COMBATE-FANTASMA — guard do auto-register genérico ────────────────────────

def test_generico_so_em_combate_sem_npcs():
    # luta de monstro puro (sem NPC na cena) e sem inimigo → cria o genérico
    wm = WorkingMemory.nova_sessao("masmorra", "Masmorra", "s")
    wm.entrar_combate()
    assert deve_auto_registrar_generico(wm) is True


def test_generico_nao_cria_com_npcs_presentes():
    # com a família na cena, o inimigo é um deles (nomeado) — NÃO cria o fantasma
    wm = WorkingMemory.nova_sessao("vila", "Vila", "s")
    wm.entrar_combate()
    wm.npcs_presentes = ["aldric-drevasson", "maren-drevadottir"]
    assert deve_auto_registrar_generico(wm) is False


def test_generico_nao_cria_se_ja_ha_inimigo():
    wm = _wm_combate()  # já tem "goblin"
    assert deve_auto_registrar_generico(wm) is False


def test_generico_nao_cria_fora_de_combate():
    wm = WorkingMemory.nova_sessao("vila", "Vila", "s")
    assert deve_auto_registrar_generico(wm) is False


# ── Hostilidade por grafo (Neo4j) — a família defende o patriarca ─────────────

_PRESENTES = ["bjorn-tharnsson", "runa-tharnsdottir", "halvard-o-cinza"]
_RELS_BJORN = [
    {"tipo": "ally", "alvo_id": "runa-tharnsdottir", "alvo_nome": "Runa"},
    {"tipo": "family", "alvo_id": "halvard-o-cinza", "alvo_nome": "Halvard"},
    {"tipo": "rival", "alvo_id": "torvin-kaelsson", "alvo_nome": "Torvin"},  # rival, e ausente
]


def test_aliados_presentes_viram_hostis():
    out = aliados_presentes_para_hostil(_RELS_BJORN, _PRESENTES)
    assert set(out) == {"runa-tharnsdottir", "halvard-o-cinza"}


def test_rival_nao_vira_hostil():
    out = aliados_presentes_para_hostil(_RELS_BJORN, _PRESENTES)
    assert "torvin-kaelsson" not in out


def test_aliado_ausente_nao_entra():
    rels = [{"tipo": "ally", "alvo_id": "soren-tharnsson", "alvo_nome": "Soren"}]  # não presente
    assert aliados_presentes_para_hostil(rels, _PRESENTES) == []


def test_companion_nao_vira_hostil():
    out = aliados_presentes_para_hostil(
        _RELS_BJORN, _PRESENTES, companions={"runa-tharnsdottir"}
    )
    assert "runa-tharnsdottir" not in out
    assert "halvard-o-cinza" in out


def test_ja_inimigo_nao_duplica():
    out = aliados_presentes_para_hostil(
        _RELS_BJORN, _PRESENTES, ja_inimigos={"runa-tharnsdottir"}
    )
    assert "runa-tharnsdottir" not in out
