// Strip de marcadores para EXIBIÇÃO — espelho de engine/markers.py.
//
// Por que existe (MARKER-DISPLAY-LEAK-1, rodada grimdark 18/07): o backend
// stripa os markers antes do TTS, mas o CHAT renderiza o stream cru — quando o
// modelo emite `[CENA: ...] [INIMIGO_MORTO: roric] [XP: +50] [Q:...]` no fim da
// resposta, a bolha mostrava tudo. Este espelho limpa o texto no ponto de
// flush do turno (useGameSession, handler tipo="fim").
//
// ⚠️ Manter NOMES em sincronia com NOMES_MARCADORES de engine/markers.py
// (+ os casos especiais [Rolagem ...] e [Q:quest:stage], stripados no Python
// por regexes próprias). Marker novo no backend → adicionar aqui também
// (teste de contrato: tests/test_contrato_markers_ws.py guarda o lado Python).

const NOMES: readonly string[] = [
  // Narrativa contínua
  "FIO", "CLIFFHANGER", "AGENDA", "CONSEQUÊNCIA", "CONSEQUENCIA", "ANCORA",
  "XP", "LAMPEJO",
  // Combate
  "POSICAO", "MOV", "INIMIGO_MORTO", "INIMIGO", "FUGIU", "COMBATE",
  "DANO", "CURA",
  // Economia
  "OURO", "LOOT", "PERDEU", "MERCADO", "FIM_MERCADO",
  // Aliados
  "COMPANION_ADD", "COMPANION_HP", "COMPANION_REMOVE",
  // Cena e persistência
  "DESCANSO", "VOZ", "AFETO", "CENA", "FEATURE_GASTA", "NPC",
  "CICATRIZ", "RELOGIO", "RELOGIO_AVANCA", "FICHA",
  // Rótulos de instrução que modelos ecoam
  "PRESSÁGIO", "PRESSAGIO", "REINCORPORAR", "PACING",
];

// [NOME ...] / [NOME=...] com envelope [TAG: ...] opcional (TAG-MALFORM-1),
// + [Rolagem ...] em qualquer variante, + [Q:quest:stage].
const RE_STRIP = new RegExp(
  String.raw`\[(?:TAG:\s*)?(?:${NOMES.join("|")})(?::|=)?[^\]]*\]` +
  String.raw`|\[Rolagem\b[^\]]*\]` +
  String.raw`|\[Q:[^\]]*\]`,
  "gi",
);

/** Remove marcadores técnicos do texto exibido; colapsa o espaço que sobra. */
export function stripMarcadoresExibicao(texto: string): string {
  if (!texto) return texto;
  return texto
    .replace(RE_STRIP, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
