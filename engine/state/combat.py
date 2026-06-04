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

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.llm.types import TokenIniciativa


# Estados narrativos válidos para inimigos (mapeiam para barra visual no frontend)
_ESTADOS_INIMIGO = frozenset(
    {"intacto", "ferido", "gravemente ferido", "incapacitado", "morto"}
)

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

    # Inimigos: id → {nome, estado, hp_rel, srd_index, ficha}
    # srd_index/ficha são opcionais — preenchidos pelo bestiário quando o monstro
    # existe no SRD indexado (engine.bestiary).
    inimigos_combate: dict[str, dict[str, str]] = field(default_factory=dict)

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

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def entrar(self) -> None:
        """Ativa modo combate. Resetta toda estrutura tática."""
        self.em_combate = True
        self.rodada_combate = 1
        self.rodadas_sem_acao_inimigo = 0
        self.iniciativa_jogador = None
        self.iniciativa_cache = {}
        self.turno_atual_idx = 0
        self.posicoes_combate = {}
        self.movimento_restante_ft = self.movimento_total_ft

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

    def avancar_rodada(self) -> None:
        """Incrementa rodada e renova movimento (SRD: speed inteiro por rodada)."""
        if self.em_combate:
            self.rodada_combate += 1
            self.movimento_restante_ft = self.movimento_total_ft

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
        self.inimigos_combate[inimigo_id] = {
            "nome": nome,
            "estado": estado if estado in _ESTADOS_INIMIGO else "intacto",
            "hp_rel": hp_rel,
            "srd_index": srd_index,
        }

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
    ) -> None:
        """Popula cache de iniciativa no primeiro turno de combate.

        Idempotente — só popula entradas que ainda não estão no cache.
        Jogador entra com `iniciativa_jogador` se definida, senão `10 + mod_des`.
        """
        if "jogador" not in self.iniciativa_cache:
            if self.iniciativa_jogador is not None:
                self.iniciativa_cache["jogador"] = self.iniciativa_jogador
            else:
                self.iniciativa_cache["jogador"] = 10 + mod_des_jogador

        proposta_llm = proposta_llm or {}
        em_uso = set(self.iniciativa_cache.values())
        proximo_fallback = 20
        for inimigo_id in self.inimigos_combate.keys():
            if inimigo_id in self.iniciativa_cache:
                continue
            valor = proposta_llm.get(inimigo_id)
            if valor is None:
                while proximo_fallback in em_uso and proximo_fallback > -50:
                    proximo_fallback -= 1
                valor = proximo_fallback
                proximo_fallback -= 1
            self.iniciativa_cache[inimigo_id] = valor
            em_uso.add(valor)

    def avancar_turno_iniciativa(self, calcular_ordem) -> None:
        """Cicla turno_atual_idx para o próximo vivo. `calcular_ordem` é callback
        passado por WorkingMemory (precisa de player_hp/player_name)."""
        if not self.em_combate or not self.iniciativa_cache:
            return
        ordem = calcular_ordem()
        vivos = [t for t in ordem if not t.morto]
        if not vivos:
            return
        n = len(vivos)
        # COMBAT-2: clamp defensivo
        self.turno_atual_idx = (max(0, self.turno_atual_idx) % n + 1) % n

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

            # Fichas SRD dos inimigos vivos — dados mecânicos reais (CA/PV/ataques)
            # pro Mestre narrar com consistência. Dedup por tipo (5 goblins = 1
            # ficha) e cap em _MAX_FICHAS pra não estourar o budget de combate.
            fichas_vistas: set[str] = set()
            blocos: list[str] = []
            for npc_id, dados in self.inimigos_combate.items():
                if dados.get("estado") == "morto":
                    continue
                ficha = dados.get("ficha")
                if not ficha:
                    continue
                chave = dados.get("srd_index") or dados.get("nome", npc_id)
                if chave in fichas_vistas:
                    continue
                fichas_vistas.add(chave)
                blocos.append(ficha)
                if len(blocos) >= _MAX_FICHAS_PROMPT:
                    break
            for bloco in blocos:
                linhas.append(f"Ficha: {bloco}")

        if self.movimento_restante_ft < self.movimento_total_ft:
            linhas.append(
                f"Movimento restante: {self.movimento_restante_ft}/{self.movimento_total_ft}ft"
            )

        return "\n".join(linhas)
