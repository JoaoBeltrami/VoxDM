"""
Interface RuleSystem — a costura para multi-sistema (Frente B3 do NEXT LEVEL).

Por que existe: hoje a mecânica D&D 5e está espalhada em engine/chargen.py,
    engine/progression.py e engine/magic/. Para um dia plugar Tormenta/CoC/PF
    sem reescrever a engine narrativa, toda regra mecânica passa por este
    contrato. Esta fase desenha SÓ a costura (Protocol + a impl D&D que delega ao
    código existente) — nenhum outro sistema é implementado, e nada ainda é
    movido: é aditivo e de risco zero (sem consumidores).
Dependências: typing.Protocol.
Armadilha: NÃO importar WorkingMemory em runtime aqui (ciclo) — só sob
    TYPE_CHECKING. O Protocol é runtime_checkable, então isinstance() funciona,
    mas só verifica a EXISTÊNCIA dos métodos, não as assinaturas.

Exemplo:
    from engine.rules import obter_sistema
    regras = obter_sistema("dnd5e")
    if regras.resolve_check(rolagem_total=17, cd=15):
        ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from engine.memory.working_memory import WorkingMemory


@runtime_checkable
class RuleSystem(Protocol):
    """Contrato mecânico de um sistema de RPG (resolução, char-gen, progressão, descanso).

    Implementações vivem em engine/rules/<sistema>.py e se registram no pacote.
    A engine narrativa (prompts, TTS, RAG) é AGNÓSTICA a qual sistema está ativo.
    """

    #: Identificador canônico do sistema (ex: "dnd5e"). Usado no registry.
    nome: str

    # ── Char-gen ──────────────────────────────────────────────────────────────
    def normalizar_classe(self, texto: str) -> str:
        """Nome livre → classe canônica do sistema ("" se desconhecida)."""
        ...

    def gerar_atributos(self, classe: str) -> dict[str, int]:
        """Atributos iniciais priorizados pela classe (ex: {'str_score': 15, ...})."""
        ...

    def hit_die(self, classe: str) -> int:
        """Tamanho do dado de vida da classe (ex: 6 para Mago, 10 para Guerreiro)."""
        ...

    def hp_inicial(self, classe: str, nivel: int, mod_con: int) -> int:
        """PV máximo de um personagem novo da classe no nível dado."""
        ...

    def slots_iniciais(self, classe: str, nivel: int) -> dict[int, dict[str, int]]:
        """Espaços de magia por nível para a classe/nível ({} se não-conjurador)."""
        ...

    def equipamento_inicial(self, classe: str) -> list[str]:
        """Itens que a classe começa carregando, já expandidos por quantidade.

        Lembrete do Beltrami (11/08): *"nossa engine futuramente não narrará só
        D&D… de maneira modular pra que no futuro outros sistemas sejam lidos"*.
        Equipamento inicial é conceito de CHAR-GEN, e char-gen é do sistema —
        Tormenta e CoC dão equipamento por outras regras, e um deles nem tem
        classe. Por isso entra no contrato, e não numa tabela que a
        `WorkingMemory` importa direto.

        [] é resposta legítima: sistema sem equipamento fixo, ou classe cujo
        equipamento todo está nas ESCOLHAS (o Guerreiro do SRD é assim).
        """
        ...

    def escolhas_de_equipamento(self, classe: str) -> list[dict[str, Any]]:
        """As escolhas de equipamento da classe, prontas pra ficha OU pra voz.

        Cada escolha: `{"escolher": N, "opcoes": [{"rotulo", "itens", "categoria"}]}`.
        `rotulo` é a frase que o Mestre lê em voz alta e que a ficha põe no
        botão; `itens` é o efeito no inventário; `categoria` marca a opção que o
        jogador ainda precisa fechar ("uma arma marcial"). O formato serve os
        DOIS caminhos de propósito — se cada um tivesse o seu, divergiriam.

        [] quando o sistema não tem escolhas de equipamento.
        """
        ...

    # ── Resolução ─────────────────────────────────────────────────────────────
    def modificador(self, score: int) -> int:
        """Modificador derivado de um valor de atributo."""
        ...

    def resolve_check(self, total: int, cd: int) -> bool:
        """True se o total da rolagem atinge/supera a CD (classe de dificuldade)."""
        ...

    # ── Progressão & descanso ───────────────────────────────────────────────────
    def nivel_por_xp(self, xp: int, nivel_atual: int) -> int:
        """Nível correspondente ao XP acumulado (pode pular múltiplos níveis)."""
        ...

    def descansar(self, wm: WorkingMemory, tipo: str) -> int:
        """Aplica descanso (curto/longo), restaura recursos; retorna recursos restaurados."""
        ...
