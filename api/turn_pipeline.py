"""
Pipeline pós-turno compartilhado entre REST `/turn` e WebSocket.

Por que existe: a lógica de "o que acontece depois que o LLM termina de falar"
    estava duplicada apenas no `api/websocket.py`. O endpoint REST `/session/{id}/turn`
    pulava trust_detector, sincronização de inimigos, avanço de rodada e detecção
    de fim de combate — causando divergência de estado entre os dois caminhos.
    Este módulo centraliza tudo em uma única função idempotente.

Dependências: engine/memory/working_memory, engine/memory/trust_detector,
    e os regexes de combate de api/websocket (re-exportados).

Armadilha: a ORDEM das operações importa.
    - Sync de inimigos DEVE rodar antes de detectar fim de combate, senão a
      última morte do combate é descartada (sair_combate limpa inimigos_combate).
    - Auto-registro de consequências também precisa rodar antes de sair_combate
      pelo mesmo motivo.

Exemplo:
    from api.turn_pipeline import aplicar_pos_turno
    mudancas_trust = aplicar_pos_turno(working_mem, texto_jogador, resposta_llm)
    # working_mem agora reflete: inimigos atualizados, trust ajustado,
    # rodada avançada, fim de combate detectado se aplicável.
"""

import re
import unicodedata
from typing import Any

import structlog

from config import settings
from engine.authority.intent import classificar_intent_economia
from engine.authority.resolve import resolver_custo_ouro
from engine.llm.extractor import (
    _canonico,
    _capar_npcs_presentes,
    _chave_conjunto,
    _chave_dedup,
    _e_entidade_invalida,
    _variante_proxima,
)
from engine.llm.types import RE_COMBATE as _RE_COMBATE_JOGADOR
from engine.llm.types import e_turno_de_rolagem as _e_turno_de_rolagem
from engine.magic.slot_tracker import detectar_tipo_descanso, restaurar_slots
from engine.memory.quest_detector import strip_marcadores
from engine.memory.trust_detector import detectar_mudancas_trust
from engine.memory.working_memory import WorkingMemory
from engine.npc.identity import parece_nome_proprio, registrar_npc, resolver_falado

log = structlog.get_logger()

# ── Regexes das Features de Mestre Veterano ───────────────────────────────────

# DM Feat 1: Fio solto — LLM emite [FIO: descrição do plot thread em aberto]
# Ex: "[FIO: O ferreiro mencionou ter visto Valdrek na mina há 3 semanas]"
_RE_FIO = re.compile(r"\[FIO:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# DM Feat 2: Cliffhanger — LLM emite [CLIFFHANGER: frase dramática de encerramento]
# Ex: "[CLIFFHANGER: E então a porta se abre — é Valdrek, segurando o corpo de Bjorn]"
_RE_CLIFFHANGER = re.compile(r"\[CLIFFHANGER:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# DM Feat 3: Agenda paralela de NPC — LLM emite [AGENDA: npc-id → descrição do plano]
# Ex: "[AGENDA: fael-valdreksson → planeja desertar à meia-noite com a chave do cofre]"
_RE_AGENDA = re.compile(r"\[AGENDA:\s*([a-z0-9-]+)\s*[→>-]+\s*([^\]]+?)\s*\]", re.IGNORECASE)

# Repetition Guard: LLM emite [ANCORA: fato já resolvido] após virada narrativa importante.
# Ex: "[ANCORA: O segredo de Valdrek foi revelado ao jogador]"
# Backend acumula max 5; prompt_builder injeta como "Não repetir narrativa já dita".
_RE_ANCORA = re.compile(r"\[ANCORA:\s*([^\]]+?)\s*\]", re.IGNORECASE)
# Diretor de Arco: o jogador declarou um segredo e o Mestre confirma.
_RE_SEGREDO_REVELADO = re.compile(
    r"\[SEGREDO_REVELADO:\s*([a-z0-9][a-z0-9-]{0,60})\s*\]", re.IGNORECASE
)

# REPETICAO-FRIO (playtest 21/06): o Mestre re-descreve a MESMA imagem sensorial
# (clima/frio/cheiro) a cada turno. Detectamos frases curtas de ambiente pra
# alimentar o repetition guard sensorial (wm.ambiente_recente). Keywords em ASCII
# (a frase é transliterada antes de casar) — cobrem clima, temperatura, olfato,
# luz/escuridão e som ambiente.
_KEYWORDS_AMBIENTE = frozenset({
    "frio", "fria", "gelado", "gelada", "gelido", "gelida", "cortante",
    "vento", "ventania", "brisa", "rajada", "nevoa", "neblina", "bruma",
    "umidade", "umido", "umida", "chuva", "chuvisco", "garoa", "tempestade",
    "calor", "quente", "abafado", "mormaco", "sol", "sufocante",
    "cheiro", "fedor", "odor", "aroma", "fedido", "mofo",
    "silencio", "silencioso", "escuridao", "escuro", "escura", "sombras",
    "penumbra", "trevas", "poeira", "fumaca", "fuligem",
})
# Frase = trecho entre pontuação forte. Captura curta (imagem, não ação longa).
_RE_FRASE_AMBIENTE = re.compile(r"[^.!?…\n]+")

# Colocações FIGURADAS onde a keyword atmosférica NÃO descreve clima/ambiente —
# descrevem temperamento/emoção ("sangue frio" = compostura, "olhar gelado" =
# frieza emocional). Sem isto, viravam falsas "imagens de ambiente" e poluíam o
# guard anti-repetição (achado no hardening adversarial). Strings transliteradas.
_IDIOMAS_NAO_AMBIENTE = (
    "sangue frio", "sangue-frio", "sangue quente",
    "cabeca fria", "cabeca quente",
    "olhar frio", "olhar gelado", "olhos frios", "olhos gelados",
    "agua fria", "coracao frio", "coracao quente", "coracao gelado",
    "calor humano", "pe frio", "guerra fria",
    "sorriso frio", "sorriso gelado", "voz fria", "voz gelada",
    "tom frio", "recepcao fria",
)


def extrair_imagens_ambiente(narracao: str) -> list[str]:
    """Extrai imagens sensoriais/de clima da narração (frio, vento, cheiro…).

    Por que existe: REPETICAO-FRIO — o Mestre repete 'frio cortante da noite'
    todo turno. Cada frase CURTA (≤12 palavras) com keyword atmosférica vira uma
    assinatura, usada pra dizer ao LLM 'você já descreveu isto, varie ou omita'.
    Conservador: ignora frases longas (ação/diálogo) e dedup case-insensitive.

    Exemplo:
        extrair_imagens_ambiente("O frio cortante da noite morde. Ele saca a espada.")
        # → ["O frio cortante da noite morde"]
    """
    out: list[str] = []
    vistos: set[str] = set()
    for bruto in _RE_FRASE_AMBIENTE.findall(narracao or ""):
        frase = bruto.strip()
        if not frase or len(frase.split()) > 12:
            continue
        ascii_low = unicodedata.normalize("NFKD", frase.lower())
        ascii_low = "".join(c for c in ascii_low if not unicodedata.combining(c))
        toks = set(re.findall(r"[a-z]+", ascii_low))
        if not (toks & _KEYWORDS_AMBIENTE):
            continue
        # Idioma figurado (sangue frio, olhar gelado…) — não é clima/ambiente.
        if any(idioma in ascii_low for idioma in _IDIOMAS_NAO_AMBIENTE):
            continue
        chave = ascii_low.strip()
        if chave in vistos:
            continue
        vistos.add(chave)
        out.append(frase[:80])
    return out

# Assinatura de voz de NPC: [VOZ: npc-id|pitch|rate]
# Ex: "[VOZ: lyssa|+5Hz|-10%]" — armazenado em wm.npc_vozes para o restante da sessão.
# Pitch: "+NHz" ou "-NHz". Rate: "+N%" ou "-N%".
_RE_VOZ = re.compile(
    r"\[VOZ:\s*([a-z0-9][a-z0-9-]{0,48})\s*\|\s*([+\-]?\d+Hz)\s*\|\s*([+\-]?\d+%)\s*\]",
    re.IGNORECASE,
)

# Caps de assinatura de voz — LLM pode emitir [VOZ: x|+20Hz|-30%] sem perceber
# o efeito caricato. Engine clampa pra manter switches sutis e crível.
# Edge TTS aceita até ±50Hz / ±50%, mas acima de ±10Hz / ±15% começa cartoon.
_CAP_PITCH_HZ: int = 10
_CAP_RATE_PCT: int = 15
_RE_PITCH_VALOR = re.compile(r"^([+\-]?)(\d+)Hz$", re.IGNORECASE)
_RE_RATE_VALOR = re.compile(r"^([+\-]?)(\d+)%$")


def _clamp_pitch(pitch_str: str) -> str:
    """Clamp pitch a ±_CAP_PITCH_HZ. Formato malformado passa adiante intacto."""
    m = _RE_PITCH_VALOR.match(pitch_str.strip())
    if not m:
        return pitch_str
    sinal, valor = m.group(1), int(m.group(2))
    val = -valor if sinal == "-" else valor
    val = max(-_CAP_PITCH_HZ, min(_CAP_PITCH_HZ, val))
    return f"{'+' if val >= 0 else ''}{val}Hz"


def _clamp_rate(rate_str: str) -> str:
    """Clamp rate a ±_CAP_RATE_PCT. Formato malformado passa adiante intacto."""
    m = _RE_RATE_VALOR.match(rate_str.strip())
    if not m:
        return rate_str
    sinal, valor = m.group(1), int(m.group(2))
    val = -valor if sinal == "-" else valor
    val = max(-_CAP_RATE_PCT, min(_CAP_RATE_PCT, val))
    return f"{'+' if val >= 0 else ''}{val}%"

# Engine-authority markers (preferíveis sobre regex de vocab):
# `[INIMIGO_MORTO: id]` — LLM declara explicitamente quem morreu. Resolve
# COMBAT-1 (22 padrões de vocab PT-BR frágeis). Regex existente permanece
# como fallback de defesa caso o LLM não emita o marker.
_RE_INIMIGO_MORTO_MARKER = re.compile(
    r"\[INIMIGO_MORTO:\s*([a-z0-9][a-z0-9-]{0,48})\s*\]",
    re.IGNORECASE,
)

# _RE_DESCANSO_MARKER migrado pra engine/magic/slot_tracker.py (junto da
# lógica de restauração de slots — autoridade do LLM agora é encapsulada
# em detectar_tipo_descanso()). Re-export aqui pra compat com testes
# externos que ainda importam o nome.

# `[COMBATE: iniciar]` — LLM declara início de combate quando a ação do jogador
# é claramente bélica mas o regex de verbos não casou (sparring narrado, "uso X
# em Y" não coberto, declarações indiretas). Bug COMBATE-VERB-1 (26/05).
# Engine-authority complementar à RE_COMBATE no texto do jogador.
_RE_COMBATE_MARKER = re.compile(
    r"\[COMBATE:\s*iniciar\s*\]",
    re.IGNORECASE,
)

# `[INIMIGO: id|nome]` ou `[INIMIGO: id|nome|srd-index]` — LLM declara um combatente
# para a engine rastrear. Resolve COMBAT-EARLY-END (teste ao vivo 01/06): quando
# o jogador ataca em massa sem nomear alvo ("ataco todos", "dei tapa em todo
# mundo"), _RE_ALVO_ATAQUE não captura ninguém → inimigos_combate fica vazio →
# CombatTracker/InitiativeBar vazios + o guard de combate-fantasma encerra o
# combate legítimo na 1ª vantagem do jogador. Com este marker o LLM popula os
# inimigos que ele mesmo está narrando (introdução de cena, reforços, ataque em
# massa). Declarar inimigo implica combate — a engine entra se ainda não está.
# O 3º campo opcional é o índice SRD do monstro (ex: "goblin") para o bestiário
# puxar a ficha mecânica; se omitido, a engine tenta o slug do nome.
# Não colide com [INIMIGO_MORTO: ...]: este exige ":" logo após INIMIGO + pipe.
_RE_INIMIGO_REGISTRAR = re.compile(
    r"\[INIMIGO:\s*([a-z0-9][a-z0-9-]{0,48})\s*\|\s*"
    r"([^|\]]{1,40}?)\s*(?:\|\s*([a-z0-9][a-z0-9-]{0,40})\s*)?\]",
    re.IGNORECASE,
)

# Estado afetivo de NPC: [AFETO: npc-id|campo|delta]
# Ex: "[AFETO: fael-valdreksson|respeito|+2]" — salvo no Neo4j (persistência entre sessões).
# Campos: afeto | medo | respeito | rancor. Delta: int com sinal (+/-).
_RE_AFETO = re.compile(
    r"\[AFETO:\s*([a-z0-9][a-z0-9-]{0,48})\s*\|\s*(afeto|medo|respeito|rancor)\s*\|\s*([+\-]?\d+)\s*\]",
    re.IGNORECASE,
)

# Gasto de class feature: [FEATURE_GASTA: feature-id] — LLM declara que o
# jogador usou Action Surge/Second Wind/etc. e a engine decrementa usos_atual.
# UI-FICHA (teste 09/06): "nem pedindo pro mestre aquilo gasta" — não existia
# canal LLM→engine pra features; só o sync manual do frontend.
_RE_FEATURE_GASTA = re.compile(
    r"\[FEATURE_GASTA:\s*([a-z0-9][a-z0-9-]{0,48})\s*\]",
    re.IGNORECASE,
)

# Mudança de cena: [CENA: local-id|Nome do Local|hora] (hora opcional).
# Ex: "[CENA: mina-abandonada|Mina Abandonada|noite]".
# Resolve CENA-1 (varredura 08/06): sem este marker o estado de cena
# (location_id/nome, time_of_day, npcs_presentes) congelava no valor da criação
# da sessão durante todo o jogo ao vivo — NPCs iniciais "perseguiam" o jogador
# pelo mapa, SceneHeader/hora/imagem-de-cena ficavam estáticos, e o gating de
# NARRATIVE_LIGHT nunca disparava (npcs_presentes nunca esvaziava). A engine
# atualiza local/hora no pipeline sync e re-infere NPCs do novo local (Neo4j)
# via reinferir_npcs_se_mudou_cena() no caller async.
_RE_CENA = re.compile(
    r"\[CENA:\s*([a-z0-9][a-z0-9-]{0,48})\s*\|\s*([^|\]]{1,40}?)\s*"
    r"(?:\|\s*([^|\]]{1,20}?)\s*)?\]",
    re.IGNORECASE,
)

# Pilar Perigo (10/06): HP do jogador é autoridade da engine.
# [DANO: -N motivo] reduz; [CURA: +N motivo] restaura (e reseta death saves).
# Antes destes markers NÃO existia canal de dano ao jogador — ataque inimigo
# narrado nunca tirava HP de verdade, e o subconsciente do jogador percebia
# que era imortal. Clamp por aplicação em hp_max (anti [DANO: -999]).
_RE_DANO = re.compile(r"\[DANO:\s*-?(\d+)\s*([^\]]*?)\s*\]", re.IGNORECASE)
_RE_CURA = re.compile(r"\[CURA:\s*\+?(\d+)\s*([^\]]*?)\s*\]", re.IGNORECASE)

# DANO-IMPROVISADO-1 (playtest #6, 16/06): teto de dano por golpe quando o
# encontro é 100% IMPROVISADO — nenhum inimigo vivo tem ficha SRD no bestiário.
# No teste, um "homem comum" sem ficha levou o 8B a inventar dano=17 num golpe só
# (quase one-shot num PJ nv3). O teto ancora em CR≈0–1/8 (commoner com clava 1d4≈4;
# bandido 1d6+1≈7): o golpe mais duro de um humano improvisado fica em ~8. Quando
# ALGUM inimigo tem ficha SRD, o LLM tem stats reais pra ancorar o dano e o clamp
# NÃO interfere (confia no teto de hp_max de aplicar_dano). Fora de combate também
# não atua — preserva dano legítimo de queda/armadilha/narrativa. Ajustável após
# validação de balance ao vivo.
_DANO_MAX_INIMIGO_IMPROVISADO = 8


def deve_zerar_dano_extractor(resposta: str, engine_resolveu_turno: bool) -> bool:
    """Decide se o `dano_ao_jogador` do extractor de prosa deve ser DESCARTADO.

    Engine-first: quando a ENGINE já resolveu o turno de combate (o resolver rodou
    `executar_turno_inimigos` e aplicou o dano do inimigo no PJ) OU quando há um
    marker `[DANO]` explícito na resposta, o extractor lendo a MESMA narração
    aplicaria o dano DE NOVO — o HP-desync/double-count do playtest 29/06 (o jogador
    tomava ~2× o dano do inimigo, porque o engine resolvia e a prosa re-aplicava).
    Nesses casos o dano lido da prosa é descartado; a engine / o marker `[DANO]` são
    a autoridade do HP do jogador.
    """
    return engine_resolveu_turno or bool(_RE_DANO.search(resposta))


def _combate_sem_ficha_srd(working_mem: Any) -> bool:
    """True quando há combate ativo e NENHUM inimigo vivo tem ficha SRD.

    Sinaliza um encontro 100% improvisado, em que o dano de inimigo não tem
    stat block pra se ancorar — gatilho do clamp DANO-IMPROVISADO-1.
    """
    if not getattr(working_mem, "em_combate", False):
        return False
    vivos = [
        d
        for d in getattr(working_mem, "inimigos_combate", {}).values()
        if d.get("estado") != "morto"
    ]
    if not vivos:
        return False
    return not any(d.get("ficha") for d in vivos)

# Cicatriz permanente — emitida quando o personagem sobrevive a 0 PV (ou a
# um custo físico dramático). Persiste via dm_state; NPCs reagem.
_RE_CICATRIZ = re.compile(r"\[CICATRIZ:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# Telemetria (decisão Beltrami 04/07): iniciativa é AUTORIDADE DA ENGINE —
# o prompt proíbe o Mestre de pedi-la, mas o LLM insiste (playtests 30/06 e
# 03/07). O frontend suprime o pedido (nem banner, nem chip — page.tsx
# pedidoEhIniciativa); aqui só CONTAMOS quantas vezes acontece, pra decidir
# com dados se um dia vale interceptar/reescrever a resposta. Verbo de
# rolagem PERTO da palavra "iniciativa", nas duas ordens.
_RE_MESTRE_PEDE_INICIATIVA = re.compile(
    r"(?:rol[ae]\w*|jogu\w+|test\w+|fa[çc]a\w*)[^.!?\n]{0,60}\biniciativa\b"
    r"|\biniciativa\b[^.!?\n]{0,40}(?:rol[ae]\w*|jogu\w+|d20)",
    re.IGNORECASE,
)


def mestre_pediu_iniciativa(resposta: str) -> bool:
    """True se a narração do Mestre PEDE uma rolagem de iniciativa.

    Menção casual ("sua iniciativa o coloca na frente") não conta — precisa
    de verbo de rolagem próximo. Helper puro pra teste; o pipeline só loga.
    """
    return bool(_RE_MESTRE_PEDE_INICIATIVA.search(resposta))


# Telemetria (playtest 05/07, sess-95a7c47468c5): o Mestre narrou golpe de
# inimigo CONECTANDO no jogador e "declarou o dano" em prosa — mas nunca emitiu
# [DANO], então o HP ficou 24/24 a sessão inteira. Detector conservador de
# "golpe acertou o jogador": verbo de impacto + alvo-jogador (te/você/sua parte
# do corpo), nas duas ordens. Só LOGA — a autoridade continua no marker.
_RE_GOLPE_NO_JOGADOR = re.compile(
    r"\b(?:te|lhe)\s+(?:acert\w+|ating\w+|golpe\w+|cort\w+|perfur\w+|rasg\w+|fer\w+|queim\w+)"
    r"|\b(?:acert\w+|ating\w+|golpe\w+|cort\w+|perfur\w+|rasg\w+|crav\w+|abr\w+)"
    r"[^.!?\n]{0,28}\b(?:em voc[êe]\b|te\b|seu\s+(?:peito|bra[çc]o|rosto|flanco|ombro|abd[ôo]men|cr[âa]nio)"
    r"|sua\s+(?:perna|m[ãa]o|coxa|face|carne|cabe[çc]a))",
    re.IGNORECASE,
)


def dano_narrado_sem_marker(resposta: str, em_combate: bool) -> bool:
    """True se a narração descreve golpe conectando no jogador SEM [DANO].

    Falso-positivo moderado é aceitável — é telemetria pura pra medir a
    não-compliance do marker antes de decidir uma intervenção mais dura
    (engine-first: o dano do inimigo deveria vir do turno de inimigo da
    engine, que exige combatente registrado).
    """
    if not em_combate:
        return False
    if "[dano" in resposta.lower():
        return False
    return bool(_RE_GOLPE_NO_JOGADOR.search(resposta))

# Session Zero (Ritual P3) — o mestre fecha a entrevista de criação com
# [FICHA: Nome|Raça|Classe|background|traço] (traço opcional). A engine gera
# atributos/HP/slots/features — o jogador nunca fala de números.
_RE_FICHA = re.compile(
    r"\[FICHA:\s*([^|\]]{1,40}?)\s*\|\s*([^|\]]{1,30}?)\s*\|\s*([^|\]]{1,20}?)\s*"
    r"\|\s*([^|\]]{1,60}?)\s*(?:\|\s*([^|\]]{1,120}?)\s*)?\]",
    re.IGNORECASE,
)

# Ações sociais explícitas no texto do jogador (Ritual P2 — perfil do
# jogador). Não precisa ser exaustivo: é contador de tendência, não gate.
_RE_ACAO_SOCIAL = re.compile(
    r"\b(fal[oa]|pergunt[oa]|convers[oa]|digo|peço|pe[cç]o|convenç[oa]|"
    r"mint[oa]|persuad[oa]|intimid[oa]|negoci[oa]|cumpriment[oa]|respond[oa]|"
    r"apresent[oa]|explico|agradeç[oa])\b",
    re.IGNORECASE,
)

# Relógios de Ameaça (Mundo Vivo, 10/06) — fronts à la Apocalypse World.
# [RELOGIO: id|Nome|segmentos] cria (segmentos opcional, default 6, clamp 3-8);
# [RELOGIO_AVANCA: id] avança 1 por decisão dramática do LLM. A engine também
# avança TODOS em descanso longo e em viagem (mudança de local) — o mundo
# anda sem o jogador. Cheio → irrupção one-shot no próximo prompt.
_RE_RELOGIO = re.compile(
    r"\[RELOGIO:\s*([a-z0-9][a-z0-9-]{0,48})\s*\|\s*([^|\]]{1,60}?)\s*"
    r"(?:\|\s*(\d)\s*)?\]",
    re.IGNORECASE,
)
_RE_RELOGIO_AVANCA = re.compile(
    r"\[RELOGIO_AVANCA:\s*([a-z0-9][a-z0-9-]{0,48})\s*\]", re.IGNORECASE
)

# Entrada de NPC na cena: [NPC: npc-id|Nome] (nome opcional).
# Teste ao vivo 10/06: o mestre apresentou um viajante novo ("Aldric se aproxima
# e se apresenta") mas npcs_presentes só era populado pela inferência Neo4j na
# troca de local — NPC improvisado nunca entrava no HUD nem no prompt de cena,
# e o jogador quase atacou alguém que "não existia". Com o marker, o LLM
# registra a entrada; a engine adiciona a presentes + apresentados.
_RE_NPC_ENTRA = re.compile(
    r"\[NPC:\s*([a-z0-9][a-z0-9-]{0,48})\s*(?:\|\s*([^|\]]{1,40}?)\s*)?\]",
    re.IGNORECASE,
)

# Feature 3: Consequências visíveis — LLM emite [CONSEQUÊNCIA: efeito duradouro no mundo]
# Ex: "[CONSEQUÊNCIA: A guarda de Valdrek passou a reconhecer Drevamor como suspeito]"
# Efeitos válidos: NPC morto, aliança formada, local destruído, reputação alterada.
_RE_CONSEQUENCIA = re.compile(r"\[CONSEQUÊNCIA:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# Feature progressão: LLM emite [XP: +N motivo] em vitórias, descobertas, quests.
# Ex: "[XP: +50 derrotou goblin patrulheiro]", "[XP: +200 quest concluída]"
# Backend acumula em wm.xp e detecta level up via tabela SRD.
_RE_XP = re.compile(r"\[XP:\s*\+?(\d+)\s*([^\]]*?)\s*\]", re.IGNORECASE)
# Teto por marker (XP-CLAMP-1): [XP:] é bônus narrativo 25–100; acima é inflação
# do LLM (abate/quest a engine paga por conta própria, fora deste marker).
_XP_MARKER_MAX = 100

# Lampejo — visão dramática emitida pelo LLM. Conteúdo entre `:` e `]` vira
# uma mensagem WS `tipo="lampejo"` separada, com voz alterada (rate/pitch).
# Usado por _extrair_lampejos / _enviar_lampejo no websocket — a regex vive
# aqui pra ficar com os demais markers (futura tabela única em D4).
_RE_LAMPEJO = re.compile(r"\[LAMPEJO:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# Feature combate tático: LLM emite [POSICAO: npc-id = N ft] (ou "= N ft cobertura").
# Ex: "[POSICAO: goblin = 10 ft]", "[POSICAO: orco-arqueiro = 60 ft cobertura]"
# Engine atualiza wm.posicoes_combate para o CombatTracker mostrar chip de distância.
_RE_POSICAO = re.compile(
    r"\[POSICAO:\s*([a-z0-9-]+)\s*=\s*(\d+)\s*ft\s*(cobertura)?\s*\]",
    re.IGNORECASE,
)

# Movimento do jogador na rodada — LLM emite [MOV: -N ft motivo] quando o jogador
# se desloca. Backend decrementa wm.movimento_restante_ft (max 30 padrão).
# Ex: "[MOV: -20 ft em direção ao orc]" → restante 30→10.
_RE_MOVIMENTO = re.compile(r"\[MOV:\s*-?(\d+)\s*ft\s*([^\]]*?)\s*\]", re.IGNORECASE)

# Feature economia: [OURO: ±N motivo] / [LOOT: item] / [PERDEU: item]
# [OURO: +50 saque do orc] adiciona 50 po; [OURO: -10 paga a pousada] tira 10.
# [LOOT: poção de cura] adiciona ao inventário; [PERDEU: poção de cura] remove.
# [MERCADO] / [FIM_MERCADO] flag pra UI de venda no frontend.
_RE_OURO = re.compile(r"\[OURO:\s*([+-]?)(\d+)\s*([^\]]*?)\s*\]", re.IGNORECASE)
_RE_LOOT = re.compile(r"\[LOOT:\s*([^\]]+?)\s*\]", re.IGNORECASE)
_RE_PERDEU = re.compile(r"\[PERDEU:\s*([^\]]+?)\s*\]", re.IGNORECASE)
_RE_MERCADO = re.compile(r"\[MERCADO\]", re.IGNORECASE)
_RE_FIM_MERCADO = re.compile(r"\[FIM_MERCADO\]", re.IGNORECASE)

# Feature companions/party: aliados que lutam ao lado do jogador.
# `[COMPANION_ADD: id|nome|tipo|hp|ca|atq|dano]` — adiciona/atualiza companion.
#   Ex: `[COMPANION_ADD: lyssa|Lyssa|hireling|25|15|+4|1d8 cortante]`
# `[COMPANION_HP: id|±N motivo]` — ajusta HP (dano/cura).
# `[COMPANION_REMOVE: id]` — companion morre/dispensa/fim de summon.
_RE_COMPANION_ADD = re.compile(
    r"\[COMPANION_ADD:\s*([^|\]]+)\|([^|\]]+)\|([^|\]]+)\|(\d+)\|(\d+)\|([^|\]]+)\|([^\]]+?)\s*\]",
    re.IGNORECASE,
)
_RE_COMPANION_HP = re.compile(
    r"\[COMPANION_HP:\s*([^|\]]+)\|\s*([+-]?\d+)\s*([^\]]*?)\s*\]",
    re.IGNORECASE,
)
_RE_COMPANION_REMOVE = re.compile(r"\[COMPANION_REMOVE:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# ─── Regexes de detecção (compartilhados; espelham os do websocket.py) ────────

_RE_ALVO_ATAQUE = re.compile(
    # Bug R5-1: "lanço" removido — causava falso positivo onde armas/feitiços
    # eram registrados como inimigos: "lanço a flecha no orc" → "Flecha" virava
    # inimigo no CombatTracker. "lanço" é detectado separadamente pelo spell_detector
    # (spell_detector.py:_RE_CASTING) que extrai o nome da magia corretamente.
    # FUNC-1 (playtest 07/07): quebro/esfaqueio/degolo — golpes com arma
    # improvisada ou mutilação explícita, mesma classe dos verbos já aceitos.
    r"\b(?:ataco?|atacar|golpei?o|firo|apunhalo|atinge?|atinjo|acerto|"
    r"quebr[oa]|quebrei|quebrar|esfaquei[oa]|esfaqueei|esfaquear|"
    r"degol[oa]|degolei|degolar)\s+"
    r"(?:o|a|ao?s?|na?s?)\s+"
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,30}?)(?=\s+(?:com|de|usando|n[ao])\b|[.!,?]|$)",
    re.IGNORECASE,
)
_RE_INIMIGO_MORTO = re.compile(
    r"\b([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,25}?)\s+"
    r"(?:caiu|morreu|morre|está morto|está morta|foi abatido|foi abatida|jaz|tombou|"
    r"desmorona|sucumbe|sucumbiu|pereceu|perece|fenece|feneceu|"
    r"se dissolve|dissolveu|se dissipa|dissipou|"
    r"cai sem vida|caiu sem vida|cai morto|caiu morto|cai inerte|caiu inerte|"
    r"entra em colapso|entrou em colapso|desaba|desabou|"
    r"não se levanta|não se move mais|exala o último|"
    r"foi eliminado|foi eliminada|é eliminado|é eliminada|"
    r"foi destruído|foi destruída|é destruído|é destruída|"
    r"se fragmenta|fragmentou|"
    r"expira|expirou|"
    r"não respira|deixou de respirar)\b",
    re.IGNORECASE,
)
_RE_INIMIGO_GRAVE = re.compile(
    r"\b([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,25}?)\s+"
    r"(?:gravemente ferido|muito ferido|mal consegue|vacila|claudica|cambaleando|aos trancos)\b",
    re.IGNORECASE,
)
_RE_INIMIGO_FERIDO = re.compile(
    r"\b([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,25}?)\s+"
    r"(?:está ferido|foi atingido|foi atingida|sangra|grita de dor|recua|recuou|tropeçou)\b",
    re.IGNORECASE,
)
_RE_FIM_COMBATE_LLM = re.compile(
    r"\b("
    # Declarações diretas de fim de combate
    r"o combate termina|a luta termina|combate encerrado|batalha encerrada|"
    r"a batalha chegou ao fim|o confronto termina|o confronto acabou|"
    # Estado de ausência de ameaças
    r"não há mais inimigos|sem mais ameaças|ambiente está seguro|"
    r"área está segura|local está seguro|ameaça foi neutralizada|"
    r"ameaças foram neutralizadas|não resta[m]? inimigos|"
    # Silêncio pós-combate (muito comum em PT-BR)
    r"silêncio retorna|silêncio toma conta|silêncio se instala|"
    r"silêncio cai sobre|o barulho cessa|o caos cessa|"
    # Todos os inimigos caíram
    r"todos os inimigos ca[íi]ram|inimigos foram derrotados|"
    r"todos ca[íi]ram|todos foram abatidos|todos pereceram|"
    # Último inimigo
    r"último inimigo|únic[oa] sobrevivente|nenhum sobreviveu|"
    # Recuo dos inimigos (também encerra combate para o jogador)
    r"inimigos recuaram|fugiram em desbandada|debandam|desbandada"
    r")\b",
    re.IGNORECASE,
)


# Pronomes em PT-BR que NUNCA devem virar id de inimigo. Sem isso, frases como
# "você está ferido" ou "ataco o você" (LLM gago) viram registro espúrio.
_PRONOMES: frozenset[str] = frozenset({
    "você", "vocês", "voce", "voces",
    "eu", "nós", "nos",
    "me", "te", "lhe", "se",
    "ele", "ela", "eles", "elas",
    "isso", "isto", "aquilo",
})

# ALVO-PRONOME-1 (playtest 06/07): "vou atacar ele do nada!" — _RE_ALVO_ATAQUE
# exige um ARTIGO entre o verbo e o alvo ("ataco O goblin"), então um objeto-
# pronome ("atacar ele", sem artigo) nunca bate no regex nenhuma vez — o loop
# de match nem roda, e sem NOME no texto o passo 2 (busca por substring) também
# falha. Verbo de ataque + pronome de objeto DIRETO (sem artigo) → só entra em
# jogo quando há exatamente 1 candidato (NPC presente OU inimigo já vivo);
# ambíguo (0 ou 2+) mantém o comportamento de sempre (sem alvo, nunca adivinha).
# FUNC-1 (playtest 07/07, sess-c48c397df10a): 5 turnos de combate real, ZERO
# markers [INIMIGO], ZERO dano aplicado — o resolver nunca engatou porque as
# falas do jogador não bateram em NENHUM regex de alvo. Duas construções que
# escapavam:
#   (a) verbo + pronome de objeto direto, mas com verbo fora da lista antiga
#       ("quebrar ELE na cabeça com o copo" — arma improvisada);
#   (b) alvo como POSSESSIVO do corpo atingido, não objeto direto do verbo
#       ("o chute na cara DELE", "abrir as tripas DELE" — o pronome está preso
#       a um substantivo de golpe/parte-do-corpo, não ao verbo).
# (b) é um padrão novo — precisa de uma segunda alternativa no regex, não só
# mais verbos na lista de (a).
_RE_PRONOME_ATAQUE = re.compile(
    r"\b(?:ataco?|atacar|golpei?o|firo|apunhalo|atinge?|atinjo|acerto|"
    r"quebr[oa]|quebrei|quebrar|esfaquei[oa]|esfaqueei|esfaquear|"
    r"degol[oa]|degolei|degolar)\s+"
    r"(?:nele|nela|ele|ela|aquele|aquela|esse|essa|isso|aquilo)\b"
    r"|"
    r"\b(?:tapa|soco|murro|chute|empurr[ãa]o|joelhada|cabe[çc]ada|cotovelada|"
    r"bofetada|estocada|facada|punhalada|tripas|garganta|pesco[çc]o)\b"
    r"[^.!?\n]{0,25}\b(?:dele|dela)\b",
    re.IGNORECASE,
)

# ALVO-INSTRUMENTO-1 (playtest 10/07, sess-cc69c30f7c4f): "Quebro a caneca na
# cabeça do grandão" — _RE_ALVO_ATAQUE captura "caneca" (objeto direto do
# verbo) porque ela aparece ANTES do possessivo do corpo atingido, e devolve
# na hora (loop com `return` no primeiro match). A engine registrou "Caneca"
# como inimigo (CA/HP default) e ele "revidou" na narrativa — o instrumento do
# golpe nunca é o alvo. Espelho do padrão golpe-substantivo do FUNC-1 ("o
# chute na cara DELE"), só que aqui o possuidor é um NOME, não um pronome —
# não cai em _RE_PRONOME_ATAQUE (que só cobre dele/dela). Roda sobre o texto
# SEM ACENTO (mesmo padrão de `_ALVO_NAO_NPC`) pra não depender de acentuação.
_RE_ALVO_POSSESSIVO_CORPO = re.compile(
    r"\bn[ao]s?\s+(?:cabeca|cara|rosto|peito|costas|pescoco|garganta|"
    r"barriga|ventre|nuca|corpo|tronco|olhos?|bracos?|pernas?|maos?|"
    r"ombros?|joelhos?|pes?)\s+"
    r"d[oa]s?\s+"
    r"([a-z][a-z\s]{1,30}?)(?=[.,!?]|$)",
    re.IGNORECASE,
)


# ALVO-FANTASMA-1 (playtest 29/06): "corto a cabeça de aldric" tem alvo "aldric",
# NÃO "cabeça". Partes do corpo nunca são o alvo-NPC — se o regex pegar uma delas,
# descarta e tenta o NPC presente (scan da cena).
_ALVO_NAO_NPC: frozenset[str] = frozenset({
    "cabeca", "braco", "bracos", "perna", "pernas", "peito", "pescoco", "rosto",
    "cara", "mao", "maos", "costas", "barriga", "ventre", "torax", "ombro",
    "ombros", "olho", "olhos", "garganta", "coracao", "joelho", "pe", "pes",
    "dedo", "dedos", "nuca", "corpo", "tronco", "flanco",
})


def _slugify(nome: str) -> str:
    """Converte nome livre para id kebab-case."""
    normalizado = unicodedata.normalize("NFD", nome.strip().lower())
    sem_acento = "".join(c for c in normalizado if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento).strip("-")


def _sem_acento(s: str) -> str:
    """minúsculo + sem acento (pra casar nomes de NPC no texto do ataque)."""
    n = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in n if unicodedata.category(c) != "Mn")


def deve_auto_registrar_generico(working_mem: WorkingMemory) -> bool:
    """True se a engine deve criar o inimigo genérico "oponente-1" (fallback de
    combate sem nenhuma info de inimigo).

    COMBATE-FANTASMA (playtest 29/06): o genérico era criado SEMPRE que o combate
    não tinha inimigo — inclusive quando havia NPCs presentes (a família). Aí o
    jogador atacava "aldric" mas a engine resolvia o fantasma, e matar o fantasma
    encerrava o combate. Regra nova: se há NPCs PRESENTES, o inimigo é um deles —
    registrado por nome quando o jogador o ataca (extrair_alvo_ataque/ALVO-FANTASMA).
    O genérico só entra em luta SEM NPCs na cena (monstro puro que o LLM esqueceu
    de declarar com [INIMIGO]).
    """
    return bool(
        working_mem.em_combate
        and not working_mem.inimigos_combate
        and not working_mem.npcs_presentes
    )


def _encontrar_id_inimigo(
    trecho: str, nomes_registrados: dict[str, str]
) -> str | None:
    """Mapeia um trecho do LLM para o id de um inimigo registrado.

    Regra: o nome registrado precisa aparecer como **palavra inteira** dentro do
    trecho. Se vários candidatos baterem, vence o nome registrado mais **longo**
    (mais específico) — assim "goblin arqueiro" não colide com "goblin" simples
    quando o LLM narra "o goblin arqueiro caiu".

    Pronomes (você/eu/nós/...) nunca casam — protege contra LLM narrar "você
    está ferido" virando registro espúrio de inimigo chamado "você".
    """
    trecho_lower = trecho.strip().lower()
    if not trecho_lower or trecho_lower in _PRONOMES:
        return None
    candidatos: list[tuple[int, str]] = []
    for nome_reg, iid in nomes_registrados.items():
        if re.search(rf"\b{re.escape(nome_reg)}\b", trecho_lower):
            candidatos.append((len(nome_reg), iid))
    if not candidatos:
        return None
    # Maior tamanho primeiro; tiebreaker por id (determinístico)
    candidatos.sort(key=lambda t: (-t[0], t[1]))
    return candidatos[0][1]


def extrair_alvo_ataque(texto_jogador: str, working_mem: WorkingMemory) -> str | None:
    """Id do inimigo que o jogador está atacando, ou None se ambíguo/ausente.

    Usado pela costura de combate engine-autoritativo (task 7) ANTES do LLM, pra
    saber contra quem resolver a rolagem. Estratégia (em ordem):
      0. ALVO-INSTRUMENTO-1 (playtest 10/07): possessivo NOMEADO de parte do
         corpo ("na cabeça DO GRANDÃO") vence o objeto direto do verbo — o
         instrumento do golpe (a caneca, a espada) nunca é o alvo;
      1. `_RE_ALVO_ATAQUE` clássico ("ataco o goblin") — registra e devolve;
         ignora pronome e PARTE DO CORPO ("a cabeça");
      2. ALVO-FANTASMA (playtest 29/06): NPC PRESENTE nomeado no texto — "corto a
         cabeça de aldric" mira aldric porque ele está em npcs_presentes (mais
         robusto que o regex e EVITA cair no genérico "oponente-1");
      3. sem nome → único inimigo VIVO ("ataco ele");
      4. senão None (ambíguo — caller pede alvo ou cai no fluxo antigo).
    """
    _m_corpo = _RE_ALVO_POSSESSIVO_CORPO.search(_sem_acento(texto_jogador))
    if _m_corpo:
        nome = _m_corpo.group(1).strip().rstrip(".,!?")
        primeira = nome.split()[0] if nome.split() else ""
        if nome and nome not in _PRONOMES and primeira not in _PRONOMES:
            iid = _slugify(nome)
            if iid:
                try:
                    _canonico = resolver_falado(working_mem, iid)
                except Exception:
                    _canonico = None
                if _canonico:
                    iid = _canonico
                    nome = str(iid).replace("-", " ")
                if iid not in working_mem.inimigos_combate:
                    working_mem.registrar_inimigo(iid, nome.title(), "intacto")
                return iid

    for m in _RE_ALVO_ATAQUE.finditer(texto_jogador):
        nome = m.group(1).strip().rstrip(".,!?")
        if not nome:
            continue
        primeira = nome.split()[0].lower() if nome.split() else ""
        if nome.lower() in _PRONOMES or primeira in _PRONOMES:
            continue
        if _sem_acento(primeira) in _ALVO_NAO_NPC:
            continue  # "a cabeça de X" — a parte do corpo não é o alvo; tenta o NPC
        iid = _slugify(nome)
        if not iid:
            continue
        # NPC-IDENTIDADE (05/07): "ataco o monge" resolvia pra um id CURTO novo
        # ("monge") enquanto a presença tinha "monge-da-taverna-kaelmund" — o
        # trust/inimigo nasciam numa 3ª chave que nenhum outro sistema lia.
        # resolver_falado casa o alvo falado com o NPC presente (subconjunto de
        # tokens, match único); ambíguo mantém o comportamento antigo.
        try:
            _canonico = resolver_falado(working_mem, iid)
        except Exception:
            _canonico = None  # stub de teste sem scene.npc_registro
        if _canonico:
            iid = _canonico
            nome = str(iid).replace("-", " ")
        if iid not in working_mem.inimigos_combate:
            working_mem.registrar_inimigo(iid, nome.title(), "intacto")
        return iid

    # 2. NPC presente nomeado no ataque (pega o que o regex perde: "corto a cabeça
    #    de aldric", "decapito o velho aldric"). Registra-o como inimigo — quem o
    #    jogador ataca por nome VIRA combatente, em vez do fantasma "oponente-1".
    texto_norm = _sem_acento(texto_jogador)
    for nid in list(working_mem.npcs_presentes):
        primeiro = _sem_acento(str(nid).split("-")[0])
        if len(primeiro) >= 3 and re.search(rf"\b{re.escape(primeiro)}\b", texto_norm):
            if nid not in working_mem.inimigos_combate:
                working_mem.registrar_inimigo(nid, str(nid).replace("-", " ").title(), "intacto")
            return nid

    vivos = [
        iid for iid, d in working_mem.inimigos_combate.items()
        if d.get("estado") != "morto"
    ]
    if len(vivos) == 1:
        return vivos[0]

    # 2.5 (ALVO-PRONOME-1): "vou atacar ele do nada" — sem artigo, o passo 1
    # nem roda (_RE_ALVO_ATAQUE exige artigo entre verbo e alvo); sem nome no
    # texto, o passo 2 também falha. Único candidato (NPC presente OU inimigo
    # já registrado) → resolve; ambíguo (0 ou 2+) segue None, nunca adivinha.
    if _RE_PRONOME_ATAQUE.search(texto_jogador):
        candidatos = list(dict.fromkeys(vivos + list(working_mem.npcs_presentes)))
        if len(candidatos) == 1:
            iid = candidatos[0]
            if iid not in working_mem.inimigos_combate:
                working_mem.registrar_inimigo(iid, str(iid).replace("-", " ").title(), "intacto")
            return iid

    return None


# Rolagem de d20 que o JOGADOR envia da UI — tolerante a DOIS formatos legítimos
# do frontend (frontend/app/page.tsx):
#   - toolbar simples:  "[Rolagem: d20 = 18]"                  → já o BRUTO
#   - chip contextual:  "[Rolagem: Iniciativa (+3) d20+3 = 9]" → TOTAL com mod
# O chip contextual aparece sempre que o Mestre pede um atributo NOMEADO — ex:
# "Iniciativa", "Persuasão" — inclusive durante combate, se o prompt falhar em
# manter o pedido restrito ao ataque puro. Sem essa tolerância, o regex antigo
# (só casava o formato simples) descartava silenciosamente o `combate_pendente`
# quando o jogador rolava pelo chip — playtest 30/06: "a iniciativa rolou um
# ataque" (a pendência sumia sem nunca resolver o turno pela engine).
_RE_D20_JOGADOR = re.compile(
    r"\[Rolagem\s*:\s*(?:[^\[\]]*?\s)?d(\d+)\s*([+-]\d+)?\s*=\s*(-?\d+)",
    re.IGNORECASE,
)


def extrair_d20_jogador(texto_jogador: str) -> int | None:
    """Extrai o valor BRUTO (1-20) de uma rolagem de d20 enviada pelo jogador.

    Aceita o formato simples (já bruto) e o formato rico do chip contextual
    (subtrai o modificador do total pra recuperar o bruto). Retorna None se o
    texto não contiver `[Rolagem: ...]` ou se a face não for d20.
    """
    m = _RE_D20_JOGADOR.search(texto_jogador)
    if not m or m.group(1) != "20":
        return None
    modificador = int(m.group(2)) if m.group(2) else 0
    total = int(m.group(3))
    return total - modificador


# Tipos de relação (edges do módulo) que indicam ALIANÇA — o NPC defende o atacado.
# "rival"/"enemy" NÃO defendem. Cobre variações PT/EN do schema v1.2.
_TIPOS_ALIADO_HOSTIL: frozenset[str] = frozenset({
    "ally", "aliado", "aliada", "mentor", "family", "familia", "kin",
    "parente", "irmao", "irma", "filho", "filha", "pai", "mae", "leal", "loyal",
})


def aliados_presentes_para_hostil(
    relacoes: list[dict[str, Any]],
    npcs_presentes: list[str],
    ja_inimigos: set[str] | None = None,
    companions: set[str] | None = None,
) -> list[str]:
    """NPCs PRESENTES que viram hostis quando o jogador ataca um NPC (família-29/06).

    HOSTILIDADE POR GRAFO (Neo4j ativo): atacar X traz pro combate os ALIADOS de X
    (edges type ally/mentor/family) que estão NA CENA — a família defende o
    patriarca. RIVAIS não defendem. Companions e quem já é inimigo ficam de fora.
    `relacoes` = saída de `neo4j_client.buscar_relacionamentos(alvo)`. PURO/testável.
    """
    ja_inimigos = ja_inimigos or set()
    companions = companions or set()
    presentes = set(npcs_presentes)
    saida: list[str] = []
    vistos: set[str] = set()
    for r in relacoes:
        tipo = str(r.get("tipo", "")).strip().lower()
        alvo = str(r.get("alvo_id", "")).strip()
        if (
            tipo in _TIPOS_ALIADO_HOSTIL
            and alvo
            and alvo in presentes
            and alvo not in ja_inimigos
            and alvo not in companions
            and alvo not in vistos
        ):
            vistos.add(alvo)
            saida.append(alvo)
    return saida


def sincronizar_inimigos_combate(
    working_mem: WorkingMemory,
    texto_jogador: str,
    resposta_llm: str,
    *,
    ids_ja_marcados_morte: set[str] | None = None,
) -> None:
    """Popula e atualiza inimigos_combate a partir do turno atual.

    1. Se jogador declara ataque com alvo nomeado → registrar inimigo (intacto)
    2. Varrer resposta do LLM por descritores de saúde e atualizar estado

    Args:
        ids_ja_marcados_morte: set de IDs já processados via marker [INIMIGO_MORTO].
            Esses são pulados na detecção regex de morte para evitar dupla
            atualização e log spam. Demais estados (ferido, grave) ainda são
            processados normalmente.
    """
    if not working_mem.em_combate:
        return
    _ja_mortos = ids_ja_marcados_morte or set()

    for m in _RE_ALVO_ATAQUE.finditer(texto_jogador):
        nome = m.group(1).strip().rstrip(".,!?")
        if not nome:
            continue
        # Rejeita se o nome inteiro ou a PRIMEIRA palavra é pronome — protege
        # contra LLM/STT gerando frases como "ataco o você" ou "atinjo nós dois"
        primeira_palavra = nome.split()[0].lower() if nome.split() else ""
        if nome.lower() in _PRONOMES or primeira_palavra in _PRONOMES:
            continue
        # ALVO-INSTRUMENTO-2 (11/07): espelho dos guards que extrair_alvo_ataque
        # já tinha e este loop não — sem eles, o MESMO texto registrava inimigos
        # diferentes nos dois caminhos:
        #   (a) parte do corpo nunca é alvo (ALVO-FANTASMA-1): "golpeio a cabeça
        #       de aldric" registrava "cabeça" como inimigo aqui;
        #   (b) possessivo nomeado de corpo vence o objeto direto
        #       (ALVO-INSTRUMENTO-1): "quebro a caneca na cabeça do grandão"
        #       registrava "caneca" — o instrumento. O trecho logo após o match
        #       ("na cabeça do grandão") identifica o alvo real; troca o nome
        #       ANTES de registrar, por match (multi-alvo na mesma fala intacto).
        if _sem_acento(primeira_palavra) in _ALVO_NAO_NPC:
            continue
        _resto = _sem_acento(texto_jogador[m.end():].lstrip())
        _m_corpo = _RE_ALVO_POSSESSIVO_CORPO.match(_resto)
        if _m_corpo:
            _possuidor = _m_corpo.group(1).strip().rstrip(".,!?")
            _primeira_pos = _possuidor.split()[0] if _possuidor.split() else ""
            if _possuidor and _possuidor not in _PRONOMES and _primeira_pos not in _PRONOMES:
                nome = _possuidor
        inimigo_id = _slugify(nome)
        if not inimigo_id:
            continue
        if inimigo_id not in working_mem.inimigos_combate:
            working_mem.registrar_inimigo(inimigo_id, nome.title(), "intacto")
            log.info("combate_inimigo_registrado", id=inimigo_id, nome=nome)

    if not working_mem.inimigos_combate:
        return

    nomes_registrados = {
        dados["nome"].lower(): iid
        for iid, dados in working_mem.inimigos_combate.items()
    }

    for m in _RE_INIMIGO_MORTO.finditer(resposta_llm):
        iid = _encontrar_id_inimigo(m.group(1), nomes_registrados)
        if not iid or iid in _ja_mortos:
            continue
        # Engine-first: se a ENGINE rastreia o HP deste inimigo e ele está VIVO
        # (hp_max>0 e hp_atual>0), a autoridade da morte é da engine
        # (`aplicar_dano_inimigo`, morte determinística em HP≤0) — NÃO da regex de
        # prosa. Sem isso, o Mestre narrando "o goblin caiu/tombou" mata um inimigo
        # que a engine tem a 5 de HP — o HP-desync/over-kill do playtest 29/06
        # (mesma classe do fix de fim-de-combate 7a). Inimigo sem stats aplicados
        # (hp_max ausente) OU engine desligada mantêm a regex como sinal de morte
        # (fallback legado intacto).
        _d = working_mem.inimigos_combate.get(iid, {})
        _hp_max = int(_d.get("hp_max", 0) or 0)
        _hp_atual = int(_d.get("hp_atual", 0) or 0)
        if settings.COMBATE_ENGINE_ATIVO and _hp_max > 0 and _hp_atual > 0:
            log.info("combate_morte_prosa_ignorada_engine_hp", id=iid, hp_atual=_hp_atual)
            continue
        working_mem.atualizar_estado_inimigo(iid, "morto", "sem vida")
        log.info("combate_inimigo_morto", id=iid)

    for m in _RE_INIMIGO_GRAVE.finditer(resposta_llm):
        iid = _encontrar_id_inimigo(m.group(1), nomes_registrados)
        if iid and working_mem.inimigos_combate.get(iid, {}).get("estado") not in ("morto",):
            working_mem.atualizar_estado_inimigo(iid, "gravemente ferido", "quase sem forças")

    for m in _RE_INIMIGO_FERIDO.finditer(resposta_llm):
        iid = _encontrar_id_inimigo(m.group(1), nomes_registrados)
        if iid and working_mem.inimigos_combate.get(iid, {}).get("estado") == "intacto":
            working_mem.atualizar_estado_inimigo(iid, "ferido", "ainda de pé")


def aplicar_pos_turno(
    working_mem: WorkingMemory,
    texto_jogador: str,
    resposta_completa: str,
    *,
    engine_resolveu_turno: bool = False,
    aguardando_rolagem: bool = False,
) -> list[tuple[str, int]]:
    """Aplica todos os efeitos colaterais de um turno completo na WorkingMemory.

    Idempotente em relação a `dialogo_recente` desde que `registrar_fala("mestre", ...)`
    NÃO tenha sido chamado antes — esta função chama internamente.

    engine_resolveu_turno=True quando o resolver engine-autoritativo (task 7)
    já aplicou o dano deste turno diretamente (resolver_turno_ataque_jogador →
    executar_turno_inimigos). Nesse caso [DANO]/[CURA] narrados pelo Mestre são
    ECO do que já aconteceu, não um evento novo — ver ENGINE-DANO-DUP-1 no step
    16c abaixo. Também pula o avanço de rodada do step 6 (o orchestrator JÁ
    avançou ao renovar action economy) — RODADA-SALTO, playtest 10/07.

    aguardando_rolagem=True quando há uma pendência de ataque viva no fim do
    turno (`sessao.combate_pendente` no websocket) — turno de DECLARAÇÃO ("quebro
    a caneca...") ou de conversa com a rolagem ainda em aberto. Nenhuma troca de
    combate se resolveu, então a rodada não anda (RODADA-SALTO: a UI mostrava
    "Rodada 2" na entrada do combate antes de qualquer d20).

    Returns:
        Lista de mudanças de trust aplicadas: [(npc_id, delta), ...].
        Útil para o caller emitir eventos / telemetria.
    """
    # 0a. Telemetria de iniciativa (04/07) — o Mestre pediu rolagem de
    # iniciativa? É sempre inválido (autoridade da engine); o frontend suprime
    # o pedido, aqui só contamos a incidência pra calibrar próximos passos.
    if mestre_pediu_iniciativa(resposta_completa):
        log.info(
            "mestre_pediu_iniciativa",
            em_combate=working_mem.em_combate,
            trecho=resposta_completa[:80],
        )

    # 0b. Telemetria de dano narrado sem marker (playtest 05/07) — golpe
    # conectou no jogador na prosa mas o [DANO] não veio: o HP visível não
    # muda e a narração desgruda do estado. Só conta a incidência.
    if dano_narrado_sem_marker(resposta_completa, working_mem.em_combate):
        log.info(
            "dano_narrado_sem_marker",
            inimigos_registrados=len(working_mem.inimigos_combate),
            trecho=resposta_completa[:80],
        )

    # 0. Session Zero (Ritual P3) — [FICHA] fecha a entrevista de criação:
    # aplica identidade, gera atributos (standard array por classe), HP/hit
    # dice/slots/features de nível, e desliga o modo entrevista. O caller
    # (websocket) detecta a transição e envia tipo="ficha_criada" + checkpoint.
    if working_mem.session_zero_ativa:
        m_ficha = _RE_FICHA.search(resposta_completa)
        if m_ficha:
            from engine.chargen import gerar_atributos, hit_die, hp_nivel, normalizar_classe
            from engine.magic.spell_list import (
                limite_progressao,
                slots_padrao,
                spells_da_classe,
            )

            ch = working_mem.character
            ch.player_name = m_ficha.group(1).strip()[:40]
            ch.player_race = m_ficha.group(2).strip()[:30]
            classe = normalizar_classe(m_ficha.group(3)) or m_ficha.group(3).strip().title()[:20]
            ch.player_class = classe
            ch.player_background = m_ficha.group(4).strip()[:60]
            ch.player_description = (m_ficha.group(5) or "").strip()[:200]
            for campo, valor in gerar_atributos(classe).items():
                setattr(ch, campo, valor)
            ch.hp_max = hp_nivel(classe, ch.player_level, ch.mod_con)
            ch.hp_current = ch.hp_max
            ch.hit_dice_type = hit_die(classe)
            ch.hit_dice_max = ch.player_level
            ch.hit_dice_current = ch.player_level
            ch.spell_slots = slots_padrao(classe, ch.player_level)
            ch.inicializar_features_classe(classe, "")
            # Repertório inicial para conjuradores — sem isto, spells_conhecidas
            # fica vazio e (a) o guard de cast libera QUALQUER magia (a heurística
            # `not spells_lower` vira True) e (b) o prompt não lista magia alguma,
            # então o LLM deixa o jogador "inventar" feitiços fora da classe
            # (teste 13/06: Paladino lançava bola de fogo). Damos toda a lista da
            # classe até o nível de magia acessível — o jogador só conjura o que a
            # classe dele realmente conhece. Não-conjuradores ficam com [] (nivel_max=0).
            _lim = limite_progressao(classe, ch.player_level)
            if _lim.get("nivel_max", 0) > 0:
                ch.spells_conhecidas = [
                    s.nome_pt
                    for s in spells_da_classe(classe)
                    if s.nivel <= _lim["nivel_max"]
                ]
            working_mem.session_zero_ativa = False
            log.info(
                "ficha_criada_session_zero",
                nome=ch.player_name, raca=ch.player_race,
                classe=classe, hp=ch.hp_max,
            )

    # 1. Registra fala do mestre + apresenta NPCs mencionados.
    # Strips marcadores internos ([FIO:], [CONSEQUÊNCIA:], [XP:], etc.) ANTES de
    # armazenar em dialogo_recente — o histórico enviado ao LLM como "assistant"
    # messages não deve conter marcadores de engine, senão o modelo aprende a
    # emiti-los desnecessariamente ou a referenciar seu próprio scaffolding interno.
    # A extração dos marcadores (steps 10-14) ainda usa `resposta_completa` original.
    fala_limpa = strip_marcadores(resposta_completa)
    working_mem.registrar_fala("mestre", fala_limpa)
    working_mem.apresentar_npcs_mencionados(resposta_completa)

    # Rolling summary: conta este turno. Só turnos reais do jogador — a
    # abertura/reconexão chama com texto_jogador="" e não deve contar.
    if texto_jogador:
        working_mem.narrative.marcar_turno_resumo()


    # 1b. Entrar em combate via marker — LLM tem autoridade para iniciar combate
    #     quando a ação do jogador é narrativamente bélica mas o regex de verbos
    #     não casou (sparring, "uso X em Y", declaração indireta). Bug
    #     COMBATE-VERB-1 (26/05): jogador dizia "vou usar chama sagrada nele"
    #     e o combate não iniciava — Mestre ficava em modo exploração tentando
    #     narrar troca de golpes sem combat.md/saves.md/initiative.
    if not working_mem.em_combate and _RE_COMBATE_MARKER.search(resposta_completa):
        working_mem.entrar_combate()
        log.info("combate_iniciado_por_marker")

    # 1c. Registro de inimigos via marker — engine-authority. LLM declara os
    #     combatentes ([INIMIGO: id|nome|estado?]) que está narrando. Resolve
    #     COMBAT-EARLY-END (teste 01/06): ataque genérico sem alvo nomeado deixava
    #     inimigos_combate vazio e o guard de combate-fantasma (7c) encerrava
    #     combate legítimo. Roda ANTES do sync de morte (2a/2b) para que um inimigo
    #     declarado e abatido no mesmo turno já exista quando [INIMIGO_MORTO] casar.
    #     Declarar inimigo implica combate — entra se ainda não está (entrar_combate
    #     já zera rodadas_sem_acao_inimigo; reforço mid-combate zera explicitamente).
    inimigos_declarados = list(_RE_INIMIGO_REGISTRAR.finditer(resposta_completa))
    if inimigos_declarados:
        if not working_mem.em_combate:
            working_mem.entrar_combate()
            log.info("combate_iniciado_por_inimigo_declarado")
        for m in inimigos_declarados:
            iid = m.group(1).strip().lower()
            nome = m.group(2).strip()
            srd = (m.group(3) or "").strip().lower()
            existente = working_mem.inimigos_combate.get(iid)
            if existente is not None:
                # Re-declaração: NÃO reseta estado/ficha (inimigo já ferido não
                # volta a intacto); só completa o srd_index se ainda faltava.
                if srd and not existente.get("srd_index"):
                    existente["srd_index"] = srd
            else:
                working_mem.registrar_inimigo(iid, nome, "intacto", srd_index=srd)
                log.info("combate_inimigo_declarado", id=iid, srd=srd)
        working_mem.rodadas_sem_acao_inimigo = 0

    # 2. Sync de inimigos ANTES de detectar fim de combate (ordem crítica —
    #    sair_combate limpa inimigos_combate, perderíamos a última morte).
    # 2a. Engine-authority: marker [INIMIGO_MORTO: id] tem prioridade sobre regex.
    #     LLM declara explicitamente quem morreu. Resolve COMBAT-1 onde vocab
    #     PT-BR sutil ("o último orc cai ao chão") não casava com regex.
    # Audit FIX-1: rastreia IDs já marcados via marker para que o regex fallback
    # não os reprocesse (evita log duplicado + double-set idempotente).
    ids_via_marker: set[str] = set()
    if working_mem.em_combate:
        for m in _RE_INIMIGO_MORTO_MARKER.finditer(resposta_completa):
            iid = m.group(1).strip().lower()
            if iid in working_mem.inimigos_combate:
                working_mem.atualizar_estado_inimigo(iid, "morto", "sem vida")
                ids_via_marker.add(iid)
                log.info("combate_inimigo_morto_marker", id=iid)
    # 2b. Fallback de defesa: regex de vocab para casos onde LLM não emitiu marker.
    sincronizar_inimigos_combate(
        working_mem, texto_jogador, resposta_completa,
        ids_ja_marcados_morte=ids_via_marker,
    )
    # 2c. XP engine-first (decisão 01/07): abate detectado via marker/regex paga
    #     XP determinístico ANTES da detecção de fim de combate abaixo — depois
    #     de sair_combate() o dict some e o morto não pagaria. Dedup pela flag
    #     xp_concedido (mortes já pagas pelo resolver não pagam de novo).
    if working_mem.em_combate:
        from engine.progression import conceder_xp_abates_pendentes
        conceder_xp_abates_pendentes(working_mem)

    # 3. Iniciativa — engine é authority
    # Bug #8: cada chamada de pipeline = uma rodada COMPLETA (jogador age,
    # narração descreve player + todos NPCs). Antes incrementávamos
    # turno_atual_idx em +1 a cada turno do jogador, fazendo a InitiativeBar
    # mostrar "orc1" highlighted enquanto era a vez do jogador digitar.
    # Agora: popular iniciativa (idempotente) e voltar pro jogador (idx=0).
    # O avanço de rodada acontece no step 6, mais abaixo.
    if working_mem.em_combate and working_mem.inimigos_combate:
        inimigos_sem_ini = [
            iid for iid in working_mem.inimigos_combate
            if iid not in working_mem.iniciativa_cache
        ]
        if inimigos_sem_ini:
            # debug, não warning: cair no fallback decrescente é o caminho
            # ESPERADO (o LLM raramente propõe iniciativa numérica). Vira ruído
            # de log a cada turno de combate sem indicar problema algum.
            log.debug("iniciativa_fallback", inimigos=inimigos_sem_ini)
        working_mem.popular_iniciativa()
        # Volta o cursor visual pro JOGADOR — é a próxima vez que ele vai agir.
        # Bug R4-1: turno_atual_idx=0 sempre apontava para a posição 0 da lista,
        # que é o inimigo de MAIOR iniciativa (fallback 20,19,18...), não o jogador.
        # Jogador começa com 10+mod_des ≈ 12 — fica após os inimigos. Solução:
        # encontrar o índice real do token "jogador" entre os vivos.
        _ordem_ini = working_mem.calcular_ordem_iniciativa()
        _vivos = [t for t in _ordem_ini if not t.morto]
        _idx_jogador = next(
            (i for i, t in enumerate(_vivos) if t.id == "jogador"), 0
        )
        working_mem.turno_atual_idx = _idx_jogador

    # 4. Descanso — restaura spell slots se jogador declarou descanso neste turno.
    # detectar_tipo_descanso encapsula a prioridade engine-authority:
    # marker do LLM > regex no texto do jogador.
    tipo_descanso = detectar_tipo_descanso(texto_jogador, resposta_completa)
    if tipo_descanso:
        restaurados = restaurar_slots(working_mem, tipo_descanso)
        # Também restaura class features (Action Surge, Rage, etc.) — fix de bug
        # latente: descanso só restaurava slots, features ficavam gastas.
        working_mem.restaurar_features(tipo_descanso)
        if restaurados > 0:
            log.info("slots_restaurados", tipo=tipo_descanso, quantidade=restaurados)
        # Mundo Vivo: o tempo do descanso longo NÃO é grátis — relógios de
        # ameaça avançam (a noite passa, os vilões agem). Descanso curto não tica.
        if tipo_descanso == "longo":
            estourados = working_mem.narrative.avancar_todos_relogios(1)
            if working_mem.narrative.relogios or estourados:
                log.info("relogios_tick_descanso", estourados=estourados or None)

    # 5. Trust com base em ações do jogador
    mudancas_trust = detectar_mudancas_trust(texto_jogador, working_mem.npcs_presentes)
    for npc_id, delta in mudancas_trust:
        working_mem.atualizar_trust(npc_id, delta)
        log.info("trust_atualizado", npc_id=npc_id, delta=delta,
                 novo_valor=working_mem.trust_levels.get(npc_id))

    # 5b. Auto-registra consequências: mortos neste turno + mudanças de trust
    for dados in working_mem.inimigos_combate.values():
        if dados.get("estado") == "morto":
            c = f"{dados['nome']} foi abatido"
            if not any(c in ex for ex in working_mem.log_consequencias):
                working_mem.registrar_consequencia(c)
    for npc_id, delta in mudancas_trust:
        nome = npc_id.split("-")[0].capitalize()
        direcao = "melhorou" if delta > 0 else "piorou"
        working_mem.registrar_consequencia(f"Relação com {nome} {direcao}")

    # 6. Avanço de rodada (só faz sentido em combate E com ação real do jogador).
    # Bug R5-5: `aplicar_pos_turno` é chamado com `texto_jogador=""` na abertura
    # (_enviar_abertura). Se a sessão era continuada em combate, `em_combate=True`
    # e `avancar_rodada()` incrementava `rodada_combate` sem rodada real acontecer —
    # player retomava em "Rodada 2" ao invés de "Rodada 1".
    # RODADA-SALTO (playtest 10/07): dois guards novos —
    #   engine_resolveu_turno: o orchestrator JÁ avançou a rodada ao renovar a
    #     action economy; avançar de novo aqui dobrava a contagem (+2/troca:
    #     "Rodada 4" após uma única troca resolvida);
    #   aguardando_rolagem: declaração de ataque com d20 ainda pendente — nenhuma
    #     troca se resolveu, a rodada fica parada ("Rodada 2" na entrada do
    #     combate antes de qualquer dado). O caminho legado (LLM narra a troca
    #     inteira sem engine) segue avançando por turno como sempre.
    if (
        working_mem.em_combate
        and texto_jogador.strip()
        and not engine_resolveu_turno
        and not aguardando_rolagem
    ):
        working_mem.avancar_rodada()

    # 7. [FUGIU] — jogador escapou do combate. Encerra combate imediatamente.
    # Distinct do _RE_FIM_COMBATE_LLM que detecta resolução da cena: fuga é a
    # decisão ativa de sair sem derrotar os inimigos. Strip do TTS já feito por
    # _RE_MESTRE_VET em quest_detector.strip_marcadores().
    if working_mem.em_combate and re.search(r"\[FUGIU\]", resposta_completa, re.IGNORECASE):
        working_mem.sair_combate()
        log.info("combate_encerrado_fuga")

    # 7a. Fim de combate detectado na narração — POR ÚLTIMO, depois do sync.
    # Engine-first (29/06): a ENGINE é a AUTORIDADE sobre o fim de combate
    # (orchestrator.fim_combate e o step 7b exigem TODOS os inimigos mortos).
    # Quando COMBATE_ENGINE_ATIVO e há inimigos registrados VIVOS, a narração do
    # LLM NÃO encerra o combate — só o step 7b (todos mortos), o [FUGIU] do
    # jogador (step 7) ou o timeout (7c) podem. Sem essa trava, o lite narrando
    # "a área está segura" enquanto a família do patriarca ainda luta (registrada,
    # hp>0) abandonava combatentes vivos — o "dois donos"/família-bystander do
    # playtest 29/06. Quando NÃO há inimigos vivos registrados (combate
    # fantasma/legado sem [INIMIGO]) OU a engine está desligada, a narração segue
    # sendo o sinal de fim — 7a mantém o comportamento antigo.
    if working_mem.em_combate and _RE_FIM_COMBATE_LLM.search(resposta_completa):
        algum_inimigo_vivo = any(
            d.get("estado") != "morto"
            for d in working_mem.inimigos_combate.values()
        )
        if settings.COMBATE_ENGINE_ATIVO and algum_inimigo_vivo:
            log.info("combate_fim_llm_ignorado_inimigos_vivos")
        else:
            working_mem.sair_combate()
            log.info("combate_encerrado_por_llm")

    # 7b. Auto-encerrar combate quando TODOS os inimigos estão mortos.
    # Garante que combates terminam mesmo quando o LLM usa frases de morte fora
    # do vocabulário de _RE_FIM_COMBATE_LLM (ex: "o último orc respira seu
    # último fôlego" sem dizer "combate termina"). Executado SÓ se o passo 7
    # não já chamou sair_combate() — por isso checa em_combate novamente.
    if working_mem.em_combate and working_mem.inimigos_combate:
        todos_mortos = all(
            d.get("estado") == "morto"
            for d in working_mem.inimigos_combate.values()
        )
        if todos_mortos:
            working_mem.sair_combate()
            log.info("combate_encerrado_auto_todos_mortos")

    # 7c. Timeout — combate sem nenhum inimigo registrado por 2+ rodadas, ou sem
    # menção a inimigos vivos por 3+ rodadas. Evita "combate eterno" quando a
    # cena migra silenciosamente para fora de combate (jogador foge, mestre
    # esquece de declarar). Sem isso, vinheta vermelha + animação de turno +
    # combat.md/saves.md injetados desperdiçam tokens indefinidamente.
    if working_mem.em_combate and texto_jogador.strip():
        # Inimigos vivos esperados na narração
        vivos = [
            d.get("nome", "")
            for d in working_mem.inimigos_combate.values()
            if d.get("estado") not in ("morto",)
        ]
        if not vivos:
            # Combate ativo sem NENHUM inimigo registrado. Isso acontece em dois
            # casos: (a) combate fantasma de verdade (cena migrou pra fora), ou
            # (b) combate legítimo cujo alvo a regra _RE_ALVO_ATAQUE não capturou
            # ("dei tapa em todo mundo", "ataco ele" — pronome rejeitado).
            # COMBAT-GHOST-2 (teste ao vivo 09/06): "Eu ataco ele e tento matar
            # ele" não registrava inimigo → o contador chegou a 4 enquanto o
            # jogador AINDA golpeava o cavaleiro, e o combate foi encerrado no
            # meio da luta (XP veio com em_combate=False). Fix: se o turno tem
            # ação de combate do jogador, ele está obviamente lutando — zera o
            # contador. Combate fantasma real (jogador conversando/andando) não
            # tem verbo de ataque e continua expirando em 4 rodadas.
            # COMBAT-GHOST-3 (playtest 21/07, sess-cac7ae249bb3): o turno que é
            # SÓ uma rolagem — `[Rolagem: d20 = 13]`, que é o que a toolbar manda
            # quando o Mestre pede ataque — não tem verbo de ataque nenhum, então
            # caía no else e incrementava o contador. O jogador estava trocando
            # socos e facadas ("acerta um golpe firme no peito do oponente") com
            # `em_combate=False` do turno 20 ao 23: sem combat.md, sem saves.md,
            # sem inimigo registrado, sem CA/dano/XP. Rolar É lutar.
            # COMBATE-FANTASMA-RAIZ (playtest 26/07, sess-68ebf02e5fa8): antes
            # havia só dois caminhos — verbo de ataque OU rolagem zeravam; o resto
            # incrementava. Uma rolagem ZERAR é forte demais: `[Rolagem: d20 = 13]`
            # é o que a toolbar manda tanto pra ataque quanto pra PERSUASÃO. Num
            # jantar em Kaelmünd o jogador rolou Persuasão de tempos em tempos e o
            # contador nunca chegou a 4 — resultado: em_combate=True com
            # inimigos_combate={} por ~19 turnos. Como `_beat_turno_inimigo` aborta
            # sem inimigo (`if not vivos: return`), ele ficou INVULNERÁVEL (HP 28/28
            # em 45 turnos), e o combate fantasma ainda desligou o extractor de NPC,
            # o dossiê, a assinatura de voz e inflou o pacing até 10.
            #
            # Agora são TRÊS caminhos. Verbo de ataque continua zerando (é prova de
            # luta — COMBAT-GHOST-2/3 dependem disso). Rolagem apenas SEGURA: não
            # zera, não incrementa — ela é ambígua, então não conta pra nenhum lado.
            # Só turno sem verbo e sem rolagem incrementa. Em luta real o jogador
            # ataca; num jantar as falas comuns fazem o contador subir e expirar.
            if _RE_COMBATE_JOGADOR.search(texto_jogador):
                working_mem.rodadas_sem_acao_inimigo = 0
            elif not _e_turno_de_rolagem(texto_jogador):
                working_mem.rodadas_sem_acao_inimigo += 1
            if working_mem.rodadas_sem_acao_inimigo >= 4:
                working_mem.sair_combate()
                log.info("combate_encerrado_sem_inimigos_vivos")
        else:
            # Algum inimigo vivo precisa ser mencionado na narração
            resp_lower = resposta_completa.lower()
            mencionado = any(n.lower() in resp_lower for n in vivos if n)
            # Mesma razão do ramo acima (COMBAT-GHOST-3): quem está rolando dado
            # não migrou pra fora da cena de combate.
            if mencionado or _e_turno_de_rolagem(texto_jogador):
                working_mem.rodadas_sem_acao_inimigo = 0
            else:
                working_mem.rodadas_sem_acao_inimigo += 1
                if working_mem.rodadas_sem_acao_inimigo >= 3:
                    working_mem.sair_combate()
                    log.info("combate_encerrado_timeout_sem_mencao")

    # 7d. Decay das cartas de improviso — após 5 turnos sem uso explícito, descarta.
    # Sem isso o prompt carrega 3 cartas (~260 chars) todo turno mesmo se o mestre
    # nunca as invoca, queimando 2-3k tokens em sessão de 1h.
    # CRIT-4: só decay em turno real do jogador — abertura/reconexão NÃO conta.
    if working_mem.cartas_improviso and texto_jogador.strip() and working_mem.decay_cartas():
        log.info("cartas_improviso_descartadas", motivo="decay 5 turnos sem uso")

    # CRIT-4: steps 8 e 9 só rodam em turnos REAIS do jogador. A abertura e
    # reconexões chamam aplicar_pos_turno(wm, "", resposta_intro) — sem guard,
    # essas chamadas incrementavam turnos_sem_tensao e mexiam no pacing sem
    # ter havido ação do jogador, causando drift cumulativo em reconexões e
    # PACING [BAIXO] disparado cedo demais.
    if texto_jogador.strip():
        # 8-9. Tensão narrativa + Pacing Meter (Feat 5), calibração 09/06/26
        # (respiração pós-combate, drenagem de pico, arco da sessão) — tudo
        # centralizado em NarrativeState.ajustar_pacing(), única fonte de
        # verdade (era duplicado inline aqui, valores tinham divergido do
        # método testado — auditoria de dead code de 01/07).
        # PACING-INTEGRADOR-1 (26/07): o meter passa a andar por EVENTO, não pela
        # flag. `em_combate` sozinho mentia — no playtest a flag ficou ligada ~19
        # turnos numa cena de jantar e levou o pacing de 0.4 a 10.0 com o jogador
        # em HP cheio o tempo todo. Perigo é dano e morte, não estar "em combate".
        #
        # O dano é lido da RESPOSTA por regex em vez do HP porque o `[DANO]` só é
        # aplicado no step ~16, depois deste — ler o HP aqui pegaria o valor do
        # turno anterior. Custo zero e sem reordenar o pipeline.
        _eventos_pacing: list[str] = []
        if _RE_DANO.search(resposta_completa):
            _eventos_pacing.append("dano_no_jogador")
        if _RE_INIMIGO_MORTO_MARKER.search(resposta_completa):
            _eventos_pacing.append("abate")
        working_mem.ajustar_pacing(
            em_combate=working_mem.em_combate,
            saiu_combate_recentemente=working_mem.saiu_combate_recentemente,
            trust_mudou=mudancas_trust,
            eventos=_eventos_pacing,
        )
        log.debug("pacing_atualizado", nivel=round(working_mem.pacing_nivel, 1))

        # 9b. Perfil do jogador (Ritual P2) — classifica o estilo do turno.
        # Combate > social (trust mudou OU verbo social) > exploração.
        if _RE_COMBATE_JOGADOR.search(texto_jogador):
            working_mem.narrative.registrar_estilo("combate")
        elif mudancas_trust or _RE_ACAO_SOCIAL.search(texto_jogador):
            working_mem.narrative.registrar_estilo("social")
        else:
            working_mem.narrative.registrar_estilo("exploracao")

        # 9c. Iniciativa de NPC (Mundo Vivo P2) — em cena calma, um NPC com
        # agenda age por conta própria. One-shot consumido pelo prompt_builder.
        working_mem.narrative.avaliar_iniciativa_npc(
            list(working_mem.npcs_presentes), working_mem.em_combate
        )

    # 10. Fios Soltos (Feat 1) — coleta [FIO: ...] da resposta do LLM
    for m in _RE_FIO.finditer(resposta_completa):
        fio = m.group(1).strip()
        if fio and working_mem.adicionar_fio(fio):
            log.info("fio_solto_registrado", fio=fio[:60])

    # 11. Cliffhanger (Feat 2) — captura [CLIFFHANGER: ...] da resposta do LLM
    for m in _RE_CLIFFHANGER.finditer(resposta_completa):
        ch = m.group(1).strip()
        if ch:
            working_mem.cliffhanger_pendente = ch
            log.info("cliffhanger_registrado", texto=ch[:80])
            break  # Máx 1 cliffhanger por turno — o último vence

    # 12. Agenda NPC (Feat 3) — coleta [AGENDA: npc-id → plano]
    # Cap de 8 agendas ativas (eviction oldest-first) vive em
    # NarrativeState.atualizar_agenda() — sem esse teto, sessões longas com
    # muitos NPCs namedropped acumulam agendas indefinidamente e inflam o
    # prompt em ~30-50 tokens por entrada extra.
    for m in _RE_AGENDA.finditer(resposta_completa):
        npc_id = m.group(1).strip().lower()
        plano = m.group(2).strip()
        if npc_id and plano:
            working_mem.atualizar_agenda(npc_id, plano)
            log.info("agenda_npc_atualizada", npc_id=npc_id, plano=plano[:60])

    # 13. Consequências visíveis (Feature 3) — coleta [CONSEQUÊNCIA: efeito duradouro]
    # Efeitos que persistem além da cena: NPCs mortos, alianças, locais destruídos,
    # reputação alterada. Lista circular de máx 5 via registrar_consequencia().
    for m in _RE_CONSEQUENCIA.finditer(resposta_completa):
        consequencia = m.group(1).strip()
        if consequencia and not any(consequencia in ex for ex in working_mem.log_consequencias):
            working_mem.registrar_consequencia(consequencia)
            log.info("consequencia_registrada_llm", texto=consequencia[:80])

    # 13.5. Economia — ouro, loot, mercado.
    # Idempotência: cada marcador é processado uma vez por turno. Não há buffer
    # entre turnos, então re-aplicar a mesma resposta dobraria o efeito (ok pq
    # cada resposta é única no tempo).
    #
    # Autoridade-primeiro (Economia/Loot, 1ª instância fora do combate — decisão
    # de 30/06): antes, [OURO: -N] aplicava `max(0, gold - N)` sem checar fundos —
    # narração dizia "pagou 500", o jogador só perdia os 50 que tinha e ficava em
    # 0, em silêncio (descolamento narração×estado, mesma classe do HP-desync do
    # combate). Agora `resolver_custo_ouro` é a autoridade: ganho sempre aplica;
    # custo só aplica INTEIRO se há fundos, senão REJEITA por completo (ouro
    # intacto) em vez de clampar parcial. Preço/regateio continuam do Mestre —
    # a engine só valida o valor já decidido, não inventa quanto custa nada.
    _intent_economia = classificar_intent_economia(texto_jogador)
    if _intent_economia:
        log.info("intent_economia_detectada", intent=_intent_economia)

    for m in _RE_OURO.finditer(resposta_completa):
        sinal = m.group(1)
        try:
            qtd = int(m.group(2))
        except ValueError:
            continue
        if sinal == "-":
            qtd = -qtd
        novo_gold, sucesso = resolver_custo_ouro(working_mem.gold, qtd)
        working_mem.gold = novo_gold
        if sucesso:
            log.info("ouro_alterado", delta=qtd, novo=working_mem.gold,
                     motivo=m.group(3)[:60])
        else:
            log.warning("ouro_rejeitado_fundos_insuficientes", delta=qtd,
                        gold_atual=working_mem.gold, motivo=m.group(3)[:60])

    # ROB-4: teto de 50 itens e truncamento em 80 chars para evitar prompt inflation.
    # O sync_inventory do WebSocket já aplica esses limites para edições manuais;
    # este bloco espelha a mesma política para itens adicionados pelo LLM via [LOOT:].
    _MAX_INVENTARIO = 50
    for m in _RE_LOOT.finditer(resposta_completa):
        item = m.group(1).strip()[:80]  # trunca nomes extravagantes do LLM
        if item and item.lower() not in (i.lower() for i in working_mem.player_inventory):
            if len(working_mem.player_inventory) >= _MAX_INVENTARIO:
                log.warning("loot_ignorado_inventario_cheio", item=item[:60],
                            total=len(working_mem.player_inventory))
                continue
            working_mem.player_inventory.append(item)
            log.info("loot_adicionado", item=item[:60])

    for m in _RE_PERDEU.finditer(resposta_completa):
        item_alvo = m.group(1).strip().lower()
        for i, item_existente in enumerate(working_mem.player_inventory):
            if item_existente.lower() == item_alvo:
                removido = working_mem.player_inventory.pop(i)
                log.info("item_removido", item=removido[:60])
                break

    if _RE_MERCADO.search(resposta_completa):
        working_mem.em_mercado = True
        working_mem.turnos_sem_mercado = 0
        log.info("mercado_aberto")
    elif _RE_FIM_MERCADO.search(resposta_completa):
        working_mem.em_mercado = False
        working_mem.turnos_sem_mercado = 0
        log.info("mercado_fechado")
    elif working_mem.em_mercado:
        # Sem [MERCADO] nem [FIM_MERCADO] neste turno — incrementa contador de inatividade.
        # Se o LLM "esqueceu" de emitir [FIM_MERCADO] ao sair da loja, o botão de venda
        # fecha automaticamente após 3 turnos sem reconfirmação (evita UI travada).
        working_mem.turnos_sem_mercado += 1
        if working_mem.turnos_sem_mercado >= 3:
            working_mem.em_mercado = False
            working_mem.turnos_sem_mercado = 0
            log.info("mercado_fechado_auto_timeout")

    # 13.6. Companions/party — aliados controlados.
    for m in _RE_COMPANION_ADD.finditer(resposta_completa):
        try:
            cid = m.group(1).strip().lower()
            nome = m.group(2)
            tipo = m.group(3)
            hp = int(m.group(4))
            ca = int(m.group(5))
            atq = m.group(6)
            dano = m.group(7)
        except (ValueError, AttributeError):
            continue
        if cid:
            ja_existia = cid in working_mem.companions
            working_mem.registrar_companion(cid, nome, tipo, hp, ca, atq, dano)
            log.info("companion_registrado", id=cid, nome=nome, tipo=tipo)
            # Autoridade social (decisão 02/07): juntar-se à jornada é ato
            # positivo — trust sobe e o afeto persiste. Evento acumulado pro
            # websocket drenar (toast + afeto Neo4j). Só na 1ª vez — a
            # re-declaração do mesmo companion não re-paga.
            if not ja_existia:
                from engine.authority.social import melhorar_relacao_companion
                working_mem.scene.eventos_relacao_turno.append(
                    melhorar_relacao_companion(working_mem, cid, nome)
                )

    for m in _RE_COMPANION_HP.finditer(resposta_completa):
        cid = m.group(1).strip().lower()
        try:
            delta = int(m.group(2))
        except ValueError:
            continue
        ok = working_mem.ajustar_hp_companion(cid, delta)
        if ok:
            log.info("companion_hp_ajustado", id=cid, delta=delta,
                     hp_novo=working_mem.companions[cid].get("hp"))
            # Autoridade social: curar companion sobe afeto persistente
            # (sem toast — micro-evento, toast a cada poção seria spam).
            if delta > 0:
                from engine.authority.social import registrar_cura_companion
                working_mem.scene.eventos_relacao_turno.append(
                    registrar_cura_companion(cid)
                )

    for m in _RE_COMPANION_REMOVE.finditer(resposta_completa):
        cid = m.group(1).strip().lower()
        if working_mem.remover_companion(cid):
            log.info("companion_removido", id=cid)

    # 14. Combate tático — posições de inimigos e movimento do jogador.
    # Só processa se estamos em combate (posições fora de combate são
    # irrelevantes e podem confundir o estado).
    if working_mem.em_combate:
        for m in _RE_POSICAO.finditer(resposta_completa):
            npc_id = m.group(1).strip().lower()
            try:
                dist = int(m.group(2))
            except ValueError:
                continue
            cobertura = bool(m.group(3))
            if npc_id:
                working_mem.registrar_posicao(npc_id, dist, cobertura=cobertura)
                log.info("posicao_registrada", npc_id=npc_id, dist=dist, cobertura=cobertura)

        for m in _RE_MOVIMENTO.finditer(resposta_completa):
            try:
                ft = int(m.group(1))
            except ValueError:
                continue
            motivo = m.group(2).strip() or "movimento"
            consumido = working_mem.aplicar_movimento(ft)
            log.info("movimento_consumido", ft=consumido, motivo=motivo,
                     restante=working_mem.movimento_restante_ft)

    # 15. Repetition Guard — coleta [ANCORA: fato] para evitar re-narração em sessões longas.
    for m in _RE_ANCORA.finditer(resposta_completa):
        ancora = m.group(1).strip()
        if ancora:
            working_mem.registrar_ancora(ancora)
            log.info("ancora_registrada", texto=ancora[:80])

    # 15c. Diretor de Arco (passo 3b, caminho B): o jogador DECLAROU um segredo e
    # o Mestre confirma via [SEGREDO_REVELADO: id] → entra em secrets_revelados
    # (alimenta F4). O caminho A ("NPC honesto conta") vive no context_builder.
    for m in _RE_SEGREDO_REVELADO.finditer(resposta_completa):
        sid = m.group(1).strip().lower()
        if sid:
            working_mem.secrets_revelados.add(sid)
            log.info("segredo_revelado_marker", secret_id=sid)

    # 15b. Repetition Guard SENSORIAL (REPETICAO-FRIO) — registra as imagens de
    # ambiente/clima desta narração pra o prompt do próximo turno pedir variação.
    for imagem in extrair_imagens_ambiente(resposta_completa):
        if working_mem.registrar_ambiente(imagem):
            log.info("ambiente_registrado", imagem=imagem[:80])

    # 16. Assinaturas de voz de NPC — [VOZ: npc-id|pitch|rate] define parâmetros TTS por NPC.
    # Cap de 20 vozes por sessão (eviction oldest) vive em PartyState.registrar_voz_npc()
    # — sessão longa pode introduzir 30+ NPCs falantes; sem cap, dict cresce indefinidamente.
    for m in _RE_VOZ.finditer(resposta_completa):
        npc_id = m.group(1).strip().lower()
        pitch_raw = m.group(2).strip()
        rate_raw = m.group(3).strip()
        pitch = _clamp_pitch(pitch_raw)
        rate = _clamp_rate(rate_raw)
        if npc_id and working_mem.registrar_voz_npc(npc_id, pitch, rate):
            log.info(
                "voz_npc_registrada",
                npc_id=npc_id, pitch=pitch, rate=rate,
                pitch_raw=pitch_raw if pitch != pitch_raw else None,
                rate_raw=rate_raw if rate != rate_raw else None,
            )

    # 16b. Gasto de class feature — [FEATURE_GASTA: id] decrementa usos_atual.
    # Só features com usos finitos (usos_max > 0); ilimitadas (-1) são noop.
    for m in _RE_FEATURE_GASTA.finditer(resposta_completa):
        fid = m.group(1).strip().lower()
        feat = working_mem.class_features.get(fid)
        if feat and feat.get("usos_max", 0) > 0 and feat.get("usos_atual", 0) > 0:
            feat["usos_atual"] -= 1
            feat["disponivel"] = feat["usos_atual"] > 0
            log.info("feature_gasta_llm", feature=fid, usos_restantes=feat["usos_atual"])

    # 16c. Dano/cura no jogador — [DANO: -N] / [CURA: +N] (Pilar Perigo).
    # Soma todas as ocorrências do turno; clamps no substate. A 0 PV o
    # prompt_builder injeta o protocolo da death_policy no próximo turno.
    # DANO-IMPROVISADO-1: em combate 100% improvisado (sem ficha SRD) limita o
    # dano por golpe a um teto CR≈0 — evita o 8B inventar one-shot (dano=17).
    #
    # ENGINE-DANO-DUP-1 (playtest 05/07, sess-6e8a5b525bb2): quando a ENGINE já
    # resolveu o turno (resolver_turno_ataque_jogador rodou executar_turno_inimigos
    # e aplicou o dano do inimigo DIRETO no PJ antes do LLM narrar), o Mestre segue
    # o hábito normal de narração e emite [DANO: -N] pra descrever o MESMO golpe —
    # e este loop reaplicava, dobrando o dano (HP caindo 2× o esperado). O gate
    # deve_zerar_dano_extractor já existia pra isso, mas só protegia o extractor de
    # prosa (extrair_estado_combate) — o marker explícito aqui não tinha guard
    # nenhum. Quando a engine resolveu, [DANO]/[CURA] narrados são ECO do que já
    # aconteceu: descarta sem aplicar, só loga pra telemetria.
    if engine_resolveu_turno:
        for m in _RE_DANO.finditer(resposta_completa):
            log.info(
                "dano_narrado_descartado_engine_resolveu",
                dano=m.group(1),
                motivo=m.group(2).strip()[:60] or None,
            )
        for m in _RE_CURA.finditer(resposta_completa):
            log.info("cura_narrada_descartada_engine_resolveu", cura=m.group(1))
    else:
        teto_improvisado = (
            _DANO_MAX_INIMIGO_IMPROVISADO if _combate_sem_ficha_srd(working_mem) else None
        )
        for m in _RE_DANO.finditer(resposta_completa):
            dano = int(m.group(1))
            if teto_improvisado is not None and dano > teto_improvisado:
                log.info(
                    "dano_improvisado_clampado",
                    bruto=dano,
                    teto=teto_improvisado,
                    motivo=m.group(2).strip()[:60] or None,
                )
                dano = teto_improvisado
            antes = working_mem.player_hp
            depois = working_mem.character.aplicar_dano(dano)
            _motivo = m.group(2).strip()[:80]
            log.info(
                "dano_jogador", dano=dano, hp=f"{antes}->{depois}",
                motivo=_motivo or None,
            )
            # A causa acompanha o número até o jogador — ver DANO-SEM-CAUSA-1.
            working_mem.character.registrar_evento_vital(
                "dano", dano, _motivo, depois, working_mem.player_hp_max
            )
            if depois == 0:
                log.warning("jogador_a_zero_hp", policy=working_mem.death_policy)
        for m in _RE_CURA.finditer(resposta_completa):
            antes = working_mem.player_hp
            _cura = int(m.group(1))
            depois = working_mem.character.aplicar_cura(_cura)
            log.info("cura_jogador", cura=_cura, hp=f"{antes}->{depois}")
            working_mem.character.registrar_evento_vital(
                "cura", _cura, "", depois, working_mem.player_hp_max
            )

    # 16d. Cicatriz permanente — [CICATRIZ: texto] (dedup + cap no substate).
    # Gate de gatilho (playtest 03/07): o LLM emitia cicatriz em momento
    # questionável e a engine confiava cegamente. Regra travada: só registra se
    # o jogador chegou a 0 PV nesta sessão OU está a ≤25% do HP máximo neste
    # turno. O [DANO] do mesmo turno já foi aplicado no step 16c (logo acima)
    # — então o golpe quase-fatal do próprio turno conta pro gate.
    for m in _RE_CICATRIZ.finditer(resposta_completa):
        hp_atual = working_mem.player_hp
        hp_max = working_mem.player_hp_max
        gatilho = working_mem.character.chegou_a_zero_hp or (
            hp_max > 0 and hp_atual <= 0.25 * hp_max
        )
        if not gatilho:
            log.info(
                "cicatriz_rejeitada_sem_gatilho",
                cicatriz=m.group(1).strip()[:60],
                hp=f"{hp_atual}/{hp_max}",
            )
            continue
        if working_mem.character.registrar_cicatriz(m.group(1)):
            working_mem.narrative.registrar_cronica(f"🩸 Cicatriz: {m.group(1).strip()[:80]}")
            log.info("cicatriz_registrada", cicatriz=m.group(1).strip()[:60])

    # 16e. Relógios de Ameaça — criação e avanço dramático pelo LLM.
    for m in _RE_RELOGIO.finditer(resposta_completa):
        rid = m.group(1).strip().lower()
        seg = int(m.group(3)) if m.group(3) else 6
        # PLAY5-FRONTS: se o id casa com uma ameaça latente, ATIVA preservando os
        # segmentos/filled autorais; senão cria um relógio improvisado novo.
        if rid in working_mem.narrative.fronts_latentes:
            if working_mem.narrative.ativar_front_latente(rid):
                log.info("front_latente_ativado", relogio=rid)
        elif working_mem.narrative.criar_relogio(rid, m.group(2), seg):
            log.info("relogio_criado", relogio=rid, nome=m.group(2).strip()[:40], max=seg)
    for m in _RE_RELOGIO_AVANCA.finditer(resposta_completa):
        rid = m.group(1).strip().lower()
        if working_mem.narrative.avancar_relogio(rid):
            log.info("relogio_estourou", relogio=rid)
        else:
            log.info("relogio_avancou", relogio=rid)

    # 17. Mudança de cena (CENA-1) — [CENA: local-id|Nome|hora] atualiza local/hora
    # (sync, sem I/O). A re-inferência de NPCs do novo local (Neo4j, async) é feita
    # pelo caller via reinferir_npcs_se_mudou_cena() após este pipeline. Primeiro
    # [CENA] do turno vence — um deslocamento por turno.
    for m in _RE_CENA.finditer(resposta_completa):
        novo_id = m.group(1).strip()
        nome = m.group(2).strip()
        hora = (m.group(3) or "").strip()
        if working_mem.scene.aplicar_cena(novo_id, nome, hora):
            working_mem.narrative.registrar_cronica(f"📍 Chegada: {nome or novo_id}")
            log.info("cena_mudou", local=working_mem.location_id, nome=nome, hora=hora or None)
            # Trocar de LOCAL encerra um combate em andamento — o encontro anterior
            # ficou para trás. Evita inimigos/posições do local antigo vazarem para
            # a nova cena. (Mudar só a hora no mesmo local não cai aqui.)
            if working_mem.em_combate:
                working_mem.sair_combate()
                log.info("combate_encerrado_mudanca_cena")
            # GRIM-REATIVA-1: a escalação reativa tem escopo de CENA — trocar
            # de local encerra a cena sombria (o massacre ficou pra trás).
            if working_mem.scene.cena_sombria_reativa:
                working_mem.scene.cena_sombria_reativa = False
                log.info("cena_sombria_reativa_limpa_mudanca_cena")
            # Mundo Vivo: viagem custa tempo — relógios avançam, mas com cadência
            # (a cada 2ª troca de cena) pra não encher rápido num hub social.
            estourados = working_mem.narrative.tick_relogios_viagem()
            if estourados:
                log.info("relogios_tick_viagem", estourados=estourados)
        break

    # 17b. Entrada de NPC na cena — [NPC: id|Nome] adiciona a presentes +
    # apresentados (idempotente). Roda DEPOIS do [CENA] e registra os ids num
    # campo transiente: se o mesmo turno trocou de local, a re-inferência async
    # (que SUBSTITUI npcs_presentes) faz união com estes — NPC improvisado pelo
    # mestre não é apagado pelo Neo4j.
    working_mem.scene.npcs_introduzidos_turno.clear()
    # NPC-DUP-2: dedup por chave tolerante a epíteto — '[NPC: brennan-sem-vila]'
    # quando 'brennan' já está na cena é o mesmo NPC com a alcunha do local.
    # NPC-DUP-3: chave secundária por conjunto de tokens — pega o mesmo NPC
    # descritivo com tokens reordenados ('taverna-kaelmund-monge' ↔
    # 'monge-da-taverna-kaelmund'). Chave vazia nunca entra no set.
    # NPC-DEDUP-CANONICO-1 (playtest 06/07): universo de dedup inclui o registro
    # canônico da SESSÃO INTEIRA (não só npcs_presentes atual) — sem isso, um
    # NPC que saiu de presentes (re-inferência de cena) era re-registrado do
    # zero. Mais a chave TERCIÁRIA por distância de edição, que pega erro de
    # grafia do STT/LLM ('grimbol'/'grimbold') que nenhuma chave exata colapsa.
    _universo_ids = (
        set(working_mem.npcs_presentes)
        | set(getattr(working_mem.scene, "npc_registro", {}).keys())
        | set(getattr(working_mem.scene, "npc_aliases", {}).keys())
    )
    _presentes_chaves = {_chave_dedup(p) for p in _universo_ids}
    _presentes_conjuntos = {c for c in (_chave_conjunto(p) for p in _universo_ids) if c}
    _mapa_canon_para_id = {_canonico(p): p for p in _universo_ids}
    _loc_id = str(getattr(working_mem, "location_id", "") or "")
    _loc_nome = str(getattr(working_mem, "location_nome", "") or "")
    for m in _RE_NPC_ENTRA.finditer(resposta_completa):
        npc_id = m.group(1).strip().lower()
        if not npc_id:
            continue
        chave = _chave_dedup(npc_id)
        if chave in _presentes_chaves:
            # RENAME-BLOQUEADO-1 (playtest 26/07): este `continue` seco descartava
            # o NOME que vinha no marcador. Quem já estava em cena era imutável —
            # o Mestre apresentava o NPC como "Kael" e a engine seguia reinjetando
            # o descritor ("Guardião da Noite") todo turno, até o Mestre desistir e
            # usar o descritor de volta. Sintoma relatado: "trouxe o guardião com
            # outro nome sendo que já tinha apresentado como Kael".
            # O dedup de PRESENÇA continua certo (não duplicar a cadeira na cena);
            # o que ele não pode é bloquear a atualização de IDENTIDADE.
            _nome_marcado = (m.group(2) or "").strip()[:60]
            if _nome_marcado and parece_nome_proprio(_nome_marcado):
                _id_existente = _mapa_canon_para_id.get(_canonico(npc_id), npc_id)
                try:
                    # registrar_npc só promove quando o nome atual está vazio ou
                    # quando o novo é próprio e o antigo não era — nunca rebaixa
                    # um nome já batizado de volta pra descritor.
                    registrar_npc(working_mem, _id_existente, _nome_marcado)
                    log.info("npc_nome_revelado_em_cena",
                             id=_id_existente, nome=_nome_marcado)
                except Exception as _e_rn:
                    log.warning("npc_rename_falhou",
                                id=_id_existente, erro=str(_e_rn)[:80])
            continue  # mesmo NPC (talvez só com epíteto) já presente
        conjunto = _chave_conjunto(npc_id)
        if conjunto and conjunto in _presentes_conjuntos:
            log.info("npc_marcador_dup_tokens_reordenados", id=npc_id)
            continue  # mesmo NPC descritivo com tokens reordenados
        _variante = _variante_proxima(npc_id, _mapa_canon_para_id)
        if _variante:
            log.info("npc_marcador_dedup_variante_edicao", id=npc_id, existente=_variante)
            continue
        # PLAYTEST 24/06: barra LUGAR/DEIDADE/anônimo virando NPC (mesmo via marcador).
        if _e_entidade_invalida(npc_id, _loc_id, _loc_nome):
            log.info("npc_marcador_entidade_invalida", id=npc_id)
            continue
        working_mem.npcs_presentes.append(npc_id)
        _presentes_chaves.add(chave)
        if conjunto:
            _presentes_conjuntos.add(conjunto)
        _mapa_canon_para_id[_canonico(npc_id)] = npc_id
        working_mem.scene.npcs_apresentados.add(npc_id)
        working_mem.scene.npcs_introduzidos_turno.append(npc_id)
        log.info("npc_entrou_cena", npc=npc_id, nome=(m.group(2) or "").strip() or None)
        # F6: registra o encontro na crônica (evento determinístico).
        _nome_npc = ((m.group(2) or "").strip() or npc_id.replace("-", " ").title())[:60]
        # NPC-IDENTIDADE (05/07): entrada canônica — a retrato_seed nasce aqui
        # e sobrevive a rename futuro (rosto estável). Try/except: stubs de
        # teste sem scene.npc_registro não podem derrubar o pipeline.
        try:
            registrar_npc(working_mem, npc_id, _nome_npc)
        except Exception as _e_reg:
            log.warning("npc_registro_falhou", id=npc_id, erro=str(_e_reg)[:80])
        working_mem.narrative.registrar_cronica(f"🤝 Conheceu {_nome_npc}")

    # Teto de npcs_presentes (backstop pro que escapa do filtro) — evita os 15
    # NPCs-lixo do playtest 24/06.
    _capar_npcs_presentes(working_mem)

    # N2/F3: garante voz TTS determinística pra cada NPC presente (gênero-safe).
    garantir_vozes_npcs(working_mem)

    # 17d. DIRETOR DE ARCO (passo 4): avalia se um final de campanha disparou e
    # conduz normal → clímax → epílogo → concluída. A transição é aqui (pós-turno)
    # porque o prompt do turno SEGUINTE é quem injeta a diretiva. Falha silenciosa:
    # arco quebrado nunca derruba o turno.
    if texto_jogador.strip():
        try:
            from engine.authority.arco import conduzir_arco
            conduzir_arco(working_mem)
        except Exception as _e_arco:
            log.warning("arco_conduzir_falhou", erro=str(_e_arco)[:100])

    # 17c. CANON-MORTOS-2 (A/B 17/07): reconcilia abates pendentes. O kill da
    # engine roda pré-LLM — se o combatente só virou conhecido-da-cena AGORA
    # (extração/[NPC] acima), a flag `morto` não foi gravada na hora. Segunda
    # tentativa pós-registro; quem continua desconhecido é descartado com log
    # (inimigo puro de combate não polui o registro — decisão original mantida).
    pendentes = list(getattr(working_mem, "mortos_pendentes", []) or [])
    if pendentes:
        try:
            from engine.npc.identity import marcar_morto
            for _morto_id in pendentes:
                if marcar_morto(working_mem, _morto_id) is None:
                    log.info("canon_morto_descartado_desconhecido", id=_morto_id)
        except Exception as _e_morto:
            log.warning("canon_morto_reconciliacao_falhou", erro=str(_e_morto)[:80])
        working_mem.mortos_pendentes.clear()

    return mudancas_trust


def garantir_vozes_npcs(working_mem: Any) -> int:
    """Atribui voz TTS DETERMINÍSTICA (pitch/rate) a cada NPC presente sem voz.

    N2/F3 (playtest 24/06): `npc_vozes` ficava VAZIO porque o LLM esquece de
    emitir `[VOZ]` → tudo soava como o narrador. Aqui a engine preenche de forma
    determinística (engine/npc/persona.assinatura_tts) — gênero-safe (varia a
    voz-base, não troca de voz). Só atribui a quem ainda NÃO tem voz: um `[VOZ]`
    explícito do Mestre, se vier, é respeitado. Retorna quantas vozes atribuiu.
    """
    from engine.npc.persona import assinatura_tts
    jogador = _chave_dedup(str(getattr(working_mem, "player_name", "")))
    atribuidas = 0
    for nid in list(getattr(working_mem, "npcs_presentes", [])):
        if nid in working_mem.npc_vozes or _chave_dedup(nid) == jogador:
            continue
        # NPC-IDENTIDADE (05/07): a assinatura deriva da SEED estável (id
        # original de criação), não do id atual — NPC renomeado via name-reveal
        # mantém a MESMA voz (fundir_estado já migrou a entrada existente; este
        # caminho só roda pra quem ainda não tem voz, e precisa gerar a mesma
        # que geraria antes do rename). Mesma cura do retrato.
        try:
            from engine.npc.identity import retrato_seed
            semente = retrato_seed(working_mem, nid)
        except Exception:
            semente = nid  # stub de teste sem scene.npc_registro
        assn = assinatura_tts(semente)
        if assn:
            working_mem.npc_vozes[nid] = assn
            atribuidas += 1
    return atribuidas


async def reinferir_npcs_se_mudou_cena(
    working_mem: WorkingMemory,
    context_builder: Any,
) -> None:
    """Re-infere os NPCs presentes via Neo4j quando o turno trocou de local.

    Complemento async de `aplicar_pos_turno` (sync): a chamada de I/O ao grafo
    fica aqui, invocada pelo WebSocket e pelo REST `/turn` logo após o pipeline.
    Consome o flag one-shot setado por `SceneState.aplicar_cena()`.

    Por que separado: o pipeline é síncrono (e tem 60+ testes que dependem disso);
    a re-inferência precisa de await no Neo4j. Sem isto, os NPCs do local inicial
    permaneciam no prompt a sessão inteira (CENA-1).

    Armadilha: NUNCA lançar — Neo4j pode estar offline; o jogo segue com os NPCs
        antigos (degradação graciosa) em vez de travar o turno.
    """
    if not working_mem.scene.consumir_cena_mudou():
        return
    try:
        novos = await context_builder.inferir_npcs_presentes(working_mem.location_id)
        # União com NPCs introduzidos via [NPC] neste mesmo turno — o mestre
        # improvisou alguém que o grafo não conhece; a substituição não pode apagá-lo.
        introduzidos = [
            n for n in working_mem.scene.npcs_introduzidos_turno if n not in novos
        ]
        working_mem.npcs_presentes = novos + introduzidos
        log.info(
            "npcs_reinferidos_mudanca_cena",
            location=working_mem.location_id,
            total=len(novos),
            preservados=len(introduzidos),
        )
    except Exception as e:
        log.warning("reinferir_npcs_falhou", erro=str(e)[:120])


async def aplicar_afeto_npcs(
    resposta_completa: str,
    neo4j_client: Any,
) -> None:
    """Extrai marcadores [AFETO: npc-id|campo|delta] e persiste no Neo4j.

    Por que existe: estado afetivo de NPC (afeto/medo/respeito/rancor) precisa
        de persistência entre sessões. Neo4j é a fonte verdadeira; WorkingMemory
        não armazena — o LLM recebe via semantic_memory quando consulta o NPC.

    Armadilha: NUNCA lançar exceção — Neo4j pode estar offline; o jogo deve continuar.
        Chamada fire-and-forget em websocket.py via asyncio.create_task.
    """
    for m in _RE_AFETO.finditer(resposta_completa):
        npc_id = m.group(1).strip().lower()
        campo = m.group(2).strip().lower()
        try:
            delta = int(m.group(3).strip())
        except ValueError:
            continue
        if npc_id and campo and delta != 0:
            await neo4j_client.atualizar_afeto_npc(npc_id, campo, delta)


def aplicar_xp_e_detectar_level_up(
    working_mem: WorkingMemory, resposta_completa: str
) -> dict[str, int | list[str]] | None:
    """Extrai [XP: +N motivo] da resposta do LLM e aplica progressão.

    Separado de `aplicar_pos_turno` porque o caller precisa do resumo do level
    up pra emitir como mensagem WebSocket dedicada (modal no frontend).

    Returns:
        Dict resumo do level up se o jogador subiu de nível, ou None se só
        acumulou XP sem progredir. O resumo vem direto de `aplicar_level_up`.
    """
    from engine.progression import aplicar_level_up, calcular_novo_nivel

    ganhos: list[tuple[int, str]] = []
    _xp_vistos: set[tuple[int, str]] = set()  # dedup: mesmo marker duplicado na resposta
    for m in _RE_XP.finditer(resposta_completa):
        try:
            qtd = int(m.group(1))
        except ValueError:
            continue
        # XP-CLAMP-1 (A/B 17/07): [XP:] é SÓ bônus narrativo — guideline 25–100
        # no master_system.md. O LLM emitiu +400 por examinar um corpo e a engine
        # aceitou; abate/quest a engine já paga por fora, então marker acima de
        # 100 é sempre inflação. Clamp duro, com log pra telemetria.
        if qtd > _XP_MARKER_MAX:
            log.info("xp_marker_clampado", pedido=qtd, aplicado=_XP_MARKER_MAX)
            qtd = _XP_MARKER_MAX
        motivo = m.group(2).strip() or "ganho de experiência"
        chave = (qtd, motivo.lower())
        if chave in _xp_vistos:
            continue
        _xp_vistos.add(chave)
        ganhos.append((qtd, motivo))

    if ganhos:
        total = sum(q for q, _ in ganhos)
        working_mem.xp += total
        log.info("xp_ganho", total=total, ganhos=ganhos, xp_novo=working_mem.xp)

    # XP engine-first (decisão 01/07): o level-up é calculado SEMPRE, não só
    # quando o LLM emitiu [XP:] — a engine concede XP por conta própria (abate
    # via conceder_xp_abates_pendentes, quest via extractor) e esse XP também
    # precisa disparar o modal de level-up.
    novo_nivel = calcular_novo_nivel(working_mem.xp, working_mem.player_level)
    if novo_nivel > working_mem.player_level:
        # Imersão P4: level up é marco da crônica da sessão
        working_mem.narrative.registrar_cronica(f"⬆ Nível {novo_nivel} alcançado")
        return aplicar_level_up(working_mem, novo_nivel)
    return None
