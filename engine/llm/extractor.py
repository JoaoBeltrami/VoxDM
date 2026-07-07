"""
Extractor estruturado de estado de combate — Frente A mínima (12/06).

Por que existe: o teste ao vivo #3 provou que markers opcionais = features
    dormentes (o LLM nunca emitiu [INIMIGO] e o beat de turno inimigo não rodou
    a sessão inteira). Este módulo inverte a autoridade: após cada turno de
    combate, uma chamada LLM curta (ENTITY_EXTRACTION → 8B/Gemini) lê a narração
    e devolve JSON com inimigos/estados/dano — a engine aplica, com ou sem
    markers. É o primeiro passo dos structured outputs da Frente A.
Dependências: engine.llm.groq_client (facade), engine.llm.tasks.
Armadilha: o JSON vem por prompt ("responda APENAS JSON"), não por
    response_format nativo — parse SEMPRE via extrair_json_defensivo(), que
    tolera prefixo/sufixo de texto. Falha de parse = turno segue sem extração.

Exemplo:
    estado = await extrair_estado_combate(groq, narracao, inimigos_atuais)
    # → {"inimigos": [{"id": "guarda-1", "nome": "Guarda", "estado": "ferido"}],
    #    "dano_ao_jogador": 0}
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import structlog

from config import settings
from engine.llm.tasks import TaskType

log = structlog.get_logger()

# Bloco JSON dentro de texto livre — o LLM às vezes embrulha em prosa/markdown
_RE_BLOCO_JSON = re.compile(r"\{.*\}", re.DOTALL)

_ESTADOS_VALIDOS = {"intacto", "ferido", "grave", "morto"}

_SYSTEM_EXTRACTOR = (
    "Você extrai estado de combate de narração de RPG em PT-BR. Responda "
    "APENAS com JSON válido, sem texto antes ou depois, no formato:\n"
    '{"inimigos": [{"id": "kebab-case", "nome": "Nome", "estado": '
    '"intacto|ferido|grave|morto"}], "dano_ao_jogador": 0}\n'
    "Regras: liste TODOS os inimigos ativos na cena (inclua os já conhecidos, "
    "com estado atualizado). dano_ao_jogador = PV que o PERSONAGEM DO JOGADOR "
    "perdeu NESTA narração (0 se nenhum). NPCs aliados e espectadores NÃO são "
    "inimigos. Se não há combate na narração, devolva inimigos como lista vazia."
)


def extrair_json_defensivo(texto: str) -> dict[str, Any] | None:
    """Parse de JSON tolerante a prefixo/sufixo de prosa. None se irrecuperável."""
    texto = texto.strip()
    try:
        return json.loads(texto)
    except (json.JSONDecodeError, ValueError):
        m = _RE_BLOCO_JSON.search(texto)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            return None


def _sanitizar(bruto: dict[str, Any]) -> dict[str, Any]:
    """Valida e clampa a saída do LLM — nunca confiar em JSON de modelo."""
    inimigos: list[dict[str, str]] = []
    for item in (bruto.get("inimigos") or [])[:8]:  # cap defensivo
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id", "")).strip().lower()
        iid = re.sub(r"[^a-z0-9-]", "-", iid)[:48].strip("-")
        nome = str(item.get("nome", "")).strip()[:40]
        estado = str(item.get("estado", "intacto")).strip().lower()
        if not iid or estado not in _ESTADOS_VALIDOS:
            continue
        inimigos.append({"id": iid, "nome": nome or iid, "estado": estado})
    dano = bruto.get("dano_ao_jogador", 0)
    dano = int(dano) if isinstance(dano, (int, float)) and dano > 0 else 0
    return {"inimigos": inimigos, "dano_ao_jogador": min(dano, 60)}


_SYSTEM_NPC_EXTRACTOR = (
    "Você extrai NPCs de narração de RPG em PT-BR. Responda APENAS com JSON "
    "válido, sem texto antes ou depois, no formato:\n"
    '{"npcs": [{"id": "kebab-case", "nome": "Nome"}]}\n'
    "Liste SÓ personagens NOMEADOS que AGIRAM ou FALARAM DIRETAMENTE nesta "
    "narração e que NÃO estão na lista de conhecidos. NUNCA inclua alguém apenas "
    "CITADO, mencionado de passagem, referido em conversa ou parado no fundo da "
    "cena sem interagir. NÃO inclua: o personagem do jogador, "
    "multidões/figurantes sem nome, monstros/inimigos, **LUGARES/cidades/locais** "
    "(ex: vilas, salões), **DEUSES/divindades/santos** (ex: 'a deusa da magia'), "
    "figurantes ANÔNIMOS ('clérigo desconhecido'), nem nomes apenas CITADOS de "
    "quem NÃO está fisicamente na cena agora. Objetos também não. "
    "APELIDOS/VOCATIVOS que um personagem usa para SE DIRIGIR ao jogador (2ª "
    "pessoa: 'você/te/ti/teu') NÃO são NPCs — ex.: 'Ninguém te convidou, "
    "ladrãozinho' → 'ladrãozinho' é o JOGADOR, não um NPC. id em kebab-case "
    "derivado do nome (ex: 'Velho Mercador' → 'velho-mercador'). Se nenhum NPC "
    "novo nomeado apareceu, devolva npcs como lista vazia."
)


# PT-3 (playtest #7): o 8B virava FRAGMENTO DE NARRAÇÃO em NPC presente —
# "o velho sorri" → id 'velho-sorri', "a figura observa" → 'figura-observa'.
# Esses poluíram o HUD durante um combate de 2 guardas. Sinal forte e SEGURO:
# o último token do id é um verbo de narração conjugado. Nome próprio nunca
# termina em verbo — e isso NÃO mexe em descritor legítimo ('velho-mercador',
# que um teste existente abençoa). Descritor-vira-cenário é decisão de produto.
_VERBOS_NPC_FRAGMENTO = frozenset({
    "sorri", "sorriu", "ri", "riu", "olha", "olhou", "fala", "falou",
    "murmura", "murmurou", "observa", "observou", "geme", "gemeu", "range",
    "rangeu", "suspira", "suspirou", "grita", "gritou", "sussurra", "sussurrou",
    "acena", "acenou", "recua", "recuou", "avanca", "avancou", "hesita",
    "hesitou", "encara", "encarou", "aponta", "apontou", "cospe", "cuspiu",
    "some", "sumiu", "chega", "chegou", "entra", "entrou", "sai", "saiu",
    "espera", "esperou", "responde", "respondeu", "pergunta", "perguntou",
    "assente", "franze", "ergue", "ergueu", "vira", "virou", "treme", "tremeu",
    "balanca", "balancou", "arrasta", "arrastou", "limpa", "limpou",
})


def _transliterar(texto: str) -> str:
    """Acentos → ASCII (ç→c, ã→a) via NFKD + descarte de marcas combinantes."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _kebab_id(texto: str) -> str:
    """Nome/id → kebab-case ASCII estável.

    NPC-DUP-1 (playtest #8): sem transliterar antes do kebab, o mesmo NPC
    'Braço' virava ids diferentes ('bra-o' com ç→dash vs 'brao') conforme a
    grafia do LLM/caminho, duplicando o NPC. Transliterar fixa a grafia.
    """
    return re.sub(r"[^a-z0-9-]", "-", _transliterar(texto).lower())[:48].strip("-")


def _canonico(nid: str) -> str:
    """Chave canônica p/ dedup de NPC: ASCII sem acento, só alfanumérico, minúsculo.

    'gharen-bra-o-de-ferro' e 'gharen-brao-de-ferro' colapsam em
    'gharenbraodeferro' — o mesmo NPC não entra duas vezes (NPC-DUP-1).
    """
    return re.sub(r"[^a-z0-9]", "", _transliterar(nid).lower())


def _chave_dedup(nid: str) -> str:
    """Chave de dedup TOLERANTE A EPÍTETO (NPC-DUP-2, playtest 21/06).

    Quando o Mestre anexa a alcunha do local ao nome — 'Brennan' vira
    'Brennan, dos Sem-Vila' → id 'brennan-sem-vila' — o canônico completo
    ('brennansemvila') não bate com 'brennan' e o NPC duplica na cena. Aqui,
    se o id tem epíteto (multi-token) e o PRIMEIRO nome é substancial (>=4
    chars), a chave é só o primeiro nome — 'brennan-sem-vila' e 'brennan'
    colapsam em 'brennan'. Nome de um token só usa o canônico inteiro.
    """
    tokens = [t for t in re.split(r"[\s-]+", _transliterar(nid).lower()) if t]
    if len(tokens) > 1 and len(tokens[0]) >= 4:
        return re.sub(r"[^a-z0-9]", "", tokens[0])
    return _canonico(nid)


# NPC-DUP-3 (playtest 03/07): tokens ESTRUTURAIS ignorados na chave-conjunto.
# Frozenset LOCAL e curto DE PROPÓSITO — só artigos/preposições/conjunções.
# NÃO reutilizar _PALAVRAS_COMUNS: lá vivem papéis genéricos ("guarda",
# "mercador") que DISTINGUEM NPCs reais — descartá-los colapsaria
# 'guarda-do-portao-norte' com 'guarda-da-torre-sul', que são pessoas distintas.
_TOKENS_ESTRUTURAIS = frozenset({
    "o", "a", "os", "as", "de", "da", "do", "das", "dos",
    "e", "em", "no", "na", "ao", "um", "uma", "que", "com", "sem",
})


def _chave_conjunto(nid: str) -> str:
    """Chave SECUNDÁRIA de dedup: conjunto ORDENADO de tokens não-estruturais.

    NPC-DUP-3 (playtest 03/07, sess-6a851e0fa7f1): o MESMO NPC descritivo entrou
    duas vezes na cena com os tokens reordenados — 'taverna-kaelmund-monge' e
    'monge-da-taverna-kaelmund'. A chave primária (_chave_dedup) usa só o
    primeiro nome (regra do epíteto) e vê 'taverna' vs 'monge' → não colapsa.
    Aqui, descartados os estruturais (da/de/o...), ambos viram
    'kaelmund-monge-taverna' — mesma pessoa, uma entrada só. Retorna "" quando
    não sobra token útil (o caller NÃO deve casar chave vazia com chave vazia).
    """
    tokens = (
        re.sub(r"[^a-z0-9]", "", t)
        for t in re.split(r"[\s-]+", _transliterar(nid).lower())
    )
    uteis = {t for t in tokens if t and t not in _TOKENS_ESTRUTURAIS}
    return "-".join(sorted(uteis))


def _distancia_edicao(a: str, b: str) -> int:
    """Levenshtein simples (DP O(m·n), sem libs) — só pra strings curtas de id."""
    if a == b:
        return 0
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    anterior = list(range(n + 1))
    for i in range(1, m + 1):
        atual = [i] + [0] * n
        for j in range(1, n + 1):
            custo = 0 if a[i - 1] == b[j - 1] else 1
            atual[j] = min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + custo)
        anterior = atual
    return anterior[n]


# NPC-DEDUP-CANONICO-1 (playtest 06/07): 'grimbol'/'grimbold' e 'taberneiro'/
# 'taverneiro' são a MESMA pessoa com erro de grafia do STT/LLM (1 char de
# diferença) — nenhuma chave de dedup exata (canônica/epíteto/conjunto)
# colapsa erro de grafia. Limiar escalado pelo tamanho: ids curtos toleram
# MENOS erro (evita 'kael' colapsar com 'kaia'); piso mínimo de 4 chars —
# abaixo disso, distância 1-2 é ruído estatístico, não sinal de typo.
_DIST_EDICAO_LIMIAR_CURTO = 1
_DIST_EDICAO_LIMIAR_LONGO = 2
_DIST_EDICAO_MIN_LEN = 4


def _variante_proxima(candidato: str, mapa_canon_para_id: dict[str, str]) -> str | None:
    """Candidato é uma variante de GRAFIA (Levenshtein) de um id já conhecido?

    Compara a forma canônica do candidato contra a forma canônica de cada id
    já registrado; retorna o id ORIGINAL batido (não a forma canônica — o
    caller precisa da chave de verdade) ou None se nenhum estiver dentro do
    limiar. Só compara ids de comprimento comparável (corte defensivo barato
    antes do Levenshtein completo).
    """
    cand = _canonico(candidato)
    if len(cand) < _DIST_EDICAO_MIN_LEN:
        return None
    limiar = _DIST_EDICAO_LIMIAR_CURTO if len(cand) < 8 else _DIST_EDICAO_LIMIAR_LONGO
    for existente_canon, existente_id in mapa_canon_para_id.items():
        if len(existente_canon) < _DIST_EDICAO_MIN_LEN:
            continue
        if abs(len(cand) - len(existente_canon)) > limiar:
            continue
        if _distancia_edicao(cand, existente_canon) <= limiar:
            return existente_id
    return None


def _npc_fantasma(nid: str) -> bool:
    """True se o id é fragmento de narração ou figurante, não nome de NPC.

    Dois sinais fortes e seguros (nome próprio não tem nenhum dos dois):
    - último token é VERBO de narração conjugado ("o velho sorri" → 'velho-sorri');
    - último token é NÚMERO ("pessoa-1", "homem-1", "viajante-espalhado-1") —
      figurante enumerado pelo LLM, não NPC nomeado (NPC-CITADO-2, playtest #8).
    Não toca descritor como 'velho-mercador' — isso é decisão de produto.
    """
    tokens = [t for t in nid.split("-") if t]
    if not tokens:
        return True
    if tokens[-1].isdigit():
        return True
    return tokens[-1] in _VERBOS_NPC_FRAGMENTO


# Verbos de AÇÃO em 3ª pessoa — se o nome aparece como SUJEITO seguido de um
# destes, ele AGE na cena → é NPC real, nunca tratado como alcunha do jogador.
_VERBOS_ACAO_3P = _VERBOS_NPC_FRAGMENTO | {
    "disse", "diz", "fez", "faz", "veio", "vem", "ataca", "atacou",
    "saca", "sacou", "puxa", "puxou", "cai", "caiu", "morre", "morreu",
}
_RE_2P = r"voce|vc|te|ti|teu|tua|teus|tuas|contigo|vos|convosco"


def _e_apelido_do_jogador(nome: str, narracao: str) -> bool:
    """True se `nome` é uma alcunha que o Mestre usa pra SE DIRIGIR ao jogador
    (vocativo em 2ª pessoa), não um NPC (NPC-APELIDO, playtest 21/06).

    Ex.: "Ninguém te convidou, ladrãozinho" — 'ladrãozinho' é o jogador.

    Conservador por design: só descarta quando há vocativo-ao-jogador FORTE E o
    nome NUNCA aparece como sujeito de 3ª pessoa agindo. Assim um NPC que age na
    cena ("Aldric recua") é sempre preservado, mesmo que também seja citado.
    """
    nome_ascii = _transliterar(nome).strip().lower()
    # < 3 chars é ruidoso demais pra casar com segurança (evita falso positivo)
    if len(nome_ascii) < 3:
        return False
    narr = _transliterar(narracao).lower()
    nome_re = re.escape(nome_ascii)

    # NPC real: o nome como SUJEITO seguido de verbo de ação 3ª pessoa.
    verbos = "|".join(sorted(_VERBOS_ACAO_3P))
    if re.search(rf"\b{nome_re}\s+(?:{verbos})\b", narr):
        return False

    # Vocativo direto: 2ª pessoa na mesma frase + ", <nome>" (vírgula vocativa).
    # "...te convidou, ladrãozinho" / "Você não é bem-vindo, forasteiro"
    if re.search(rf"\b(?:{_RE_2P})\b[^.!?\n]*,\s*{nome_re}\b", narr):
        return True
    # Vocativo-final em FALA (playtest 05/07: "Muito bem, marinheiro." — o
    # Mestre chamou o JOGADOR de marinheiro e o extractor criou o NPC): vírgula
    # + nome imediatamente antes do fecho de aspas. Exigir o contexto de FALA
    # (aspas) evita dropar aposto de narração ("o capitão, Meridok." fora de
    # aspas segue vivo); a guarda de sujeito-3ª-pessoa acima segue valendo.
    # Guarda de APRESENTAÇÃO (adversarial): "Sou eu, Kael." / "este é meu irmão,
    # Kael." também terminam fala com vírgula+nome — mas são name-reveal de NPC,
    # nunca vocativo ao jogador. Se a janela antes da vírgula tem marcador de
    # apresentação, o nome fica.
    for m in re.finditer(rf"[,!]\s*{nome_re}\s*[.!?…]*\s*[\"”'’]", narr):
        janela = narr[max(0, m.start() - 40) : m.start()]
        if re.search(
            r"\b(?:sou|me chamo|se chama|meu nome|minha filha|meu filho|meu irmao|"
            r"minha irma|este e|esta e|apresento|conheca)\b",
            janela,
        ):
            continue  # apresentação, não vocativo
        return True
    # Vocativo invertido: "<nome>, você ..." — exige o pronome-SUJEITO "você/vc"
    # LOGO após a vírgula. Sem essa âncora, "Gareth, o ferreiro, te entrega a
    # espada" (te = objeto, Gareth = sujeito) virava falso-apelido e dropava um
    # NPC real. "Ladrãozinho, você acha que pode entrar?" segue casando.
    if re.search(rf"(?:^|[.!?\"]\s*){nome_re}\s*,\s*(?:voc[êe]|vc)\b", narr):
        return True
    return False


# Marcadores de SÍMILE — "como um guia silencioso" é comparação, não gente.
# Playtest 05/07 (sess-95a7c47468c5): "o amuleto pulsa... quase como um guia
# silencioso" virou o NPC 'guia-silencioso', que entrou na cena e ficou.
_RE_MARCADOR_SIMILE = (
    r"(?:como|feito|qual|parece(?:ndo)?|lembra(?:ndo)?|igual\s+a)\s+"
    r"(?:um[a]?|o|a)\s+$"
)


def _e_mencao_simile(nome: str, narracao: str) -> bool:
    """True se TODA ocorrência do nome na narração é comparação (símile).

    Conservador: basta UMA menção do nome fora de contexto de símile pra ele
    ser tratado como entidade real. Nome ausente da narração → False (não é
    símile comprovada; outros filtros decidem).
    """
    nome_ascii = _transliterar(nome).strip().lower()
    if len(nome_ascii) < 3:
        return False
    narr = _transliterar(narracao).lower()
    ocorrencias = list(re.finditer(re.escape(nome_ascii), narr))
    if not ocorrencias:
        return False
    for m in ocorrencias:
        janela = narr[max(0, m.start() - 24) : m.start()]
        if not re.search(_RE_MARCADOR_SIMILE, janela):
            return False  # menção "de verdade" — preserva
    return True


# PLAYTEST 24/06: o extractor inundava npcs_presentes com LUGARES (drevamor,
# tharnvik), DEIDADES (mistra, "a deusa da magia") e figurantes anônimos
# ("clerigo-desconhecido") — citados, não presentes. Entupia a cena, inflava o
# prompt (29k!) e diluía a distinção de NPC. Filtro determinístico + cap (backstop).
_TOKENS_NAO_NPC = frozenset({
    "deus", "deusa", "deuses", "deusas", "adeusa", "adeusas",  # adeusa = "a deusa" colado
    "deidade", "deidades", "divindade", "divindades", "panteao",
    "desconhecido", "desconhecida", "desconhecidos", "desconhecidas",
    "alguem", "ninguem", "figura", "vulto", "silhueta", "multidao",
    # NÃO incluir "divino"/"divina": são epítetos de pessoa ("Aldric, o Divino").
    # NPC-LIXO (playtest 27/06): OBJETOS que o 8B registrou como NPC ("barril").
    # Nunca são personagens, mesmo em id de 1 token só.
    "barril", "frasco", "garrafa", "caixa", "bau", "objeto", "amuleto", "tocha",
    # PRONOMES (playtest 29/06): o 8B registrou "ela" como NPC e ela entrou no
    # combate. Pronome NUNCA é nome próprio de NPC.
    "ela", "ele", "eles", "elas", "voce", "voces", "vc", "eu", "mim", "nos",
    "isso", "isto", "aquilo", "lhe", "lhes", "ti", "si",
    # PAPÉIS GENÉRICOS DE COMBATE (colateral 04/07): "oponente" vazou pra
    # npcs_presentes — _npc_fantasma só barra sufixo numérico ("oponente-1"),
    # e o singular sem número passava. São rótulos da RELAÇÃO de combate, nunca
    # nome próprio de NPC (o auto-registro genérico da engine usa "oponente-1"
    # em inimigos_combate, que é outro namespace).
    "oponente", "oponentes", "inimigo", "inimiga", "inimigos", "inimigas",
    "adversario", "adversaria", "adversarios", "adversarias",
    "atacante", "atacantes", "agressor", "agressora", "agressores",
    # CÔMODOS/SUBLOCAIS (playtest 06/07): "sotão" (falado pelo JOGADOR sobre
    # o CÔMODO, não um NPC) virou NPC presente. Mesma família de "taberna"/
    # "porão" — parte do cenário, nunca personagem, mesmo em id de 1 token.
    "sotao", "sotaos", "taberna", "tabernas", "porao", "poroes",
})

# NPC-LIXO (playtest 27/06): o 8B registrava DESCRITORES como NPC presente —
# "velho-mercador", "homem-esguio", "mulher-fragil", "homem-de-capuz",
# "sombra-contorcida", "recem-chegado", "pequena-bruxa", "sussurro-da-esquerda".
# Um NPC REAL tem NOME PRÓPRIO (≥1 token fora desta lista). Um id de 2+ tokens
# 100% comuns é descrição genérica, não personagem. NÃO incluir papéis que são
# NPCs LEGÍTIMOS do módulo (ex: "historiador") — só artigos/descritores/genéricos.
_PALAVRAS_COMUNS = frozenset({
    # estruturais (artigos, preposições)
    "o", "a", "os", "as", "de", "da", "do", "das", "dos", "e", "com", "sem",
    "em", "no", "na", "ao", "um", "uma", "que",
    # genéricos de pessoa
    "homem", "mulher", "velho", "velha", "crianca", "jovem", "rapaz", "moca",
    "moco", "menino", "menina", "pessoa", "gente", "sujeito", "individuo",
    "cara", "criatura", "ser", "coisa", "voz", "bruxa", "bruxo",
    # papéis GENÉRICOS (não específicos do módulo)
    "guarda", "soldado", "mercador", "comerciante", "vendedor", "viajante",
    "forasteiro", "estranho", "estranha", "estrangeiro", "aldeao", "camponos",
    "servo", "criado", "mendigo", "encapuzado", "amigo", "amiga",
    # descritores
    "esguio", "fragil", "pequeno", "pequena", "grande", "alto", "baixo",
    "magro", "gordo", "misterioso", "misteriosa", "recem", "chegado", "chegada",
    "contorcido", "contorcida", "noturno", "noturna", "escuro", "escura",
    "sombrio", "sombria", "conhecido", "conhecida",
    # objetos/fenômenos que aparecem em id composto
    "sussurro", "assobio", "eco", "grito", "murmurio", "sombra", "vulto",
    "figura", "esquerda", "direita", "fundo", "capuz", "capa",
    # meta/OOC (playtest 03/07): "guia-do-jogo" registrado como NPC — não é
    # personagem, é referência ao próprio jogo/regras. Sem entidade real no
    # grafo, gerava timeout de Neo4j TODO turno pro resto da sessão.
    "guia", "jogo",
    # FUNC-3 (playtest 07/07): "meio-elfo" (descritor de RAÇA, sem nome) virou
    # NPC presente numa cena social. Mesma família de "velho"/"mercador" —
    # descrever O QUE alguém é não é o mesmo que ter um NOME. Fica em
    # _PALAVRAS_COMUNS (só rejeita quando TODOS os tokens são genéricos), não em
    # _TOKENS_NAO_NPC (rejeitaria QUALQUER token) — um NPC nomeado com epíteto
    # racial ("Aldric o Elfo Cinzento") tem que sobreviver, só "meio-elfo" puro
    # (sem nome nenhum) é o lixo. "anã" fica de fora de propósito — colide com o
    # nome próprio "Ana" (transliterado sem acento) e um "Ana" real seria
    # descartado se combinado com outro token comum.
    "elfo", "elfa", "anao", "orc", "orcs", "humano", "humana", "meio",
})
_MAX_NPCS_PRESENTES = 8

_LOCATIONS_MODULO: set[str] | None = None


def _locations_canonicas_modulo() -> set[str]:
    """Chaves canônicas (id + nome) de TODAS as locations do módulo, cacheado.

    NPC-LOCAL-2 (playtest 05/07, sess-6e8a5b525bb2): o filtro de "local virou
    NPC" só rejeitava a location_id da CENA ATUAL — uma vila citada de PASSAGEM
    (menção a outro lugar do módulo, não onde o jogador está) ainda virava NPC
    ("kaelmund" registrado em npcs_presentes numa cena em Drevamor). Carrega
    uma vez por processo; falha silenciosa (módulo ausente/corrompido → set
    vazio, filtro cai pro comportamento de antes: só a cena atual).
    """
    global _LOCATIONS_MODULO
    if _LOCATIONS_MODULO is not None:
        return _LOCATIONS_MODULO
    canon: set[str] = set()
    try:
        caminho = Path(settings.DEFAULT_MODULE_PATH)
        if not caminho.is_absolute():
            caminho = Path(__file__).resolve().parents[2] / str(
                settings.DEFAULT_MODULE_PATH
            ).lstrip("./")
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        for elem in dados.get("locations", []):
            if isinstance(elem, dict):
                for campo in ("id", "name"):
                    valor = str(elem.get(campo) or "").strip()
                    if valor:
                        canon.add(_canonico(valor))
    except Exception as e:
        log.warning("extractor_locations_modulo_falhou", erro=str(e)[:100])
    _LOCATIONS_MODULO = canon
    return _LOCATIONS_MODULO


def _e_entidade_invalida(nid: str, location_id: str = "", location_nome: str = "") -> bool:
    """True se o id NÃO deve virar NPC presente: é o LOCAL atual (ou qualquer
    OUTRO local do módulo), uma divindade/conceito, ou um figurante anônimo.
    Conservador — só rejeita sinais claros."""
    canon = _canonico(nid)
    if not canon:
        return True
    if canon == _canonico(location_id) or (location_nome and canon == _canonico(location_nome)):
        return True  # o próprio local virou "NPC"
    if canon in _locations_canonicas_modulo():
        return True  # QUALQUER local do módulo (citado de passagem) — NPC-LOCAL-2
    tokens = {t for t in re.split(r"[\s-]+", _transliterar(nid).lower()) if t}
    if tokens & _TOKENS_NAO_NPC:
        return True
    # Raízes SEGURAS de divindade-conceito — "divindade"/"deidade". NÃO usar "deus"
    # como substring: pegava nomes próprios ("Amadeus", "Deusdedit"). A forma colada
    # "adeusa" já está em _TOKENS_NAO_NPC.
    if any(("divind" in t or "deidad" in t) for t in tokens):
        return True
    # NPC-LIXO (playtest 27/06): id de 2+ tokens, TODOS palavras comuns (sem nome
    # próprio) = descritor genérico, não NPC ("velho-mercador", "homem-de-capuz").
    # Single-token fica de fora (preserva papéis legítimos do módulo: "historiador").
    if len(tokens) >= 2 and tokens <= _PALAVRAS_COMUNS:
        return True
    return False


def _capar_npcs_presentes(wm: Any) -> None:
    """Teto de npcs_presentes com eviction do background mais antigo (preserva os
    APRESENTADOS — NPCs que o jogador conheceu). Backstop pro que escapa do filtro."""
    pres = getattr(wm, "npcs_presentes", None)
    if not pres or len(pres) <= _MAX_NPCS_PRESENTES:
        return
    apres = getattr(getattr(wm, "scene", None), "npcs_apresentados", set()) or set()
    background = [n for n in pres if n not in apres]
    excesso = len(pres) - _MAX_NPCS_PRESENTES
    remover = set(background[:excesso])
    if remover:
        wm.npcs_presentes[:] = [n for n in pres if n not in remover]
        log.info("npcs_presentes_capados", removidos=sorted(remover), restantes=len(wm.npcs_presentes))


def _sanitizar_npcs(bruto: dict[str, Any]) -> list[dict[str, str]]:
    """Valida a saída do extractor de NPC — nunca confiar em JSON de modelo."""
    out: list[dict[str, str]] = []
    vistos: set[str] = set()
    for item in (bruto.get("npcs") or [])[:4]:  # cap defensivo por turno
        if not isinstance(item, dict):
            continue
        nid = _kebab_id(str(item.get("id", "")))
        nome = str(item.get("nome", "")).strip()[:40]
        if not nid or nid in vistos:
            continue
        if _npc_fantasma(nid):
            log.info("npc_fantasma_descartado", id=nid, nome=nome)
            continue
        vistos.add(nid)
        out.append({"id": nid, "nome": nome or nid})
    return out


async def extrair_npcs_cena(
    groq: Any,
    narracao: str,
    npcs_atuais: list[str],
    nome_jogador: str = "",
) -> list[dict[str, str]] | None:
    """Extrai NPCs nomeados NOVOS introduzidos na narração (sem depender de [NPC:]).

    PLAY5-NPC: o Mestre improvisa NPCs e raramente lembra de emitir o marcador
    `[NPC: id|nome]`, então eles nunca viram presença/voz (ficam "fantasmas" no
    chat). A engine lê a narração via chamada barata (ENTITY_EXTRACTION → 8B) e
    devolve os NPCs novos — mesma inversão de autoridade do extractor de combate.

    Retorna lista sanitizada (pode ser vazia) ou None (falha = turno segue).
    """
    if not narracao.strip():
        return None
    conhecidos = ", ".join(npcs_atuais) or "nenhum"
    contexto_jogador = f"O personagem do jogador é {nome_jogador} — NUNCA o liste.\n" if nome_jogador else ""
    try:
        resposta = await groq.completar(
            [
                {"role": "system", "content": _SYSTEM_NPC_EXTRACTOR},
                {
                    "role": "user",
                    "content": (
                        f"{contexto_jogador}"
                        f"NPCs já conhecidos (NÃO repita): {conhecidos}\n\n"
                        f"Narração do turno:\n{narracao[:1500]}"
                    ),
                },
            ],
            temperatura=0.1,
            max_tokens=200,
            task=TaskType.ENTITY_EXTRACTION,
        )
    except Exception as e:
        log.warning("npc_extractor_llm_falhou", erro=str(e)[:120])
        return None
    bruto = extrair_json_defensivo(resposta or "")
    if bruto is None:
        log.warning("npc_extractor_json_invalido", amostra=(resposta or "")[:80])
        return None
    npcs = _sanitizar_npcs(bruto)
    # NPC-APELIDO: descarta alcunhas que o Mestre usa pra dirigir-se ao jogador
    # ("Ninguém te convidou, ladrãozinho") — vocativo de 2ª pessoa, não NPC.
    # NPC-SÍMILE (05/07): descarta comparações ("como um guia silencioso").
    filtrados: list[dict[str, str]] = []
    for n in npcs:
        nome_cand = n.get("nome") or n.get("id", "")
        if _e_apelido_do_jogador(nome_cand, narracao):
            log.info("npc_apelido_jogador_descartado", id=n.get("id"), nome=n.get("nome"))
            continue
        if _e_mencao_simile(nome_cand, narracao):
            log.info("npc_simile_descartado", id=n.get("id"), nome=n.get("nome"))
            continue
        filtrados.append(n)
    return filtrados


def aplicar_npcs_extraidos(
    wm: Any, npcs: list[dict[str, str]], narracao: str = ""
) -> list[str]:
    """Registra NPCs extraídos na cena (presença + apresentado). Idempotente.

    Espelha o efeito do marcador `[NPC: id|nome]` (turn_pipeline step 17b). Pula
    o id do jogador e dedup por DUAS chaves: a primária tolerante a epíteto
    (NPC-DUP-1/2: 'gharen-bra-o-de-ferro' ↔ 'gharen-brao-de-ferro',
    'brennan-sem-vila' ↔ 'brennan') e a secundária por conjunto de tokens
    (NPC-DUP-3: 'taverna-kaelmund-monge' ↔ 'monge-da-taverna-kaelmund').
    Candidato é duplicata se QUALQUER uma bater. Retorna os ids adicionados.

    NPC-IDENTIDADE (05/07): antes de registrar candidato NOVO, checa se ele é
    um NAME-REVEAL de NPC já presente ("O monge abaixa o capuz. 'Sou Kael.'")
    — nesse caso RENOMEIA o presente via registro canônico (retrato preservado)
    em vez de criar um NPC duplicado. `narracao` opcional preserva os
    call-sites antigos (sem narração = sem detecção de reveal).
    """
    from engine.npc.identity import (
        alvo_do_reveal,
        detectar_name_reveal,
        garantir_registro,
        registrar_npc,
        revelar_nome,
    )

    garantir_registro(wm)
    jogador_canon = _chave_dedup(str(getattr(wm, "player_name", "")))
    # NPC-DEDUP-CANONICO-1 (playtest 06/07): o universo de dedup NÃO pode ser
    # só npcs_presentes ATUAL — quando a re-inferência de cena (Neo4j) substitui
    # a lista, um NPC já conhecido (ex: o taverneiro) some de presentes mas
    # continua no registro canônico da SESSÃO INTEIRA (scene.npc_registro) e nos
    # aliases de rename (scene.npc_aliases). Log real: 'grimbold' foi re-registrado
    # do zero em 22:22 porque tinha saído de npcs_presentes — o registro já
    # existia, só não era consultado aqui.
    _universo_ids = (
        set(wm.npcs_presentes)
        | set(getattr(wm.scene, "npc_registro", {}).keys())
        | set(getattr(wm.scene, "npc_aliases", {}).keys())
    )
    presentes_canon = {_chave_dedup(p) for p in _universo_ids}
    # NPC-DUP-3: chave SECUNDÁRIA por conjunto de tokens — pega o mesmo NPC
    # descritivo com tokens reordenados ('taverna-kaelmund-monge' ↔
    # 'monge-da-taverna-kaelmund'). Chave vazia nunca entra no set.
    presentes_conjunto = {c for c in (_chave_conjunto(p) for p in _universo_ids) if c}
    # NPC-DEDUP-CANONICO-1: chave TERCIÁRIA por distância de edição — pega erro
    # de grafia do STT/LLM ('grimbol'/'grimbold', 'taberneiro'/'taverneiro') que
    # nenhuma chave exata acima colapsa.
    mapa_canon_para_id = {_canonico(p): p for p in _universo_ids}
    loc_id = str(getattr(wm, "location_id", "") or "")
    loc_nome = str(getattr(wm, "location_nome", "") or "")
    adicionados: list[str] = []
    for npc in npcs:
        nid = npc.get("id", "")
        canon = _chave_dedup(nid)
        if not nid or not canon or canon == jogador_canon or canon in presentes_canon:
            continue
        conjunto = _chave_conjunto(nid)
        if conjunto and conjunto in presentes_conjunto:
            log.info("npc_dup_tokens_reordenados_descartado", id=nid)
            continue
        variante = _variante_proxima(nid, mapa_canon_para_id)
        if variante:
            log.info("npc_dedup_variante_edicao_descartada", candidato=nid, existente=variante)
            continue
        if _e_entidade_invalida(nid, loc_id, loc_nome):
            log.info("npc_entidade_invalida_descartada", id=nid)
            continue
        nome = (npc.get("nome") or nid.replace("-", " ").title()).strip()[:60]
        # NAME-REVEAL: candidato novo + frase de apresentação + NPC presente
        # ancorado na janela antes dela → renomeia em vez de duplicar.
        if narracao and detectar_name_reveal(narracao, nome):
            alvo = alvo_do_reveal(wm, narracao, nome)
            if alvo:
                novo_id = revelar_nome(wm, alvo, nome)
                presentes_canon.add(_chave_dedup(novo_id))
                mapa_canon_para_id[_canonico(novo_id)] = novo_id
                log.info("npc_name_reveal_renomeado", de=alvo, para=novo_id)
                try:
                    wm.narrative.registrar_cronica(f"🎭 {nome} revelou seu nome")
                except Exception:
                    pass
                continue
            # Padrão presente mas sem âncora única — alvo_do_reveal já loga
            # npc_name_reveal_ambiguo com trecho+contagem de ancorados
            # (NPC-REVEAL-TELEMETRIA-1); nada a fazer aqui além do fallback
            # pra registrar como NPC novo (fluxo de sempre, abaixo).
        wm.npcs_presentes.append(nid)
        wm.scene.npcs_apresentados.add(nid)
        registrar_npc(wm, nid, nome)
        presentes_canon.add(canon)
        if conjunto:
            presentes_conjunto.add(conjunto)
        mapa_canon_para_id[_canonico(nid)] = nid
        adicionados.append(nid)
        # F6 (playtest 24/06): crônica vazia em sessão social — registra o
        # ENCONTRO (evento determinístico, não depende de marcador do Mestre).
        try:
            wm.narrative.registrar_cronica(f"🤝 Conheceu {nome}")
        except Exception:  # narrative ausente em stub de teste — não crítico
            pass
    if adicionados:
        log.info("npcs_extraidos_registrados", ids=adicionados)
    _capar_npcs_presentes(wm)
    return adicionados


_SYSTEM_QUEST_EXTRACTOR = (
    "Você rastreia objetivos/missões de RPG em PT-BR a partir da narração do "
    "Mestre. Responda APENAS com JSON válido, sem texto antes ou depois, no "
    'formato:\n{"novas": [{"id": "kebab-case", "titulo": "Título curto", '
    '"objetivo": "O que o jogador precisa fazer (1 frase)"}], "concluidas": '
    '["id-de-quest"]}\n'
    "Regras: 'novas' = objetivos CONCRETOS e PERSEGUÍVEIS por VÁRIOS turnos que o "
    "Mestre deu, ofereceu ou pediu ao jogador NESTA narração (ex: 'encontrar o "
    "ferreiro sumido', 'investigar as luzes na torre') e que NÃO estão na lista de "
    "missões abertas. NÃO invente missão a partir de conversa fiada, ambientação ou "
    "descrição de cenário. PROIBIDO criar missão para REAÇÕES IMEDIATAS de cena — "
    "responder alguém, abordar/acalmar/cumprimentar um NPC, decidir o próximo passo "
    "do turno NÃO são missões. PROIBIDO criar missão a partir de PEDIDO DE ROLAGEM "
    "ou teste de atributo (rolar um dado, jogar o dado, teste de Constituição, "
    "salvaguarda) nem de AÇÃO FÍSICA MOMENTÂNEA (conseguir se levantar, resistir a "
    "um golpe) — são mecânica do turno, não objetivo. Na dúvida, devolva 'novas' vazia. 'concluidas' = ids "
    "(escolhidos da lista de abertas) que a narração mostra como cumpridos. id em "
    "kebab-case derivado do título. Se nada novo nem concluído, devolva ambas as listas vazias."
)


# QUEST-SPAM-1 (playtest #6): o 8B transformava CADA reação de conversa em
# "missão" — responder-o-homem, abordar-o-homem, acalmar-a-situacao,
# responder-taverneiro. Barra determinística: missão cujo verbo inicial é uma
# reação imediata de fala/aproximação NÃO é objetivo perseguível — descartar.
_VERBOS_REATIVOS = frozenset({
    "responder", "abordar", "acalmar", "falar", "perguntar", "conversar",
    "dizer", "contar", "ouvir", "escutar", "cumprimentar", "saudar",
    "agradecer", "reagir", "decidir", "esperar", "observar", "olhar",
    # QUEST-SPAM (playtest 27/06): movimento e ação física MOMENTÂNEA também
    # viravam "missão" — "subir-ao-andar-superior", "continuar-no-corredor",
    # "acender-fosforo", "hesita-um-segundo", "sentir-que-esta-escondendo-algo".
    # São o passo do turno, não objetivo multi-turno. SÓ verbos inequívocos de
    # 1 turno: NÃO incluir investigar/descobrir/explorar/encontrar (podem ser
    # objetivos reais: "investigar as luzes na torre", "encontrar o ferreiro").
    "subir", "descer", "entrar", "sair", "continuar", "seguir", "voltar",
    "avancar", "atravessar", "recuar", "aproximar", "correr", "caminhar",
    "acender", "pegar", "agarrar", "segurar", "cheirar", "tocar", "apalpar",
    "guardar", "soltar", "largar", "sentir", "hesitar", "hesita", "abrir", "fechar",
})


def _quest_reativa(qid: str, titulo: str) -> bool:
    """True se a quest é uma reação imediata de cena (não um objetivo real).

    Checa o verbo inicial do id (kebab) e do título — se for de fala/aproximação,
    é ruído de turno, não missão perseguível.
    """
    verbo_id = qid.split("-", 1)[0] if qid else ""
    verbo_tit = titulo.strip().lower().split(" ", 1)[0] if titulo else ""
    return verbo_id in _VERBOS_REATIVOS or verbo_tit in _VERBOS_REATIVOS


# PT-2 (playtest #7): além das reações de conversa, o 8B virava PEDIDOS DE
# ROLAGEM do Mestre em "missão" — "Rolar para Ver", "Jogar o Dado",
# "Rolar para ver se sua vontade resiste". Pedido de dado/teste de atributo é
# instrução mecânica do turno, nunca objetivo perseguível. Barra determinística
# por verbo de rolagem (id/título) + notação de dado em qualquer lugar.
# Regex mantido ESTREITO de propósito: só sinais inequívocos de rolagem, pra
# não pegar exploração legítima como "ir à torre para ver se há sobreviventes".
_VERBOS_ROLAGEM = frozenset({"rolar", "role", "rolagem"})

_RE_QUEST_ROLAGEM = re.compile(
    r"\b(rolar|role|rolagem|jog\w*\s+o\s+dado|d4|d6|d8|d10|d12|d20|d100)\b",
    re.IGNORECASE,
)


def _quest_mecanica(qid: str, titulo: str, objetivo: str) -> bool:
    """True se a 'missão' é na verdade um pedido de rolagem/teste de atributo.

    Checa o verbo inicial do id/título (rolar/role/rolagem) e a notação de dado
    no título+objetivo. "Jogar o dado", "Rolar para ver se a Constituição
    aguenta" não são objetivos — são a instrução de rolagem virando ruído.
    """
    verbo_id = qid.split("-", 1)[0] if qid else ""
    verbo_tit = titulo.strip().lower().split(" ", 1)[0] if titulo else ""
    if verbo_id in _VERBOS_ROLAGEM or verbo_tit in _VERBOS_ROLAGEM:
        return True
    return bool(_RE_QUEST_ROLAGEM.search(f"{titulo} {objetivo}"))


def _sanitizar_quests(
    bruto: dict[str, Any], ids_abertos: set[str]
) -> dict[str, Any]:
    """Valida a saída do extractor de quest — nunca confiar em JSON de modelo.

    'novas' rejeita ids já abertos (não duplica) E reações imediatas de conversa
    (QUEST-SPAM-1). 'concluidas' só aceita ids que estão de fato na lista de
    abertas (o LLM não pode concluir o que não existe nem inventar ids).
    """
    novas: list[dict[str, str]] = []
    vistos: set[str] = set()
    for item in (bruto.get("novas") or [])[:3]:  # cap defensivo por turno
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id", "")).strip().lower()
        qid = re.sub(r"[^a-z0-9-]", "-", qid)[:48].strip("-")
        titulo = str(item.get("titulo", "")).strip()[:80]
        objetivo = str(item.get("objetivo", "")).strip()[:200]
        if not qid or qid in vistos or qid in ids_abertos:
            continue
        if _quest_reativa(qid, titulo):
            log.info("quest_reativa_descartada", id=qid, titulo=titulo)
            continue
        if _quest_mecanica(qid, titulo, objetivo):
            log.info("quest_mecanica_descartada", id=qid, titulo=titulo)
            continue
        vistos.add(qid)
        novas.append({"id": qid, "titulo": titulo or qid, "objetivo": objetivo})
    concluidas: list[str] = []
    for cid in (bruto.get("concluidas") or [])[:6]:
        cid_s = re.sub(r"[^a-z0-9-]", "-", str(cid).strip().lower())[:48].strip("-")
        if cid_s and cid_s in ids_abertos and cid_s not in concluidas:
            concluidas.append(cid_s)
    return {"novas": novas, "concluidas": concluidas}


async def extrair_quests_cena(
    groq: Any,
    narracao: str,
    quests_abertas: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Extrai quests improvisadas (novas/concluídas) da narração — sem [Q:].

    PLAY5-QUEST: o sistema de quests valida `[Q:id:stage]` contra o catálogo do
    módulo e rejeita o que o autor não escreveu. Quando o Mestre improvisa uma
    missão, ela nunca vira estado (`quest_stages` vazio) e some no chat. A engine
    lê a narração via chamada barata (ENTITY_EXTRACTION → 8B) e devolve as
    missões novas + as concluídas — mesma inversão de autoridade dos extractors
    de combate e NPC.

    Retorna {"novas": [...], "concluidas": [...]} sanitizado (pode ser vazio)
    ou None (falha = turno segue sem captura).
    """
    if not narracao.strip():
        return None
    ids_abertos = {q.get("id", "") for q in quests_abertas if q.get("id")}
    abertas_txt = "; ".join(
        f"{q.get('id')} ({q.get('titulo', '')})" for q in quests_abertas
    ) or "nenhuma"
    try:
        resposta = await groq.completar(
            [
                {"role": "system", "content": _SYSTEM_QUEST_EXTRACTOR},
                {
                    "role": "user",
                    "content": (
                        f"Missões já abertas (NÃO repita em 'novas'): {abertas_txt}\n\n"
                        f"Narração do turno:\n{narracao[:1500]}"
                    ),
                },
            ],
            temperatura=0.1,
            max_tokens=240,
            task=TaskType.ENTITY_EXTRACTION,
        )
    except Exception as e:
        log.warning("quest_extractor_llm_falhou", erro=str(e)[:120])
        return None
    bruto = extrair_json_defensivo(resposta or "")
    if bruto is None:
        log.warning("quest_extractor_json_invalido", amostra=(resposta or "")[:80])
        return None
    return _sanitizar_quests(bruto, ids_abertos)


def aplicar_quests_extraidas(
    wm: Any, extraido: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Registra quests novas e marca concluídas na WorkingMemory. Idempotente.

    Retorna (ids_adicionados, ids_concluidos). Falha silenciosa de dados ruins
    é absorvida pelo sanitizador — aqui só aplicamos o que já passou.
    """
    adicionadas: list[str] = []
    for q in extraido.get("novas", []):
        if wm.narrative.registrar_quest_improvisada(
            q.get("id", ""), q.get("titulo", ""), q.get("objetivo", "")
        ):
            adicionadas.append(q["id"])
    concluidas: list[str] = []
    for cid in extraido.get("concluidas", []):
        if wm.narrative.concluir_quest_improvisada(cid):
            concluidas.append(cid)
            # XP engine-first (decisão 01/07): quest concluída paga XP
            # determinístico — concluir_quest_improvisada é idempotente (True
            # só na 1ª vez), então a concessão nunca duplica. O level-up
            # decorrente é detectado no próximo aplicar_xp_e_detectar_level_up
            # (o extractor roda pós-turno; modal chega 1 turno depois, ok).
            from engine.progression import XP_QUEST_CONCLUIDA
            wm.xp += XP_QUEST_CONCLUIDA
            log.info("xp_quest_concedido", quest=cid, xp=XP_QUEST_CONCLUIDA, xp_total=wm.xp)
    if adicionadas or concluidas:
        log.info(
            "quests_improvisadas_aplicadas", novas=adicionadas, concluidas=concluidas
        )
    return adicionadas, concluidas


async def extrair_estado_combate(
    groq: Any,
    narracao: str,
    inimigos_atuais: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Extrai inimigos/estados/dano da narração via LLM barato (JSON por prompt).

    Retorna dict sanitizado ou None (falha = jogo segue sem extração).
    """
    if not narracao.strip():
        return None
    atuais = ", ".join(
        f"{iid} ({d.get('nome', iid)}: {d.get('estado', '?')})"
        for iid, d in inimigos_atuais.items()
    ) or "nenhum registrado"
    try:
        resposta = await groq.completar(
            [
                {"role": "system", "content": _SYSTEM_EXTRACTOR},
                {
                    "role": "user",
                    "content": (
                        f"Inimigos já registrados: {atuais}\n\n"
                        f"Narração do turno:\n{narracao[:1500]}"
                    ),
                },
            ],
            temperatura=0.1,
            max_tokens=300,
            task=TaskType.ENTITY_EXTRACTION,
        )
    except Exception as e:
        log.warning("extractor_llm_falhou", erro=str(e)[:120])
        return None
    bruto = extrair_json_defensivo(resposta or "")
    if bruto is None:
        log.warning("extractor_json_invalido", amostra=(resposta or "")[:80])
        return None
    return _sanitizar(bruto)


def aplicar_estado_extraido(wm: Any, estado: dict[str, Any]) -> None:
    """Aplica o resultado do extractor na WorkingMemory (engine-authoritative).

    - Inimigos novos são registrados; conhecidos têm o estado atualizado.
    - O placeholder "oponente-1" (auto-registro F0) é substituído quando o
      extractor identifica inimigos reais.
    - Dano ao jogador SÓ aplica se o turno não teve [DANO] explícito (o caller
      decide passando dano>0 apenas nesse caso).
    """
    inimigos = estado.get("inimigos", [])
    if inimigos:
        reais = [i for i in inimigos if i["id"] != "oponente-1"]
        if reais and "oponente-1" in wm.inimigos_combate:
            wm.remover_inimigo("oponente-1")
        for i in inimigos:
            iid = i["id"]
            if iid not in wm.inimigos_combate:
                wm.registrar_inimigo(iid, i["nome"], i["estado"])
                continue
            # Engine-first: a prosa (8B) NÃO mata um inimigo que a engine rastreia
            # VIVO (hp_max>0 e hp_atual>0) — a morte é autoridade da engine
            # (aplicar_dano_inimigo, HP≤0), igual ao gate do _RE_INIMIGO_MORTO
            # (8acdcd7). Demais estados (ferido/grave/intacto) seguem aplicando.
            _d = wm.inimigos_combate[iid]
            if (
                i["estado"] == "morto"
                and settings.COMBATE_ENGINE_ATIVO
                and int(_d.get("hp_max", 0) or 0) > 0
                and int(_d.get("hp_atual", 0) or 0) > 0
            ):
                log.info("extractor_morte_ignorada_engine_hp", id=iid)
                continue
            wm.atualizar_estado_inimigo(iid, i["estado"])
    dano = int(estado.get("dano_ao_jogador", 0))
    if dano > 0:
        antes = wm.player_hp
        depois = wm.character.aplicar_dano(dano)
        log.info("extractor_dano_aplicado", dano=dano, hp=f"{antes}->{depois}")
