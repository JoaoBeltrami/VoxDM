"""
engine/authority — pipeline de autoridade pré-LLM (classificar → validar → resolver).

Por que existe: a decisão "autoridade-primeiro, LLM-fino" (Beltrami, 20/06) inverte
    quem decide o quê no turno — a engine resolve tudo que é determinístico
    (intenção, regras, HP, ouro, mundo) e a LLM narra o resultado, em vez de narrar
    e ter que ser confiada pra "lembrar" de emitir markers corretos. O combate
    (`engine/combat/`) foi a 1ª instância desse padrão; este pacote é onde os
    demais domínios (economia primeiro, por decisão de 30/06 — baixo risco
    narrativo, "ouro é só um número") ganham a mesma disciplina.
Dependências: nenhuma no pacote em si — cada submódulo é puro (regex/aritmética),
    sem I/O. Quem chama (api/turn_pipeline.py) muta a WorkingMemory.
Armadilha: NÃO adicionar domínios especulativos aqui antes de ter um consumidor
    concreto — cada submódulo nasce quando um domínio real é decidido (ver
    memory/roadmap_mestre_consolidado.md), não antes.
"""
