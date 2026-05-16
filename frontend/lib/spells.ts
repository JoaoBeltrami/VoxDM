/**
 * Lista estática de magias do SRD 5e por classe e nível.
 *
 * Mirror do engine/magic/spell_list.py para o frontend.
 * Permite seleção de magias no CharacterForm e exibição na CharacterSheet
 * sem depender de chamada à API.
 *
 * Armadilha: manter nomes PT-BR sincronizados com o backend — o spell_detector
 * recebe exatamente esses nomes quando o jogador fala "lanço Bola de Fogo".
 */

export interface SpellEntry {
  nome_pt: string;   // "Bola de Fogo"
  nome_en: string;   // "Fireball"
  nivel: number;     // 0=truque, 1-9=nível de magia
  escola: string;    // "Evocação", "Ilusão", etc.
  desc_curta: string; // Resumo mecânico compacto (máx ~80 chars)
}

export interface ProgressaoEntry {
  truques: number;
  magias: number;
  nivel_max: number;
}

// ── Magias por classe ─────────────────────────────────────────────────────────

const MAGIAS_MAGO: SpellEntry[] = [
  // Truques
  { nome_pt: "Mão Mágica",         nome_en: "Mage Hand",          nivel: 0, escola: "Conjuração",    desc_curta: "Mão espectral manipula objetos a 9m, sem ação de bônus" },
  { nome_pt: "Luz",                 nome_en: "Light",              nivel: 0, escola: "Evocação",      desc_curta: "Objeto brilha como tocha por 1 hora" },
  { nome_pt: "Prestidigitação",     nome_en: "Prestidigitation",   nivel: 0, escola: "Transmutação",  desc_curta: "Efeitos mágicos triviais, 10m de alcance" },
  { nome_pt: "Raio de Gelo",        nome_en: "Ray of Frost",       nivel: 0, escola: "Evocação",      desc_curta: "1d8 frio, velocidade -3m. +1d8 em níveis 5/11/17" },
  { nome_pt: "Choque de Trovão",    nome_en: "Shocking Grasp",     nivel: 0, escola: "Evocação",      desc_curta: "1d8 elétrico, alvo sem reação. +1d8 em 5/11/17" },
  { nome_pt: "Explosão de Ácido",   nome_en: "Acid Splash",        nivel: 0, escola: "Conjuração",    desc_curta: "1d6 ácido, até 2 alvos adjacentes, save DES" },
  { nome_pt: "Chama Produzida",     nome_en: "Produce Flame",      nivel: 0, escola: "Conjuração",    desc_curta: "1d8 fogo corpo a corpo ou 9m arremessado" },
  { nome_pt: "Dança das Luzes",     nome_en: "Dancing Lights",     nivel: 0, escola: "Evocação",      desc_curta: "Até 4 luzes flutuantes, ilumina 3m cada, concentração" },
  // Nível 1
  { nome_pt: "Míssil Mágico",       nome_en: "Magic Missile",      nivel: 1, escola: "Evocação",      desc_curta: "3 dardos 1d4+1 força, sempre acertam; +1 dardo por slot extra" },
  { nome_pt: "Escudo Arcano",       nome_en: "Shield",             nivel: 1, escola: "Abjuração",     desc_curta: "Reação: +5 CA até próximo turno, bloqueia Míssil Mágico" },
  { nome_pt: "Sono",                nome_en: "Sleep",              nivel: 1, escola: "Encantamento",  desc_curta: "5d8 PV de criaturas adormecidas (mais fracas primeiro)" },
  { nome_pt: "Mãos Ardentes",       nome_en: "Burning Hands",      nivel: 1, escola: "Evocação",      desc_curta: "3d6 fogo, cone 4,5m, save DES para metade" },
  { nome_pt: "Charme de Pessoa",    nome_en: "Charm Person",       nivel: 1, escola: "Encantamento",  desc_curta: "Encanta humanoide, save SAB, dura 1 hora" },
  { nome_pt: "Armadura de Mago",    nome_en: "Mage Armor",         nivel: 1, escola: "Abjuração",     desc_curta: "CA 13+DES por 8 horas (sem armadura)" },
  { nome_pt: "Compreender Idiomas", nome_en: "Comprehend Languages", nivel: 1, escola: "Adivinhação", desc_curta: "Entende idiomas escritos e falados por 1 hora, ritual" },
  { nome_pt: "Identificar",         nome_en: "Identify",           nivel: 1, escola: "Adivinhação",   desc_curta: "Revela propriedades mágicas de item, ritual, 1 min" },
  { nome_pt: "Explosão Colorida",   nome_en: "Color Spray",        nivel: 1, escola: "Ilusão",        desc_curta: "6d10 PV de criaturas cegas por 1 rodada (mais fracas)" },
  { nome_pt: "Nuvem de Névoa",      nome_en: "Fog Cloud",          nivel: 1, escola: "Conjuração",    desc_curta: "Esfera 6m de névoa pesada, bloqueia visão, 1 hora" },
  { nome_pt: "Riso Hilariante",     nome_en: "Hideous Laughter",   nivel: 1, escola: "Encantamento",  desc_curta: "Humanoide ri, fica incapacitado, save SAB a cada turno" },
  { nome_pt: "Salto",               nome_en: "Jump",               nivel: 1, escola: "Transmutação",  desc_curta: "Distância de salto ×3 por 1 minuto" },
  // Nível 2
  { nome_pt: "Invisibilidade",      nome_en: "Invisibility",       nivel: 2, escola: "Ilusão",        desc_curta: "Alvo invisível por 1 hora ou até atacar/lançar magia" },
  { nome_pt: "Flecha Ácida de Melf",nome_en: "Melf's Acid Arrow",  nivel: 2, escola: "Evocação",      desc_curta: "Acerto: 4d4 ácido imediato + 2d4 no próximo turno" },
  { nome_pt: "Sugestão",            nome_en: "Suggestion",         nivel: 2, escola: "Encantamento",  desc_curta: "Sugestão razoável compelida, save SAB, dura 8 horas" },
  { nome_pt: "Escuridão",           nome_en: "Darkness",           nivel: 2, escola: "Evocação",      desc_curta: "Esfera 4,5m de escuridão mágica, bloqueia visão no escuro" },
  { nome_pt: "Imobilizar Pessoa",   nome_en: "Hold Person",        nivel: 2, escola: "Encantamento",  desc_curta: "Humanoide paralisado, save SAB a cada turno, 1 minuto" },
  { nome_pt: "Detectar Pensamentos",nome_en: "Detect Thoughts",    nivel: 2, escola: "Adivinhação",   desc_curta: "Lê pensamentos superficiais ou sonda mais fundo, 1 min" },
  { nome_pt: "Força Fantasmal",     nome_en: "Phantasmal Force",   nivel: 2, escola: "Ilusão",        desc_curta: "Ilusão que parece real ao alvo, 1d6 por turno, 1 min" },
  { nome_pt: "Visão no Escuro",     nome_en: "Darkvision",         nivel: 2, escola: "Transmutação",  desc_curta: "Alvo ganha visão no escuro 18m por 8 horas" },
  { nome_pt: "Destrancar",          nome_en: "Knock",              nivel: 2, escola: "Transmutação",  desc_curta: "Abre fechaduras mágicas/normais com som alto" },
  // Nível 3
  { nome_pt: "Bola de Fogo",        nome_en: "Fireball",           nivel: 3, escola: "Evocação",      desc_curta: "8d6 fogo, esfera 6m, save DES para metade, 45m" },
  { nome_pt: "Relâmpago",           nome_en: "Lightning Bolt",     nivel: 3, escola: "Evocação",      desc_curta: "8d6 elétrico, linha 30m×1,5m, save DES para metade" },
  { nome_pt: "Voo",                 nome_en: "Fly",                nivel: 3, escola: "Transmutação",  desc_curta: "Velocidade de voo 18m por 10 minutos, concentração" },
  { nome_pt: "Contramagia",         nome_en: "Counterspell",       nivel: 3, escola: "Abjuração",     desc_curta: "Reação: interrompe magia sendo lançada (automático ≤3)" },
  { nome_pt: "Dissipar Magia",      nome_en: "Dispel Magic",       nivel: 3, escola: "Abjuração",     desc_curta: "Remove magias em criaturas ou objetos (automático ≤3)" },
  { nome_pt: "Animar Mortos",       nome_en: "Animate Dead",       nivel: 3, escola: "Necromancia",   desc_curta: "Cria esqueleto ou zumbi de cadáver, controla 24h" },
  { nome_pt: "Hipnose Hipnótica",   nome_en: "Hypnotic Pattern",   nivel: 3, escola: "Ilusão",        desc_curta: "Padrão hipnótico: criaturas em 9m ficam enfeitiçadas 1 min" },
  { nome_pt: "Velocidade",          nome_en: "Haste",              nivel: 3, escola: "Transmutação",  desc_curta: "Velocidade ×2, +2 CA, ação bônus extra, concentração 1 min" },
  { nome_pt: "Forma Gasosa",        nome_en: "Gaseous Form",       nivel: 3, escola: "Transmutação",  desc_curta: "Alvo vira nuvem: voar 3m, imune a físico, concentração" },
  // Nível 4
  { nome_pt: "Polimorfar",          nome_en: "Polymorph",          nivel: 4, escola: "Transmutação",  desc_curta: "Transforma criatura em besta, usa HP da forma, concentração" },
  { nome_pt: "Olho Arcano",         nome_en: "Arcane Eye",         nivel: 4, escola: "Adivinhação",   desc_curta: "Olho invisível voa 9m/turno, ver tudo, 1 hora" },
  { nome_pt: "Dimensão Porta",      nome_en: "Dimension Door",     nivel: 4, escola: "Conjuração",    desc_curta: "Teleporta até 500m (com 1 passageiro)" },
  { nome_pt: "Tempestade de Gelo",  nome_en: "Ice Storm",          nivel: 4, escola: "Evocação",      desc_curta: "2d8 contundente+4d6 frio, cilindro 6m, save DES" },
  { nome_pt: "Invisibilidade Maior",nome_en: "Greater Invisibility",nivel: 4, escola: "Ilusão",       desc_curta: "Invisibilidade que persiste ao atacar, concentração 1 min" },
  // Nível 5
  { nome_pt: "Cone de Frio",        nome_en: "Cone of Cold",       nivel: 5, escola: "Evocação",      desc_curta: "8d8 frio, cone 18m, save CON para metade" },
  { nome_pt: "Telecinesia",         nome_en: "Telekinesis",        nivel: 5, escola: "Transmutação",  desc_curta: "Move objetos/criaturas com força mental, concentração 10 min" },
  { nome_pt: "Teleporte",           nome_en: "Teleport",           nivel: 5, escola: "Conjuração",    desc_curta: "Teleporta grupo para local familiar (com risco de desvio)" },
  { nome_pt: "Mão de Bigby",        nome_en: "Bigby's Hand",       nivel: 5, escola: "Evocação",      desc_curta: "Mão arcana: soco 5d8, agarrar, empurrar, 1 minuto" },
];

const MAGIAS_CLERIGO: SpellEntry[] = [
  // Truques
  { nome_pt: "Chama Sagrada",      nome_en: "Sacred Flame",       nivel: 0, escola: "Evocação",      desc_curta: "1d8 radiante, save DES, ignora cobertura. +1d8 em 5/11/17" },
  { nome_pt: "Luz",                nome_en: "Light",              nivel: 0, escola: "Evocação",      desc_curta: "Objeto brilha como tocha por 1 hora" },
  { nome_pt: "Taumaturgia",        nome_en: "Thaumaturgy",        nivel: 0, escola: "Transmutação",  desc_curta: "Pequenos milagres: voz trovejante, portas, chamas, 1 min" },
  { nome_pt: "Conselho",           nome_en: "Guidance",           nivel: 0, escola: "Adivinhação",   desc_curta: "Aliado ganha 1d4 em próxima verificação, concentração" },
  { nome_pt: "Resistência",        nome_en: "Resistance",         nivel: 0, escola: "Abjuração",     desc_curta: "Aliado adiciona 1d4 em próxima saving throw, concentração" },
  { nome_pt: "Estabilizar",        nome_en: "Spare the Dying",    nivel: 0, escola: "Necromancia",   desc_curta: "Criatura estabilizada em 0 HP a 9m de distância" },
  // Nível 1
  { nome_pt: "Curar Ferimentos",   nome_en: "Cure Wounds",        nivel: 1, escola: "Evocação",      desc_curta: "1d8+mod.SAB PV curados por toque" },
  { nome_pt: "Abençoar",           nome_en: "Bless",              nivel: 1, escola: "Encantamento",  desc_curta: "Até 3 aliados: +1d4 em ataques e saves, 1 min, concentração" },
  { nome_pt: "Infligir Ferimentos",nome_en: "Inflict Wounds",     nivel: 1, escola: "Necromancia",   desc_curta: "Toque: 3d10 necrótico; +1d10 por slot extra" },
  { nome_pt: "Guia Brilhante",     nome_en: "Guiding Bolt",       nivel: 1, escola: "Evocação",      desc_curta: "Ranged: 4d6 radiante + vantagem no próximo ataque ao alvo" },
  { nome_pt: "Cura Menor",         nome_en: "Healing Word",       nivel: 1, escola: "Evocação",      desc_curta: "Ação bônus: 1d4+mod.SAB PV a alvo a 18m" },
  { nome_pt: "Santuário",          nome_en: "Sanctuary",          nivel: 1, escola: "Abjuração",     desc_curta: "Atacantes fazem save SAB ou escolhem outro alvo, 1 min" },
  { nome_pt: "Escudo da Fé",       nome_en: "Shield of Faith",    nivel: 1, escola: "Abjuração",     desc_curta: "+2 CA a aliado por 10 minutos, concentração" },
  { nome_pt: "Detectar Magia",     nome_en: "Detect Magic",       nivel: 1, escola: "Adivinhação",   desc_curta: "Sentir auras mágicas a 9m, concentração 10 min, ritual" },
  // Nível 2
  { nome_pt: "Arma Espiritual",    nome_en: "Spiritual Weapon",   nivel: 2, escola: "Evocação",      desc_curta: "Arma mágica: ação bônus atacar 1d8+SAB força, 1 min" },
  { nome_pt: "Silêncio",           nome_en: "Silence",            nivel: 2, escola: "Ilusão",        desc_curta: "Zona 6m sem som por 10 min, bloqueia magias verbais" },
  { nome_pt: "Orar pelos Feridos", nome_en: "Prayer of Healing",  nivel: 2, escola: "Evocação",      desc_curta: "Cura até 6 aliados: 2d8+SAB cada (10 min para conjurar)" },
  { nome_pt: "Imobilizar Pessoa",  nome_en: "Hold Person",        nivel: 2, escola: "Encantamento",  desc_curta: "Humanoide paralisado, save SAB a cada turno, 1 minuto" },
  { nome_pt: "Augúrio",            nome_en: "Augury",             nivel: 2, escola: "Adivinhação",   desc_curta: "Ritual: resposta sobre ação nos próximos 30 min" },
  { nome_pt: "Zona da Verdade",    nome_en: "Zone of Truth",      nivel: 2, escola: "Encantamento",  desc_curta: "Esfera 4,5m: criaturas não podem mentir conscientemente" },
  // Nível 3
  { nome_pt: "Cura em Massa",      nome_en: "Mass Healing Word",  nivel: 3, escola: "Evocação",      desc_curta: "Ação bônus: 1d4+SAB a até 6 aliados a 18m" },
  { nome_pt: "Remover Maldição",   nome_en: "Remove Curse",       nivel: 3, escola: "Abjuração",     desc_curta: "Termina todas as maldições sobre toque" },
  { nome_pt: "Revivificar",        nome_en: "Revivify",           nivel: 3, escola: "Necromancia",   desc_curta: "Ressuscita morto há ≤1 minuto com 1 HP (100 po)" },
  { nome_pt: "Luz do Dia",         nome_en: "Daylight",           nivel: 3, escola: "Evocação",      desc_curta: "Esfera 18m de luz solar brilhante por 1 hora" },
  { nome_pt: "Animar Mortos",      nome_en: "Animate Dead",       nivel: 3, escola: "Necromancia",   desc_curta: "Cria esqueleto ou zumbi de cadáver, controla 24h" },
  // Nível 4
  { nome_pt: "Banimento",          nome_en: "Banishment",         nivel: 4, escola: "Abjuração",     desc_curta: "Criatura deslocada para outro plano, save CAR, concentração" },
  { nome_pt: "Guardiões da Fé",    nome_en: "Guardian of Faith",  nivel: 4, escola: "Conjuração",    desc_curta: "Guardião 10m: 20 radiante ou sombrio a invasores" },
  { nome_pt: "Liberdade de Movimento",nome_en:"Freedom of Movement",nivel: 4,escola: "Abjuração",    desc_curta: "Aliado ignora terreno difícil e imobilização, 1 hora" },
  { nome_pt: "Polimorfar",         nome_en: "Polymorph",          nivel: 4, escola: "Transmutação",  desc_curta: "Transforma criatura em besta, usa HP da forma, concentração" },
  // Nível 5
  { nome_pt: "Curar em Massa",     nome_en: "Mass Cure Wounds",   nivel: 5, escola: "Evocação",      desc_curta: "Até 6 criaturas a 18m: 3d8+SAB PV curadas cada" },
  { nome_pt: "Chama Divina",       nome_en: "Flame Strike",       nivel: 5, escola: "Evocação",      desc_curta: "Coluna de fogo divino: 4d6 fogo+4d6 radiante, save CON" },
];

const MAGIAS_DRUIDA: SpellEntry[] = [
  // Truques
  { nome_pt: "Chama Produzida",    nome_en: "Produce Flame",      nivel: 0, escola: "Conjuração",    desc_curta: "1d8 fogo corpo a corpo ou 9m arremessado. +1d8 em 5/11/17" },
  { nome_pt: "Bafejo Venenoso",    nome_en: "Poison Spray",       nivel: 0, escola: "Conjuração",    desc_curta: "3m: 1d12 veneno, save CON. +1d12 em 5/11/17" },
  { nome_pt: "Conselho",           nome_en: "Guidance",           nivel: 0, escola: "Adivinhação",   desc_curta: "Aliado ganha 1d4 em próxima verificação, concentração" },
  { nome_pt: "Resistência",        nome_en: "Resistance",         nivel: 0, escola: "Abjuração",     desc_curta: "Aliado adiciona 1d4 em próxima saving throw, concentração" },
  { nome_pt: "Mordida de Gelo",    nome_en: "Frostbite",          nivel: 0, escola: "Evocação",      desc_curta: "Save CON ou 1d6 frio + desvantagem no próximo ataque" },
  { nome_pt: "Chicote de Espinhos",nome_en: "Thorn Whip",         nivel: 0, escola: "Transmutação",  desc_curta: "Ataque: 1d6 perfurante, puxa alvo 3m. +1d6 em 5/11/17" },
  // Nível 1
  { nome_pt: "Absorver Elementos", nome_en: "Absorb Elements",    nivel: 1, escola: "Abjuração",     desc_curta: "Reação: resistência ao elemento; próximo acerto +1d6 dano" },
  { nome_pt: "Curar Ferimentos",   nome_en: "Cure Wounds",        nivel: 1, escola: "Evocação",      desc_curta: "1d8+mod.SAB PV curados por toque" },
  { nome_pt: "Fogo das Fadas",     nome_en: "Faerie Fire",        nivel: 1, escola: "Evocação",      desc_curta: "Luz: alvos visíveis, vantagem em ataques contra eles, 1 min" },
  { nome_pt: "Névoa de Adormecimento",nome_en:"Fog Cloud",        nivel: 1, escola: "Conjuração",    desc_curta: "Esfera 6m de névoa pesada, bloqueia visão, 1 hora" },
  { nome_pt: "Entrelaçar",         nome_en: "Entangle",           nivel: 1, escola: "Conjuração",    desc_curta: "Quadrado 6m de vinhas: save FOR ou paralisado, concentração" },
  { nome_pt: "Falar com Animais",  nome_en: "Speak with Animals", nivel: 1, escola: "Adivinhação",   desc_curta: "Comunicar-se com animais por 10 minutos, ritual" },
  { nome_pt: "Palavra de Cura",    nome_en: "Healing Word",       nivel: 1, escola: "Evocação",      desc_curta: "Ação bônus: 1d4+SAB PV a 18m" },
  // Nível 2
  { nome_pt: "Pele de Casca",      nome_en: "Barkskin",           nivel: 2, escola: "Transmutação",  desc_curta: "CA mínima 16 por 1 hora, concentração" },
  { nome_pt: "Silêncio",           nome_en: "Silence",            nivel: 2, escola: "Ilusão",        desc_curta: "Zona 6m sem som por 10 min, bloqueia magias verbais" },
  { nome_pt: "Imobilizar Pessoa",  nome_en: "Hold Person",        nivel: 2, escola: "Encantamento",  desc_curta: "Humanoide paralisado, save SAB a cada turno, 1 minuto" },
  { nome_pt: "Passagem Silenciosa",nome_en: "Pass without Trace", nivel: 2, escola: "Abjuração",     desc_curta: "+10 em Furtividade, rastreamento impossível, concentração" },
  { nome_pt: "Crescimento de Espinhos",nome_en:"Spike Growth",    nivel: 2, escola: "Transmutação",  desc_curta: "Solo 6m: terreno difícil + 2d4 por 1,5m percorrido" },
  { nome_pt: "Esfera de Fogo",     nome_en: "Flaming Sphere",     nivel: 2, escola: "Conjuração",    desc_curta: "Esfera flamejante: 2d6 fogo aos adjacentes, 1 min" },
  // Nível 3
  { nome_pt: "Chamar Raios",       nome_en: "Call Lightning",     nivel: 3, escola: "Conjuração",    desc_curta: "Nuvem: raio 3d10 elétrico por turno, concentração 10 min" },
  { nome_pt: "Falar com Plantas",  nome_en: "Speak with Plants",  nivel: 3, escola: "Transmutação",  desc_curta: "Plantas obedecem e informam por 10 minutos" },
  { nome_pt: "Trovão Esmagador",   nome_en: "Erupting Earth",     nivel: 3, escola: "Transmutação",  desc_curta: "Cubo 4,5m: 3d12 contundente, save DES, terreno difícil" },
  { nome_pt: "Invocar Animais",    nome_en: "Conjure Animals",    nivel: 3, escola: "Conjuração",    desc_curta: "Convoca espíritos bestas (CR total ≤2 em 2-8 criaturas)" },
  { nome_pt: "Muro de Vento",      nome_en: "Wind Wall",          nivel: 3, escola: "Evocação",      desc_curta: "Muro 15m: 3d8 contundente, saltos de projéteis, 1 min" },
  // Nível 4
  { nome_pt: "Polimorfar",         nome_en: "Polymorph",          nivel: 4, escola: "Transmutação",  desc_curta: "Transforma criatura em besta, usa HP da forma, concentração" },
  { nome_pt: "Tempestade de Gelo", nome_en: "Ice Storm",          nivel: 4, escola: "Evocação",      desc_curta: "2d8 contundente+4d6 frio, cilindro 6m, save DES" },
  { nome_pt: "Liberdade de Movimento",nome_en:"Freedom of Movement",nivel: 4,escola:"Abjuração",     desc_curta: "Aliado ignora terreno difícil e imobilização, 1 hora" },
  // Nível 5
  { nome_pt: "Invocar Elemental",  nome_en: "Conjure Elemental",  nivel: 5, escola: "Conjuração",    desc_curta: "Convoca elemental CR 5 (ar/terra/fogo/água), concentração" },
  { nome_pt: "Contagiar",          nome_en: "Contagion",          nivel: 5, escola: "Necromancia",   desc_curta: "Toque: doença incapacitante após 3 saves fracassados" },
];

const MAGIAS_BARDO: SpellEntry[] = [
  // Truques
  { nome_pt: "Zombaria Viciosa",   nome_en: "Vicious Mockery",    nivel: 0, escola: "Encantamento",  desc_curta: "Save SAB ou 1d4 psíquico + desvantagem no próximo ataque" },
  { nome_pt: "Prestidigitação",    nome_en: "Prestidigitation",   nivel: 0, escola: "Transmutação",  desc_curta: "Efeitos mágicos triviais, 10m de alcance" },
  { nome_pt: "Luz",                nome_en: "Light",              nivel: 0, escola: "Evocação",      desc_curta: "Objeto brilha como tocha por 1 hora" },
  { nome_pt: "Mão Mágica",         nome_en: "Mage Hand",          nivel: 0, escola: "Conjuração",    desc_curta: "Mão espectral manipula objetos a 9m" },
  { nome_pt: "Mensagem",           nome_en: "Message",            nivel: 0, escola: "Transmutação",  desc_curta: "Sussurra mensagem a 90m, alvo pode responder uma vez" },
  { nome_pt: "Dança das Luzes",    nome_en: "Dancing Lights",     nivel: 0, escola: "Evocação",      desc_curta: "Até 4 luzes flutuantes, ilumina 3m cada, concentração" },
  // Nível 1
  { nome_pt: "Heroísmo",           nome_en: "Heroism",            nivel: 1, escola: "Encantamento",  desc_curta: "Imune a medo, PV temporários = mod.CAR por turno, 1 min" },
  { nome_pt: "Charme de Pessoa",   nome_en: "Charm Person",       nivel: 1, escola: "Encantamento",  desc_curta: "Encanta humanoide, save SAB, dura 1 hora" },
  { nome_pt: "Palavra de Cura",    nome_en: "Healing Word",       nivel: 1, escola: "Evocação",      desc_curta: "Ação bônus: 1d4+CAR PV a alvo a 18m" },
  { nome_pt: "Sono",               nome_en: "Sleep",              nivel: 1, escola: "Encantamento",  desc_curta: "5d8 PV de criaturas adormecidas (mais fracas primeiro)" },
  { nome_pt: "Onda de Trovão",     nome_en: "Thunderwave",        nivel: 1, escola: "Evocação",      desc_curta: "Cubo 4,5m: 2d8 trovão, save CON, empurra 3m" },
  { nome_pt: "Sussurros Dissonantes",nome_en:"Dissonant Whispers",nivel: 1, escola: "Encantamento",  desc_curta: "1 alvo: 3d6 psíquico, save SAB, usa reação pra fugir" },
  { nome_pt: "Detectar Magia",     nome_en: "Detect Magic",       nivel: 1, escola: "Adivinhação",   desc_curta: "Sentir auras mágicas a 9m, concentração 10 min, ritual" },
  // Nível 2
  { nome_pt: "Invisibilidade",     nome_en: "Invisibility",       nivel: 2, escola: "Ilusão",        desc_curta: "Alvo invisível por 1 hora ou até atacar/lançar magia" },
  { nome_pt: "Sugestão",           nome_en: "Suggestion",         nivel: 2, escola: "Encantamento",  desc_curta: "Sugestão razoável compelida, save SAB, dura 8 horas" },
  { nome_pt: "Silêncio",           nome_en: "Silence",            nivel: 2, escola: "Ilusão",        desc_curta: "Zona 6m sem som por 10 min, bloqueia magias verbais" },
  { nome_pt: "Imobilizar Pessoa",  nome_en: "Hold Person",        nivel: 2, escola: "Encantamento",  desc_curta: "Humanoide paralisado, save SAB a cada turno, 1 minuto" },
  { nome_pt: "Estilhaçar",         nome_en: "Shatter",            nivel: 2, escola: "Evocação",      desc_curta: "Esfera 3m: 3d8 trovão, save CON para metade" },
  { nome_pt: "Zona da Verdade",    nome_en: "Zone of Truth",      nivel: 2, escola: "Encantamento",  desc_curta: "Esfera 4,5m: criaturas não podem mentir conscientemente" },
  // Nível 3
  { nome_pt: "Hipnose Hipnótica",  nome_en: "Hypnotic Pattern",   nivel: 3, escola: "Ilusão",        desc_curta: "Padrão hipnótico: criaturas em 9m ficam enfeitiçadas 1 min" },
  { nome_pt: "Imagem Maior",       nome_en: "Major Image",        nivel: 3, escola: "Ilusão",        desc_curta: "Ilusão com som, cheiro, temperatura; concentração 10 min" },
  { nome_pt: "Línguas",            nome_en: "Tongues",            nivel: 3, escola: "Adivinhação",   desc_curta: "Falar e entender qualquer idioma por 1 hora" },
  // Nível 4
  { nome_pt: "Polimorfar",         nome_en: "Polymorph",          nivel: 4, escola: "Transmutação",  desc_curta: "Transforma criatura em besta, usa HP da forma, concentração" },
  { nome_pt: "Confusão",           nome_en: "Confusion",          nivel: 4, escola: "Encantamento",  desc_curta: "Criaturas em 3m: comportamento aleatório, save SAB 1 min" },
  { nome_pt: "Dimensão Porta",     nome_en: "Dimension Door",     nivel: 4, escola: "Conjuração",    desc_curta: "Teleporta até 500m (com 1 passageiro)" },
  { nome_pt: "Invisibilidade Maior",nome_en:"Greater Invisibility",nivel: 4, escola: "Ilusão",       desc_curta: "Invisibilidade que persiste ao atacar, concentração 1 min" },
  // Nível 5
  { nome_pt: "Sugestão em Massa",  nome_en: "Mass Suggestion",    nivel: 5, escola: "Encantamento",  desc_curta: "Sugestão para até 12 criaturas, save SAB, 24 horas" },
];

const MAGIAS_FEITICEIRO: SpellEntry[] = [
  // Truques
  { nome_pt: "Raio de Fogo",       nome_en: "Fire Bolt",          nivel: 0, escola: "Evocação",      desc_curta: "Ataque: 1d10 fogo a 36m. +1d10 em níveis 5/11/17" },
  { nome_pt: "Choque de Trovão",   nome_en: "Shocking Grasp",     nivel: 0, escola: "Evocação",      desc_curta: "1d8 elétrico, alvo sem reação. +1d8 em 5/11/17" },
  { nome_pt: "Raio de Gelo",       nome_en: "Ray of Frost",       nivel: 0, escola: "Evocação",      desc_curta: "1d8 frio, velocidade -3m. +1d8 em níveis 5/11/17" },
  { nome_pt: "Mão Mágica",         nome_en: "Mage Hand",          nivel: 0, escola: "Conjuração",    desc_curta: "Mão espectral manipula objetos a 9m" },
  { nome_pt: "Prestidigitação",    nome_en: "Prestidigitation",   nivel: 0, escola: "Transmutação",  desc_curta: "Efeitos mágicos triviais, 10m de alcance" },
  { nome_pt: "Explosão de Ácido",  nome_en: "Acid Splash",        nivel: 0, escola: "Conjuração",    desc_curta: "1d6 ácido, até 2 alvos adjacentes, save DES" },
  // Nível 1
  { nome_pt: "Míssil Mágico",      nome_en: "Magic Missile",      nivel: 1, escola: "Evocação",      desc_curta: "3 dardos 1d4+1 força, sempre acertam" },
  { nome_pt: "Escudo Arcano",      nome_en: "Shield",             nivel: 1, escola: "Abjuração",     desc_curta: "Reação: +5 CA até próximo turno, bloqueia Míssil Mágico" },
  { nome_pt: "Mãos Ardentes",      nome_en: "Burning Hands",      nivel: 1, escola: "Evocação",      desc_curta: "3d6 fogo, cone 4,5m, save DES para metade" },
  { nome_pt: "Charme de Pessoa",   nome_en: "Charm Person",       nivel: 1, escola: "Encantamento",  desc_curta: "Encanta humanoide, save SAB, dura 1 hora" },
  { nome_pt: "Sono",               nome_en: "Sleep",              nivel: 1, escola: "Encantamento",  desc_curta: "5d8 PV de criaturas adormecidas (mais fracas primeiro)" },
  { nome_pt: "Armadura de Mago",   nome_en: "Mage Armor",         nivel: 1, escola: "Abjuração",     desc_curta: "CA 13+DES por 8 horas (sem armadura)" },
  // Nível 2
  { nome_pt: "Invisibilidade",     nome_en: "Invisibility",       nivel: 2, escola: "Ilusão",        desc_curta: "Alvo invisível por 1 hora ou até atacar/lançar magia" },
  { nome_pt: "Escuridão",          nome_en: "Darkness",           nivel: 2, escola: "Evocação",      desc_curta: "Esfera 4,5m de escuridão mágica, bloqueia visão no escuro" },
  { nome_pt: "Imobilizar Pessoa",  nome_en: "Hold Person",        nivel: 2, escola: "Encantamento",  desc_curta: "Humanoide paralisado, save SAB a cada turno, 1 minuto" },
  { nome_pt: "Estilhaçar",         nome_en: "Shatter",            nivel: 2, escola: "Evocação",      desc_curta: "Esfera 3m: 3d8 trovão, save CON para metade" },
  { nome_pt: "Sugestão",           nome_en: "Suggestion",         nivel: 2, escola: "Encantamento",  desc_curta: "Sugestão razoável compelida, save SAB, dura 8 horas" },
  // Nível 3
  { nome_pt: "Bola de Fogo",       nome_en: "Fireball",           nivel: 3, escola: "Evocação",      desc_curta: "8d6 fogo, esfera 6m, save DES para metade, 45m" },
  { nome_pt: "Relâmpago",          nome_en: "Lightning Bolt",     nivel: 3, escola: "Evocação",      desc_curta: "8d6 elétrico, linha 30m×1,5m, save DES para metade" },
  { nome_pt: "Velocidade",         nome_en: "Haste",              nivel: 3, escola: "Transmutação",  desc_curta: "Velocidade ×2, +2 CA, ação bônus extra, concentração 1 min" },
  { nome_pt: "Contramagia",        nome_en: "Counterspell",       nivel: 3, escola: "Abjuração",     desc_curta: "Reação: interrompe magia sendo lançada (automático ≤3)" },
  { nome_pt: "Hipnose Hipnótica",  nome_en: "Hypnotic Pattern",   nivel: 3, escola: "Ilusão",        desc_curta: "Padrão hipnótico: criaturas em 9m ficam enfeitiçadas 1 min" },
  // Nível 4
  { nome_pt: "Polimorfar",         nome_en: "Polymorph",          nivel: 4, escola: "Transmutação",  desc_curta: "Transforma criatura em besta, usa HP da forma, concentração" },
  { nome_pt: "Dimensão Porta",     nome_en: "Dimension Door",     nivel: 4, escola: "Conjuração",    desc_curta: "Teleporta até 500m (com 1 passageiro)" },
  { nome_pt: "Tempestade de Gelo", nome_en: "Ice Storm",          nivel: 4, escola: "Evocação",      desc_curta: "2d8 contundente+4d6 frio, cilindro 6m, save DES" },
  // Nível 5
  { nome_pt: "Cone de Frio",       nome_en: "Cone of Cold",       nivel: 5, escola: "Evocação",      desc_curta: "8d8 frio, cone 18m, save CON para metade" },
  { nome_pt: "Telecinesia",        nome_en: "Telekinesis",        nivel: 5, escola: "Transmutação",  desc_curta: "Move objetos/criaturas com força mental, concentração 10 min" },
];

const MAGIAS_BRUXO: SpellEntry[] = [
  // Truques
  { nome_pt: "Explosão Eldritch",  nome_en: "Eldritch Blast",     nivel: 0, escola: "Evocação",      desc_curta: "1 raio 1d10 força a 36m. 2 em nível 5, 3 em 11, 4 em 17" },
  { nome_pt: "Toque Gelado",       nome_en: "Chill Touch",        nivel: 0, escola: "Necromancia",   desc_curta: "1d8 necrótico, alvo não regenera HP até seu próximo turno" },
  { nome_pt: "Mão Mágica",         nome_en: "Mage Hand",          nivel: 0, escola: "Conjuração",    desc_curta: "Mão espectral manipula objetos a 9m" },
  { nome_pt: "Bafejo Venenoso",    nome_en: "Poison Spray",       nivel: 0, escola: "Conjuração",    desc_curta: "3m: 1d12 veneno, save CON. +1d12 em 5/11/17" },
  { nome_pt: "Ilusão Menor",       nome_en: "Minor Illusion",     nivel: 0, escola: "Ilusão",        desc_curta: "Som ou imagem estática em cubo 1,5m por 1 minuto" },
  // Nível 1
  { nome_pt: "Maldição Hex",       nome_en: "Hex",                nivel: 1, escola: "Encantamento",  desc_curta: "Amaldiçoa alvo: +1d6 necrótico nos ataques, desvantagem em atrib." },
  { nome_pt: "Charme de Pessoa",   nome_en: "Charm Person",       nivel: 1, escola: "Encantamento",  desc_curta: "Encanta humanoide, save SAB, dura 1 hora" },
  { nome_pt: "Braços de Hadar",    nome_en: "Arms of Hadar",      nivel: 1, escola: "Conjuração",    desc_curta: "Tentáculos 3m: 2d6 necrótico, save FOR, sem reações 1 turno" },
  { nome_pt: "Escudo Arcano",      nome_en: "Shield",             nivel: 1, escola: "Abjuração",     desc_curta: "Reação: +5 CA até próximo turno, bloqueia Míssil Mágico" },
  // Nível 2
  { nome_pt: "Escuridão",          nome_en: "Darkness",           nivel: 2, escola: "Evocação",      desc_curta: "Esfera 4,5m de escuridão mágica, bloqueia visão no escuro" },
  { nome_pt: "Imobilizar Pessoa",  nome_en: "Hold Person",        nivel: 2, escola: "Encantamento",  desc_curta: "Humanoide paralisado, save SAB a cada turno, 1 minuto" },
  { nome_pt: "Invisibilidade",     nome_en: "Invisibility",       nivel: 2, escola: "Ilusão",        desc_curta: "Alvo invisível por 1 hora ou até atacar/lançar magia" },
  { nome_pt: "Sugestão",           nome_en: "Suggestion",         nivel: 2, escola: "Encantamento",  desc_curta: "Sugestão razoável compelida, save SAB, dura 8 horas" },
  { nome_pt: "Força Fantasmal",    nome_en: "Phantasmal Force",   nivel: 2, escola: "Ilusão",        desc_curta: "Ilusão que parece real ao alvo, 1d6 por turno, 1 min" },
  // Nível 3
  { nome_pt: "Hipnose Hipnótica",  nome_en: "Hypnotic Pattern",   nivel: 3, escola: "Ilusão",        desc_curta: "Padrão hipnótico: criaturas em 9m ficam enfeitiçadas 1 min" },
  { nome_pt: "Voo",                nome_en: "Fly",                nivel: 3, escola: "Transmutação",  desc_curta: "Velocidade de voo 18m por 10 minutos, concentração" },
  { nome_pt: "Contramagia",        nome_en: "Counterspell",       nivel: 3, escola: "Abjuração",     desc_curta: "Reação: interrompe magia sendo lançada (automático ≤3)" },
  { nome_pt: "Forma Gasosa",       nome_en: "Gaseous Form",       nivel: 3, escola: "Transmutação",  desc_curta: "Alvo vira nuvem: voar 3m, imune a físico, concentração" },
  { nome_pt: "Animar Mortos",      nome_en: "Animate Dead",       nivel: 3, escola: "Necromancia",   desc_curta: "Cria esqueleto ou zumbi de cadáver, controla 24h" },
  // Nível 4
  { nome_pt: "Banimento",          nome_en: "Banishment",         nivel: 4, escola: "Abjuração",     desc_curta: "Criatura deslocada para outro plano, save CAR, concentração" },
  { nome_pt: "Polimorfar",         nome_en: "Polymorph",          nivel: 4, escola: "Transmutação",  desc_curta: "Transforma criatura em besta, usa HP da forma, concentração" },
  { nome_pt: "Dimensão Porta",     nome_en: "Dimension Door",     nivel: 4, escola: "Conjuração",    desc_curta: "Teleporta até 500m (com 1 passageiro)" },
  // Nível 5
  { nome_pt: "Dominar Pessoa",     nome_en: "Dominate Person",    nivel: 5, escola: "Encantamento",  desc_curta: "Controla humanoide: save SAB, 1 minuto, concentração" },
];

const MAGIAS_PALADINO: SpellEntry[] = [
  // Nível 1
  { nome_pt: "Bênção",             nome_en: "Bless",              nivel: 1, escola: "Encantamento",  desc_curta: "Até 3 aliados: +1d4 em ataques e saves, 1 min, concentração" },
  { nome_pt: "Curar Ferimentos",   nome_en: "Cure Wounds",        nivel: 1, escola: "Evocação",      desc_curta: "1d8+mod.CAR PV curados por toque" },
  { nome_pt: "Escudo da Fé",       nome_en: "Shield of Faith",    nivel: 1, escola: "Abjuração",     desc_curta: "+2 CA a aliado por 10 minutos, concentração" },
  { nome_pt: "Identificar",        nome_en: "Identify",           nivel: 1, escola: "Adivinhação",   desc_curta: "Revela propriedades mágicas de item, ritual, 1 min" },
  { nome_pt: "Comando",            nome_en: "Command",            nivel: 1, escola: "Encantamento",  desc_curta: "1 palavra: humanoide obedece por 1 turno, save SAB" },
  { nome_pt: "Fúria Irada",        nome_en: "Wrathful Smite",     nivel: 1, escola: "Evocação",      desc_curta: "Próximo acerto: +1d6 psíquico, alvo fica amedrontado" },
  // Nível 2
  { nome_pt: "Arma Mágica",        nome_en: "Magic Weapon",       nivel: 2, escola: "Transmutação",  desc_curta: "Arma não-mágica vira mágica +1 por 1 hora, concentração" },
  { nome_pt: "Zona da Verdade",    nome_en: "Zone of Truth",      nivel: 2, escola: "Encantamento",  desc_curta: "Esfera 4,5m: criaturas não podem mentir conscientemente" },
  { nome_pt: "Restauração Menor",  nome_en: "Lesser Restoration", nivel: 2, escola: "Abjuração",     desc_curta: "Remove uma doença, condição de cegueira, surdez, paralisia" },
  { nome_pt: "Encontrar Corcel",   nome_en: "Find Steed",         nivel: 2, escola: "Conjuração",    desc_curta: "Convoca corcel espiritual leal como bonded companion" },
  { nome_pt: "Imobilizar Pessoa",  nome_en: "Hold Person",        nivel: 2, escola: "Encantamento",  desc_curta: "Humanoide paralisado, save SAB a cada turno, 1 minuto" },
  { nome_pt: "Proteção contra Veneno",nome_en:"Protection from Poison",nivel:2,escola:"Abjuração",   desc_curta: "Anula/suspende veneno, resistência a dano veneno, 1 hora" },
  // Nível 3
  { nome_pt: "Revivificar",        nome_en: "Revivify",           nivel: 3, escola: "Necromancia",   desc_curta: "Ressuscita morto há ≤1 minuto com 1 HP (100 po)" },
  { nome_pt: "Dissipar Magia",     nome_en: "Dispel Magic",       nivel: 3, escola: "Abjuração",     desc_curta: "Remove magias em criaturas ou objetos (automático ≤3)" },
  { nome_pt: "Golpe Cegante",      nome_en: "Blinding Smite",     nivel: 3, escola: "Evocação",      desc_curta: "Próximo acerto: +3d8 radiante, alvo fica cego, save CON" },
  // Nível 4
  { nome_pt: "Banimento",          nome_en: "Banishment",         nivel: 4, escola: "Abjuração",     desc_curta: "Criatura deslocada para outro plano, save CAR, concentração" },
  { nome_pt: "Liberdade de Movimento",nome_en:"Freedom of Movement",nivel:4,escola:"Abjuração",      desc_curta: "Aliado ignora terreno difícil e imobilização, 1 hora" },
];

const MAGIAS_RANGER: SpellEntry[] = [
  // Nível 1
  { nome_pt: "Absorver Elementos", nome_en: "Absorb Elements",    nivel: 1, escola: "Abjuração",     desc_curta: "Reação: resistência ao elemento; próximo acerto +1d6 dano" },
  { nome_pt: "Curar Ferimentos",   nome_en: "Cure Wounds",        nivel: 1, escola: "Evocação",      desc_curta: "1d8+mod.SAB PV curados por toque" },
  { nome_pt: "Névoa",              nome_en: "Fog Cloud",          nivel: 1, escola: "Conjuração",    desc_curta: "Esfera 6m de névoa pesada, bloqueia visão, 1 hora" },
  { nome_pt: "Falar com Animais",  nome_en: "Speak with Animals", nivel: 1, escola: "Adivinhação",   desc_curta: "Comunicar-se com animais por 10 minutos, ritual" },
  { nome_pt: "Marca do Caçador",   nome_en: "Hunter's Mark",      nivel: 1, escola: "Adivinhação",   desc_curta: "Marca alvo: +1d6 em ataques, vantagem em rastrear, 1 hora" },
  { nome_pt: "Passo Longo",        nome_en: "Longstrider",        nivel: 1, escola: "Transmutação",  desc_curta: "Velocidade +3m por 1 hora" },
  // Nível 2
  { nome_pt: "Passagem Silenciosa",nome_en: "Pass without Trace", nivel: 2, escola: "Abjuração",     desc_curta: "+10 em Furtividade, rastreamento impossível, concentração" },
  { nome_pt: "Restauração Menor",  nome_en: "Lesser Restoration", nivel: 2, escola: "Abjuração",     desc_curta: "Remove uma doença, condição de cegueira, surdez, paralisia" },
  { nome_pt: "Visão no Escuro",    nome_en: "Darkvision",         nivel: 2, escola: "Transmutação",  desc_curta: "Alvo ganha visão no escuro 18m por 8 horas" },
  { nome_pt: "Crescimento de Espinhos",nome_en:"Spike Growth",    nivel: 2, escola: "Transmutação",  desc_curta: "Solo 6m: terreno difícil + 2d4 por 1,5m percorrido" },
  { nome_pt: "Silêncio",           nome_en: "Silence",            nivel: 2, escola: "Ilusão",        desc_curta: "Zona 6m sem som por 10 min, bloqueia magias verbais" },
  // Nível 3
  { nome_pt: "Barreira de Projéteis",nome_en:"Conjure Barrage",   nivel: 3, escola: "Conjuração",    desc_curta: "Cone 18m de projéteis: 3d8 do tipo da arma, save DES" },
  { nome_pt: "Proteção contra Energia",nome_en:"Protection from Energy",nivel:3,escola:"Abjuração",  desc_curta: "Resistência a tipo de dano elemental, concentração 1 hora" },
  { nome_pt: "Invocar Animais",    nome_en: "Conjure Animals",    nivel: 3, escola: "Conjuração",    desc_curta: "Convoca espíritos bestas (CR total ≤2 em 2-8 criaturas)" },
];

// ── Dicionário principal ──────────────────────────────────────────────────────

export const SPELLS_POR_CLASSE: Record<string, SpellEntry[]> = {
  "mago":       MAGIAS_MAGO,
  "clérigo":    MAGIAS_CLERIGO,
  "clerigo":    MAGIAS_CLERIGO,  // alias sem acento
  "druida":     MAGIAS_DRUIDA,
  "bardo":      MAGIAS_BARDO,
  "feiticeiro": MAGIAS_FEITICEIRO,
  "bruxo":      MAGIAS_BRUXO,
  "paladino":   MAGIAS_PALADINO,
  "ranger":     MAGIAS_RANGER,
};

// ── Progressão de Magias ──────────────────────────────────────────────────────

export const PROGRESSAO_MAGIAS: Record<string, Record<number, ProgressaoEntry>> = {
  "mago": {
    1: { truques: 3, magias: 6,  nivel_max: 1 },
    2: { truques: 3, magias: 8,  nivel_max: 1 },
    3: { truques: 3, magias: 10, nivel_max: 2 },
    4: { truques: 4, magias: 12, nivel_max: 2 },
    5: { truques: 4, magias: 14, nivel_max: 3 },
    6: { truques: 4, magias: 16, nivel_max: 3 },
    7: { truques: 4, magias: 18, nivel_max: 4 },
    8: { truques: 4, magias: 20, nivel_max: 4 },
    9: { truques: 4, magias: 22, nivel_max: 5 },
    10:{ truques: 5, magias: 24, nivel_max: 5 },
  },
  "clérigo": {
    1: { truques: 3, magias: 4,  nivel_max: 1 },
    2: { truques: 3, magias: 5,  nivel_max: 1 },
    3: { truques: 3, magias: 6,  nivel_max: 2 },
    4: { truques: 4, magias: 7,  nivel_max: 2 },
    5: { truques: 4, magias: 8,  nivel_max: 3 },
    6: { truques: 4, magias: 9,  nivel_max: 3 },
    7: { truques: 4, magias: 10, nivel_max: 4 },
    8: { truques: 4, magias: 11, nivel_max: 4 },
    9: { truques: 4, magias: 12, nivel_max: 5 },
    10:{ truques: 5, magias: 13, nivel_max: 5 },
  },
  "druida": {
    1: { truques: 2, magias: 4,  nivel_max: 1 },
    2: { truques: 2, magias: 5,  nivel_max: 1 },
    3: { truques: 2, magias: 6,  nivel_max: 2 },
    4: { truques: 3, magias: 7,  nivel_max: 2 },
    5: { truques: 3, magias: 8,  nivel_max: 3 },
    6: { truques: 3, magias: 9,  nivel_max: 3 },
    7: { truques: 3, magias: 10, nivel_max: 4 },
    8: { truques: 3, magias: 11, nivel_max: 4 },
    9: { truques: 3, magias: 12, nivel_max: 5 },
    10:{ truques: 4, magias: 13, nivel_max: 5 },
  },
  "bardo": {
    1: { truques: 2, magias: 4,  nivel_max: 1 },
    2: { truques: 2, magias: 5,  nivel_max: 1 },
    3: { truques: 2, magias: 6,  nivel_max: 2 },
    4: { truques: 3, magias: 7,  nivel_max: 2 },
    5: { truques: 3, magias: 8,  nivel_max: 3 },
    6: { truques: 3, magias: 9,  nivel_max: 3 },
    7: { truques: 3, magias: 10, nivel_max: 4 },
    8: { truques: 3, magias: 11, nivel_max: 4 },
    9: { truques: 3, magias: 12, nivel_max: 5 },
    10:{ truques: 4, magias: 14, nivel_max: 5 },
  },
  "feiticeiro": {
    1: { truques: 4, magias: 2,  nivel_max: 1 },
    2: { truques: 4, magias: 3,  nivel_max: 1 },
    3: { truques: 4, magias: 4,  nivel_max: 2 },
    4: { truques: 5, magias: 5,  nivel_max: 2 },
    5: { truques: 5, magias: 6,  nivel_max: 3 },
    6: { truques: 5, magias: 7,  nivel_max: 3 },
    7: { truques: 5, magias: 8,  nivel_max: 4 },
    8: { truques: 5, magias: 9,  nivel_max: 4 },
    9: { truques: 5, magias: 10, nivel_max: 5 },
    10:{ truques: 6, magias: 11, nivel_max: 5 },
  },
  "bruxo": {
    1: { truques: 2, magias: 2,  nivel_max: 1 },
    2: { truques: 2, magias: 3,  nivel_max: 1 },
    3: { truques: 2, magias: 4,  nivel_max: 2 },
    4: { truques: 3, magias: 5,  nivel_max: 2 },
    5: { truques: 3, magias: 6,  nivel_max: 3 },
    6: { truques: 3, magias: 7,  nivel_max: 3 },
    7: { truques: 3, magias: 8,  nivel_max: 4 },
    8: { truques: 3, magias: 9,  nivel_max: 4 },
    9: { truques: 3, magias: 10, nivel_max: 5 },
    10:{ truques: 4, magias: 10, nivel_max: 5 },
  },
  "paladino": {
    1: { truques: 0, magias: 0,  nivel_max: 0 },
    2: { truques: 0, magias: 4,  nivel_max: 1 },
    3: { truques: 0, magias: 6,  nivel_max: 1 },
    4: { truques: 0, magias: 7,  nivel_max: 2 },
    5: { truques: 0, magias: 8,  nivel_max: 2 },
    6: { truques: 0, magias: 9,  nivel_max: 3 },
    7: { truques: 0, magias: 10, nivel_max: 3 },
    8: { truques: 0, magias: 11, nivel_max: 3 },
    9: { truques: 0, magias: 12, nivel_max: 4 },
    10:{ truques: 0, magias: 13, nivel_max: 4 },
  },
  "ranger": {
    1: { truques: 0, magias: 0,  nivel_max: 0 },
    2: { truques: 0, magias: 2,  nivel_max: 1 },
    3: { truques: 0, magias: 3,  nivel_max: 1 },
    4: { truques: 0, magias: 3,  nivel_max: 1 },
    5: { truques: 0, magias: 4,  nivel_max: 2 },
    6: { truques: 0, magias: 4,  nivel_max: 2 },
    7: { truques: 0, magias: 5,  nivel_max: 2 },
    8: { truques: 0, magias: 5,  nivel_max: 2 },
    9: { truques: 0, magias: 6,  nivel_max: 3 },
    10:{ truques: 0, magias: 6,  nivel_max: 3 },
  },
};

// Aliases sem acentos para o PROGRESSAO_MAGIAS
PROGRESSAO_MAGIAS["clerigo"] = PROGRESSAO_MAGIAS["clérigo"];

// ── Funções públicas ──────────────────────────────────────────────────────────

/** Retorna todas as spells disponíveis para a classe (lowercase). */
export function spellsDaClasse(classe: string): SpellEntry[] {
  return SPELLS_POR_CLASSE[classe.toLowerCase()] ?? [];
}

/** Filtra spells da classe por nível de magia (0=truques). */
export function spellsPorNivel(classe: string, nivelSpell: number): SpellEntry[] {
  return spellsDaClasse(classe).filter(s => s.nivel === nivelSpell);
}

/** Retorna limites de magias para a classe no nível do personagem (1-20). */
export function limiteProgressao(classe: string, nivelPersonagem: number): ProgressaoEntry {
  const tabela = PROGRESSAO_MAGIAS[classe.toLowerCase()];
  if (!tabela) return { truques: 0, magias: 0, nivel_max: 0 };
  const nivelClamped = Math.max(1, Math.min(10, nivelPersonagem));
  return tabela[nivelClamped] ?? { truques: 0, magias: 0, nivel_max: 0 };
}

/** Retorna o nível de uma spell pelo nome PT-BR dentro da classe (case-insensitive). */
export function nivelDaSpell(nomePt: string, classe: string): number | null {
  const nomeLower = nomePt.toLowerCase();
  const spell = spellsDaClasse(classe).find(s => s.nome_pt.toLowerCase() === nomeLower);
  return spell ? spell.nivel : null;
}

/** Verifica se a classe é spellcaster. */
export function ehConjuradorDaClasse(classe: string): boolean {
  return classe.toLowerCase() in SPELLS_POR_CLASSE &&
    (PROGRESSAO_MAGIAS[classe.toLowerCase()]?.[1]?.nivel_max ?? 0) >= 0 &&
    spellsDaClasse(classe).length > 0;
}

/** Clamp utilitário para nível no range [1,10]. */
export function clampNivel(nivel: number): number {
  return Math.max(1, Math.min(10, nivel));
}
