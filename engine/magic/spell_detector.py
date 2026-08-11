"""
Detecta uso de magia no texto do jogador e recupera dados mecânicos do SRD.

Por que existe: o LLM narra magias bonito mas sem esta camada ignora CD saves,
    área de efeito, duração e usos de slot corretos. Este módulo garante que
    os dados do SRD sejam injetados no contexto quando o jogador casta.

Dependências: engine/memory/qdrant_client
Armadilha: busca Qdrant pode falhar (network). Em caso de erro, retorna None
    silenciosamente — o jogo continua sem dados de magia (narrativa pura).

Exemplo:
    dados = await buscar_dados_magia("bola de fogo")
    # → {"nome": "Fireball", "nivel": 3, "cd_save": "DES DC 14", ...}
    # → None se não encontrado
"""

import re
from typing import Any

import structlog

log = structlog.get_logger()

# Detecta verbos de casting no texto do jogador.
# "lanço" e "conjuro" sozinhos são mantidos como triggers de primeira passagem —
# a validação real é feita por extrair_nome_magia + buscar_dados_magia:
# se não extrair um nome de magia válido, nenhum slot é decrementado.
# Os sufixos genéricos ".{1,30}" foram removidos pois não adicionavam valor
# e tornavam o regex verboso sem benefício de filtragem.
# VERBO-DUPLICADO-1 (varredura 10/08): esta lista era escrita à mão, tinha 9
# formas, e era a SEGUNDA lista de verbos de conjuração do projeto — a canônica é
# `casting._VERBOS_CASTING`, com 40+. Duas listas que precisam concordar e não
# concordam é a mesma armadilha do "prompt e código que derivam em silêncio", em
# forma de código: acrescentar `utilizar` numa (o fix do playtest de 10/08) não
# acrescentava na outra, e o caminho de REFORÇO continuava cego pro verbo novo.
# Agora é DERIVADA: a canônica manda, e as formas compostas ("uso a magia") ficam
# aqui porque só existem neste caminho.
_COMPOSTOS: tuple[str, ...] = (
    "uso a magia", "uso o feitiço", "lanço a magia", "lanço o feitiço",
    "conjuro a magia", "conjuro o feitiço",
)


def _padrao_de_casting() -> re.Pattern[str]:
    from engine.magic.casting import _VERBOS_CASTING

    # Compostos primeiro: "uso a magia" tem que vencer o "uso" solto.
    formas = sorted({*_COMPOSTOS, *_VERBOS_CASTING, "lanço", "conjuro"},
                    key=len, reverse=True)
    return re.compile(
        r"\b(" + "|".join(re.escape(f) for f in formas) + r")\b", re.IGNORECASE
    )


_RE_CASTING = _padrao_de_casting()

# Extrai o nome da magia após o verbo de casting.
# Grupo 1 captura o nome: 3–30 chars após o verbo, terminando em pontuação ou fim.
# Evita capturar artigos sós ("lanço o" sem magia) pelo mínimo de 3 chars.
_RE_NOME_MAGIA = re.compile(
    r"\b(?:lanço|conjuro|uso a magia|uso o feitiço|lanço a magia|lanço o feitiço|casto|castando)\s+"
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{2,29}?)(?=[.!,?]|$|\s{2})",
    re.IGNORECASE,
)

# Bug #15: stopwords que cortam o nome da magia.
# "lanço bola de fogo no grupo" → quebra em "no" → "Bola de Fogo".
# CUIDADO: nomes reais de magia contêm "de/do/da" (Bola de Fogo, Mão de Mago),
# então essas preposições NÃO podem entrar. Pegamos só palavras que claramente
# indicam um alvo/contexto fora do nome.
_STOPWORDS_NOME_MAGIA: frozenset[str] = frozenset({
    "para", "em", "contra", "no", "na", "nos", "nas",
    "sobre", "perto", "longe", "rumo", "direção",
    "minha", "meu", "meus", "minhas", "nossa", "nosso",
})


def extrair_nome_magia(texto: str) -> str | None:
    """Extrai o nome da magia declarada pelo jogador.

    Exemplos:
        "Lanço Bola de Fogo no grupo!" → "Bola de Fogo"
        "Conjuro Missil Mágico" → "Missil Mágico"
        "Ataco o goblin" → None

    Returns:
        Nome da magia com capitalização original, ou None se não detectado.
    """
    m = _RE_NOME_MAGIA.search(texto)
    if not m:
        return None
    nome = m.group(1).strip().rstrip(".,!? ")
    # Corta no primeiro stopword — "lanço meu olhar para o orc" → "meu olhar"
    # (que é filtrado depois por ser curto e/ou não bater no SRD).
    palavras = nome.split()
    nome_palavras: list[str] = []
    for p in palavras:
        if p.lower() in _STOPWORDS_NOME_MAGIA:
            break
        nome_palavras.append(p)
    nome = " ".join(nome_palavras).strip()
    # Filtra matches muito curtos (artigos isolados como "o", "a")
    if len(nome) >= 3:
        return nome
    return None


async def buscar_dados_magia(nome: str) -> dict[str, Any] | None:
    """Busca dados mecânicos de uma magia no SRD indexado no Qdrant.

    Estratégia: busca "{nome} spell magic" em voxdm_rules com top_k=1.
    Retorna o chunk mais relevante parseado como dict de campos mecânicos.
    Falha silenciosa em qualquer exception — o jogo segue sem dados.

    Args:
        nome: Nome da magia como detectado no texto do jogador.

    Returns:
        Dict com campos: nome, nivel, escola, alcance, duracao, cd_save,
        dano — ou None se não encontrado / erro de rede.
    """
    try:
        from engine.memory.qdrant_client import QdrantMemoryClient

        cliente = QdrantMemoryClient()
        # Query em inglês aumenta recall no SRD (indexado em EN + PT)
        query = f"{nome} spell magic"
        resultados = await cliente.buscar(
            query=query,
            colecao="voxdm_rules",
            top_k=1,
            score_threshold=0.35,  # limiar mais permissivo — nome em PT pode ter score menor
        )
        if not resultados:
            log.info("spell_nao_encontrada", nome=nome)
            return None

        chunk = resultados[0]
        dados = _extrair_campos_mecanicos(chunk)
        if dados:
            log.info("spell_encontrada", nome=nome, nivel=dados.get("nivel"), score=chunk.get("_score"))
        return dados

    except Exception as exc:
        # Falha silenciosa — rede fora, Qdrant indisponível, etc.
        log.warning("spell_busca_falhou", nome=nome, erro=str(exc)[:120])
        return None


def _extrair_campos_mecanicos(chunk: dict[str, Any]) -> dict[str, Any] | None:
    """Extrai campos mecânicos relevantes de um chunk SRD.

    O chunk pode vir em vários formatos dependendo de como foi indexado.
    Tenta campos diretos primeiro, depois tenta parsear do campo "text".

    Returns:
        Dict normalizado ou None se o chunk não parece ser uma magia.
    """
    dados: dict[str, Any] = {}

    # Campos diretos no payload (indexados pelo rules_loader.py)
    nome_raw = chunk.get("name") or chunk.get("nome") or ""
    dados["nome"] = str(nome_raw).strip() if nome_raw else ""

    nivel_raw = chunk.get("level") or chunk.get("nivel")
    if nivel_raw is not None:
        try:
            dados["nivel"] = int(nivel_raw)
        except (TypeError, ValueError):
            dados["nivel"] = 0
    else:
        dados["nivel"] = 0

    escola_raw = chunk.get("school") or chunk.get("escola") or ""
    dados["escola"] = str(escola_raw).strip() if escola_raw else ""

    alcance_raw = chunk.get("range") or chunk.get("alcance") or ""
    dados["alcance"] = str(alcance_raw).strip() if alcance_raw else ""

    duracao_raw = chunk.get("duration") or chunk.get("duracao") or ""
    dados["duracao"] = str(duracao_raw).strip() if duracao_raw else ""

    # CD Save — pode estar em campos variados conforme o indexador
    cd_raw = chunk.get("dc") or chunk.get("cd_save") or chunk.get("save") or ""
    dados["cd_save"] = str(cd_raw).strip() if cd_raw else ""

    # Dano — pode estar em campo "damage" ou aninhado
    dano_raw = chunk.get("damage") or chunk.get("dano") or ""
    if isinstance(dano_raw, dict):
        # Formato aninhado: {"damage_type": "fire", "damage_at_slot_level": {"3": "8d6"}}
        tipo_dano = dano_raw.get("damage_type", "")
        dice_map = dano_raw.get("damage_at_slot_level") or dano_raw.get("damage_at_character_level", {})
        if dice_map and isinstance(dice_map, dict):
            # Pega o menor nível disponível como baseline
            menor_nivel = min(dice_map.keys(), key=lambda k: int(k) if str(k).isdigit() else 99)
            dados["dano"] = f"{dice_map[menor_nivel]} {tipo_dano}".strip()
        elif tipo_dano:
            dados["dano"] = tipo_dano
        else:
            dados["dano"] = ""
    else:
        dados["dano"] = str(dano_raw).strip() if dano_raw else ""

    # Se não tem nome nem nível, provavelmente não é uma magia
    if not dados["nome"] and dados["nivel"] == 0:
        # Tenta extrair nome do campo "text" como fallback
        texto_chunk = str(chunk.get("text", ""))
        if texto_chunk and len(texto_chunk) > 5:
            # Usa a primeira linha como nome aproximado
            primeira_linha = texto_chunk.split("\n")[0].strip()[:50]
            dados["nome"] = primeira_linha if primeira_linha else "Magia"
        else:
            return None

    return dados


def formatar_bloco_magia(dados: dict[str, Any]) -> str:
    """Formata dados mecânicos de magia para injeção compacta no prompt.

    Produz 1–2 linhas que o LLM pode usar como referência obrigatória ao narrar
    o efeito da magia. Campos ausentes são omitidos silenciosamente.

    Args:
        dados: Dict retornado por buscar_dados_magia() ou _extrair_campos_mecanicos().

    Returns:
        String formatada, ex:
        "⚡ MAGIA: Fireball (nível 3) | Alcance: 150ft | Área: esfera 20ft | Dano: 8d6 fogo | Save: DES DC 14"

    Exemplo:
        dados = {"nome": "Fireball", "nivel": 3, "dano": "8d6 fogo", "cd_save": "DES DC 14"}
        formatar_bloco_magia(dados)
        # → "⚡ MAGIA: Fireball (nível 3) | Dano: 8d6 fogo | Save: DES DC 14"
    """
    partes: list[str] = []

    nome = dados.get("nome", "Magia desconhecida")
    nivel = dados.get("nivel", 0)
    nivel_str = f"nível {nivel}" if nivel and nivel > 0 else "truque"
    partes.append(f"⚡ MAGIA: {nome} ({nivel_str})")

    if dados.get("escola"):
        partes.append(f"Escola: {dados['escola']}")

    if dados.get("alcance"):
        partes.append(f"Alcance: {dados['alcance']}")

    if dados.get("duracao"):
        partes.append(f"Duração: {dados['duracao']}")

    if dados.get("dano"):
        partes.append(f"Dano: {dados['dano']}")

    if dados.get("cd_save"):
        partes.append(f"Save: {dados['cd_save']}")

    return " | ".join(partes)
