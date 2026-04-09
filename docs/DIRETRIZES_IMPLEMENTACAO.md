# Diretrizes de Implementação — VoxDM
> Criado em 09/04/2026 — Para o Claude Code ler antes de implementar os arquivos listados
> Atualizar esta seção sempre que uma nova diretriz for identificada durante o desenvolvimento

---

## Como usar este arquivo

**Antes de implementar qualquer arquivo listado aqui:** leia a seção correspondente.
**Após implementar:** marque o item como concluído e registre armadilhas encontradas.
**Se uma diretriz virar obsoleta:** não delete — comente com data e motivo.

---

## `context_builder.py` — Fase 3

### Avaliação de trigger_condition em ordem de custo crescente

Avaliar condições baratas primeiro. Se o `AND` falhar cedo, evita I/O desnecessário.

Ordem recomendada:
1. `npc_trust` → Working Memory (RAM) — custo zero
2. `player_action` → Working Memory — custo zero
3. `location_visited` → Working Memory — custo zero
4. `quest_stage` → SQLite — 1 query local
5. `faction_standing` → SQLite — 1 query local
6. `item_used` → SQLite — 1 query local
7. `npc_relationship` → Neo4j — query de grafo
8. Condições compostas AND/OR → avaliar cada filho na mesma ordem acima

```python
# Padrão recomendado — curto-circuito em AND
async def avaliar_condicao(cond: dict, estado: GameState) -> bool:
    if cond["operator"] == "AND":
        for filho in cond["conditions"]:
            if not await _avaliar_filho(filho, estado):
                return False  # falha cedo, não avalia o resto
        return True
```

### on_complete de quests — fila sequencial, nunca gather

Efeitos de `on_complete` podem criar dependências em cadeia:
completar stage A → ativa quest B → muda disposition de NPC → desbloqueia secret.

**Nunca usar `asyncio.gather` para processar efeitos.** Usar fila FIFO e drenar um por um.

```python
# Correto
fila_efeitos: list[dict] = stage["on_complete"].copy()
while fila_efeitos:
    efeito = fila_efeitos.pop(0)
    novos_efeitos = await aplicar_efeito(efeito, estado)
    fila_efeitos.extend(novos_efeitos)  # efeitos podem gerar filhos
```

### honesty é estático — decisão de mentir é dinâmica

O schema guarda `honesty: 0.7`. O context_builder decide se o NPC mente.

Lógica de decisão (implementar aqui, nunca no schema):
```
se trigger_condition satisfeita:
    se trust_level_atual >= secret.min_trust_level:
        se npc.honesty >= HONESTY_THRESHOLD (ex: 0.5):
            revelar secret.content
        senão se npc.political_allegiance protege o secret:
            revelar secret.lie_content (ou "não sei" se lie_content for null)
        senão:
            revelar secret.content  # honesto mesmo com allegiance
    senão:
        não revelar (trust insuficiente)
```

### lie_content nulo não é crash — é narrativa

Se `lie_content` for `null`, o NPC muda de assunto ou nega saber.
Passar `lie_content=None` para o `prompt_builder.py` como instrução de evasão — nunca deixar chegar como string vazia ao LLM.

---

## `neo4j_uploader.py` — Fase 1

### Ler edges diretamente do schema v1.2

O schema v1.2 entrega `edges[]` prontos. **Não inferir relações** a partir de `relationships: {}` nos NPCs — esse campo é legado e será removido na v1.3.

```python
# Correto — lê do top-level edges
for edge in schema.get("edges", []):
    await session.run(
        "MERGE (a {id: $from}) MERGE (b {id: $to}) "
        "CREATE (a)-[r:%s {weight: $weight}]->(b)" % edge["type"].upper(),
        {"from": edge["from"], "to": edge["to"], "weight": edge.get("weight", 0.0)},
    )
```

### Labels separados — nunca nó genérico

Labels válidos no Neo4j para este projeto:
`NPC` | `Companion` | `Entity` | `Location` | `Faction` | `Item` | `Quest` | `Secret`

Nunca criar nó com label genérico `Entity` para tudo — quebra as queries de grafo do context_builder.

---

## `session_writer.py` — Fase 3

### trust_level e faction_standing precisam ser persistidos entre sessões

Ao final de cada sessão, persistir no Qdrant junto com o resumo:
- `trust_level` atual por NPC (dict `npc_id → int`)
- `faction_standing` atual por facção (dict `faction_id → int`)

Na próxima sessão, o context_builder recupera esses valores **antes** de avaliar qualquer `trigger_condition`. Se não persistir, o sistema de secrets reseta entre sessões — bug silencioso e difícil de diagnosticar.

```python
# Estrutura do payload de sessão a salvar no Qdrant
{
    "session_id": "...",
    "resumo": "...",
    "trust_levels": {"fael-valdreksson": 2, "osmund-ferreiro": 1},
    "faction_standings": {"filhos-de-valdrek": 15, "errantes": -5},
    "timestamp": "..."
}
```

---

## `groq_refiner.py` e `groq_client.py` — Fase 1/3

### Centralizar GROQ_MODEL em config.py

Quando implementar qualquer um desses arquivos, remover `_GROQ_MODEL` do `schema_converter.py` e adicionar em `config.py`:

```python
# config.py — Settings
GROQ_MODEL: str = "llama-3.3-70b-versatile"
```

```python
# schema_converter.py — remover a constante local e usar:
model=settings.GROQ_MODEL
```

---

## `prompt_builder.py` — Fase 3

### Recebe estado pré-processado — nunca acessa banco diretamente

O `prompt_builder.py` recebe o contexto já montado pelo `context_builder.py`.
Nunca fazer queries ao Qdrant, Neo4j ou SQLite dentro do prompt_builder — ele é puro: `estado → string`.

### lie_content como instrução de comportamento, não substituição de conteúdo

Quando `lie_content` está presente, passar como instrução de tom ao LLM:
```
[INSTRUÇÃO INTERNA — NÃO REVELAR AO JOGADOR]
Este NPC sabe a verdade mas vai mentir ou esquivar.
Mentira a usar se pressionado: "{lie_content}"
```

---

## `schema_converter.py` — Manutenção

### Ruído de campos vazios do Groq

O Groq frequentemente preenche campos opcionais com `""` ou `[]` mesmo com instrução de omitir.
Se isso gerar ruído no Qdrant, adicionar etapa de limpeza pós-parse antes de `merge_schema_fragments`:

```python
def _limpar_campos_vazios(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _limpar_campos_vazios(v) for k, v in obj.items()
                if v not in ("", [], None)}
    if isinstance(obj, list):
        return [_limpar_campos_vazios(i) for i in obj]
    return obj
```

### Deduplicação de edges com weight conflitante

A deduplicação atual mantém a primeira edge encontrada para o par (from, to, type).
Se dois chunks gerarem weights diferentes para a mesma aresta, o segundo é descartado silenciosamente.
Se isso gerar inconsistência nos grafos, implementar merge por média:

```python
# Estratégia futura: média de weights para edges duplicadas
weight_medio = (edge_existente["weight"] + nova_edge["weight"]) / 2
```

---

## Histórico de atualizações

| Data | Arquivo | Diretriz adicionada |
|---|---|---|
| 09/04/2026 | Todos | Criação inicial — diretrizes do schema v1.2 |
