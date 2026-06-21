"""
Lista estática de magias do SRD 5e por classe e nível.

Por que existe: fornece a seleção disponível para cada classe spellcaster
    na criação de personagem sem depender do Qdrant. Os nomes PT-BR são
    usados na UI e no prompt; o nome EN acompanha para o LLM correlacionar
    com o SRD indexado.
Dependências: nenhuma — dados puramente estáticos.
Armadilha: manter os nomes PT-BR consistentes com o que o spell_detector
    recebe do jogador (ele fala "bola de fogo", não "Fireball").

Exemplo:
    entrada = SpellEntry("Bola de Fogo", "Fireball", 3, "Evocação", "8d6 fogo, save DES")
    lista = spells_da_classe("mago")
    limite = limite_progressao("mago", 3)
    # → {"truques": 3, "magias": 10, "nivel_max": 2}
"""

from dataclasses import dataclass


@dataclass
class SpellEntry:
    """Representa uma magia do SRD 5e com metadados para UI e prompt."""
    nome_pt: str      # "Bola de Fogo"
    nome_en: str      # "Fireball"
    nivel: int        # 0=truque, 1-9=nível
    escola: str       # "Evocação", "Ilusão", etc.
    desc_curta: str   # máx 80 chars para exibição na UI


# ── Catálogo de Magias por Classe (SRD 5e Open Content) ──────────────────────
#
# Apenas spells do System Reference Document (conteúdo livre sob OGL 1.0a).
# Nomes PT-BR seguem terminologia consagrada em comunidades de D&D brasileiras.
# desc_curta: resumo mecânico compacto (alcance, dano, save, duração essencial).

_MAGIAS_MAGO: list[SpellEntry] = [
    # Truques (nível 0)
    SpellEntry("Mão Mágica", "Mage Hand", 0, "Conjuração", "Mão espectral manipula objetos a 9m, sem ação de bônus"),
    SpellEntry("Luz", "Light", 0, "Evocação", "Objeto brilha como tocha por 1 hora"),
    SpellEntry("Prestidigitação", "Prestidigitation", 0, "Transmutação", "Efeitos mágicos triviais, 10m de alcance"),
    SpellEntry("Raio de Gelo", "Ray of Frost", 0, "Evocação", "1d8 frio, velocidade -3m. +1d8 em níveis 5/11/17"),
    SpellEntry("Choque de Trovão", "Shocking Grasp", 0, "Evocação", "1d8 elétrico, alvo sem reação. +1d8 em 5/11/17"),
    SpellEntry("Explosão de Ácido", "Acid Splash", 0, "Conjuração", "1d6 ácido, até 2 alvos adjacentes, save DES"),
    SpellEntry("Chama Produzida", "Produce Flame", 0, "Conjuração", "1d8 fogo corpo a corpo ou 9m arremessado"),
    SpellEntry("Dança das Luzes", "Dancing Lights", 0, "Evocação", "Até 4 luzes flutuantes, ilumina 3m cada, concentração"),
    # Nível 1
    SpellEntry("Míssil Mágico", "Magic Missile", 1, "Evocação", "3 dardos 1d4+1 força, sempre acertam; +1 dardo por slot extra"),
    SpellEntry("Escudo Arcano", "Shield", 1, "Abjuração", "Reação: +5 CA até próximo turno, bloqueia Míssil Mágico"),
    SpellEntry("Sono", "Sleep", 1, "Encantamento", "5d8 PV de criaturas adormecidas (mais fracas primeiro), 9m"),
    SpellEntry("Mãos Ardentes", "Burning Hands", 1, "Evocação", "3d6 fogo, cone 4,5m, save DES para metade"),
    SpellEntry("Charme de Pessoa", "Charm Person", 1, "Encantamento", "Encanta humanoide, save SAB, dura 1 hora"),
    SpellEntry("Armadura de Mago", "Mage Armor", 1, "Abjuração", "CA 13+DES por 8 horas (sem armadura)"),
    SpellEntry("Compreender Idiomas", "Comprehend Languages", 1, "Adivinhação", "Entende idiomas escritos e falados por 1 hora, ritual"),
    SpellEntry("Identificar", "Identify", 1, "Adivinhação", "Revela propriedades mágicas de item, ritual, 1 min"),
    SpellEntry("Explosão Colorida", "Color Spray", 1, "Ilusão", "6d10 PV de criaturas cegas por 1 rodada (mais fracas)"),
    SpellEntry("Nuvem de Névoa", "Fog Cloud", 1, "Conjuração", "Esfera 6m de névoa pesada, bloqueia visão, 1 hora"),
    SpellEntry("Dormir Mágico", "Hideous Laughter", 1, "Encantamento", "Humanoide ri, fica incapacitado, save SAB a cada turno"),
    SpellEntry("Salto", "Jump", 1, "Transmutação", "Distância de salto ×3 por 1 minuto"),
    # Nível 2
    SpellEntry("Invisibilidade", "Invisibility", 2, "Ilusão", "Alvo invisível por 1 hora ou até atacar/lançar magia"),
    SpellEntry("Flecha Ácida de Melf", "Melf's Acid Arrow", 2, "Evocação", "Acerto: 4d4 ácido imediato + 2d4 no próximo turno"),
    SpellEntry("Nuvem de Adormecimento", "Cloud of Daggers", 2, "Conjuração", "Cubo 1,5m de facas: 4d4 cortante por criaturas que entram"),
    SpellEntry("Sugestão", "Suggestion", 2, "Encantamento", "Sugestão razoável compelida, save SAB, dura 8 horas"),
    SpellEntry("Escuridão", "Darkness", 2, "Evocação", "Esfera 4,5m de escuridão mágica, bloqueia visão no escuro"),
    SpellEntry("Imobilizar Pessoa", "Hold Person", 2, "Encantamento", "Humanoide paralisado, save SAB a cada turno, 1 minuto"),
    SpellEntry("Detectar Pensamentos", "Detect Thoughts", 2, "Adivinhação", "Lê pensamentos superficiais ou sonda mais fundo, 1 min"),
    SpellEntry("Força Fantasmal", "Phantasmal Force", 2, "Ilusão", "Ilusão que parece real ao alvo, 1d6 por turno, 1 min"),
    SpellEntry("Visão no Escuro", "Darkvision", 2, "Transmutação", "Alvo ganha visão no escuro 18m por 8 horas"),
    SpellEntry("Presença Mágica", "Knock", 2, "Transmutação", "Abre fechaduras mágicas/normais com som alto"),
    # Nível 3
    SpellEntry("Bola de Fogo", "Fireball", 3, "Evocação", "8d6 fogo, esfera 6m, save DES para metade, 45m"),
    SpellEntry("Relâmpago", "Lightning Bolt", 3, "Evocação", "8d6 elétrico, linha 30m×1,5m, save DES para metade"),
    SpellEntry("Voo", "Fly", 3, "Transmutação", "Velocidade de voo 18m por 10 minutos, concentração"),
    SpellEntry("Bola de Fogo Gélida", "Sleet Storm", 3, "Conjuração", "Cilindro 6m de granizo: dif. terreno, queda, concentração"),
    SpellEntry("Contramagia", "Counterspell", 3, "Abjuração", "Reação: interrompe magia sendo lançada (automático ≤3)"),
    SpellEntry("Dissipar Magia", "Dispel Magic", 3, "Abjuração", "Remove magias em criaturas ou objetos (automático ≤3)"),
    SpellEntry("Animar Mortos", "Animate Dead", 3, "Necromancia", "Cria esqueleto ou zumbi de cadáver, controla 24h"),
    SpellEntry("Hipnose Hipnótica", "Hypnotic Pattern", 3, "Ilusão", "Padrão hipnótico: criaturas em 9m ficam enfeitiçadas 1 min"),
    SpellEntry("Velocidade", "Haste", 3, "Transmutação", "Velocidade ×2, +2 CA, ação bônus extra, concentração 1 min"),
    SpellEntry("Forma Gasosa", "Gaseous Form", 3, "Transmutação", "Alvo vira nuvem: voar 3m, imune a físico, concentração"),
    # Nível 4
    SpellEntry("Polimorfar", "Polymorph", 4, "Transmutação", "Transforma criatura em besta, usa HP da forma, concentração"),
    SpellEntry("Olho Arcano", "Arcane Eye", 4, "Adivinhação", "Olho invisível voa 9m/turno, ver tudo, 1 hora"),
    SpellEntry("Dimensão Porta", "Dimension Door", 4, "Conjuração", "Teleporta até 500m (com 1 passageiro)"),
    SpellEntry("Explosão de Congelamento", "Ice Storm", 4, "Evocação", "Granizo: 2d8 contundente+4d6 frio, cilindro 6m, save DES"),
    SpellEntry("Mistura Maior", "Greater Invisibility", 4, "Ilusão", "Invisibilidade que persiste ao atacar, concentração 1 min"),
    # Nível 5
    SpellEntry("Cone de Frio", "Cone of Cold", 5, "Evocação", "8d8 frio, cone 18m, save CON para metade"),
    SpellEntry("Telecinesia", "Telekinesis", 5, "Transmutação", "Move objetos/criaturas com força mental, concentração 10 min"),
    SpellEntry("Teleporte", "Teleport", 5, "Conjuração", "Teleporta grupo para local familiar (com risco de desvio)"),
    SpellEntry("Mão de Bigby", "Bigby's Hand", 5, "Evocação", "Mão arcana: soco 5d8, agarrar, empurrar, 1 minuto"),
]

_MAGIAS_CLERIGO: list[SpellEntry] = [
    # Truques (nível 0)
    SpellEntry("Chama Sagrada", "Sacred Flame", 0, "Evocação", "1d8 radiante, save DES, ignora cobertura. +1d8 em 5/11/17"),
    SpellEntry("Luz", "Light", 0, "Evocação", "Objeto brilha como tocha por 1 hora"),
    SpellEntry("Taumaturgia", "Thaumaturgy", 0, "Transmutação", "Pequenos milagres: voz trovejante, portas, chamas, 1 min"),
    SpellEntry("Conselho", "Guidance", 0, "Adivinhação", "Aliado ganha 1d4 em próxima verificação, concentração"),
    SpellEntry("Resistência", "Resistance", 0, "Abjuração", "Aliado adiciona 1d4 em próxima saving throw, concentração"),
    SpellEntry("Palavra de Cura", "Spare the Dying", 0, "Necromancia", "Criatura estabilizada em 0 HP a 9m de distância"),
    # Nível 1
    SpellEntry("Curar Ferimentos", "Cure Wounds", 1, "Evocação", "1d8+mod.SAB PV curados por toque"),
    SpellEntry("Abençoar", "Bless", 1, "Encantamento", "Até 3 aliados: +1d4 em ataques e saves, 1 min, concentração"),
    SpellEntry("Infligir Ferimentos", "Inflict Wounds", 1, "Necromancia", "Toque: 3d10 necrótico; +1d10 por slot extra"),
    SpellEntry("Proteção do Mal e do Bem", "Protection from Evil and Good", 1, "Abjuração", "Proteção contra aberrações, mortos-vivos, fiendish, 10 min"),
    SpellEntry("Detectar Magia", "Detect Magic", 1, "Adivinhação", "Sentir auras mágicas a 9m, concentração 10 min, ritual"),
    SpellEntry("Guia", "Guiding Bolt", 1, "Evocação", "Ranged: 4d6 radiante + vantagem no próximo ataque ao alvo"),
    SpellEntry("Cura Menor", "Healing Word", 1, "Evocação", "Ação bônus: 1d4+mod.SAB PV a alvo a 18m"),
    SpellEntry("Santuário", "Sanctuary", 1, "Abjuração", "Atacantes fazem save SAB ou escolhem outro alvo, 1 min"),
    SpellEntry("Escudo da Fé", "Shield of Faith", 1, "Abjuração", "+2 CA a aliado por 10 minutos, concentração"),
    # Nível 2
    SpellEntry("Palavra de Cura Maior", "Healing Spirit", 2, "Conjuração", "Espírito que cura 1d6 a aliados adjacentes, concentração"),
    SpellEntry("Arma Espiritual", "Spiritual Weapon", 2, "Evocação", "Arma mágica: ação bônus atacar 1d8+SAB força, 1 min"),
    SpellEntry("Silêncio", "Silence", 2, "Ilusão", "Zona 6m sem som por 10 min, bloqueia magias verbais"),
    SpellEntry("Orar pelos Mortos", "Prayer of Healing", 2, "Evocação", "Cura até 6 aliados: 2d8+SAB cada (10 min para conjurar)"),
    SpellEntry("Imobilizar Pessoa", "Hold Person", 2, "Encantamento", "Humanoide paralisado, save SAB a cada turno, 1 minuto"),
    SpellEntry("Visão Espiritual", "Augury", 2, "Adivinhação", "Ritual: bom/mau/misto/nada sobre ação nos próximos 30 min"),
    SpellEntry("Consagrar", "Consecrate", 2, "Necromancia", "Área de terreno sagrado, mortos-vivos com desvantagem"),
    # Nível 3
    SpellEntry("Cura de Ferimentos em Massa", "Mass Healing Word", 3, "Evocação", "Ação bônus: 1d4+SAB a até 6 aliados a 18m"),
    SpellEntry("Remover Maldição", "Remove Curse", 3, "Abjuração", "Termina todas as maldições sobre toque"),
    SpellEntry("Revivificar", "Revivify", 3, "Necromancia", "Ressuscita morto há ≤1 minuto com 1 HP (100 po)"),
    SpellEntry("Luz do Dia", "Daylight", 3, "Evocação", "Esfera 18m de luz solar brilhante por 1 hora"),
    SpellEntry("Chamar Raios", "Call Lightning", 3, "Conjuração", "Nuvem: raio 3d10 elétrico por turno, concentração 10 min"),
    SpellEntry("Animar Mortos", "Animate Dead", 3, "Necromancia", "Cria esqueleto ou zumbi de cadáver, controla 24h"),
    SpellEntry("Visão Clairvoyante", "Clairvoyance", 3, "Adivinhação", "Câmera espiritual invisível em local conhecido, 10 min"),
    # Nível 4
    SpellEntry("Banimento", "Banishment", 4, "Abjuração", "Criatura deslocada para outro plano, save CAR, concentração"),
    SpellEntry("Guardiões Espirituais", "Guardian of Faith", 4, "Conjuração", "Guardião 10m: 20 radiante ou sombrio a invasores"),
    SpellEntry("Liberdade de Movimento", "Freedom of Movement", 4, "Abjuração", "Aliado ignora terreno difícil e imobilização, 1 hora"),
    SpellEntry("Polimorfar", "Polymorph", 4, "Transmutação", "Transforma criatura em besta, usa HP da forma, concentração"),
    # Nível 5
    SpellEntry("Curar Ferimentos em Massa", "Mass Cure Wounds", 5, "Evocação", "Até 6 criaturas a 18m: 3d8+SAB PV curadas cada"),
    SpellEntry("Flamestrike", "Flame Strike", 5, "Evocação", "Coluna de fogo divino: 4d6 fogo+4d6 radiante, save CON"),
    SpellEntry("Contato de Plano Superior", "Commune", 5, "Adivinhação", "Ritual: 3 respostas sim/não da divindade"),
]

_MAGIAS_DRUIDA: list[SpellEntry] = [
    # Truques (nível 0)
    SpellEntry("Chama Produzida", "Produce Flame", 0, "Conjuração", "1d8 fogo corpo a corpo ou 9m arremessado. +1d8 em 5/11/17"),
    SpellEntry("Veneno Irritante", "Poison Spray", 0, "Conjuração", "3m alcance: 1d12 veneno, save CON. +1d12 em 5/11/17"),
    SpellEntry("Conselho", "Guidance", 0, "Adivinhação", "Aliado ganha 1d4 em próxima verificação, concentração"),
    SpellEntry("Resistência", "Resistance", 0, "Abjuração", "Aliado adiciona 1d4 em próxima saving throw, concentração"),
    SpellEntry("Formação de Gelo", "Frostbite", 0, "Evocação", "Save CON ou 1d6 frio + desvantagem no próximo ataque"),
    SpellEntry("Crescimento de Espinhos", "Thorn Whip", 0, "Transmutação", "Ataque: 1d6 perfurante, puxa alvo 3m. +1d6 em 5/11/17"),
    # Nível 1
    SpellEntry("Absorver Elementos", "Absorb Elements", 1, "Abjuração", "Reação: resistência ao elemento; próximo acerto +1d6 dano"),
    SpellEntry("Criar ou Destruir Água", "Create or Destroy Water", 1, "Transmutação", "Cria 40L de água limpa ou destrói névoa/chuva"),
    SpellEntry("Cura de Ferimentos", "Cure Wounds", 1, "Evocação", "1d8+mod.SAB PV curados por toque"),
    SpellEntry("Armadilha de Fadas", "Faerie Fire", 1, "Evocação", "Luz: alvos visíveis, vantagem em ataques contra eles, 1 min"),
    SpellEntry("Névoa de Adormecimento", "Fog Cloud", 1, "Conjuração", "Esfera 6m de névoa pesada, bloqueia visão, 1 hora"),
    SpellEntry("Salto", "Jump", 1, "Transmutação", "Distância de salto ×3 por 1 minuto"),
    SpellEntry("Entrelaçar", "Entangle", 1, "Conjuração", "Quadrado 6m de vinhas: save FOR ou paralisado, concentração"),
    SpellEntry("Falar com Animais", "Speak with Animals", 1, "Adivinhação", "Comunicar-se com animais por 10 minutos, ritual"),
    SpellEntry("Curar Ferimentos por Cura Rápida", "Healing Word", 1, "Evocação", "Ação bônus: 1d4+SAB PV a 18m"),
    # Nível 2
    SpellEntry("Pele de Casca de Carvalho", "Barkskin", 2, "Transmutação", "CA mínima 16 por 1 hora, concentração"),
    SpellEntry("Florescimento", "Flaming Sphere", 2, "Conjuração", "Esfera flamejante: 2d6 fogo aos adjacentes, 1 min"),
    SpellEntry("Silêncio", "Silence", 2, "Ilusão", "Zona 6m sem som por 10 min, bloqueia magias verbais"),
    SpellEntry("Imobilizar Pessoa", "Hold Person", 2, "Encantamento", "Humanoide paralisado, save SAB a cada turno, 1 minuto"),
    SpellEntry("Passagem entre Árvores", "Pass without Trace", 2, "Abjuração", "+10 em Furtividade, rastreamento impossível, concentração"),
    SpellEntry("Enxame de Espinhos", "Spike Growth", 2, "Transmutação", "Solo 6m: terreno difícil + 2d4 por 1,5m percorrido"),
    SpellEntry("Forma Enxame", "Summon Beast", 2, "Conjuração", "Convoca espírito besta CR 1 ou menor, concentração 1 hora"),
    # Nível 3
    SpellEntry("Chamar Raios", "Call Lightning", 3, "Conjuração", "Nuvem: raio 3d10 elétrico por turno, concentração 10 min"),
    SpellEntry("Remodelar a Terra", "Meld into Stone", 3, "Transmutação", "Funde-se com pedra por 8 horas, ritual"),
    SpellEntry("Falar com Plantas", "Speak with Plants", 3, "Transmutação", "Plantas obedecem e informam por 10 minutos"),
    SpellEntry("Muro de Água", "Wall of Water", 3, "Evocação", "Muro de água 9m: meia cobertura, retarda projéteis"),
    SpellEntry("Trovão Esmagador", "Erupting Earth", 3, "Transmutação", "Cubo 4,5m: 3d12 contundente, save DES, terreno difícil"),
    SpellEntry("Ressuscitar Animais", "Conjure Animals", 3, "Conjuração", "Convoca espíritos bestas (CR total ≤2 em 2-8 criaturas)"),
    SpellEntry("Vento de Muro", "Wind Wall", 3, "Evocação", "Muro 15m: 3d8 contundente, saltos de projéteis, 1 min"),
    # Nível 4
    SpellEntry("Polimorfar", "Polymorph", 4, "Transmutação", "Transforma criatura em besta, usa HP da forma, concentração"),
    SpellEntry("Tempestade de Gelo", "Ice Storm", 4, "Evocação", "Granizo: 2d8 contundente+4d6 frio, cilindro 6m, save DES"),
    SpellEntry("Liberdade de Movimento", "Freedom of Movement", 4, "Abjuração", "Aliado ignora terreno difícil e imobilização, 1 hora"),
    SpellEntry("Localizar Criatura", "Locate Creature", 4, "Adivinhação", "Sentir criatura conhecida em 1,5km, concentração 1 hora"),
    # Nível 5
    SpellEntry("Conjurar Elemental", "Conjure Elemental", 5, "Conjuração", "Convoca elemental CR 5 (ar/terra/fogo/água), concentração"),
    SpellEntry("Contagiar", "Contagion", 5, "Necromancia", "Toque: doença incapacitante após 3 saves fracassados"),
    SpellEntry("Despertar", "Awaken", 5, "Transmutação", "Besta ou planta ganha INT 10 e linguagem, 8h ritual"),
]

_MAGIAS_BARDO: list[SpellEntry] = [
    # Truques (nível 0)
    SpellEntry("Prestidigitação", "Prestidigitation", 0, "Transmutação", "Efeitos mágicos triviais, 10m de alcance"),
    SpellEntry("Raio Venenoso", "Vicious Mockery", 0, "Encantamento", "Save SAB ou 1d4 psíquico + desvantagem no próximo ataque"),
    SpellEntry("Luz", "Light", 0, "Evocação", "Objeto brilha como tocha por 1 hora"),
    SpellEntry("Mão Mágica", "Mage Hand", 0, "Conjuração", "Mão espectral manipula objetos a 9m"),
    SpellEntry("Mensagem", "Message", 0, "Transmutação", "Sussurra mensagem a 90m, alvo pode responder uma vez"),
    SpellEntry("Dança das Luzes", "Dancing Lights", 0, "Evocação", "Até 4 luzes flutuantes, ilumina 3m cada, concentração"),
    # Nível 1
    SpellEntry("Inspiração Bélica", "Heroism", 1, "Encantamento", "Imune a medo, PV temporários = mod.CAR por turno, 1 min"),
    SpellEntry("Charme de Pessoa", "Charm Person", 1, "Encantamento", "Encanta humanoide, save SAB, dura 1 hora"),
    SpellEntry("Palavra de Cura", "Healing Word", 1, "Evocação", "Ação bônus: 1d4+CAR PV a alvo a 18m"),
    SpellEntry("Dormir", "Sleep", 1, "Encantamento", "5d8 PV de criaturas adormecidas (mais fracas primeiro)"),
    SpellEntry("Onda de Trovão", "Thunderwave", 1, "Evocação", "Cubo 4,5m: 2d8 trovão, save CON, empurra 3m"),
    SpellEntry("Falar com Animais", "Speak with Animals", 1, "Adivinhação", "Comunicar-se com animais por 10 minutos, ritual"),
    SpellEntry("Detectar Magia", "Detect Magic", 1, "Adivinhação", "Sentir auras mágicas a 9m, concentração 10 min, ritual"),
    SpellEntry("Sussurros Dissonantes", "Dissonant Whispers", 1, "Encantamento", "1 alvo: 3d6 psíquico, save SAB, usa reação pra fugir"),
    # Nível 2
    SpellEntry("Invisibilidade", "Invisibility", 2, "Ilusão", "Alvo invisível por 1 hora ou até atacar/lançar magia"),
    SpellEntry("Sugestão", "Suggestion", 2, "Encantamento", "Sugestão razoável compelida, save SAB, dura 8 horas"),
    SpellEntry("Silêncio", "Silence", 2, "Ilusão", "Zona 6m sem som por 10 min, bloqueia magias verbais"),
    SpellEntry("Imobilizar Pessoa", "Hold Person", 2, "Encantamento", "Humanoide paralisado, save SAB a cada turno, 1 minuto"),
    SpellEntry("Shatter", "Shatter", 2, "Evocação", "Esfera 3m: 3d8 trovão, save CON para metade"),
    SpellEntry("Visão no Escuro", "Darkvision", 2, "Transmutação", "Alvo ganha visão no escuro 18m por 8 horas"),
    SpellEntry("Zona da Verdade", "Zone of Truth", 2, "Encantamento", "Esfera 4,5m: criaturas não podem mentir conscientemente"),
    # Nível 3
    SpellEntry("Hipnose Hipnótica", "Hypnotic Pattern", 3, "Ilusão", "Padrão hipnótico: criaturas em 9m ficam enfeitiçadas 1 min"),
    SpellEntry("Imagem Maior", "Major Image", 3, "Ilusão", "Ilusão com som, cheiro, temperatura; concentração 10 min"),
    SpellEntry("Linguagem Perfeita", "Tongues", 3, "Adivinhação", "Falar e entender qualquer idioma por 1 hora"),
    SpellEntry("Fantasma Stinking Cloud", "Stinking Cloud", 3, "Conjuração", "Nuvem amarela 6m: save CON ou gastar ação em náusea"),
    # Nível 4
    SpellEntry("Polimorfar", "Polymorph", 4, "Transmutação", "Transforma criatura em besta, usa HP da forma, concentração"),
    SpellEntry("Confusão", "Confusion", 4, "Encantamento", "Criaturas em 3m: comportamento aleatório, save SAB 1 min"),
    SpellEntry("Dimensão Porta", "Dimension Door", 4, "Conjuração", "Teleporta até 500m (com 1 passageiro)"),
    SpellEntry("Sugestão em Massa", "Greater Invisibility", 4, "Ilusão", "Invisibilidade que persiste ao atacar, concentração 1 min"),
    # Nível 5
    SpellEntry("Sugestão em Massa", "Mass Suggestion", 5, "Encantamento", "Sugestão para até 12 criaturas, save SAB, 24 horas"),
    SpellEntry("Projete Imagem", "Mislead", 5, "Ilusão", "Torna-se invisível e cria ilusão de si, concentração 1 hora"),
]

_MAGIAS_FEITICEIRO: list[SpellEntry] = [
    # Truques (nível 0)
    SpellEntry("Raio de Fogo", "Fire Bolt", 0, "Evocação", "Ataque: 1d10 fogo a 36m. +1d10 em níveis 5/11/17"),
    SpellEntry("Choque de Trovão", "Shocking Grasp", 0, "Evocação", "1d8 elétrico, alvo sem reação. +1d8 em 5/11/17"),
    SpellEntry("Raio de Gelo", "Ray of Frost", 0, "Evocação", "1d8 frio, velocidade -3m. +1d8 em níveis 5/11/17"),
    SpellEntry("Chama Verdadeira", "True Strike", 0, "Adivinhação", "Concentração: vantagem no próximo ataque ao alvo"),
    SpellEntry("Mão Mágica", "Mage Hand", 0, "Conjuração", "Mão espectral manipula objetos a 9m"),
    SpellEntry("Prestidigitação", "Prestidigitation", 0, "Transmutação", "Efeitos mágicos triviais, 10m de alcance"),
    # Nível 1
    SpellEntry("Míssil Mágico", "Magic Missile", 1, "Evocação", "3 dardos 1d4+1 força, sempre acertam"),
    SpellEntry("Escudo Arcano", "Shield", 1, "Abjuração", "Reação: +5 CA até próximo turno, bloqueia Míssil Mágico"),
    SpellEntry("Mãos Ardentes", "Burning Hands", 1, "Evocação", "3d6 fogo, cone 4,5m, save DES para metade"),
    SpellEntry("Charme de Pessoa", "Charm Person", 1, "Encantamento", "Encanta humanoide, save SAB, dura 1 hora"),
    SpellEntry("Sono", "Sleep", 1, "Encantamento", "5d8 PV de criaturas adormecidas (mais fracas primeiro)"),
    SpellEntry("Armadura de Mago", "Mage Armor", 1, "Abjuração", "CA 13+DES por 8 horas (sem armadura)"),
    SpellEntry("Raio de Doença", "Ray of Sickness", 1, "Necromancia", "Ataque: 2d8 veneno, save CON ou envenenado 1 turno"),
    # Nível 2
    SpellEntry("Invisibilidade", "Invisibility", 2, "Ilusão", "Alvo invisível por 1 hora ou até atacar/lançar magia"),
    SpellEntry("Flecha Ácida de Melf", "Melf's Acid Arrow", 2, "Evocação", "Acerto: 4d4 ácido imediato + 2d4 no próximo turno"),
    SpellEntry("Escuridão", "Darkness", 2, "Evocação", "Esfera 4,5m de escuridão mágica, bloqueia visão no escuro"),
    SpellEntry("Imobilizar Pessoa", "Hold Person", 2, "Encantamento", "Humanoide paralisado, save SAB a cada turno, 1 minuto"),
    SpellEntry("Rajada de Trovão", "Shatter", 2, "Evocação", "Esfera 3m: 3d8 trovão, save CON para metade"),
    SpellEntry("Sugestão", "Suggestion", 2, "Encantamento", "Sugestão razoável compelida, save SAB, dura 8 horas"),
    # Nível 3
    SpellEntry("Bola de Fogo", "Fireball", 3, "Evocação", "8d6 fogo, esfera 6m, save DES para metade, 45m"),
    SpellEntry("Relâmpago", "Lightning Bolt", 3, "Evocação", "8d6 elétrico, linha 30m×1,5m, save DES para metade"),
    SpellEntry("Velocidade", "Haste", 3, "Transmutação", "Velocidade ×2, +2 CA, ação bônus extra, concentração 1 min"),
    SpellEntry("Contramagia", "Counterspell", 3, "Abjuração", "Reação: interrompe magia sendo lançada (automático ≤3)"),
    SpellEntry("Hipnose Hipnótica", "Hypnotic Pattern", 3, "Ilusão", "Padrão hipnótico: criaturas em 9m ficam enfeitiçadas 1 min"),
    # Nível 4
    SpellEntry("Polimorfar", "Polymorph", 4, "Transmutação", "Transforma criatura em besta, usa HP da forma, concentração"),
    SpellEntry("Dimensão Porta", "Dimension Door", 4, "Conjuração", "Teleporta até 500m (com 1 passageiro)"),
    SpellEntry("Tempestade de Gelo", "Ice Storm", 4, "Evocação", "Granizo: 2d8 contundente+4d6 frio, cilindro 6m, save DES"),
    # Nível 5
    SpellEntry("Cone de Frio", "Cone of Cold", 5, "Evocação", "8d8 frio, cone 18m, save CON para metade"),
    SpellEntry("Telecinesia", "Telekinesis", 5, "Transmutação", "Move objetos/criaturas com força mental, concentração 10 min"),
]

_MAGIAS_BRUXO: list[SpellEntry] = [
    # Truques (nível 0)
    SpellEntry("Explosão Eldritch", "Eldritch Blast", 0, "Evocação", "1 raio 1d10 força a 36m. 2 em nível 5, 3 em 11, 4 em 17"),
    SpellEntry("Toque Gelado", "Chill Touch", 0, "Necromancia", "1d8 necrótico, alvo não regenera HP até seu próximo turno"),
    SpellEntry("Mão Mágica", "Mage Hand", 0, "Conjuração", "Mão espectral manipula objetos a 9m"),
    SpellEntry("Veneno Irritante", "Poison Spray", 0, "Conjuração", "3m: 1d12 veneno, save CON. +1d12 em 5/11/17"),
    SpellEntry("Sussurros Sombrios", "Minor Illusion", 0, "Ilusão", "Som ou imagem estática em cubo 1,5m por 1 minuto"),
    # Nível 1
    SpellEntry("Armadura de Hex", "Hex", 1, "Encantamento", "Amaldiçoa alvo: +1d6 necrótico nos ataques, desvantagem em atrib."),
    SpellEntry("Charme de Pessoa", "Charm Person", 1, "Encantamento", "Encanta humanoide, save SAB, dura 1 hora"),
    SpellEntry("Maldição de Praga", "Arms of Hadar", 1, "Conjuração", "Tentáculos 3m: 2d6 necrótico, save FOR, sem reações 1 turno"),
    SpellEntry("Raio de Doença", "Ray of Sickness", 1, "Necromancia", "Ataque: 2d8 veneno, save CON ou envenenado 1 turno"),
    SpellEntry("Escudo Arcano", "Shield", 1, "Abjuração", "Reação: +5 CA até próximo turno, bloqueia Míssil Mágico"),
    # Nível 2
    SpellEntry("Escuridão", "Darkness", 2, "Evocação", "Esfera 4,5m de escuridão mágica, bloqueia visão no escuro"),
    SpellEntry("Imobilizar Pessoa", "Hold Person", 2, "Encantamento", "Humanoide paralisado, save SAB a cada turno, 1 minuto"),
    SpellEntry("Invisibilidade", "Invisibility", 2, "Ilusão", "Alvo invisível por 1 hora ou até atacar/lançar magia"),
    SpellEntry("Sugestão", "Suggestion", 2, "Encantamento", "Sugestão razoável compelida, save SAB, dura 8 horas"),
    SpellEntry("Rajada de Sombras", "Shadow of Moil", 2, "Necromancia", "Ataques contra você têm desvantagem, causar escuridão"),
    SpellEntry("Força Fantasmal", "Phantasmal Force", 2, "Ilusão", "Ilusão que parece real ao alvo, 1d6 por turno, 1 min"),
    # Nível 3
    SpellEntry("Hipnose Hipnótica", "Hypnotic Pattern", 3, "Ilusão", "Padrão hipnótico: criaturas em 9m ficam enfeitiçadas 1 min"),
    SpellEntry("Voo", "Fly", 3, "Transmutação", "Velocidade de voo 18m por 10 minutos, concentração"),
    SpellEntry("Contramagia", "Counterspell", 3, "Abjuração", "Reação: interrompe magia sendo lançada (automático ≤3)"),
    SpellEntry("Forma Gasosa", "Gaseous Form", 3, "Transmutação", "Alvo vira nuvem: voar 3m, imune a físico, concentração"),
    SpellEntry("Animar Mortos", "Animate Dead", 3, "Necromancia", "Cria esqueleto ou zumbi de cadáver, controla 24h"),
    # Nível 4
    SpellEntry("Banimento", "Banishment", 4, "Abjuração", "Criatura deslocada para outro plano, save CAR, concentração"),
    SpellEntry("Polimorfar", "Polymorph", 4, "Transmutação", "Transforma criatura em besta, usa HP da forma, concentração"),
    SpellEntry("Dimensão Porta", "Dimension Door", 4, "Conjuração", "Teleporta até 500m (com 1 passageiro)"),
    # Nível 5
    SpellEntry("Contato de Plano Superior", "Contact Other Plane", 5, "Adivinhação", "Ritual: 5 perguntas a entidade extraplanar (save INT ou insanidade)"),
    SpellEntry("Dominar Pessoa", "Dominate Person", 5, "Encantamento", "Controla humanoide: save SAB, 1 minuto, concentração"),
]

_MAGIAS_PALADINO: list[SpellEntry] = [
    # Nível 1
    SpellEntry("Bênção", "Bless", 1, "Encantamento", "Até 3 aliados: +1d4 em ataques e saves, 1 min, concentração"),
    SpellEntry("Curar Ferimentos", "Cure Wounds", 1, "Evocação", "1d8+mod.CAR PV curados por toque"),
    SpellEntry("Proteção do Mal e do Bem", "Protection from Evil and Good", 1, "Abjuração", "Proteção contra aberrações, mortos-vivos, fiendish, 10 min"),
    SpellEntry("Palavra Divina", "Command", 1, "Encantamento", "1 palavra: humanoide obedece por 1 turno, save SAB"),
    SpellEntry("Identificar", "Identify", 1, "Adivinhação", "Revela propriedades mágicas de item, ritual, 1 min"),
    SpellEntry("Escudo da Fé", "Shield of Faith", 1, "Abjuração", "+2 CA a aliado por 10 minutos, concentração"),
    SpellEntry("Feridas da Luz", "Wrathful Smite", 1, "Evocação", "Próximo acerto: +1d6 psíquico, alvo fica amedrontado"),
    # Nível 2
    SpellEntry("Arma Divina", "Magic Weapon", 2, "Transmutação", "Arma não-mágica vira mágica +1 por 1 hora, concentração"),
    SpellEntry("Aura de Invulnerabilidade", "Zone of Truth", 2, "Encantamento", "Esfera 4,5m: criaturas não podem mentir conscientemente"),
    SpellEntry("Restauração Menor", "Lesser Restoration", 2, "Abjuração", "Remove uma doença, condição de cegueira, surdez, paralisia"),
    SpellEntry("Encontrar Corcel", "Find Steed", 2, "Conjuração", "Convoca corcel espiritual leal como bonded companion"),
    SpellEntry("Imobilizar Pessoa", "Hold Person", 2, "Encantamento", "Humanoide paralisado, save SAB a cada turno, 1 minuto"),
    SpellEntry("Proteção contra Veneno", "Protection from Poison", 2, "Abjuração", "Anula/suspende veneno, resistência a dano veneno, 1 hora"),
    # Nível 3
    SpellEntry("Revivificar", "Revivify", 3, "Necromancia", "Ressuscita morto há ≤1 minuto com 1 HP (100 po)"),
    SpellEntry("Aura de Coragem", "Beacon of Hope", 3, "Abjuração", "Aliados: vantagem em SAB e morte saves, max HP em curas"),
    SpellEntry("Dissipar Magia", "Dispel Magic", 3, "Abjuração", "Remove magias em criaturas ou objetos (automático ≤3)"),
    SpellEntry("Ouro Cegante", "Blinding Smite", 3, "Evocação", "Próximo acerto: +3d8 radiante, alvo fica cego, save CON"),
    SpellEntry("Criar Alimento e Água", "Create Food and Water", 3, "Conjuração", "Cria comida e água para 15 pessoas por 1 dia"),
    # Nível 4
    SpellEntry("Banimento", "Banishment", 4, "Abjuração", "Criatura deslocada para outro plano, save CAR, concentração"),
    SpellEntry("Liberdade de Movimento", "Freedom of Movement", 4, "Abjuração", "Aliado ignora terreno difícil e imobilização, 1 hora"),
    SpellEntry("Polimorfar", "Polymorph", 4, "Transmutação", "Transforma criatura em besta, usa HP da forma, concentração"),
]

_MAGIAS_RANGER: list[SpellEntry] = [
    # Nível 1
    SpellEntry("Absorver Elementos", "Absorb Elements", 1, "Abjuração", "Reação: resistência ao elemento; próximo acerto +1d6 dano"),
    SpellEntry("Alarme", "Alarm", 1, "Abjuração", "Alerta mental/sonoro se criaturas entram na zona, ritual"),
    SpellEntry("Curar Ferimentos", "Cure Wounds", 1, "Evocação", "1d8+mod.SAB PV curados por toque"),
    SpellEntry("Névoa de Adormecimento", "Fog Cloud", 1, "Conjuração", "Esfera 6m de névoa pesada, bloqueia visão, 1 hora"),
    SpellEntry("Saltar", "Longstrider", 1, "Transmutação", "Velocidade +3m por 1 hora"),
    SpellEntry("Desestruturar Terreno", "Snare", 1, "Abjuração", "Armadilha mágica no chão: imobiliza, save DES, 8 horas"),
    SpellEntry("Falar com Animais", "Speak with Animals", 1, "Adivinhação", "Comunicar-se com animais por 10 minutos, ritual"),
    SpellEntry("Marca do Caçador", "Hunter's Mark", 1, "Adivinhação", "Marca alvo: +1d6 em ataques, vantagem em rastrear, 1 hora"),
    # Nível 2
    SpellEntry("Passo de Silêncio", "Pass without Trace", 2, "Abjuração", "+10 em Furtividade, rastreamento impossível, concentração"),
    SpellEntry("Localizar Animais ou Plantas", "Locate Animals or Plants", 2, "Adivinhação", "Ritual: sentir espécie conhecida em 8km, mais próxima"),
    SpellEntry("Restauração Menor", "Lesser Restoration", 2, "Abjuração", "Remove uma doença, condição de cegueira, surdez, paralisia"),
    SpellEntry("Visão no Escuro", "Darkvision", 2, "Transmutação", "Alvo ganha visão no escuro 18m por 8 horas"),
    SpellEntry("Enxame de Espinhos", "Spike Growth", 2, "Transmutação", "Solo 6m: terreno difícil + 2d4 por 1,5m percorrido"),
    SpellEntry("Silêncio", "Silence", 2, "Ilusão", "Zona 6m sem som por 10 min, bloqueia magias verbais"),
    # Nível 3
    SpellEntry("Voo de Besta", "Conjure Barrage", 3, "Conjuração", "Cone 18m de projéteis: 3d8 do tipo da arma, save DES"),
    SpellEntry("Proteção contra Energia", "Protection from Energy", 3, "Abjuração", "Resistência a tipo de dano elemental, concentração 1 hora"),
    SpellEntry("Vento Tempestuoso", "Wind Wall", 3, "Evocação", "Muro 15m: 3d8 contundente, saltos de projéteis, 1 min"),
    SpellEntry("Criar Alimento", "Conjure Animals", 3, "Conjuração", "Convoca espíritos bestas (CR total ≤2 em 2-8 criaturas)"),
]


# ── Dicionário principal: classe (lowercase) → lista de SpellEntry ────────────
SPELLS_POR_CLASSE: dict[str, list[SpellEntry]] = {
    "mago":       _MAGIAS_MAGO,
    "clérigo":    _MAGIAS_CLERIGO,
    "druida":     _MAGIAS_DRUIDA,
    "bardo":      _MAGIAS_BARDO,
    "feiticeiro": _MAGIAS_FEITICEIRO,
    "bruxo":      _MAGIAS_BRUXO,
    "paladino":   _MAGIAS_PALADINO,
    "ranger":     _MAGIAS_RANGER,
}

# Alias para nomes com acento — facilita lookups sem normalização
SPELLS_POR_CLASSE["clerigo"] = SPELLS_POR_CLASSE["clérigo"]


# ── Progressão de Magias por Classe e Nível de Personagem ────────────────────
#
# Baseado nas tabelas do SRD 5e (System Reference Document).
# "magias": número máximo de magias conhecidas/preparadas (usa nível+3 como
#   aproximação para classes que preparam — Clérigo, Druida, Paladino, Ranger).
# "nivel_max": nível máximo de spell slot disponível para o personagem.
# Conjuradores plenos: Mago, Bardo, Clérigo, Druida, Feiticeiro.
# Meio-conjuradores: Paladino, Ranger (começam com magia no nível 2).
# Invocações especiais: Bruxo (slots únicos, número fixo).

def _prog_pleno(truques_por_nivel: list[int], magias_por_nivel: list[int]) -> dict[int, dict]:
    """Gera tabela de progressão para full casters."""
    # nivel_max por nível de personagem (full caster SRD)
    nivel_max_full = [1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,9,9]
    tabela: dict[int, dict] = {}
    for i in range(10):
        nivel_pers = i + 1
        tabela[nivel_pers] = {
            "truques": truques_por_nivel[i],
            "magias": magias_por_nivel[i],
            "nivel_max": nivel_max_full[i],
        }
    return tabela


PROGRESSAO_MAGIAS: dict[str, dict[int, dict]] = {
    "mago": {
        1: {"truques": 3, "magias": 6,  "nivel_max": 1},
        2: {"truques": 3, "magias": 8,  "nivel_max": 1},
        3: {"truques": 3, "magias": 10, "nivel_max": 2},
        4: {"truques": 4, "magias": 12, "nivel_max": 2},
        5: {"truques": 4, "magias": 14, "nivel_max": 3},
        6: {"truques": 4, "magias": 16, "nivel_max": 3},
        7: {"truques": 4, "magias": 18, "nivel_max": 4},
        8: {"truques": 4, "magias": 20, "nivel_max": 4},
        9: {"truques": 4, "magias": 22, "nivel_max": 5},
        10: {"truques": 5, "magias": 24, "nivel_max": 5},
    },
    # Clérigo e Druida: preparam nível+mod.SAB, aqui usa nível+3 como aproximação
    "clérigo": {
        1: {"truques": 3, "magias": 4,  "nivel_max": 1},
        2: {"truques": 3, "magias": 5,  "nivel_max": 1},
        3: {"truques": 3, "magias": 6,  "nivel_max": 2},
        4: {"truques": 4, "magias": 7,  "nivel_max": 2},
        5: {"truques": 4, "magias": 8,  "nivel_max": 3},
        6: {"truques": 4, "magias": 9,  "nivel_max": 3},
        7: {"truques": 4, "magias": 10, "nivel_max": 4},
        8: {"truques": 4, "magias": 11, "nivel_max": 4},
        9: {"truques": 4, "magias": 12, "nivel_max": 5},
        10: {"truques": 5, "magias": 13, "nivel_max": 5},
    },
    "druida": {
        1: {"truques": 2, "magias": 4,  "nivel_max": 1},
        2: {"truques": 2, "magias": 5,  "nivel_max": 1},
        3: {"truques": 2, "magias": 6,  "nivel_max": 2},
        4: {"truques": 3, "magias": 7,  "nivel_max": 2},
        5: {"truques": 3, "magias": 8,  "nivel_max": 3},
        6: {"truques": 3, "magias": 9,  "nivel_max": 3},
        7: {"truques": 3, "magias": 10, "nivel_max": 4},
        8: {"truques": 3, "magias": 11, "nivel_max": 4},
        9: {"truques": 3, "magias": 12, "nivel_max": 5},
        10: {"truques": 4, "magias": 13, "nivel_max": 5},
    },
    "bardo": {
        1: {"truques": 2, "magias": 4,  "nivel_max": 1},
        2: {"truques": 2, "magias": 5,  "nivel_max": 1},
        3: {"truques": 2, "magias": 6,  "nivel_max": 2},
        4: {"truques": 3, "magias": 7,  "nivel_max": 2},
        5: {"truques": 3, "magias": 8,  "nivel_max": 3},
        6: {"truques": 3, "magias": 9,  "nivel_max": 3},
        7: {"truques": 3, "magias": 10, "nivel_max": 4},
        8: {"truques": 3, "magias": 11, "nivel_max": 4},
        9: {"truques": 3, "magias": 12, "nivel_max": 5},
        10: {"truques": 4, "magias": 14, "nivel_max": 5},
    },
    "feiticeiro": {
        1: {"truques": 4, "magias": 2,  "nivel_max": 1},
        2: {"truques": 4, "magias": 3,  "nivel_max": 1},
        3: {"truques": 4, "magias": 4,  "nivel_max": 2},
        4: {"truques": 5, "magias": 5,  "nivel_max": 2},
        5: {"truques": 5, "magias": 6,  "nivel_max": 3},
        6: {"truques": 5, "magias": 7,  "nivel_max": 3},
        7: {"truques": 5, "magias": 8,  "nivel_max": 4},
        8: {"truques": 5, "magias": 9,  "nivel_max": 4},
        9: {"truques": 5, "magias": 10, "nivel_max": 5},
        10: {"truques": 6, "magias": 11, "nivel_max": 5},
    },
    # Bruxo: número especial de slots "pacto" — usa "magias" como conhecidas
    "bruxo": {
        1: {"truques": 2, "magias": 2,  "nivel_max": 1},
        2: {"truques": 2, "magias": 3,  "nivel_max": 1},
        3: {"truques": 2, "magias": 4,  "nivel_max": 2},
        4: {"truques": 3, "magias": 5,  "nivel_max": 2},
        5: {"truques": 3, "magias": 6,  "nivel_max": 3},
        6: {"truques": 3, "magias": 7,  "nivel_max": 3},
        7: {"truques": 3, "magias": 8,  "nivel_max": 4},
        8: {"truques": 3, "magias": 9,  "nivel_max": 4},
        9: {"truques": 3, "magias": 10, "nivel_max": 5},
        10: {"truques": 4, "magias": 10, "nivel_max": 5},
    },
    # Meio-conjuradores: nível 1 sem magia, progresso mais lento
    "paladino": {
        1: {"truques": 0, "magias": 0,  "nivel_max": 0},
        2: {"truques": 0, "magias": 4,  "nivel_max": 1},
        3: {"truques": 0, "magias": 6,  "nivel_max": 1},
        4: {"truques": 0, "magias": 7,  "nivel_max": 2},
        5: {"truques": 0, "magias": 8,  "nivel_max": 2},
        6: {"truques": 0, "magias": 9,  "nivel_max": 3},
        7: {"truques": 0, "magias": 10, "nivel_max": 3},
        8: {"truques": 0, "magias": 11, "nivel_max": 3},
        9: {"truques": 0, "magias": 12, "nivel_max": 4},
        10: {"truques": 0, "magias": 13, "nivel_max": 4},
    },
    "ranger": {
        1: {"truques": 0, "magias": 0,  "nivel_max": 0},
        2: {"truques": 0, "magias": 2,  "nivel_max": 1},
        3: {"truques": 0, "magias": 3,  "nivel_max": 1},
        4: {"truques": 0, "magias": 3,  "nivel_max": 1},
        5: {"truques": 0, "magias": 4,  "nivel_max": 2},
        6: {"truques": 0, "magias": 4,  "nivel_max": 2},
        7: {"truques": 0, "magias": 5,  "nivel_max": 2},
        8: {"truques": 0, "magias": 5,  "nivel_max": 2},
        9: {"truques": 0, "magias": 6,  "nivel_max": 3},
        10: {"truques": 0, "magias": 6, "nivel_max": 3},
    },
}

# Alias sem acento
PROGRESSAO_MAGIAS["clerigo"] = PROGRESSAO_MAGIAS["clérigo"]


# ── Funções públicas ──────────────────────────────────────────────────────────

def spells_da_classe(classe: str) -> list[SpellEntry]:
    """Retorna todas as spells disponíveis para a classe (lowercase).

    Args:
        classe: Nome da classe em lowercase (ex: "mago", "clérigo", "druida").

    Returns:
        Lista de SpellEntry, vazia se a classe não for spellcaster ou desconhecida.
    """
    return SPELLS_POR_CLASSE.get(classe.lower(), [])


def spells_por_nivel(classe: str, nivel_spell: int) -> list[SpellEntry]:
    """Filtra spells da classe por nível de magia.

    Args:
        classe: Nome da classe em lowercase.
        nivel_spell: Nível da spell (0=truques, 1-9=nível de magia).

    Returns:
        Lista filtrada de SpellEntry com o nível especificado.
    """
    return [s for s in spells_da_classe(classe) if s.nivel == nivel_spell]


def limite_progressao(classe: str, nivel_personagem: int) -> dict:
    """Retorna limites de magias para a classe no nível do personagem.

    Args:
        classe: Nome da classe em lowercase.
        nivel_personagem: Nível do personagem (1-20). Clampado ao range da tabela.

    Returns:
        Dict {"truques": N, "magias": N, "nivel_max": N}.
        Nível fora do range retorna o limite mais próximo (1 ou 10 — máximo da tabela).
        Classe desconhecida retorna {"truques": 0, "magias": 0, "nivel_max": 0}.
    """
    tabela = PROGRESSAO_MAGIAS.get(classe.lower())
    if tabela is None:
        return {"truques": 0, "magias": 0, "nivel_max": 0}
    # Clampa ao range disponível (1–10 na tabela atual)
    nivel_clamped = max(1, min(10, nivel_personagem))
    return tabela[nivel_clamped]


def nivel_da_spell(nome_pt: str, classe: str) -> int | None:
    """Busca o nível de uma spell pelo nome PT-BR dentro da classe.

    Útil para o prompt_builder formatar magias conhecidas por nível.

    Args:
        nome_pt: Nome PT-BR da magia (case-insensitive).
        classe: Classe do personagem em lowercase.

    Returns:
        Nível da spell (0=truque), ou None se não encontrada.
    """
    nome_lower = nome_pt.lower()
    for spell in spells_da_classe(classe):
        if spell.nome_pt.lower() == nome_lower:
            return spell.nivel
    return None


# ── Tabelas de spell slots SRD 5e (espelha CharacterSheet.tsx) ───────────────

# Full casters (Mago, Clérigo, Druida, Bardo, Feiticeiro): slots por nível de personagem
# Índice 0 = nível 1 do personagem. Lista interna: slots por nível de spell (1-based index).
_SLOTS_CONJURADOR_PLENO: list[list[int]] = [
    [2],                # nível 1
    [3],                # nível 2
    [4, 2],             # nível 3
    [4, 3],             # nível 4
    [4, 3, 2],          # nível 5
    [4, 3, 3],          # nível 6
    [4, 3, 3, 1],       # nível 7
    [4, 3, 3, 2],       # nível 8
    [4, 3, 3, 3, 1],    # nível 9
    [4, 3, 3, 3, 2],    # nível 10
]

# Half casters (Paladino, Ranger): slots começam no nível 2
_SLOTS_MEIO_CONJURADOR: list[list[int]] = [
    [],                 # nível 1 — sem slots
    [2],                # nível 2
    [3],                # nível 3
    [3],                # nível 4
    [4, 2],             # nível 5
    [4, 3],             # nível 6
    [4, 3, 2],          # nível 7
    [4, 3, 3],          # nível 8
    [4, 3, 3, 1],       # nível 9
    [4, 3, 3, 2],       # nível 10
]

# Bruxo: Pact Magic — (nível_do_slot, qtd_slots) por nível de personagem
_SLOTS_BRUXO: list[tuple[int, int]] = [
    (1, 1), (1, 2), (2, 2), (2, 2), (3, 2),
    (3, 2), (4, 2), (4, 2), (5, 2), (5, 2),
]

_FULL_CASTERS = {"mago", "clérigo", "druida", "bardo", "feiticeiro"}
_HALF_CASTERS = {"paladino", "ranger"}


def slots_padrao(classe: str, nivel_personagem: int) -> dict[int, dict[str, int]]:
    """Retorna spell slots padrão SRD 5e para a classe e nível do personagem.

    Usado para inicializar WorkingMemory quando o frontend não envia spell_slots
    (ex: personagem recém-criado ou restaurado de sessão sem estado salvo).

    Args:
        classe: Nome da classe do personagem (qualquer case).
        nivel_personagem: Nível do personagem (1–10+, clampado a 10).

    Returns:
        dict[nivel_spell, {"current": N, "max": N}]
        Retorna {} para classes sem casting (Guerreiro, Bárbaro, etc.).

    Exemplos:
        slots_padrao("Mago", 3)
        # → {1: {"current": 4, "max": 4}, 2: {"current": 2, "max": 2}}
        slots_padrao("Bruxo", 3)
        # → {2: {"current": 2, "max": 2}}
        slots_padrao("Guerreiro", 3)
        # → {}
    """
    classe_lower = classe.lower()
    # Índice na tabela — clampa em 10 (máx suportado)
    idx = max(0, min(9, nivel_personagem - 1))

    if classe_lower == "bruxo":
        nivel_slot, qtd = _SLOTS_BRUXO[idx]
        return {nivel_slot: {"current": qtd, "max": qtd}}

    if classe_lower in _FULL_CASTERS:
        tabela = _SLOTS_CONJURADOR_PLENO
    elif classe_lower in _HALF_CASTERS:
        tabela = _SLOTS_MEIO_CONJURADOR
    else:
        return {}  # Não-conjurador

    linha = tabela[idx]
    resultado: dict[int, dict[str, int]] = {}
    for i, max_slots in enumerate(linha):
        if max_slots > 0:
            nivel_spell = i + 1
            resultado[nivel_spell] = {"current": max_slots, "max": max_slots}
    return resultado
