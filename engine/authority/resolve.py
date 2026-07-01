"""
Dispatcher único de resolução autoritativa — delega pro domínio certo.

Por que existe: unifica o PONTO DE ENTRADA de "a engine resolve, o LLM narra"
    pros domínios já existentes — combate (`engine/combat/orchestrator.py`) e
    economia (`engine/authority/economia.py`) viviam em pacotes diferentes, e
    os call-sites (api/websocket.py, api/turn_pipeline.py) importavam cada um
    de um lugar distinto. Decisão de 01/07 (Beltrami, "consolidar arquitetura"):
    `engine/combat/` continua pacote próprio (maduro, grande demais pra mover
    só por estética de pasta) — este módulo é a CAMADA de cima que sabe pra
    onde delegar, preparando o terreno pros próximos domínios (mundo/social)
    sem mudar UMA LINHA de comportamento hoje.
Dependências: engine.combat.orchestrator, engine.authority.economia.
Armadilha: NÃO adicionar lógica de negócio aqui — é só roteamento (re-export).
    Regra nova de domínio vive no submódulo do domínio, nunca aqui.

Exemplo:
    from engine.authority.resolve import resolver_turno_ataque_jogador, resolver_custo_ouro
    resolver_turno_ataque_jogador(wm, "goblin", d20=15)   # delega pro combate
    resolver_custo_ouro(gold_atual=50, delta=-30)         # delega pra economia
"""

from engine.authority.economia import resolver_custo_ouro
from engine.combat.orchestrator import resolver_turno_ataque_jogador

__all__ = ["resolver_custo_ouro", "resolver_turno_ataque_jogador"]
