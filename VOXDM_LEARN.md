# VOXDM_LEARN.md
> Caderno de aprendizado do VoxDM — cresce junto com o projeto
> Adicionar seção aqui toda vez que um arquivo novo for criado

---

## Como usar

**Criou um arquivo novo?** Cola uma seção aqui antes de fechar a sessão.

**Quer entender um arquivo?** Ctrl+F pelo nome e lê os 4 campos.

**Vai gravar um Short?** Copia o campo "Short 30s" e fala em voz alta.

**Template de seção:**
```
### `caminho/arquivo.py`
**O que faz:** [1 frase]
**Por que essa escolha:** [a decisão técnica — por que não a alternativa óbvia]
**Exemplo:**
# entrada
# saída — o que aconteceu em 1 linha
**Short 30s:** "[texto sem jargão, lê em voz alta em 30 segundos]"
```

---

## Fase 0 — Setup de Ambiente

### `config.py`
**O que faz:** centraliza e valida todas as variáveis de ambiente antes do projeto rodar.

**Por que essa escolha:** se uma API key está faltando, você descobre no boot — não 3 horas depois quando a IA trava no meio de uma sessão. `os.getenv()` espalhado pelo código não dá esse aviso.

**Exemplo:**
```python
# Ruim — falha silencioso
groq_key = os.getenv("GROQ_API_KEY", "")  # vazio e você nem sabe

# Certo — falha ruidoso
from config import settings
groq_key = settings.groq_api_key  # joga erro claro no boot se não tiver
```

**Short 30s:**
> "Config é um contrato com seu próprio código. Antes de qualquer coisa rodar,
> ele checa se todas as chaves estão lá. Se falta uma, o projeto não sobe — e você
> vê exatamente o que está faltando. Melhor descobrir agora do que no meio de uma sessão de RPG."

---

### `Makefile`
**O que faz:** atalhos de terminal para as tarefas mais comuns do projeto.

**Por que essa escolha:** `make test` é mais rápido que lembrar `uv run pytest tests/ -v --asyncio-mode=auto`. E padroniza — qualquer pessoa (ou o Claude Code) sabe como rodar o projeto sem ler documentação.

**Exemplo:**
```bash
make test      # roda todos os testes
make lint      # verifica formatação
make run       # sobe o servidor
```

**Short 30s:**
> "Makefile é uma lista de atalhos pra linha de comando. Em vez de lembrar
> comandos longos toda vez, você digita make test e pronto.
> É o equivalente de salvar um contato no celular — você não decora o número,
> só sabe o nome."

---

## Fase 1 — Pipeline de Ingestão

### `engine/ingestion/pdf_reader.py`
**O que faz:** abre o PDF do módulo de RPG e extrai o texto página por página.

**Por que essa escolha:** PyMuPDF é mais rápido que pypdf e lida melhor com PDFs com formatação complexa (tabelas, colunas) — que é exatamente o que livros de RPG têm.

**Exemplo:**
```python
reader = PDFReader("modulo_teste/aventura.pdf")
pages = await reader.extract()
# pages = [{"page": 1, "text": "Capítulo 1: A Vila..."}, ...]
```

**Short 30s:**
> "O primeiro passo do VoxDM é ler o livro de RPG.
> Esse arquivo abre o PDF e extrai o texto de cada página.
> É simples — mas é a fundação. Sem isso, a IA não tem nada pra aprender."

---

### `engine/ingestion/gemini_converter.py`
**O que faz:** recebe texto bruto do PDF e converte para o schema estruturado do VoxDM.

**Por que essa escolha:** Gemini 2.0 Flash tem 1 milhão de tokens de contexto no free tier — cabe o livro inteiro numa chamada só. GPT-4 cobraria caro e ainda teria que dividir em pedaços.

**Exemplo:**
```python
converter = GeminiConverter()
schema = await converter.convert(raw_text)
# schema = {"locations": [...], "npcs": [...], "events": [...]}
```

**Short 30s:**
> "Texto bruto de livro não é útil pra uma IA. É como tentar cozinhar com
> ingredientes que nem foram lavados. O Gemini pega esse texto e organiza —
> 'isso aqui é um personagem, isso aqui é um lugar, isso aqui é um evento'.
> A IA passa a entender a estrutura, não só as palavras."

---

### `engine/ingestion/chunker.py`
**O que faz:** divide o conteúdo estruturado em pedaços semânticos para indexar no Qdrant.

**Por que essa escolha:** chunk por parágrafo perde contexto. Chunk por número fixo de tokens corta no meio de uma ideia. Chunking semântico agrupa pelo que *significa* junto — uma cena, um NPC, um local.

**Exemplo:**
```python
chunker = SemanticChunker()
chunks = await chunker.split(schema)
# chunks = [{"id": "...", "text": "Strahd von Zarovich é...", "type": "npc"}]
```

**Short 30s:**
> "Imagina que você vai estudar um livro. Você não sublinha letra por letra —
> você sublinha por ideia. É isso que o chunker faz. Divide o livro em
> pedaços que fazem sentido juntos, pra quando a IA precisar buscar algo,
> ela encontre uma ideia completa, não metade de uma frase."

---

### `engine/ingestion/embedder.py`
**O que faz:** converte cada chunk de texto em um vetor numérico (embedding).

**Por que essa escolha:** sentence-transformers `all-MiniLM-L6-v2` roda local, é rápido, e é bom o suficiente para português e inglês. Não precisa de API key e não tem custo por uso.

**Exemplo:**
```python
embedder = Embedder()
vectors = await embedder.encode(chunks)
# "Strahd está no castelo" → [0.23, -0.11, 0.87, ...] (384 números)
```

**Short 30s:**
> "Texto não tem matemática. Número tem. O embedder transforma cada pedaço de texto
> num conjunto de 384 números — a impressão digital semântica daquele texto.
> Textos com significado parecido têm números parecidos. É isso que permite
> a IA encontrar 'onde está Strahd' mesmo que você pergunte de formas diferentes."

---

### `engine/ingestion/qdrant_uploader.py`
**O que faz:** salva os vetores e os textos originais no Qdrant Cloud.

**Por que essa escolha:** Qdrant é especializado em busca vetorial — é o que faz a busca por similaridade semântica ser rápida. SQLite guardaria o texto, mas não saberia buscar por significado.

**Exemplo:**
```python
uploader = QdrantUploader()
await uploader.upload(vectors, chunks)
# Depois: query("onde está Strahd?") → retorna chunks mais relevantes
```

**Short 30s:**
> "O Qdrant é a memória de longo prazo do VoxDM. Depois que os textos viram números,
> precisam de um lugar pra morar — e esse lugar precisa saber buscar por significado,
> não só por palavra exata. É como a diferença entre buscar no Google e buscar num
> arquivo de texto: o Google entende o que você quer, não só o que você escreveu."

---

### `engine/ingestion/neo4j_uploader.py`
**O que faz:** salva as relações entre entidades no Neo4j — quem conhece quem, quem odeia quem.

**Por que essa escolha:** o Qdrant sabe *o que* existe. O Neo4j sabe *como as coisas se conectam*. São problemas diferentes. "Strahd odeia Ismark" não é uma busca por similaridade — é uma relação que precisa ser atravessada.

**Exemplo:**
```python
uploader = Neo4jUploader()
await uploader.upload(schema["relationships"])
# Grafo: Strahd --[ODEIA]--> Ismark --[IRMÃO_DE]--> Ireena
```

**Short 30s:**
> "Banco vetorial guarda o que existe. Banco de grafos guarda como as coisas se conectam.
> Quando o VoxDM precisa saber que Strahd odeia Ismark, que é irmão da Ireena,
> que é a pessoa que Strahd quer capturar — essa cadeia de relações está no Neo4j.
> É o mapa de relacionamentos do seu módulo de RPG."

---

## Fase 2 — Pipeline de Voz

*(seções adicionadas quando Fase 2 for implementada)*

---

## Fase 3 — O Mestre de Verdade

*(seções adicionadas quando Fase 3 for implementada)*

---

## Fase 4 — Interface Web

*(seções adicionadas quando Fase 4 for implementada)*

---

## Progresso

| Arquivo | Data | Fase | Documentado |
|---|---|---|---|
| config.py | — | 0 | exemplo |
| Makefile | — | 0 | exemplo |
| pdf_reader.py | — | 1 | exemplo |
| gemini_converter.py | — | 1 | exemplo |
| chunker.py | — | 1 | exemplo |
| embedder.py | | 1 | exemplo |
| qdrant_uploader.py | — | 1 | exemplo |
| neo4j_uploader.py | — | 1 | exemplo |
