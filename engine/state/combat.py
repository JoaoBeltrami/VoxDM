"""
Estado de combate ativo — vive apenas entre `entrar()` e `sair()`.

Por que existe: combate é um modal claro do jogo. Fora dele, todos os campos
    (inimigos, iniciativa, posições, movimento) ficam zerados em WorkingMemory,
    poluindo o estado. Encapsulado aqui, o reset é uma única operação atômica
    e o to_prompt() só emite algo quando em_combate=True.

Dependências: engine/llm/types.TokenIniciativa (import tardio para evitar ciclo)

Armadilha: `sair()` deve ser idempotente — chamado em múltiplos paths (FUGIU,
    fim_combate_LLM, todos_mortos, timeout). Estado completamente zerado a cada
    chamada.

Exemplo:
    combat = CombatState()
    combat.entrar()
    combat.registrar_inimigo("goblin", "Goblin")
    combat.atualizar_estado_inimigo("goblin", "morto")
    combat.sair()  # → estado completamente zerado
"""

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from engine.combat.stats import descritor_de_inimigo, stats_inimigo

if TYPE_CHECKING:
    pass


# Estados narrativos válidos para inimigos (mapeiam para barra visual no frontend)
_ESTADOS_INIMIGO = frozenset(
    {"intacto", "ferido", "gravemente ferido", "incapacitado", "morto"}
)

# Escala de GRAVIDADE dos mesmos estados. O frozenset acima valida pertinência,
# mas não ordena — e ordenar é o que impede um `[INIMIGO: c1|carniçal]` repetido
# (que chega com o default "intacto") de CURAR quem já estava ferido.
_GRAVIDADE_ESTADO: dict[str, int] = {
    "intacto": 0, "ferido": 1, "gravemente ferido": 2, "incapacitado": 3, "morto": 4,
}

# Máximo de fichas SRD injetadas no prompt de combate (dedup por tipo de monstro).
# Teto de budget: cada ficha compacta ~55 palavras; 3 tipos cobrem a esmagadora
# maioria dos encontros sem inflar o prompt além do teto de tokens do combate.
_MAX_FICHAS_PROMPT = 3


@dataclass
class CombatState:
    """Tudo que existe apenas durante combate ativo."""

    em_combate: bool = False
    rodada_combate: int = 0
    iniciativa_jogador: int | None = None

    # Inimigos: id → {nome, estado, hp_rel, srd_index, ficha, ca, hp_max, hp_atual}
    # srd_index/ficha são opcionais — preenchidos pelo bestiário quando o monstro
    # existe no SRD indexado (engine.bestiary). ca/hp_* (int) entram via
    # aplicar_stats_inimigo, permitindo morte determinística por HP.
    inimigos_combate: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Cache de iniciativa: token_id → valor
    iniciativa_cache: dict[str, int] = field(default_factory=dict)
    turno_atual_idx: int = 0

    # Tactical: posição relativa em ft
    posicoes_combate: dict[str, dict[str, int | bool]] = field(default_factory=dict)
    movimento_restante_ft: int = 30
    movimento_total_ft: int = 30

    # Aftermath flags
    saiu_combate_recentemente: bool = False
    rodadas_sem_acao_inimigo: int = 0

    # Action economy (combate engine-autoritativo, task 1): 1 ação + 1 bônus +
    # movimento por rodada. Resetados ao entrar, a cada rodada e ao sair. A engine
    # é a autoridade — recusa 2ª ação na mesma rodada (enforcement = task 5).
    acao_usada: bool = False
    bonus_usada: bool = False

    # DANO-INIMIGO-INVISIVEL-1 (playtest 07/08): "dano no inimigo nunca é
    # mostrado ou contado". A engine calculava (`combate_engine_resolveu dano=9`)
    # e o número morria no log — o prompt PROÍBE o Mestre de citar número
    # (`combat.md`), então não sobrava fonte nenhuma pro jogador. É o espelho
    # exato do DANO-SEM-CAUSA-1 do lado do PJ, e a solução é a mesma que já foi
    # aceita lá: buffer por turno, drenado 1×, entregue no payload `fim`.
    # Cada item: {"alvo", "nome", "dano", "estado", "hp", "hp_max", "morreu"}.
    golpes_turno: list[dict[str, Any]] = field(default_factory=list)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def entrar(self) -> None:
        """Ativa modo combate. Resetta toda estrutura tática.

        IDEMPOTENTE: se já estamos em combate, não faz nada. Antes do fix de
        13/06, `entrar_combate()` era chamado em TODO turno de ataque
        (websocket: `if _RE_COMBATE.search(texto_jogador): entrar_combate()`),
        re-zerando `iniciativa_cache` (warning `iniciativa_fallback` a cada
        turno + InitiativeBar saltando), `rodada_combate` (voltava pra 1 a cada
        golpe → pacing/rodada nunca avançavam) e `posicoes_combate`/movimento.
        Reentrar só faz sentido vindo de FORA de combate.
        """
        if self.em_combate:
            return
        self.em_combate = True
        self.rodada_combate = 1
        self.rodadas_sem_acao_inimigo = 0
        self.iniciativa_jogador = None
        self.iniciativa_cache = {}
        self.turno_atual_idx = 0
        self.posicoes_combate = {}
        self.movimento_restante_ft = self.movimento_total_ft
        self.reset_economia()

    def sair(self) -> None:
        """Desativa combate. Idempotente — todos os campos voltam ao default."""
        self.em_combate = False
        self.iniciativa_jogador = None
        self.rodada_combate = 0
        self.rodadas_sem_acao_inimigo = 0
        self.inimigos_combate.clear()
        self.iniciativa_cache.clear()
        self.turno_atual_idx = 0
        self.posicoes_combate.clear()
        self.movimento_restante_ft = self.movimento_total_ft
        self.saiu_combate_recentemente = True
        self.golpes_turno.clear()
        self.reset_economia()

    def avancar_rodada(self) -> None:
        """Incrementa rodada e renova movimento + economia (SRD: tudo novo por rodada)."""
        if self.em_combate:
            self.rodada_combate += 1
            self.movimento_restante_ft = self.movimento_total_ft
            self.reset_economia()

    # ── Action economy (autoridade da engine) ────────────────────────────────

    def reset_economia(self) -> None:
        """Zera ação e bônus da rodada (movimento é renovado em avancar_rodada)."""
        self.acao_usada = False
        self.bonus_usada = False

    def usar_acao(self) -> bool:
        """Consome a ação principal da rodada. False se já foi usada."""
        if self.acao_usada:
            return False
        self.acao_usada = True
        return True

    def usar_bonus(self) -> bool:
        """Consome a ação bônus da rodada. False se já foi usada."""
        if self.bonus_usada:
            return False
        self.bonus_usada = True
        return True

    def pode_agir(self) -> bool:
        """True se o jogador ainda tem a ação principal nesta rodada."""
        return not self.acao_usada

    # ── Inimigos ─────────────────────────────────────────────────────────────

    def registrar_inimigo(
        self,
        inimigo_id: str,
        nome: str,
        estado: str = "intacto",
        hp_rel: str = "",
        srd_index: str = "",
    ) -> None:
        """Adiciona ou atualiza inimigo no combate atual.

        srd_index: índice SRD do monstro (ex: "goblin") para o bestiário puxar a
        ficha mecânica. A ficha em si (campo "ficha") é preenchida depois, async,
        por engine.bestiary.enriquecer_fichas_inimigos.
        """
        novo = estado if estado in _ESTADOS_INIMIGO else "intacto"
        existente = self.inimigos_combate.get(inimigo_id)
        if existente is None:
            self.inimigos_combate[inimigo_id] = {
                "nome": nome,
                "estado": novo,
                "hp_rel": hp_rel,
                "srd_index": srd_index,
            }
            return

        # RESSURREICAO-1 (playtest 26/07): esta função dizia "adiciona ou
        # ATUALIZA" e fazia substituição CEGA do dicionário — toda re-registração
        # do mesmo id apagava `hp_atual`, `hp_max`, `ca`, a ficha SRD e o
        # `estado: morto`. Relato do jogador: "um carniçal que morreu caindo
        # voltou do nada" e, depois, "matei mais um e eles continuam". Estado ao
        # vivo confirmando: rodada 9, os dois ghouls em `intacto` com hp_atual
        # cheio (9/9) depois de terem morrido.
        #
        # Morte é ESTADO ABSORVENTE: nada re-registra um inimigo morto de volta
        # pra vivo. Quem quiser ressuscitar de propósito usa
        # `atualizar_estado_inimigo`, que é explícito.
        if existente.get("estado") == "morto":
            return
        existente["nome"] = nome or existente.get("nome", "")
        # Só PIORA ou mantém: um `[INIMIGO: c1|carniçal]` repetido chega com o
        # default "intacto" e não pode curar quem já está ferido.
        if _GRAVIDADE_ESTADO.get(novo, 0) > _GRAVIDADE_ESTADO.get(
            str(existente.get("estado", "intacto")), 0
        ):
            existente["estado"] = novo
        if hp_rel:
            existente["hp_rel"] = hp_rel
        if srd_index:
            existente["srd_index"] = srd_index

    def atualizar_estado_inimigo(
        self, inimigo_id: str, estado: str, hp_rel: str = ""
    ) -> None:
        """Atualiza estado narrativo de inimigo existente."""
        if inimigo_id in self.inimigos_combate:
            self.inimigos_combate[inimigo_id]["estado"] = (
                estado if estado in _ESTADOS_INIMIGO else "ferido"
            )
            if hp_rel:
                self.inimigos_combate[inimigo_id]["hp_rel"] = hp_rel
            # Limpa posição tática quando inimigo morre
            if estado == "morto":
                self.posicoes_combate.pop(inimigo_id, None)

    def aplicar_stats_inimigo(self, inimigo_id: str, ca: int, hp_max: int) -> None:
        """Define CA/HP numéricos de um inimigo (da ficha SRD ou default por CR).

        Idempotente por turno: NÃO re-zera `hp_atual` se o inimigo já tomou dano.
        """
        d = self.inimigos_combate.get(inimigo_id)
        if d is None:
            return
        d["ca"] = int(ca)
        d["hp_max"] = int(hp_max)
        d.setdefault("hp_atual", int(hp_max))

    def aplicar_dano_inimigo(self, inimigo_id: str, dano: int) -> str:
        """Reduz o HP numérico do inimigo e deriva o estado narrativo. Retorna o estado.

        Morte é DETERMINÍSTICA (HP ≤ 0) — não depende de regex de vocabulário do
        LLM (resolve COMBAT-1). Sem HP numérico (inimigo sem stats aplicados),
        mantém o estado narrativo atual e não inventa morte.
        """
        d = self.inimigos_combate.get(inimigo_id)
        if d is None:
            return ""
        hp_max = int(d.get("hp_max", 0) or 0)
        if hp_max <= 0:
            return str(d.get("estado", "intacto"))
        hp = int(d.get("hp_atual", hp_max)) - max(0, int(dano))
        hp = max(0, hp)
        d["hp_atual"] = hp
        if hp <= 0:
            estado = "morto"
        elif hp <= hp_max * 0.25:
            estado = "gravemente ferido"
        elif hp < hp_max:
            estado = "ferido"
        else:
            estado = "intacto"
        d["estado"] = estado
        # DANO-INIMIGO-INVISIVEL-1: registra AQUI, no ponto em que o dano é
        # aplicado — mesmo lugar do análogo no PJ (`registrar_evento_vital`).
        # Registrar no websocket deixaria de fora qualquer caminho que não passe
        # por lá; aqui passa todo dano que a engine aplica, por definição.
        if dano > 0:
            self.golpes_turno.append({
                "alvo": inimigo_id,
                "nome": str(d.get("nome") or inimigo_id),
                "dano": int(dano),
                "estado": estado,
                "hp": hp,
                "hp_max": hp_max,
                "morreu": estado == "morto",
            })
        if estado == "morto":
            self.posicoes_combate.pop(inimigo_id, None)
        return estado

    def drenar_golpes(self) -> list[dict[str, Any]]:
        """Devolve e limpa os golpes do turno (mesmo idioma de `eventos_vitais`)."""
        golpes = list(self.golpes_turno)
        self.golpes_turno.clear()
        return golpes

    def remover_inimigo(self, inimigo_id: str) -> None:
        """Remove inimigo (morte definitiva ou fuga)."""
        self.inimigos_combate.pop(inimigo_id, None)

    # ── Tactical ─────────────────────────────────────────────────────────────

    def registrar_posicao(
        self, npc_id: str, distancia_ft: int, cobertura: bool = False
    ) -> None:
        """Atualiza posição relativa do NPC. Clamp [0, 999] ft."""
        if distancia_ft < 0:
            distancia_ft = 0
        if distancia_ft > 999:
            distancia_ft = 999
        self.posicoes_combate[npc_id] = {
            "distancia_ft": int(distancia_ft),
            "cobertura": bool(cobertura),
        }

    def aplicar_movimento(self, delta_ft: int) -> int:
        """Consome movimento na rodada. Retorna o quanto realmente foi consumido."""
        if delta_ft <= 0:
            return 0
        consumido = min(delta_ft, self.movimento_restante_ft)
        self.movimento_restante_ft -= consumido
        return consumido

    # ── Iniciativa (authority = engine) ──────────────────────────────────────

    def popular_iniciativa(
        self,
        mod_des_jogador: int,
        proposta_llm: dict[str, int] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """Rola iniciativa (d20 + mod) pra quem ainda não tem. Idempotente.

        COMBATE-SEM-RODADA-1 (playtest 07/08): *"ainda não temos mecânica de
        iniciativa pra dar sentido ao combate"*. Não faltava infraestrutura —
        faltava DADO. O jogador entrava com um "take 10" (`10 + mod_des`) e os
        inimigos num fallback DECRESCENTE fixo a partir de 20, então a ordem era
        sempre a mesma e o jogador era SEMPRE o último da barra.

        Empate é aceito de propósito: `calcular_ordem_iniciativa` já desempata de
        forma determinística (-iniciativa, jogador antes de inimigo, id). Forçar
        unicidade era o que exigia o fallback decrescente — e com d20 e muitos
        inimigos a colisão é garantida por casa-dos-pombos, não é evitável.

        Inimigo rola d20 puro: `StatsInimigo` não tem DES, e inventar um
        modificador seria número sem lastro no SRD.
        """
        rng = rng or random.Random()
        if "jogador" not in self.iniciativa_cache:
            if self.iniciativa_jogador is None:
                self.iniciativa_jogador = rng.randint(1, 20) + mod_des_jogador
            self.iniciativa_cache["jogador"] = self.iniciativa_jogador

        proposta_llm = proposta_llm or {}
        for inimigo_id in self.inimigos_combate:
            if inimigo_id in self.iniciativa_cache:
                continue
            valor = proposta_llm.get(inimigo_id)
            if valor is None:
                valor = rng.randint(1, 20)
            self.iniciativa_cache[inimigo_id] = valor

    def avancar_turno_iniciativa(self, calcular_ordem) -> bool:
        """Cicla turno_atual_idx para o próximo vivo. Retorna True se DEU A VOLTA.

        O retorno é o que transforma rodada em unidade de TEMPO: até 07/08 a
        rodada avançava quando *o jogador* agia (`orchestrator`/`turn_pipeline`),
        então "um turno de combate tinha vários turnos com o mestre" — a queixa
        literal do playtest. Rodada nova = a ordem deu a volta, nada mais.

        `calcular_ordem` é callback passado por WorkingMemory (precisa de
        player_hp/player_name).
        """
        if not self.em_combate or not self.iniciativa_cache:
            return False
        ordem = calcular_ordem()
        vivos = [t for t in ordem if not t.morto]
        if not vivos:
            return False
        n = len(vivos)
        # COMBAT-2: clamp defensivo
        proximo = (max(0, self.turno_atual_idx) % n + 1) % n
        self.turno_atual_idx = proximo
        return proximo == 0

    def de_quem_e_a_vez(self) -> str:
        """Nome de quem age agora, pela ordem de iniciativa. "" se não há ordem.

        Puro e sem callback de propósito: `calcular_ordem_iniciativa` precisa do
        HP/nome do jogador (que vivem em outro substate), e o prompt só precisa
        do RÓTULO. Ordena com o mesmo desempate da ordem oficial.
        """
        if not self.em_combate or not self.iniciativa_cache:
            return ""
        vivos = [
            (iid, int(self.iniciativa_cache.get(iid, 0)))
            for iid, d in self.inimigos_combate.items()
            if d.get("estado") != "morto" and iid in self.iniciativa_cache
        ]
        if "jogador" not in self.iniciativa_cache:
            return ""
        vivos.append(("jogador", int(self.iniciativa_cache["jogador"])))
        vivos.sort(key=lambda t: (-t[1], 0 if t[0] == "jogador" else 1, t[0]))
        if not vivos:
            return ""
        iid = vivos[max(0, self.turno_atual_idx) % len(vivos)][0]
        if iid == "jogador":
            return "o jogador"
        return str(self.inimigos_combate.get(iid, {}).get("nome") or iid)

    # ── Serialização para prompt ─────────────────────────────────────────────

    def to_prompt(self) -> str:
        """Bloco de combate ativo no system prompt. Vazio quando sem combate."""
        if not self.em_combate:
            return ""

        linhas: list[str] = []
        rodada_str = (
            f"Rodada {self.rodada_combate}" if self.rodada_combate else "combate iniciando"
        )
        ini_str = (
            f"iniciativa {self.iniciativa_jogador}"
            if self.iniciativa_jogador is not None
            else "aguardando iniciativa"
        )
        linhas.append(f"COMBATE ATIVO — {rodada_str} — {ini_str}")

        # COMBATE-SEM-RODADA-1: de quem é a vez. Sem isto o Mestre não tinha como
        # saber que a rodada tem uma ORDEM, e narrava a cena como se todo mundo
        # agisse ao mesmo tempo — "os turnos não fazem sentido no combate".
        vez = self.de_quem_e_a_vez()
        if vez:
            linhas.append(f"Vez de: {vez}")

        if self.inimigos_combate:
            partes_ini = []
            for npc_id, dados in self.inimigos_combate.items():
                if dados.get("estado") == "morto":
                    continue
                desc = dados["nome"]
                if dados.get("estado") and dados["estado"] != "intacto":
                    desc += f" ({dados['estado']})"
                if dados.get("hp_rel"):
                    desc += f" [{dados['hp_rel']}]"
                pos = self.posicoes_combate.get(npc_id)
                if pos:
                    cob = " cobertura" if pos.get("cobertura") else ""
                    desc += f" {pos['distancia_ft']}ft{cob}"
                partes_ini.append(desc)
            if partes_ini:
                linhas.append(f"Inimigos: {', '.join(partes_ini)}")

            # Porte dos inimigos vivos — COMO a criatura se porta, sem número.
            #
            # Até 07/08 isto era a ficha SRD INTEIRA (~55 palavras cada, até 3 por
            # turno de combate). Os números saíram: quem calcula é a engine, que já
            # guarda CA/PV parseados em `inimigos_combate`, e o master_system proíbe
            # o Mestre de citar número mesmo. Dedup por tipo (5 goblins = 1 linha).
            vistos: set[str] = set()
            portes: list[str] = []
            for npc_id, dados in self.inimigos_combate.items():
                if dados.get("estado") == "morto":
                    continue
                ficha = dados.get("ficha")
                if not ficha:
                    continue
                chave = dados.get("srd_index") or dados.get("nome", npc_id)
                if chave in vistos:
                    continue
                vistos.add(chave)
                portes.append(
                    descritor_de_inimigo(dados.get("nome", npc_id), stats_inimigo(ficha))
                )
                if len(portes) >= _MAX_FICHAS_PROMPT:
                    break
            if portes:
                linhas.append(f"Porte: {' | '.join(portes)}")

        if self.movimento_restante_ft < self.movimento_total_ft:
            linhas.append(
                f"Movimento restante: {self.movimento_restante_ft}/{self.movimento_total_ft}ft"
            )

        return "\n".join(linhas)
