# VoxDM Schema v2

> Formato declarativo de módulo do VoxDM. **Forward-compatível com o v1.2**: um
> módulo v1.2 valida como v2 sem mudanças — os campos novos são todos opcionais.
> Validação canônica: `engine/schema/v2.py` (`validar_modulo()`), Pydantic v2.

O Schema v2 é a evolução do v1.2 para um **mundo vivo dirigido por dados**, não
por improviso do LLM. A regra de ouro: tudo que o autor declara, a engine executa
com autoridade — e o Mestre (LLM) narra.

---

## Por que v2

O v1.2 já trazia `locations`, `npcs` (com `knowledge`/`speech_style`/`personality`),
`secrets` com `trigger_condition` machine-readable, `factions`, `items`, `quests`
e `edges`. O v2 **acrescenta** as peças que faltavam para o autor controlar o
mundo sem depender do modelo lembrar de marcadores:

| Novidade v2 | Resolve |
|---|---|
| Grafo de mapa navegável (`connections` como objetos) | "para onde dá pra ir, por qual rota, está trancado?" |
| `encounter_tables` | combates/encontros por local, com pesos e monstros do bestiário |
| NPC `appearance` / `voice` / `agenda` / `portrait_hint` nativos | alimenta retrato gerado, voz TTS por NPC e iniciativa de agenda |
| `fronts` (relógios autorais) | ameaças com contagem definida pelo autor ("a horda chega em 6 passos") |
| `loot_tables` | recompensas por tabela, com ouro e pesos |
| `canon` protegido | verdades imutáveis (mortos continuam mortos) injetadas no prompt |

Nada disso quebra o v1.2: campos ausentes assumem default vazio.

---

## Estrutura

```jsonc
{
  "_meta": { "schema_version": "2.0" },
  "module": { "id": "...", "title": "..." },

  "locations": [
    {
      "id": "gruta-da-cinza",
      "name": "Gruta da Cinza",
      "description": "...",
      // v1.2 aceitava connections: ["vila", "estrada"] (só ids). v2 normaliza
      // strings para { "to": id } e aceita a forma rica:
      "connections": [
        { "to": "vila-drevamor", "via": "trilha da garganta", "distance": "meio dia", "locked": false }
      ],
      "encounter_table": "enc-gruta"
    }
  ],

  "npcs": [
    {
      "id": "garrek", "name": "Garrek", "role": "bandido-chefe",
      "personality": "...", "knowledge": ["sabe onde..."], "speech_style": "...",
      // novos no v2:
      "appearance": "cicatriz cruzando o olho esquerdo, armadura de couro amassada",
      "voice": { "pitch": "-3Hz", "rate": "-10%", "style": "rouca, lenta" },
      "agenda": "vingar o irmão morto na mina — escala se ignorado",
      "portrait_hint": "anão barbudo, olhar duro, fantasy art"
    }
  ],

  "secrets": [
    {
      "id": "verdade-do-cisma", "content": "...", "lie_content": null,
      "known_by": ["fael-drevasson"], "min_trust_level": 3,
      "trigger_condition": {
        "operator": "OR",
        "conditions": [
          { "type": "item_used", "target": "cronica-de-valdrek", "value": null },
          { "type": "npc_trust",  "target": "fael-drevasson",     "value": 3 }
        ]
      }
    }
  ],

  "encounter_tables": [
    {
      "id": "enc-gruta", "location": "gruta-da-cinza",
      "entries": [
        { "description": "2 goblins emboscam", "weight": 3, "enemies": ["goblin", "goblin"] },
        { "description": "um owlbear faminto",  "weight": 1, "enemies": ["owlbear"] }
      ]
    }
  ],

  "fronts": [
    { "id": "horda", "name": "A horda da cinza avança", "segments": 6, "filled": 1,
      "advances_on": "cada noite sem resolver a mina" }
  ],

  "loot_tables": [
    { "id": "loot-gruta", "entries": [
      { "item": "Poção de Cura", "weight": 2, "gold": "2d6" },
      { "item": "Anel rúnico",   "weight": 1 }
    ]}
  ],

  "canon": [
    { "fact": "Valdrek, o fundador, está morto há gerações — lenda, não pessoa viva.", "immutable": true }
  ]

  // factions / items / quests / companions / entities / edges: como no v1.2
}
```

---

## Validação

```python
from engine.schema import validar_modulo
import json

modulo = validar_modulo(json.load(open("meu_modulo.json", encoding="utf-8")))
# → ModuloV2 | levanta pydantic.ValidationError com mensagem clara
#   (ex: location sem id, encounter weight < 1, front segments < 1)
```

A validação é **permissiva por design** (`extra="allow"`): chaves não modeladas
(seções autorais extras, campos do v1.2 não enriquecidos) passam intactas — um
módulo não quebra por trazer uma chave a mais.

---

## Estado da adoção

- **Definição + validação:** prontas (`engine/schema/v2.py`, testes em
  `tests/test_schema_v2.py`).
- **Ingestão nativa do v2** (ler `encounter_tables`/`fronts`/`loot`/`canon` no
  pipeline) e **"Os Filhos de Valdrek" v2**: passo seguinte (B2). Hoje a ingestão
  ainda lê o v1.2 — que continua válido.
