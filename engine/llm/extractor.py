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
from typing import Any

import structlog

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
    # Vocativo invertido: "<nome>, você ..." — exige o pronome-SUJEITO "você/vc"
    # LOGO após a vírgula. Sem essa âncora, "Gareth, o ferreiro, te entrega a
    # espada" (te = objeto, Gareth = sujeito) virava falso-apelido e dropava um
    # NPC real. "Ladrãozinho, você acha que pode entrar?" segue casando.
    if re.search(rf"(?:^|[.!?\"]\s*){nome_re}\s*,\s*(?:voc[êe]|vc)\b", narr):
        return True
    return False


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
})
_MAX_NPCS_PRESENTES = 8


def _e_entidade_invalida(nid: str, location_id: str = "", location_nome: str = "") -> bool:
    """True se o id NÃO deve virar NPC presente: é o LOCAL atual, uma divindade/
    conceito, ou um figurante anônimo. Conservador — só rejeita sinais claros."""
    canon = _canonico(nid)
    if not canon:
        return True
    if canon == _canonico(location_id) or (location_nome and canon == _canonico(location_nome)):
        return True  # o próprio local virou "NPC"
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
    filtrados: list[dict[str, str]] = []
    for n in npcs:
        if _e_apelido_do_jogador(n.get("nome") or n.get("id", ""), narracao):
            log.info("npc_apelido_jogador_descartado", id=n.get("id"), nome=n.get("nome"))
            continue
        filtrados.append(n)
    return filtrados


def aplicar_npcs_extraidos(wm: Any, npcs: list[dict[str, str]]) -> list[str]:
    """Registra NPCs extraídos na cena (presença + apresentado). Idempotente.

    Espelha o efeito do marcador `[NPC: id|nome]` (turn_pipeline step 17b). Pula
    o id do jogador e dedup por CHAVE CANÔNICA (NPC-DUP-1): 'gharen-bra-o-de-ferro'
    e 'gharen-brao-de-ferro' não entram os dois. Retorna os ids adicionados.
    """
    jogador_canon = _chave_dedup(str(getattr(wm, "player_name", "")))
    presentes_canon = {_chave_dedup(p) for p in wm.npcs_presentes}
    loc_id = str(getattr(wm, "location_id", "") or "")
    loc_nome = str(getattr(wm, "location_nome", "") or "")
    adicionados: list[str] = []
    for npc in npcs:
        nid = npc.get("id", "")
        canon = _chave_dedup(nid)
        if not nid or not canon or canon == jogador_canon or canon in presentes_canon:
            continue
        if _e_entidade_invalida(nid, loc_id, loc_nome):
            log.info("npc_entidade_invalida_descartada", id=nid)
            continue
        wm.npcs_presentes.append(nid)
        wm.scene.npcs_apresentados.add(nid)
        presentes_canon.add(canon)
        adicionados.append(nid)
        # F6 (playtest 24/06): crônica vazia em sessão social — registra o
        # ENCONTRO (evento determinístico, não depende de marcador do Mestre).
        nome = (npc.get("nome") or nid.replace("-", " ").title()).strip()[:60]
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
            if i["id"] in wm.inimigos_combate:
                wm.atualizar_estado_inimigo(i["id"], i["estado"])
            else:
                wm.registrar_inimigo(i["id"], i["nome"], i["estado"])
    dano = int(estado.get("dano_ao_jogador", 0))
    if dano > 0:
        antes = wm.player_hp
        depois = wm.character.aplicar_dano(dano)
        log.info("extractor_dano_aplicado", dano=dano, hp=f"{antes}->{depois}")
