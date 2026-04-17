# VoxDM Schema v1.2
> Especificação do formato de módulo para a engine VoxDM
> Versão 1.2 — abril 2026

---

## O que é

O VoxDM Schema é o formato JSON que descreve um módulo de RPG de mesa para ser ingerido pela engine VoxDM. A engine processa esse JSON para:

1. Gerar embeddings semânticos dos textos e subir ao Qdrant (busca por similaridade)
2. Criar nós e arestas no Neo4j (busca por grafo de relações)
3. Montar contexto para o LLM (Mestre de jogo) em tempo real durante a sessão

O schema é intencionalmente simples e legível por humanos. O objetivo é que um autor de módulo consiga escrever ou adaptar um módulo à mão sem ferramentas especiais.

---

## Convenções

- **IDs:** sempre em kebab-case — `bjorn-tharnsson`, `gargantas-vulcanicas`
- **Campos opcionais:** marcados com `(opcional)` — podem ser omitidos sem quebrar a pipeline
- **`_ext`:** campos de extensão livres — não são processados pela engine, mas ficam disponíveis para uso futuro
- **Idioma do conteúdo:** qualquer idioma funciona; o campo `module.language` declara o idioma principal

---

## Estrutura top-level

```json
{
  "_meta": { ... },
  "module": { ... },
  "locations": [ ... ],
  "npcs": [ ... ],
  "companions": [ ... ],
  "entities": [ ... ],
  "factions": [ ... ],
  "items": [ ... ],
  "quests": [ ... ],
  "secrets": [ ... ],
  "rules_references": [ ... ],
  "edges": [ ... ]
}
```

---

## `_meta`

Metadados da conversão. Preenchido automaticamente pelo `schema_converter.py` — não precisa escrever à mão.

```json
{
  "_meta": {
    "schema_version": "1.2",
    "converted_by": "Claude Opus 4.6",
    "conversion_date": "2026-04-09",
    "source_document": "Nome do documento original",
    "migration_notes": [
      "v1.0 → v1.2: companions separados de npcs"
    ]
  }
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim | Versão do schema — deve ser `"1.2"` |
| `converted_by` | string | não | Ferramenta ou pessoa que criou o arquivo |
| `conversion_date` | string | não | Data no formato `YYYY-MM-DD` |
| `source_document` | string | não | Nome do documento original (para rastreabilidade) |
| `migration_notes` | array | não | Registro de mudanças entre versões |

---

## `module`

Identificação e metadados do módulo.

```json
{
  "module": {
    "id": "os-filhos-de-valdrek",
    "name": "Os Filhos de Valdrek",
    "system": "D&D 5e",
    "language": "pt-BR",
    "_ext": {
      "level": 3,
      "tone": "dark fantasy",
      "setting": "wasteland bárbara",
      "player_count": "solo + 1 NPC companheiro",
      "language_support": ["pt-BR", "en"]
    }
  }
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `id` | string | **sim** | Identificador único, kebab-case |
| `name` | string | **sim** | Nome legível do módulo |
| `system` | string | não | Sistema de regras (ex: `"D&D 5e"`, `"Pathfinder 2e"`) |
| `language` | string | não | Idioma principal do conteúdo (BCP 47: `"pt-BR"`, `"en"`) |
| `_ext` | object | não | Campos de extensão livres |

---

## `locations`

Locais do módulo. O campo `npcs` lista IDs de NPCs presentes neste local por padrão — não é uma cópia dos dados do NPC.

```json
{
  "id": "tharnvik",
  "name": "Tharnvik",
  "description": "Vila do Norte — construída nas bordas de gargantas vulcânicas...",
  "connections": ["wasteland", "gargantas-vulcanicas"],
  "npcs": ["bjorn-tharnsson", "runa-tharnsdottir"],
  "atmosphere": "Calor constante. Cinza no ar. Tudo é pedra escura e fogo azul..."
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `id` | string | **sim** | Identificador único, kebab-case |
| `name` | string | **sim** | Nome legível |
| `description` | string | **sim** | Descrição do local para o contexto do LLM |
| `connections` | array de IDs | não | IDs de outros locais conectados |
| `npcs` | array de IDs | não | IDs de NPCs que ficam neste local por padrão |
| `atmosphere` | string | não | Texto de ambientação para narração do mestre |

---

## `npcs`

Personagens com quem o jogador interage diretamente — têm diálogo, motivações, segredos e estado emocional rastreado.

**Separados de `companions`** (que acompanham o jogador) e de `entities` (criaturas sem personalidade complexa).

```json
{
  "id": "bjorn-tharnsson",
  "name": "Bjorn Tharnsson",
  "role": "lider-de-tharnvik",
  "personality": "Calculista por trás da brutalidade aparente...",
  "knowledge": [
    "Sabe que Vyrmathax existe",
    "NÃO sabe que Runa troca cartas com Kaëlmund"
  ],
  "speech_style": "Direto, frases curtas. Nunca pede — declara.",
  "honesty": 0.4,
  "disposition": "hostile",
  "political_allegiance": "os-tharn",
  "_ext": {
    "race": "humano",
    "age": 44,
    "appearance": "Alto, largo, cicatrizes visíveis...",
    "motivation": "Tomar os artefatos de Drevamor."
  }
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `id` | string | **sim** | Identificador único, kebab-case |
| `name` | string | **sim** | Nome legível |
| `role` | string | não | Papel no módulo (kebab-case: `"lider-de-tharnvik"`) |
| `personality` | string | não | Descrição de personalidade para o LLM |
| `knowledge` | array de strings | não | O que este NPC sabe (e o que NÃO sabe) |
| `speech_style` | string | não | Como o NPC fala — usado no prompt de voz |
| `honesty` | float 0.0–1.0 | não | Traço estático: 0 = sempre mente, 1 = sempre verdade |
| `disposition` | string | não | Estado inicial: `friendly`, `neutral`, `hostile`, `fearful`, `indifferent` |
| `political_allegiance` | string (ID) | não | ID da facção à qual este NPC pertence |
| `_ext` | object | não | Campos de extensão: raça, idade, aparência, motivação |

---

## `companions`

Personagens que acompanham o jogador durante a aventura. Têm os mesmos campos de NPC, mais o campo `companion_for`.

```json
{
  "id": "soren-tharnsson",
  "name": "Soren Tharnsson",
  "companion_for": "tharnvik",
  "role": "guerreiro-herdeiro-tharnvik",
  "personality": "Impetuoso, leal, desesperado para provar que merece a liderança...",
  "knowledge": [ ... ],
  "speech_style": "Entusiasmado demais. Fala rápido.",
  "honesty": 0.8,
  "disposition": "friendly",
  "political_allegiance": "os-tharn"
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `companion_for` | string | não | ID da facção/vila de origem do companion |
| *(demais campos)* | — | — | Idênticos aos de `npcs` |

---

## `entities`

Criaturas, forças da natureza ou entidades sem personalidade de NPC completa. Não têm `honesty`, `disposition` nem `political_allegiance`.

```json
{
  "id": "vyrmathax",
  "name": "Vyrmathax",
  "type": "criatura",
  "description": "Dragoa vermelha adulta. Não é aliada nem inimiga — é uma força da natureza com memória.",
  "abilities": [
    "Adult Red Dragon — CR 17",
    "Memória de três gerações"
  ]
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `id` | string | **sim** | Identificador único, kebab-case |
| `name` | string | **sim** | Nome legível |
| `type` | string | não | `"criatura"`, `"artefato"`, `"força"`, etc. |
| `description` | string | não | Descrição para o LLM |
| `abilities` | array de strings | não | Habilidades especiais |

---

## `factions`

Grupos políticos ou sociais. Controlam o estado de reputação do jogador com cada grupo.

```json
{
  "id": "os-tharn",
  "name": "Os Tharn — Facção de Tharnvik",
  "goal": "Supremacia militar. Tomar os artefatos de Drevamor.",
  "members": ["bjorn-tharnsson", "runa-tharnsdottir", "soren-tharnsson"],
  "reputation_thresholds": {
    "hostile": -20,
    "neutral": 0,
    "friendly": 20,
    "allied": 50
  }
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `id` | string | **sim** | Identificador único, kebab-case |
| `name` | string | **sim** | Nome legível |
| `goal` | string | não | Objetivo da facção |
| `members` | array de IDs | não | IDs dos membros (NPCs ou companions) |
| `reputation_thresholds` | object | não | Pontuação de reputação para cada nível de standing |

---

## `items`

Itens mágicos, artefatos ou objetos narrativamente importantes.

```json
{
  "id": "cajado-de-valdrek",
  "name": "Cajado de Valdrek",
  "description": "Gera um globo de força translúcido. 10 charges, recarrega 1d6+4 ao amanhecer.",
  "properties": ["requires_attunement", "staff", "10_charges"],
  "owner": "aldric-drevasson",
  "unlock_conditions": []
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `id` | string | **sim** | Identificador único, kebab-case |
| `name` | string | **sim** | Nome legível |
| `description` | string | não | Descrição completa do item |
| `properties` | array de strings | não | Propriedades mecânicas |
| `owner` | string (ID) | não | ID do NPC que possui o item inicialmente |
| `unlock_conditions` | array | não | Condições para o item se tornar disponível |

---

## `quests`

Missões e arcos narrativos. Cada quest tem `stages` com efeitos encadeados via `on_complete`.

```json
{
  "id": "a-verdade-enterrada",
  "name": "Quest 3 — A Verdade Enterrada",
  "description": "Fael revela ao jogador que a Crônica contém algo que muda tudo.",
  "stages": [
    {
      "id": "encontrar-fael",
      "description": "Encontrar Fael em Drevamor disposto a falar.",
      "on_complete": [
        { "type": "unlock_secret", "target": "verdade-do-cisma" }
      ]
    }
  ]
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `id` | string | **sim** | Identificador único, kebab-case |
| `name` | string | **sim** | Nome legível |
| `description` | string | não | Descrição geral da quest |
| `stages` | array | não | Fases da quest, em ordem |
| `stages[].id` | string | não | ID da fase, kebab-case |
| `stages[].description` | string | não | O que acontece nesta fase |
| `stages[].on_complete` | array | não | Efeitos ao completar a fase (desbloqueios, mudanças de estado) |

---

## `secrets`

Informações que o jogador só descobre sob condições específicas. O campo `lie_content` define o que o NPC diz quando mente (se `honesty` < threshold).

```json
{
  "id": "verdade-do-cisma",
  "content": "Valdrek não morreu em combate. Kaëla o envenenou...",
  "lie_content": null,
  "known_by": ["fael-drevasson"],
  "min_trust_level": 3,
  "trigger_condition": {
    "operator": "OR",
    "conditions": [
      { "type": "item_used", "target": "cronica-de-valdrek", "value": null },
      { "type": "npc_trust", "target": "fael-drevasson", "value": 3 }
    ]
  }
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `id` | string | **sim** | Identificador único, kebab-case |
| `content` | string | **sim** | A verdade que o jogador pode descobrir |
| `lie_content` | string ou null | não | O que o NPC diz se decidir mentir. `null` = o NPC não comenta |
| `known_by` | array de IDs | não | IDs dos NPCs que sabem este segredo |
| `min_trust_level` | int 0–3 | não | Nível mínimo de confiança para revelar. `0` = sempre revela; `3` = só revela com confiança máxima |
| `trigger_condition` | object | não | Condição estruturada (ver abaixo) |

### `trigger_condition`

```json
{
  "operator": "OR",
  "conditions": [
    { "type": "item_used",  "target": "id-do-item", "value": null },
    { "type": "npc_trust",  "target": "id-do-npc",  "value": 3 },
    { "type": "quest_complete", "target": "id-da-quest", "value": null },
    { "type": "location",   "target": "id-do-local", "value": null }
  ]
}
```

| Tipo de condição | `target` | `value` | Significado |
|---|---|---|---|
| `item_used` | ID do item | null | Jogador usou ou apresentou o item |
| `npc_trust` | ID do NPC | int 0–3 | Nível de confiança com esse NPC atingido |
| `quest_complete` | ID da quest | null | Quest concluída |
| `location` | ID do local | null | Jogador está neste local |

`operator` pode ser `"OR"` (basta uma condição) ou `"AND"` (todas as condições).

---

## `rules_references`

Referências a blocos de estatísticas do SRD 5e ou sistemas externos. Permite que a engine consulte regras sem incluir texto licenciado no módulo.

```json
{
  "id": "carnicais-da-cinza",
  "name": "Carniçais da Cinza",
  "stat_block_base": "Ghoul",
  "cr": 1,
  "count_encounter": "2-3",
  "reflavor": "Pele cinzenta, cheiro de cinza queimada. Reanimados por energia residual.",
  "notes": "Encontro de abertura — testar pipeline de combate"
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | string | Identificador, kebab-case |
| `name` | string | Nome no módulo |
| `stat_block_base` | string | Nome do stat block no SRD (ex: `"Ghoul"`, `"Hill Giant"`) |
| `cr` | number | Challenge Rating |
| `count` / `count_encounter` | string/number | Quantidade esperada no encontro |
| `reflavor` | string | Descrição visual customizada |
| `notes` | string | Notas do autor |

---

## `edges`

Todas as relações entre entidades do módulo. Ficam no top-level (não dentro de cada entidade) para facilitar a ingestão no Neo4j sem joins.

```json
{ "from": "bjorn-tharnsson", "to": "runa-tharnsdottir", "type": "ally",         "weight": 0.6 },
{ "from": "bjorn-tharnsson", "to": "soren-tharnsson",   "type": "mentor",       "weight": 0.5 },
{ "from": "soren-tharnsson", "to": "dalla-drevadottir", "type": "rival",        "weight": 0.3 },
{ "from": "bjorn-tharnsson", "to": "os-tharn",          "type": "member_of",    "weight": 0.9 },
{ "from": "aldric-drevasson","to": "cajado-de-valdrek",  "type": "owns",         "weight": 1.0 },
{ "from": "bjorn-tharnsson", "to": "tharnvik",           "type": "located_in",   "weight": 1.0 },
{ "from": "maren-drevadottir","to": "fael-drevasson",   "type": "guard",        "weight": 0.7 },
{ "from": "fael-drevasson",  "to": "verdade-do-cisma",  "type": "knows_secret", "weight": 1.0 }
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `from` | string (ID) | **sim** | ID da entidade de origem |
| `to` | string (ID) | **sim** | ID da entidade de destino |
| `type` | string | **sim** | Tipo da relação (ver tabela abaixo) |
| `weight` | float 0.0–1.0 | não | Intensidade da relação. Padrão: `1.0` |

### Tipos de aresta definidos na v1.2

| Tipo | Descrição |
|---|---|
| `ally` | Aliança — podem cooperar ativamente |
| `rival` | Rivalidade — tensão, competição, mas não necessariamente hostilidade aberta |
| `mentor` | Relação de ensino ou tutela |
| `member_of` | Pertence a uma facção |
| `located_in` | Reside ou opera habitualmente num local |
| `owns` | Possui um item |
| `guard` | Protege ou defende outra entidade |
| `knows_secret` | Conhece um segredo |

Novos tipos podem ser adicionados livremente — a engine lida com qualquer string como tipo de aresta.

---

## Validação

O arquivo `ingestor/parser.py` valida o schema antes da ingestão. Regras principais:

- Todo elemento em `locations`, `npcs`, `companions`, `entities`, `factions`, `items`, `quests`, `secrets` deve ter `id` em kebab-case
- Todo elemento exceto `secrets` deve ter `name`
- Todo edge deve ter `from`, `to` e `type` não-vazios
- `honesty` deve ser float entre 0.0 e 1.0 (se presente)
- `disposition` deve ser um de: `friendly`, `neutral`, `hostile`, `fearful`, `indifferent` (se presente)

Para validar manualmente:
```bash
uv run main.py --modulo seu_modulo.json --dry-run
```

---

## Histórico de versões

| Versão | Data | Mudanças principais |
|---|---|---|
| **1.2** | abril 2026 | companions e entities separados de npcs; `honesty`, `disposition`, `political_allegiance`; secrets com `lie_content` e `trigger_condition` composto; `on_complete` em quest stages; `reputation_thresholds` em factions; `owner` e `unlock_conditions` em items; `edges[]` top-level |
| 1.1 | março 2026 | Adição de `edges[]` internos por entidade (substituído pelo top-level na 1.2) |
| 1.0 | março 2026 | Versão inicial — NPCs, locations, quests, items básicos |
