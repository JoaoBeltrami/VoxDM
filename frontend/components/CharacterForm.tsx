"use client";

import { useEffect, useState } from "react";
import {
  listarArmas, obterEquipamentoInicial,
  type ArmaOpcao, type PersonagemConfig,
} from "@/lib/api";
import {
  spellsDaClasse, spellsPorNivel, limiteProgressao,
  type SpellEntry,
} from "@/lib/spells";
import { Card, Chip } from "@/components/ui";

const CLASSES_DND = [
  "Bárbaro", "Bardo", "Clérigo", "Druida", "Guerreiro",
  "Monge", "Paladino", "Ranger", "Ladino", "Feiticeiro", "Bruxo", "Mago",
];

/** Atributo do ataque, em palavra de mesa. "MELHOR" é a licença de `finesse`:
 *  o SRD deixa o jogador ESCOLHER, e mostrar a sigla crua faria a ficha parecer
 *  um dump de tabela. */
const ATRIBUTO_ARMA: Record<string, string> = {
  FOR: "Força",
  DES: "Destreza",
  MELHOR: "Força ou Destreza",
};

/** Sugestões para as categorias abertas que NÃO são arma (foco, símbolo,
 *  instrumento). A engine só resolve ARMA mecanicamente — nestas o campo segue
 *  LIVRE de propósito, e a lista é conforto de digitação, não trilho. */
const SUGESTOES_ABERTAS: Record<string, string[]> = {
  "um foco arcano": ["Orbe", "Cajado", "Varinha", "Cristal"],
  "um foco druídico": ["Bastão de teixo", "Ramo de azevinho", "Totem"],
  "um símbolo sagrado": ["Amuleto", "Emblema", "Relicário"],
  "um instrumento musical": ["Alaúde", "Flauta", "Tambor", "Lira"],
};

/** As armas válidas para uma categoria aberta do SRD.
 *
 *  "uma arma marcial corpo a corpo" → marciais que não são de distância. A
 *  filtragem vive aqui e não no backend porque a lista inteira tem 37 itens:
 *  uma busca só, e a ficha responde sem ida e volta a cada clique. */
function armasPara(categoria: string, todas: ArmaOpcao[]): ArmaOpcao[] {
  const cat = (categoria || "").toLowerCase();
  if (!cat.includes("arma")) return [];
  const querida = cat.includes("marcial") ? "marcial" : "simples";
  const soCorpoACorpo = cat.includes("corpo a corpo");
  return todas.filter(
    a => a.categoria === querida && (!soCorpoACorpo || !a.distancia),
  );
}

// Subclasses disponíveis por classe (nível 3, SRD 5e)
/** Os nove da tabela clássica, na ordem de leitura da grade 3×3.
 *  Espelha `engine/alinhamento.alinhamentos()` — se um lado mudar, o outro
 *  acompanha. A descrição existe pra quem nunca jogou D&D de mesa. */
const ALINHAMENTOS: { rotulo: string; nota: string }[] = [
  { rotulo: "Leal e Bom",     nota: "honra e compaixão — a palavra vale" },
  { rotulo: "Neutro e Bom",   nota: "faz o bem sem se prender a regras" },
  { rotulo: "Caótico e Bom",  nota: "coração certo, métodos próprios" },
  { rotulo: "Leal e Neutro",  nota: "a ordem acima do certo e do errado" },
  { rotulo: "Neutro",         nota: "equilíbrio — ou indiferença" },
  { rotulo: "Caótico e Neutro", nota: "liberdade acima de tudo" },
  { rotulo: "Leal e Mau",     nota: "cruel dentro das regras que escreve" },
  { rotulo: "Neutro e Mau",   nota: "sem causa, só interesse" },
  { rotulo: "Caótico e Mau",  nota: "destruição sem freio nem plano" },
];

const SUBCLASSES: Record<string, string[]> = {
  "Bárbaro":     ["Caminho do Berserker", "Caminho do Totem do Guerreiro"],
  "Bardo":       ["Colégio do Saber", "Colégio da Valentia"],
  "Clérigo":     ["Domínio da Vida", "Domínio da Luz", "Domínio da Guerra", "Domínio do Conhecimento", "Domínio do Truque"],
  "Druida":      ["Círculo da Terra", "Círculo da Lua"],
  "Feiticeiro":  ["Linhagem Dracônica", "Alma Selvagem"],
  "Guerreiro":   ["Campeão", "Mestre de Batalha", "Cavaleiro Místico"],
  "Ladino":      ["Ladrão", "Assassino", "Arquétipo Arcano"],
  "Mago":        ["Escola da Abjuração", "Escola da Conjuração", "Escola da Evocação", "Escola da Ilusão", "Escola da Necromancia", "Escola da Transmutação"],
  "Monge":       ["Caminho da Mão Aberta", "Caminho da Sombra"],
  "Paladino":    ["Juramento da Devoção", "Juramento dos Anciões", "Juramento da Vingança"],
  "Ranger":      ["Caçador", "Mestre das Bestas"],
  "Bruxo":       ["O Arquifada", "O Imundo", "O Grande Antigo"],
};

const RACAS_DND = [
  "Humano", "Elfo", "Anão", "Halfling", "Gnomo",
  "Meio-Elfo", "Meio-Orc", "Tiefling", "Draconato",
];

const BACKGROUNDS_DND = [
  "Acólito", "Artesão", "Criminoso", "Entretenedor",
  "Herói do Povo", "Nobre", "Forasteiro", "Sábio",
  "Marinheiro", "Soldado", "Vagabundo",
];

const HIT_DICE: Record<string, number> = {
  "Bárbaro": 12, "Guerreiro": 10, "Paladino": 10, "Ranger": 10,
  "Bardo": 8, "Clérigo": 8, "Druida": 8, "Monge": 8, "Ladino": 8,
  "Feiticeiro": 6, "Bruxo": 6, "Mago": 6,
};

const CLASS_SAVES: Record<string, string[]> = {
  "Bárbaro": ["FOR", "CON"], "Bardo": ["DES", "CAR"],
  "Clérigo": ["SAB", "CAR"], "Druida": ["INT", "SAB"],
  "Guerreiro": ["FOR", "CON"], "Monge": ["FOR", "DES"],
  "Paladino": ["SAB", "CAR"], "Ranger": ["FOR", "DES"],
  "Ladino": ["DES", "INT"], "Feiticeiro": ["CON", "CAR"],
  "Bruxo": ["SAB", "CAR"], "Mago": ["INT", "SAB"],
};

const CLASS_SKILLS: Record<string, string[]> = {
  "Bárbaro": ["Atletismo", "Intimidação"],
  "Bardo": ["Persuasão", "Atuação"],
  "Clérigo": ["Intuição", "Religião"],
  "Druida": ["Natureza", "Percepção"],
  "Guerreiro": ["Atletismo", "Percepção"],
  "Monge": ["Acrobacia", "Intuição"],
  "Paladino": ["Persuasão", "Religião"],
  "Ranger": ["Percepção", "Sobrevivência"],
  "Ladino": ["Furtividade", "Enganação"],
  "Feiticeiro": ["Arcanismo", "Persuasão"],
  "Bruxo": ["Arcanismo", "Enganação"],
  "Mago": ["Arcanismo", "História"],
};

const BACKGROUND_SKILLS: Record<string, string[]> = {
  "Acólito": ["Intuição", "Religião"],
  "Artesão": ["História", "Persuasão"],
  "Criminoso": ["Enganação", "Furtividade"],
  "Entretenedor": ["Acrobacia", "Atuação"],
  "Herói do Povo": ["Adestrar Animais", "Sobrevivência"],
  "Nobre": ["História", "Persuasão"],
  "Forasteiro": ["Atletismo", "Sobrevivência"],
  "Sábio": ["Arcanismo", "História"],
  "Marinheiro": ["Atletismo", "Percepção"],
  "Soldado": ["Atletismo", "Intimidação"],
  "Vagabundo": ["Prestidigitação", "Furtividade"],
};

const LOCAIS_INICIO = [
  {
    id: "drevamor",
    nome: "Drevamor",
    descricao: "Vila central. Ponto de encontro de mercadores e aventureiros.",
  },
  {
    id: "tharnvik",
    nome: "Tharnvik",
    descricao: "Vila do norte, perto das gargantas vulcânicas. Guerreiros e mineradores.",
  },
  {
    id: "kaelmund",
    nome: "Kaelmünd",
    descricao: "Vila oriental de pedra. Mestres artesãos e guardas da fronteira.",
  },
  {
    id: "acampamento-sem-vila",
    nome: "Acampamento dos Sem-Vila",
    descricao: "Marginalizado, fora das muralhas. Refugiados e forasteiros.",
  },
];

// Standard Array D&D 5e
const ARRAY_PADRAO = [15, 14, 13, 12, 10, 8];

type AtribKey = "str" | "dex" | "con" | "int" | "wis" | "cha";

// 4d6, descarta o menor — método clássico de mesa, range 3–18, média ~12.2
function rolar4d6DescartaMenor(): number {
  const dados = [0, 1, 2, 3].map(() => Math.floor(Math.random() * 6) + 1);
  dados.sort((a, b) => a - b);            // [menor, ..., maior]
  return dados[1] + dados[2] + dados[3];  // soma os 3 maiores
}

// Distribui 6 rolagens nos atributos priorizando o que faz sentido pra classe.
// Sem classe definida → distribui ordenado em FOR/DES/CON/INT/SAB/CAR.
const PRIORIDADE_POR_CLASSE: Record<string, AtribKey[]> = {
  "Bárbaro":   ["str", "con", "dex", "wis", "cha", "int"],
  "Bardo":     ["cha", "dex", "con", "wis", "int", "str"],
  "Clérigo":   ["wis", "con", "str", "cha", "dex", "int"],
  "Druida":    ["wis", "con", "dex", "int", "cha", "str"],
  "Guerreiro": ["str", "con", "dex", "wis", "cha", "int"],
  "Monge":     ["dex", "wis", "con", "str", "int", "cha"],
  "Paladino":  ["str", "cha", "con", "wis", "dex", "int"],
  "Ranger":    ["dex", "wis", "con", "str", "int", "cha"],
  "Ladino":    ["dex", "cha", "con", "int", "wis", "str"],
  "Feiticeiro":["cha", "con", "dex", "wis", "int", "str"],
  "Bruxo":     ["cha", "con", "dex", "wis", "int", "str"],
  "Mago":      ["int", "con", "dex", "wis", "cha", "str"],
};

const ATRIBS: { key: AtribKey; label: string; abrev: string }[] = [
  { key: "str", label: "Força",        abrev: "FOR" },
  { key: "dex", label: "Destreza",     abrev: "DES" },
  { key: "con", label: "Constituição", abrev: "CON" },
  { key: "int", label: "Inteligência", abrev: "INT" },
  { key: "wis", label: "Sabedoria",    abrev: "SAB" },
  { key: "cha", label: "Carisma",      abrev: "CAR" },
];

function fmtMod(score: number): string {
  const m = Math.floor((score - 10) / 2);
  return m >= 0 ? `+${m}` : `${m}`;
}

function calcHP(classe: string, nivel: number, conScore: number): number {
  const hd = HIT_DICE[classe] ?? 8;
  const conMod = Math.floor((conScore - 10) / 2);
  const lvl1 = Math.max(1, hd + conMod);
  const perNivel = Math.max(1, Math.floor(hd / 2) + 1 + conMod);
  return lvl1 + Math.max(0, nivel - 1) * perNivel;
}

function calcCA(classe: string, dex: number, con: number, wis: number): number {
  const dexMod = Math.floor((dex - 10) / 2);
  if (classe === "Bárbaro") return 10 + dexMod + Math.floor((con - 10) / 2);
  if (classe === "Monge")   return 10 + dexMod + Math.floor((wis - 10) / 2);
  return 10 + dexMod;
}

function profBonus(nivel: number): number {
  return Math.floor((nivel - 1) / 4) + 2;
}

interface Props {
  onChange: (config: PersonagemConfig) => void;
}

const NOMES_FANTASIA = [
  "Aldric", "Lyra", "Torvin", "Brenna", "Kael", "Mira",
  "Doran", "Vex", "Sylas", "Riona", "Cassian", "Nyx",
  "Garruk", "Elara", "Thane", "Selene", "Orin", "Vela",
];

export function CharacterForm({ onChange }: Props) {
  const [nome, setNome] = useState("");
  const [raca, setRaca] = useState("");
  const [classe, setClasse] = useState("");
  const [subclasse, setSubclasse] = useState("");
  const [alinhamento, setAlinhamento] = useState("Neutro");
  const [background, setBackground] = useState("");
  // Descrição livre do personagem — opcional. Quando preenchida, o Mestre
  // usa pra moldar a abertura narrativa (motivação, segredos, aparência).
  // Limite de 600 chars previne abuso e estouro de tokens na intro.
  const DESC_MAX = 600;
  const [descricao, setDescricao] = useState("");
  const [nivel] = useState(3);
  const [localId, setLocalId] = useState("");

  // "array"          = Standard Array picker (15/14/13/12/10/8)
  // "rolado-auto"    = 4d6 drop lowest, distribuído por prioridade de classe
  // "rolado-manual"  = 4d6 drop lowest, jogador atribui via selects da pool (Task 3)
  const [modoAtributos, setModoAtributos] = useState<"array" | "rolado-auto" | "rolado-manual">("array");

  const [scores, setScores] = useState<Record<AtribKey, number>>({
    str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0,
  });

  // P18 frente A — equipamento inicial: o que a classe dá de graça e o que o
  // jogador escolhe. Buscado do servidor pra que a REGRA (quais opções existem)
  // continue morando atrás do RuleSystem, e não numa cópia no frontend.
  const [equipDaClasse, setEquipDaClasse] = useState<import("@/lib/api").EquipamentoDaClasse | null>(null);
  // índice da opção escolhida por pergunta; -1 = ainda não escolheu
  const [equipEscolhas, setEquipEscolhas] = useState<number[]>([]);
  // texto livre das opções ABERTAS ("uma arma marcial"), por índice de pergunta
  const [equipAbertas, setEquipAbertas] = useState<Record<number, string>>({});
  // Catálogo de armas para as escolhas ABERTAS. Buscado uma vez: são 37 itens,
  // e refazer a chamada a cada clique deixaria o seletor com lag visível.
  const [armas, setArmas] = useState<ArmaOpcao[]>([]);
  const [filtroArma, setFiltroArma] = useState<Record<number, string>>({});

  // Magias selecionadas no CharacterForm — sincronizadas no onChange
  const [selectedSpells, setSelectedSpells] = useState<string[]>([]);
  // Aba ativa na seção de magias: "truques" | 1 | 2 | 3 | 4 | 5
  const [nivelTabSpells, setNivelTabSpells] = useState<number>(0);

  // Pool de valores 4d6 rolados — usado em modo "rolado-manual" pra que o jogador
  // possa decidir qual rolagem vai pra qual atributo (com bag-of-values: cada
  // valor pode ser atribuído uma vez, ainda que dois dados tenham caído iguais).
  const [valoresRolados, setValoresRolados] = useState<number[]>([]);

  // Conta multiset de valores ainda disponíveis (rolados − usados).
  // Usado pra popular os selects em rolado-manual sem duplicar quando há ties.
  const valoresUsadosManual = modoAtributos === "rolado-manual"
    ? ATRIBS.map(a => scores[a.key]).filter(v => v > 0)
    : [];
  const remainingRolados = (() => {
    if (modoAtributos !== "rolado-manual") return [];
    const usados = [...valoresUsadosManual];
    const restante: number[] = [];
    for (const v of valoresRolados) {
      const idx = usados.indexOf(v);
      if (idx >= 0) usados.splice(idx, 1);
      else restante.push(v);
    }
    return restante.sort((a, b) => b - a);
  })();

  const assignedValues = Object.values(scores).filter(v => v > 0);
  const remainingValues = modoAtributos === "array"
    ? ARRAY_PADRAO.filter(v => !assignedValues.includes(v))
    : remainingRolados;
  const allAssigned = assignedValues.length === 6;

  const assignScore = (key: AtribKey, value: number) => {
    setScores(prev => ({ ...prev, [key]: value }));
  };

  // Rola 6× 4d6-drop-lowest e distribui prioritariamente pra classe atual.
  // Em ausência de classe, ordem FOR/DES/CON/INT/SAB/CAR.
  const rolarAtributos = () => {
    const rolados = Array.from({ length: 6 }, () => rolar4d6DescartaMenor())
      .sort((a, b) => b - a); // maior → menor
    const ordem: AtribKey[] = PRIORIDADE_POR_CLASSE[classe] ?? ["str","dex","con","int","wis","cha"];
    const novos: Record<AtribKey, number> = { str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 };
    ordem.forEach((k, i) => { novos[k] = rolados[i]; });
    setScores(novos);
    setValoresRolados(rolados);
    setModoAtributos("rolado-auto");
  };

  // Task 3: alterna entre auto (priorizado pela classe) e manual (jogador atribui).
  // Em manual: zera os scores, mantém o pool 4d6 já rolado, e o jogador usa
  // selects pra colocar cada valor onde quiser.
  const alternarRolagemManual = () => {
    if (modoAtributos === "rolado-manual") {
      // Voltar pra auto: redistribui usando prioridade de classe
      const ordem: AtribKey[] = PRIORIDADE_POR_CLASSE[classe] ?? ["str","dex","con","int","wis","cha"];
      const ordenados = [...valoresRolados].sort((a, b) => b - a);
      const novos: Record<AtribKey, number> = { str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 };
      ordem.forEach((k, i) => { novos[k] = ordenados[i] ?? 0; });
      setScores(novos);
      setModoAtributos("rolado-auto");
    } else {
      // Ir pra manual: zera os slots, mantém o pool intacto
      setScores({ str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 });
      setModoAtributos("rolado-manual");
    }
  };

  // Personagem completo aleatório — raça, classe, background, atributos.
  // Preserva nome se já preenchido; senão escolhe um nome fantasia.
  const personagemAleatorio = () => {
    const pick = <T,>(arr: readonly T[]): T => arr[Math.floor(Math.random() * arr.length)];
    const novaClasse = pick(CLASSES_DND);
    // Sorteia subclasse aleatória se a classe tiver opções
    const subclasseOpcoes = SUBCLASSES[novaClasse] ?? [];
    const novaSubclasse = subclasseOpcoes.length > 0 ? pick(subclasseOpcoes) : "";
    setRaca(pick(RACAS_DND));
    setClasse(novaClasse);
    setSubclasse(novaSubclasse);
    setBackground(pick(BACKGROUNDS_DND));
    if (!nome.trim()) setNome(pick(NOMES_FANTASIA));
    if (!localId) setLocalId(pick(LOCAIS_INICIO).id);

    const rolados = Array.from({ length: 6 }, () => rolar4d6DescartaMenor())
      .sort((a, b) => b - a);
    const ordem = PRIORIDADE_POR_CLASSE[novaClasse] ?? ["str","dex","con","int","wis","cha"];
    const novos: Record<AtribKey, number> = { str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 };
    ordem.forEach((k, i) => { novos[k as AtribKey] = rolados[i]; });
    setScores(novos);
    setValoresRolados(rolados);
    setModoAtributos("rolado-auto");
  };

  const resetarParaArray = () => {
    setScores({ str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 });
    setValoresRolados([]);
    setModoAtributos("array");
  };

  const hp  = allAssigned && classe ? calcHP(classe, nivel, scores.con) : 0;
  const ca  = allAssigned && classe ? calcCA(classe, scores.dex, scores.con, scores.wis) : 10;
  const prof = profBonus(nivel);

  const allSkills = Array.from(new Set([
    ...(CLASS_SKILLS[classe] ?? []),
    ...(BACKGROUND_SKILLS[background] ?? []),
  ]));

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const local = LOCAIS_INICIO.find(l => l.id === localId);
    const hd = HIT_DICE[classe] ?? 8;
    const hpFinal = allAssigned
      ? calcHP(classe, nivel, scores.con)
      : hd + (nivel - 1) * (Math.floor(hd / 2) + 1);

    onChange({
      player_name:       nome.trim(),
      player_race:       raca,
      player_class:      classe,
      player_subclass:   subclasse,
      player_alignment:  alinhamento,
      player_background: background,
      player_description: descricao.trim(),
      player_level:      nivel,
      player_hp:         hpFinal,
      player_hp_max:     hpFinal,
      location_id:       local?.id ?? "",
      location_nome:     local?.nome ?? "",
      str_score:  scores.str || 10,
      dex_score:  scores.dex || 10,
      con_score:  scores.con || 10,
      int_score:  scores.int || 10,
      wis_score:  scores.wis || 10,
      cha_score:  scores.cha || 10,
      skill_profs: allSkills,
      save_profs:  CLASS_SAVES[classe] ?? [],
      player_spells: selectedSpells,
      player_equipamento: itensEscolhidos,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nome, raca, classe, subclasse, background, descricao, nivel, localId, scores,
      selectedSpells, equipEscolhas, equipAbertas, equipDaClasse]);

  // Classe mudou → busca as opções e ZERA as escolhas. Manter a escolha antiga
  // daria ao Guerreiro o alaúde do Bardo, e o índice nem apontaria pra mesma
  // pergunta: as listas têm tamanhos diferentes por classe.
  useEffect(() => {
    let vivo = true;
    if (!classe) { setEquipDaClasse(null); setEquipEscolhas([]); setEquipAbertas({}); return; }
    obterEquipamentoInicial(classe).then(dados => {
      if (!vivo) return;
      setEquipDaClasse(dados);
      setEquipEscolhas((dados?.escolhas ?? []).map(() => -1));
      setEquipAbertas({});
      setFiltroArma({});
    });
    return () => { vivo = false; };
  }, [classe]);

  // Catálogo de armas — uma vez por montagem, independente da classe.
  useEffect(() => {
    let vivo = true;
    listarArmas().then(lista => { if (vivo) setArmas(lista); });
    return () => { vivo = false; };
  }, []);

  // Itens que a escolha produziu — é isto que vai no payload da sessão. A opção
  // ABERTA vira o texto que o jogador digitou; vazio simplesmente não entra,
  // porque item sem nome é item que ninguém acha depois.
  const itensEscolhidos: string[] = (equipDaClasse?.escolhas ?? []).flatMap((esc, i) => {
    const j = equipEscolhas[i];
    if (j == null || j < 0 || j >= esc.opcoes.length) return [];
    const opcao = esc.opcoes[j];
    const itens = opcao.itens.flatMap(it => Array(it.quantidade).fill(it.nome) as string[]);
    const aberto = (equipAbertas[i] ?? "").trim();
    return opcao.categoria && aberto ? [...itens, aberto] : itens;
  });

  // Uma escolha só conta como FEITA quando também tem o nome, se a opção era
  // aberta. Antes bastava marcar o botão: dava pra escolher "uma arma marcial",
  // não dizer qual, e sair com um Guerreiro sem arma nenhuma — o buraco exato
  // que o P17 (cobrar posse de item) espera fechar.
  const totalEscolhas = equipDaClasse?.escolhas.length ?? 0;
  const escolhasFeitas = (equipDaClasse?.escolhas ?? []).filter((esc, i) => {
    const j = equipEscolhas[i] ?? -1;
    if (j < 0 || j >= esc.opcoes.length) return false;
    const categoria = esc.opcoes[j]?.categoria ?? "";
    return !categoria || (equipAbertas[i] ?? "").trim().length > 0;
  }).length;
  const faltamEscolhas = escolhasFeitas < totalEscolhas;

  // O que o personagem VAI carregar, já somado: fixos + escolhidos, com
  // contagem. É o "nascimento visível" da ficha — o jogador vê a mochila encher
  // enquanto decide, em vez de descobrir o inventário no primeiro combate.
  const mochila: { nome: string; qtd: number }[] = (() => {
    const contagem = new Map<string, number>();
    for (const nome of [...(equipDaClasse?.fixos ?? []), ...itensEscolhidos]) {
      contagem.set(nome, (contagem.get(nome) ?? 0) + 1);
    }
    // Array.from, não spread: o target do tsconfig não itera MapIterator.
    return Array.from(contagem.entries()).map(([nome, qtd]) => ({ nome, qtd }));
  })();

  return (
    <div className="w-full space-y-4 text-left">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-vox-accent-glow uppercase tracking-wider">
          Seu Personagem
        </p>
        <Chip
          tone="violet"
          onClick={personagemAleatorio}
          title="Gera raça, classe, background, atributos e local aleatórios"
          className="rounded-full px-2.5 py-1 text-[10px] font-semibold active:scale-95"
        >
          🎲 Aleatório
        </Chip>
      </div>

      {/* Nome */}
      <div>
        <label className="mb-1 block text-xs text-vox-text-secondary">
          Nome <span className="text-red-400">*</span>
        </label>
        <input
          value={nome}
          onChange={e => setNome(e.target.value)}
          placeholder="Ex: Aldric, Lyra, Torvin..."
          maxLength={40}
          className="w-full rounded border border-vox-border-soft bg-vox-bg-elevated px-2 py-1.5 text-xs text-vox-text-primary outline-none focus:border-vox-accent-primary"
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        {/* Raça */}
        <div>
          <label className="mb-1 block text-xs text-vox-text-secondary">
            Raça <span className="text-red-400">*</span>
          </label>
          <select
            value={raca}
            onChange={e => setRaca(e.target.value)}
            className="w-full rounded border border-vox-border-soft bg-vox-bg-elevated px-2 py-1.5 text-xs text-vox-text-primary outline-none focus:border-vox-accent-primary"
          >
            <option value="">— Escolher —</option>
            {RACAS_DND.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>

        {/* Classe */}
        <div>
          <label className="mb-1 block text-xs text-vox-text-secondary">
            Classe <span className="text-red-400">*</span>
          </label>
          <select
            value={classe}
            onChange={e => { setClasse(e.target.value); setSubclasse(""); setSelectedSpells([]); setNivelTabSpells(0); }}
            className="w-full rounded border border-vox-border-soft bg-vox-bg-elevated px-2 py-1.5 text-xs text-vox-text-primary outline-none focus:border-vox-accent-primary"
          >
            <option value="">— Escolher —</option>
            {CLASSES_DND.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {/* Subclasse — aparece somente quando a classe tem subclasses mapeadas */}
      {classe && (SUBCLASSES[classe]?.length ?? 0) > 0 && (
        <div>
          <label className="mb-1 block text-xs text-vox-text-secondary">
            Subclasse
            <span className="ml-1 text-[10px] text-vox-text-muted">(opcional)</span>
          </label>
          <select
            value={subclasse}
            onChange={e => setSubclasse(e.target.value)}
            className="w-full rounded border border-vox-border-soft bg-vox-bg-elevated px-2 py-1.5 text-xs text-vox-text-primary outline-none focus:border-vox-accent-primary"
          >
            <option value="">— Sem subclasse —</option>
            {(SUBCLASSES[classe] ?? []).map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      )}

      {/* Feitio (alinhamento) — a bússola moral declarada. Vira a POSIÇÃO
          INICIAL dos eixos no backend; os atos do jogador movem dali. */}
      <div>
        <label className="mb-1 block text-xs text-vox-text-secondary">
          Feitio
          <span className="ml-1 text-[10px] text-vox-text-muted">
            (como você costuma agir — o mundo julga pelos atos, não pela ficha)
          </span>
        </label>
        <select
          value={alinhamento}
          onChange={e => setAlinhamento(e.target.value)}
          className="w-full rounded border border-vox-border-soft bg-vox-bg-elevated px-2 py-1.5 text-xs text-vox-text-primary outline-none focus:border-vox-accent-primary"
        >
          {ALINHAMENTOS.map(a => (
            <option key={a.rotulo} value={a.rotulo}>
              {a.rotulo} — {a.nota}
            </option>
          ))}
        </select>
      </div>

      {/* P18 frente A — Equipamento inicial (SRD). O bloco só aparece quando a
          classe tem algo a mostrar: classe sem dados não deixa um vazio na tela. */}
      {equipDaClasse && (equipDaClasse.fixos.length > 0 || equipDaClasse.escolhas.length > 0) && (
        <div className="space-y-3 rounded-lg border border-vox-border-soft bg-vox-bg-elevated/40 p-3">
          {/* O progresso é a informação mais importante do bloco: sem ele o
              jogador não descobre que PRECISA escolher — e sai de mãos abanando,
              que é literalmente como o Guerreiro nasce (fixos = []). */}
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-vox-accent-glow">
              Equipamento
            </p>
            {totalEscolhas > 0 && (
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${
                  faltamEscolhas
                    ? "bg-amber-900/40 text-amber-300"
                    : "bg-emerald-900/40 text-emerald-300"
                }`}
              >
                {faltamEscolhas ? `${escolhasFeitas} de ${totalEscolhas}` : "tudo escolhido"}
              </span>
            )}
          </div>

          {totalEscolhas > 0 && (
            <div className="h-0.5 w-full overflow-hidden rounded-full bg-vox-bg-base/60">
              <div
                className="h-full rounded-full bg-vox-accent-primary transition-all duration-300"
                style={{ width: `${(escolhasFeitas / totalEscolhas) * 100}%` }}
              />
            </div>
          )}

          {equipDaClasse.fixos.length > 0 && (
            <div>
              <p className="mb-1 text-[10px] uppercase tracking-wide text-vox-text-muted">
                Já vem com você
              </p>
              <div className="flex flex-wrap gap-1">
                {Array.from(new Set(equipDaClasse.fixos)).map(nome => {
                  const qtd = equipDaClasse.fixos.filter(f => f === nome).length;
                  return (
                    <span
                      key={nome}
                      className="rounded border border-vox-border-soft bg-vox-bg-elevated px-1.5 py-0.5 text-[10px] text-vox-text-secondary"
                    >
                      {nome}
                      {qtd > 1 && <span className="text-vox-text-muted"> ×{qtd}</span>}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {equipDaClasse.escolhas.map((esc, i) => {
            const j = equipEscolhas[i] ?? -1;
            const categoria = (j >= 0 ? esc.opcoes[j]?.categoria : "") ?? "";
            const nomeAberto = (equipAbertas[i] ?? "").trim();
            const pendente = j < 0 || (!!categoria && !nomeAberto);
            const opcoesArma = categoria ? armasPara(categoria, armas) : [];
            const filtro = (filtroArma[i] ?? "").toLowerCase().trim();
            const armasVisiveis = filtro
              ? opcoesArma.filter(a => a.nome.toLowerCase().includes(filtro))
              : opcoesArma;
            const sugestoes = SUGESTOES_ABERTAS[categoria.toLowerCase()] ?? [];

            return (
              <div key={i} className="space-y-1.5">
                <p className="text-[10px] uppercase tracking-wide text-vox-text-muted">
                  Escolha {i + 1}
                  {pendente && <span className="ml-1 text-amber-400/80">— falta decidir</span>}
                </p>

                {/* Cartão por opção, mostrando os ITENS que ela dá em vez da
                    frase corrida do SRD. "Armadura de couro, Arco longo, Flecha
                    ×20" numa linha só é uma etiqueta; em peças, é uma escolha. */}
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {esc.opcoes.map((opcao, k) => {
                    const ativa = j === k;
                    return (
                      <button
                        key={k}
                        type="button"
                        onClick={() => {
                          setEquipEscolhas(a => a.map((v, idx) => (idx === i ? k : v)));
                          // Trocar de opção limpa o nome antigo: a arma marcial
                          // escolhida não faz sentido sob a opção do escudo.
                          setEquipAbertas(a => ({ ...a, [i]: "" }));
                          setFiltroArma(a => ({ ...a, [i]: "" }));
                        }}
                        className={`rounded-md border p-2 text-left transition ${
                          ativa
                            ? "border-vox-accent-primary bg-vox-accent-primary/20"
                            : "border-vox-border-soft bg-vox-bg-elevated hover:border-vox-accent-primary/60"
                        }`}
                      >
                        <div className="flex flex-wrap items-center gap-1">
                          <span
                            className={`text-[10px] leading-none ${
                              ativa ? "text-vox-accent-glow" : "text-vox-text-muted"
                            }`}
                          >
                            {ativa ? "◉" : "○"}
                          </span>
                          {opcao.itens.map((it, n) => (
                            <span
                              key={n}
                              className="rounded bg-vox-bg-base/60 px-1.5 py-0.5 text-[10px] text-vox-text-primary"
                            >
                              {it.nome}
                              {it.quantidade > 1 && (
                                <span className="text-vox-text-muted"> ×{it.quantidade}</span>
                              )}
                            </span>
                          ))}
                          {opcao.categoria && (
                            <span className="rounded border border-dashed border-vox-border-soft px-1.5 py-0.5 text-[10px] italic text-vox-text-secondary">
                              {opcao.categoria}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>

                {/* Categoria ABERTA. Era um <input> de texto livre cujo conteúdo
                    virava NOME DE ITEM — e "espada" não é "Espada longa" para
                    `identificar_arma`, então a arma sumia na hora do ataque.
                    Agora a ficha OFERECE as armas válidas da categoria, com dado
                    e atributo à vista: escolher deixa de ser adivinhar. */}
                {categoria && (
                  <div className="rounded-md border border-vox-accent-primary/30 bg-vox-bg-base/30 p-2">
                    <div className="mb-1.5 flex items-baseline justify-between gap-2">
                      <p className="text-[10px] uppercase tracking-wide text-vox-text-muted">
                        Qual {categoria.replace(/^umas?\s+|^um\s+/i, "")}?
                      </p>
                      {nomeAberto && (
                        <span className="truncate text-[10px] font-semibold text-vox-accent-glow">
                          {nomeAberto}
                        </span>
                      )}
                    </div>

                    {opcoesArma.length > 0 ? (
                      <>
                        {opcoesArma.length > 8 && (
                          <input
                            value={filtroArma[i] ?? ""}
                            onChange={e => setFiltroArma(a => ({ ...a, [i]: e.target.value }))}
                            placeholder={`filtrar ${opcoesArma.length} armas…`}
                            className="mb-1.5 w-full rounded border border-vox-border-soft bg-vox-bg-elevated px-2 py-1 text-[11px] text-vox-text-primary outline-none focus:border-vox-accent-primary"
                          />
                        )}
                        <div className="grid max-h-36 grid-cols-2 gap-1 overflow-y-auto pr-0.5 sm:grid-cols-3">
                          {armasVisiveis.map(a => {
                            const escolhida = nomeAberto === a.nome;
                            return (
                              <button
                                key={a.id}
                                type="button"
                                onClick={() => setEquipAbertas(prev => ({ ...prev, [i]: a.nome }))}
                                className={`rounded border px-1.5 py-1 text-left transition ${
                                  escolhida
                                    ? "border-vox-accent-primary bg-vox-accent-primary/25"
                                    : "border-vox-border-soft bg-vox-bg-elevated hover:border-vox-accent-primary/60"
                                }`}
                              >
                                <span className="block truncate text-[11px] leading-tight text-vox-text-primary">
                                  {a.nome}
                                </span>
                                <span className="block truncate text-[9px] leading-tight text-vox-text-muted">
                                  {a.dado} · {ATRIBUTO_ARMA[a.atributo] ?? a.atributo}
                                  {a.distancia && " · à distância"}
                                </span>
                              </button>
                            );
                          })}
                          {armasVisiveis.length === 0 && (
                            <p className="col-span-full py-1 text-[10px] text-vox-text-muted">
                              Nenhuma arma com esse nome.
                            </p>
                          )}
                        </div>
                      </>
                    ) : (
                      <>
                        {/* Foco, símbolo e instrumento: a engine não resolve isso
                            mecanicamente, então o campo continua LIVRE. As
                            sugestões são conforto de digitação, não trilho. */}
                        <input
                          value={equipAbertas[i] ?? ""}
                          onChange={e => setEquipAbertas(a => ({ ...a, [i]: e.target.value }))}
                          placeholder="escreva o que você carrega"
                          maxLength={40}
                          className="w-full rounded border border-vox-border-soft bg-vox-bg-elevated px-2 py-1 text-xs text-vox-text-primary outline-none focus:border-vox-accent-primary"
                        />
                        {sugestoes.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {sugestoes.map(s => (
                              <button
                                key={s}
                                type="button"
                                onClick={() => setEquipAbertas(a => ({ ...a, [i]: s }))}
                                className={`rounded-full border px-2 py-0.5 text-[10px] transition ${
                                  nomeAberto === s
                                    ? "border-vox-accent-primary bg-vox-accent-primary/25 text-vox-accent-glow"
                                    : "border-vox-border-soft text-vox-text-muted hover:border-vox-accent-primary/60 hover:text-vox-text-primary"
                                }`}
                              >
                                {s}
                              </button>
                            ))}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {/* A mochila enchendo enquanto ele decide. É o mesmo dado que vai no
              payload — o jogador confere o que vai carregar ANTES de jogar, em
              vez de descobrir o inventário no primeiro combate. */}
          {mochila.length > 0 && (
            <div className="rounded-md border border-vox-border-soft/60 bg-vox-bg-base/30 p-2">
              <p className="mb-1 text-[10px] uppercase tracking-wide text-vox-text-muted">
                Você começa com
              </p>
              <div className="flex flex-wrap gap-1">
                {mochila.map(it => (
                  <span
                    key={it.nome}
                    className="rounded bg-vox-accent-primary/15 px-1.5 py-0.5 text-[10px] text-vox-text-primary"
                  >
                    {it.nome}
                    {it.qtd > 1 && <span className="text-vox-text-muted"> ×{it.qtd}</span>}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Seleção de Magias — só para classes conjuradoras */}
      {(() => {
        const CLASSES_SPELLCASTERS = ["Mago", "Clérigo", "Druida", "Bardo", "Feiticeiro", "Bruxo", "Paladino", "Ranger"];
        if (!classe || !CLASSES_SPELLCASTERS.includes(classe)) return null;
        const classeLower = classe.toLowerCase();
        const limites = limiteProgressao(classeLower, nivel);
        if (limites.nivel_max === 0 && limites.magias === 0) return null; // nível 1 sem magia (Paladino/Ranger)

        const niveisDisponiveis = [0, ...Array.from({ length: limites.nivel_max }, (_, i) => i + 1)];
        const truquesSelecionados = selectedSpells.filter(n => spellsDaClasse(classeLower).find(s => s.nome_pt === n && s.nivel === 0)).length;
        const magiasSelecionadas = selectedSpells.filter(n => spellsDaClasse(classeLower).find(s => s.nome_pt === n && s.nivel > 0)).length;
        const totalSelecionadas = selectedSpells.length;
        const totalPermitido = limites.truques + limites.magias;

        const toggleSpell = (spell: SpellEntry) => {
          const jaSelecionada = selectedSpells.includes(spell.nome_pt);
          if (jaSelecionada) {
            setSelectedSpells(prev => prev.filter(n => n !== spell.nome_pt));
            return;
          }
          // Verifica limite por tipo
          if (spell.nivel === 0 && truquesSelecionados >= limites.truques) return;
          if (spell.nivel > 0 && magiasSelecionadas >= limites.magias) return;
          setSelectedSpells(prev => [...prev, spell.nome_pt]);
        };

        const spellsNaAba: SpellEntry[] = spellsPorNivel(classeLower, nivelTabSpells);

        return (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-xs text-vox-text-secondary">Magias</label>
              <span className={`text-[10px] font-semibold ${totalSelecionadas >= totalPermitido ? "text-vox-accent-glow" : "text-vox-text-muted"}`}>
                {totalSelecionadas}/{totalPermitido} selecionadas
              </span>
            </div>

            {/* Tabs por nível */}
            <div className="mb-2 flex gap-1 flex-wrap">
              {niveisDisponiveis.map(lv => {
                const rotulo = lv === 0 ? "Truques" : `Nível ${lv}`;
                const ativo = nivelTabSpells === lv;
                return (
                  <button
                    key={lv}
                    type="button"
                    onClick={() => setNivelTabSpells(lv)}
                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${
                      ativo
                        ? "border border-vox-accent-primary bg-vox-accent-primary/40 text-vox-accent-glow"
                        : "border border-vox-border-soft text-vox-text-muted hover:border-vox-border-strong hover:text-vox-text-primary"
                    }`}
                  >
                    {rotulo}
                  </button>
                );
              })}
            </div>

            {/* Lista de spells na aba ativa */}
            <Card variant="subtle" elevation="none" padding="sm" className="space-y-1 max-h-48 overflow-y-auto">
              {spellsNaAba.length === 0 && (
                <p className="text-[10px] text-vox-text-muted">Nenhuma magia disponível neste nível.</p>
              )}
              {spellsNaAba.map(spell => {
                const selecionada = selectedSpells.includes(spell.nome_pt);
                const ehTruque = spell.nivel === 0;
                const limiteAtingido = !selecionada && (
                  (ehTruque && truquesSelecionados >= limites.truques) ||
                  (!ehTruque && magiasSelecionadas >= limites.magias)
                );
                return (
                  <label
                    key={spell.nome_pt}
                    className={`flex items-start gap-2 cursor-pointer rounded p-1.5 transition ${
                      selecionada
                        ? "bg-vox-accent-primary/20 border border-vox-accent-primary/60/40"
                        : limiteAtingido
                          ? "opacity-50 cursor-not-allowed border border-transparent"
                          : "hover:bg-vox-bg-elevated/60 border border-transparent"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="mt-0.5 accent-violet-500"
                      checked={selecionada}
                      disabled={limiteAtingido}
                      onChange={() => !limiteAtingido && toggleSpell(spell)}
                    />
                    <div className="min-w-0">
                      <p className="text-[11px] font-semibold text-vox-text-primary leading-tight">{spell.nome_pt}</p>
                      <p className="text-[10px] text-vox-text-secondary leading-tight">{spell.desc_curta}</p>
                    </div>
                  </label>
                );
              })}
            </Card>

            {/* Resumo das selecionadas */}
            {totalSelecionadas > 0 && (
              <p className="mt-1.5 text-[10px] text-vox-accent-glow">
                Selecionadas: {selectedSpells.slice(0, 6).join(", ")}{selectedSpells.length > 6 ? ` +${selectedSpells.length - 6}` : ""}
              </p>
            )}
          </div>
        );
      })()}

      {/* Background — obrigatório: afeta perícias */}
      <div>
        <label className="mb-1 block text-xs text-vox-text-secondary">
          Background <span className="text-red-400">*</span>
        </label>
        <select
          value={background}
          onChange={e => setBackground(e.target.value)}
          className="w-full rounded border border-vox-border-soft bg-vox-bg-elevated px-2 py-1.5 text-xs text-vox-text-primary outline-none focus:border-vox-accent-primary"
        >
          <option value="">— Escolher —</option>
          {BACKGROUNDS_DND.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
      </div>

      {/* Descrição livre — opcional. Molda a abertura narrativa do Mestre. */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <label className="text-xs text-vox-text-secondary">
            Quem é seu personagem?
            <span className="ml-1 text-[10px] text-vox-text-muted">(opcional)</span>
          </label>
          <span className={`text-[10px] ${descricao.length > DESC_MAX * 0.9 ? "text-amber-400" : "text-vox-text-muted"}`}>
            {descricao.length}/{DESC_MAX}
          </span>
        </div>
        <textarea
          value={descricao}
          onChange={e => setDescricao(e.target.value.slice(0, DESC_MAX))}
          placeholder="Aparência, personalidade, motivação, segredo... O mestre usa pra moldar sua entrada na cena."
          rows={3}
          className="w-full resize-none rounded border border-vox-border-soft bg-vox-bg-elevated px-2 py-1.5 text-xs leading-relaxed text-vox-text-primary outline-none focus:border-vox-accent-primary"
        />
      </div>

      {/* Atributos — Standard Array OU 4d6 drop lowest */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs text-vox-text-secondary">Atributos</label>
          <div className="flex items-center gap-1.5">
            <Chip
              tone="amber"
              onClick={rolarAtributos}
              title="Rola 4d6 e descarta o menor, seis vezes. Distribui priorizando sua classe."
              className="rounded-full px-2.5 py-0.5 text-[10px] font-semibold active:scale-95"
            >
              🎲 Rolar 4d6↓
            </Chip>
            {(modoAtributos === "rolado-auto" || modoAtributos === "rolado-manual") && (
              <>
                <Chip
                  tone={modoAtributos === "rolado-manual" ? "violet" : "neutral"}
                  onClick={alternarRolagemManual}
                  title={modoAtributos === "rolado-manual"
                    ? "Voltar para distribuição automática (priorizada pela classe)"
                    : "Distribuir manualmente: arraste os valores rolados pros atributos"}
                  className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                >
                  {modoAtributos === "rolado-manual" ? "✋ manual" : "✋ distribuir"}
                </Chip>
                <Chip
                  tone="neutral"
                  onClick={resetarParaArray}
                  title="Voltar para o Standard Array (15, 14, 13, 12, 10, 8)"
                  className="rounded-full px-2 py-0.5 text-[10px]"
                >
                  array
                </Chip>
              </>
            )}
          </div>
        </div>

        {modoAtributos === "array" && (
          <p className="mb-1.5 text-[10px] text-vox-text-muted">
            Standard array: <span className="text-vox-text-muted">15, 14, 13, 12, 10, 8</span>
          </p>
        )}
        {modoAtributos === "rolado-auto" && allAssigned && (
          <p className="mb-1.5 text-[10px] text-amber-500/80">
            Rolado: <span className="text-amber-400 font-mono">{
              ATRIBS.map(a => scores[a.key]).sort((a, b) => b - a).join(", ")
            }</span> · total {ATRIBS.reduce((s, a) => s + scores[a.key], 0)} · auto pela classe
          </p>
        )}
        {modoAtributos === "rolado-manual" && (
          <div className="mb-1.5 flex items-center gap-2 text-[10px]">
            <span className="text-amber-500/80">Pool:</span>
            <span className="font-mono text-amber-400">
              {[...valoresRolados].sort((a, b) => b - a).join(", ")}
            </span>
            {remainingRolados.length > 0 && (
              <span className="text-vox-accent-glow">
                · restam: <span className="font-mono">{remainingRolados.join(", ")}</span>
              </span>
            )}
          </div>
        )}

        <div className="grid grid-cols-3 gap-1.5">
          {ATRIBS.map(({ key, label, abrev }) => {
            const valor = scores[key];
            const disponiveis = [
              ...(valor ? [valor] : []),
              ...remainingValues,
            ].sort((a, b) => b - a);

            const destaque = valor >= 16 ? "ring-1 ring-violet-500/60" : "";

            return (
              <div
                key={key}
                className={`rounded-lg border p-2 transition ${destaque} ${
                  valor
                    ? "border-vox-accent-primary/60/60 bg-vox-accent-primary/10"
                    : "border-vox-border-soft bg-vox-bg-elevated/50"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-vox-text-primary">{abrev}</span>
                  <span className={`text-xs font-semibold ${valor ? "text-vox-accent-glow" : "text-vox-text-muted"}`}>
                    {valor ? fmtMod(valor) : "—"}
                  </span>
                </div>

                {modoAtributos === "array" || modoAtributos === "rolado-manual" ? (
                  <select
                    value={valor || ""}
                    onChange={e => assignScore(key, Number(e.target.value))}
                    className={`w-full rounded border bg-vox-bg-panel py-0.5 text-center text-xs outline-none focus:border-vox-accent-primary ${
                      modoAtributos === "rolado-manual"
                        ? "border-amber-800/60 text-amber-200 font-bold"
                        : "border-vox-border-soft text-vox-text-primary"
                    }`}
                  >
                    <option value="">—</option>
                    {disponiveis.map((v, i) => (
                      // key precisa ser único — ties no pool (ex: dois 14) causam warning sem o índice
                      <option key={`${v}-${i}`} value={v}>{v}</option>
                    ))}
                  </select>
                ) : (
                  <div className="w-full rounded border border-amber-800/40 bg-vox-bg-panel py-0.5 text-center text-xs font-bold text-amber-300">
                    {valor || "—"}
                  </div>
                )}

                <p className="mt-0.5 text-center text-[10px] text-vox-text-muted truncate">{label}</p>
              </div>
            );
          })}
        </div>

        {(modoAtributos === "array" || modoAtributos === "rolado-manual") && remainingValues.length > 0 && (
          <p className="mt-1.5 text-xs text-vox-text-muted">
            Disponíveis: {remainingValues.join(", ")}
          </p>
        )}
      </div>

      {/* Preview de stats — aparece quando classe + atributos atribuídos */}
      {classe && allAssigned && (
        <Card variant="subtle" elevation="none" padding="none" className="px-3 py-2 space-y-1.5">
          <div className="grid grid-cols-3 gap-x-4 text-xs">
            <div className="flex justify-between">
              <span className="text-vox-text-muted">HP</span>
              <span className="font-semibold text-vox-accent-glow">{hp}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-vox-text-muted">CA</span>
              <span className="font-semibold text-vox-text-primary">{ca}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-vox-text-muted">Proef</span>
              <span className="font-semibold text-vox-text-primary">+{prof}</span>
            </div>
          </div>
          {(CLASS_SAVES[classe] ?? []).length > 0 && (
            <div className="text-xs">
              <span className="text-vox-text-muted">Saves: </span>
              <span className="text-vox-text-secondary">{(CLASS_SAVES[classe] ?? []).join(", ")}</span>
            </div>
          )}
          {allSkills.length > 0 && (
            <div className="text-xs">
              <span className="text-vox-text-muted">Perícias: </span>
              <span className="text-vox-text-secondary">{allSkills.join(", ")}</span>
            </div>
          )}
        </Card>
      )}

      {/* Local de início */}
      <div>
        <label className="mb-1 block text-xs text-vox-text-secondary">
          Local de início <span className="text-red-400">*</span>
        </label>
        <div className="space-y-2">
          {LOCAIS_INICIO.map(local => (
            <button
              key={local.id}
              type="button"
              onClick={() => setLocalId(local.id)}
              className={`w-full rounded-lg border px-3 py-2 text-left transition ${
                localId === local.id
                  ? "border-vox-accent-primary bg-vox-accent-primary/30"
                  : "border-vox-border-soft bg-vox-bg-elevated/50 hover:border-vox-border-strong"
              }`}
            >
              <p className={`text-xs font-semibold ${localId === local.id ? "text-vox-accent-glow" : "text-vox-text-primary"}`}>
                {local.nome}
              </p>
              <p className="text-xs text-vox-text-muted mt-0.5">{local.descricao}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
