"""
Estado de aliados controlados pela party — companions e assinaturas de voz.

Por que existe: companions (hireling, familiar, animal companion, summons) e
    suas vozes de TTS são domínio separado da cena e do combate. Aliados
    sobrevivem a múltiplos combates; suas vozes persistem entre cenas.

Dependências: apenas stdlib

Armadilha: hp/hp_max devem ser inteiros e clampados. Vozes são imutáveis
    após registradas na 1ª fala (re-registrar do mesmo NPC é no-op).
"""

from dataclasses import dataclass, field

# Cap de vozes para evitar dict crescer indefinidamente em sessões longas
_MAX_VOZES = 20


@dataclass
class PartyState:
    """Aliados ativos + assinaturas de voz dos NPCs falantes."""

    # companions: id → {nome, tipo, hp, hp_max, ca, atq, dano}
    # tipo: hireling | familiar | animal | summon
    companions: dict[str, dict[str, str | int]] = field(default_factory=dict)

    # npc_vozes: id → {pitch: "+NHz", rate: "+N%"}
    npc_vozes: dict[str, dict[str, str]] = field(default_factory=dict)

    # ── Companions ───────────────────────────────────────────────────────────

    def registrar_companion(
        self, companion_id: str, nome: str, tipo: str,
        hp: int, ca: int, atq: str, dano: str,
    ) -> None:
        """Adiciona ou atualiza companion. Idempotente."""
        self.companions[companion_id] = {
            "nome": nome.strip(),
            "tipo": tipo.strip().lower(),
            "hp": max(0, int(hp)),
            "hp_max": max(1, int(hp)),
            "ca": int(ca),
            "atq": atq.strip(),
            "dano": dano.strip(),
        }

    def ajustar_hp_companion(self, companion_id: str, delta: int) -> bool:
        """Aplica delta de HP. Retorna False se id não existe. Clamp [0, hp_max]."""
        comp = self.companions.get(companion_id)
        if not comp:
            return False
        hp_max = int(comp.get("hp_max", 1))
        hp_atual = int(comp.get("hp", 0))
        comp["hp"] = max(0, min(hp_max, hp_atual + int(delta)))
        return True

    def remover_companion(self, companion_id: str) -> bool:
        """Remove companion. Retorna True se removido."""
        return self.companions.pop(companion_id, None) is not None

    # ── Vozes de NPC ─────────────────────────────────────────────────────────

    def registrar_voz_npc(self, npc_id: str, pitch: str, rate: str) -> bool:
        """Registra voz (imutável após 1ª fala). Retorna True se registrada."""
        if not npc_id or self.npc_vozes.get(npc_id):
            return False
        if len(self.npc_vozes) >= _MAX_VOZES:
            mais_antiga = next(iter(self.npc_vozes))
            del self.npc_vozes[mais_antiga]
        self.npc_vozes[npc_id] = {"pitch": pitch, "rate": rate}
        return True

    # ── Serialização ─────────────────────────────────────────────────────────

    def to_prompt(self, em_combate: bool) -> str:
        """Bloco de aliados — contexto graduado por situação.

        Em combate: stats completos (CA, atq, dano) para LLM narrar ataques.
        Fora de combate: resumo compacto (nome + estado de saúde) para
        manter continuidade sem inflar tokens.
        """
        if not self.companions:
            return ""

        if em_combate:
            partes_comp = []
            for cid, c in self.companions.items():
                if int(c.get("hp", 1)) <= 0:
                    continue  # morto — omitir do bloco ativo
                partes_comp.append(
                    f"{c.get('nome', cid)} ({c.get('tipo', 'aliado')}, "
                    f"HP {c.get('hp')}/{c.get('hp_max')}, "
                    f"CA {c.get('ca')}, atq {c.get('atq')}, {c.get('dano')})"
                )
            if not partes_comp:
                return ""
            return "Aliados:\n" + "\n".join(f"- {p}" for p in partes_comp)

        # Fora de combate
        def _status_hp(c: dict) -> str:
            hp = int(c.get("hp", 0))
            hp_max = int(c.get("hp_max", 1))
            pct = hp / max(hp_max, 1)
            if pct <= 0:    return "morto"
            if pct <= 0.3:  return "grave"
            if pct <= 0.6:  return "ferido"
            return "saudável"

        nomes = [
            f"{c.get('nome', cid)} ({_status_hp(c)})"
            for cid, c in self.companions.items()
        ]
        return f"Aliados: {', '.join(nomes)}"
