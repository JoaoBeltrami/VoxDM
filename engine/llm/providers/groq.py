"""
Provider Groq — encapsula a chamada ao Groq SDK com modelo configurável.

Por que existe: o Groq tem cotas TPD separadas por modelo. Quando o 70B
    estoura, o 8B normalmente ainda tem quota. Cada instância dessa classe
    representa um modelo (ex: 70B versatile, 8B instant), e o router cascateia.
Dependências: groq SDK, structlog, config.
Armadilha: refusal do safety layer chega como 200 OK com texto começando por
    "não posso", "desculpe-me", etc. Detectamos e lançamos LLMRetriable
    com categoria=refusal para que o router caia pro próximo provider.

Exemplo:
    p70 = GroqProvider(nome="groq-70b", modelo="llama-3.3-70b-versatile")
    p8  = GroqProvider(nome="groq-8b",  modelo="llama-3.1-8b-instant")
    # Router as cascateia automaticamente.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog
from groq import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncGroq,
    InternalServerError,
    RateLimitError,
)

from config import settings
from engine.llm.amarelada import e_amarelada
from engine.llm.providers.base import BaseLLMProvider, LLMRetriable

log = structlog.get_logger(__name__)

# Prefixos de recusa do safety layer Groq — retorna 200 + texto refusal.
#
# ARMADILHA: expressões como "lamento", "não posso", "não consigo", "não é
# possível" são falas válidas de NPCs e narrador em D&D. Um guarda diz "não
# posso deixá-lo passar", um personagem diz "lamento sua perda", o mestre diz
# "não é possível atravessar sem a chave". Detectar isso como recusa causava
# cascata falsa e degradava a resposta para modelos menores.
#
# Regra de ouro: refusal real é quando o LLM quebra o personagem para referenciar
# sua própria natureza como modelo ou para recusar "ajudar" como assistente.
# Frases de ficção (NPCs, narrador, jogador) NUNCA são refusal.
_PREFIXOS_RECUSA = (
    # O LLM se identifica como IA/assistente — sempre quebra de personagem
    "como ia,", "como ia ", "como modelo", "como assistente de ia",
    "como assistente virtual", "como um modelo",
    # O LLM recusa explicitamente a TAREFA (não um NPC recusando uma ação)
    "não posso ajudar", "não consigo ajudar", "não posso gerar esse",
    "não posso criar esse", "não posso produzir", "não posso escrever esse",
    "sou incapaz de ajudar", "é contra as minhas",
    # Meta-commentary de IA
    "preciso esclarecer que", "devo informar que", "devo esclarecer que",
    "é importante notar que", "como uma ia,", "como uma inteligência",
    # Inglês — VoxDM é PT-BR; saída em inglês no início = modelo em modo safety
    "i cannot", "i'm unable to", "i can't help", "i must decline",
    "i won't be able", "i'm not able to help", "as an ai", "as a language model",
    "i'm sorry, but i", "i apologize, but i",
)

# Chars a coletar antes de checar recusa no stream Groq.
# 150 chars cobre a frase de recusa típica sem atrasar respostas normais.
_BUFFER_RECUSA = 150


def _e_recusa(texto: str) -> bool:
    txt = texto.lower().strip()
    return any(txt.startswith(p) for p in _PREFIXOS_RECUSA)


# Erros do SDK Groq que disparam fallback (recuperáveis).
_ERROS_RECUPERAVEIS = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
)

# Quota também aparece disfarçada de outros status codes — o Groq retorna
# 413 (Payload Too Large) quando o pedido excede TPM (tokens per minute),
# embora o body contenha "code: rate_limit_exceeded". Sem este detector,
# 413 escapava da cascata e o websocket caía sem tentar Gemini.
_PALAVRAS_QUOTA = (
    "rate_limit_exceeded",
    "tokens per minute",
    "tokens per day",
    "request too large",
    "payload too large",
    "quota",
)


def _e_quota_disfarcada(exc: BaseException) -> bool:
    """True quando o erro é rate-limit não-429 (ex: 413 TPM, 400 com 'quota')."""
    corpo = str(exc).lower()
    return any(kw in corpo for kw in _PALAVRAS_QUOTA)


# TOOL-FANTASMA-1 (playtest 01/08): o `openai/gpt-oss-20b` chamou uma ferramenta
# que ninguém ofereceu, e o Groq devolveu 400 "Tool choice is none, but model
# called a tool". O 400 caía no `raise` do `except APIError` — não é quota, não é
# rede — subia inteiro e MATAVA o turno. Gemini e 70B, que rodam o MESMO prompt
# sem problema, nunca eram tentados.
#
# É falha DO MODELO, não do nosso pedido: fallback-able por definição. Categoria
# própria ("modelo") por dois motivos — aparece separada na telemetria, e o
# cooldown só penaliza `rate_limit`, então um surto estocástico não tira o
# provider de circulação por 75s.
#
# Não reproduzido em 12 chamadas com o mesmo prompt (6 no 20b, 6 no 120b) — é
# intermitente. Frequência baixa não muda o desenho: turno morto é turno morto.
#
# MODELO-DESLIGADO-1 (pré-voo de 17/08): a MESMA porta deixou passar uma falha
# muito pior, e por meses ela seria fatal. O Groq desligou a família Llama de
# chat em 16/08/26 — o projeto rastreava só o `llama-3.1-8b-instant` e migrou o
# fallback, mas o PRIMÁRIO (`llama-3.3-70b-versatile`) foi junto. A partir daí
# TODA chamada devolvia 404 `model_not_found`; o 404 não casava com quota nem
# com a tool-fantasma, caía no `raise`, e o `gpt-oss-120b` — vivo, disponível e
# a duas linhas de distância na cascata — nunca era tentado. Cascata de cinco
# degraus servindo de nada porque o primeiro degrau evaporou em silêncio.
#
# Modelo que não existe é a definição de falha DO MODELO: é fallback-able, e a
# categoria "modelo" está certa aqui (não é quota, então não penaliza o provider
# com cooldown — os OUTROS slots Groq seguem saudáveis).
#
# As três frases abaixo são as do Groq LITERAIS, não exemplos inventados:
# "does not exist or you do not have access to it" é a de hoje; "decommissioned"
# é a que ele usa no aviso de desligamento; `model_not_found` é o code do JSON.
_PALAVRAS_FALHA_MODELO = (
    "tool choice is none",
    "model called a tool",
    "does not exist or you do not have access",
    "model_not_found",
    "decommissioned",
    "has been deprecated",
)


def _e_falha_do_modelo(exc: BaseException) -> bool:
    """True quando o erro é do MODELO (errático ou inexistente), não do pedido.

    Cobre duas famílias que têm o mesmo desfecho correto — cair pro próximo
    degrau: comportamento errático (TOOL-FANTASMA-1) e modelo desligado pelo
    provider (MODELO-DESLIGADO-1). Ambas são 4xx que NÃO são culpa do payload,
    então propagá-las mata um turno que o degrau seguinte atenderia sem esforço.
    """
    corpo = str(exc).lower()
    return any(kw in corpo for kw in _PALAVRAS_FALHA_MODELO)



def _extrair_usage(resp: Any) -> dict[str, int]:
    """Tokens da resposta, incluindo os gastos em RACIOCÍNIO quando houver.

    TOKENS-CEGOS (26/07): o projeto media latência e chars, nunca tokens — então
    "quantos turnos cabem no TPD" era conta de guardanapo. E há um caso em que a
    conta muda de figura: a família `openai/gpt-oss` gasta tokens num campo
    `reasoning` ANTES do `content`. O TPD dela é 2× o do 70B (200K vs 100K), mas
    isso só vale o dobro de sessão se ela não gastar o dobro por turno — e
    ninguém sabia. Aqui é onde o número passa a existir.

    Tolerante de propósito: a forma de `completion_tokens_details` varia entre
    versões do SDK e entre modelos (o 70B não tem raciocínio nenhum). Campo
    ausente vira 0, nunca exceção — telemetria não pode derrubar turno. O mesmo
    vale pro `prompt_tokens_details`, que só existe onde há prompt cache.
    """
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    def _i(obj: Any, campo: str) -> int:
        try:
            return int(getattr(obj, campo, 0) or 0)
        except (TypeError, ValueError):
            return 0
    det = getattr(u, "completion_tokens_details", None)
    det_prompt = getattr(u, "prompt_tokens_details", None)
    return {
        "prompt_tokens": _i(u, "prompt_tokens"),
        "completion_tokens": _i(u, "completion_tokens"),
        "total_tokens": _i(u, "total_tokens"),
        "reasoning_tokens": _i(det, "reasoning_tokens") if det is not None else 0,
        "cached_tokens": _i(det_prompt, "cached_tokens") if det_prompt is not None else 0,
    }


def _logar_cache(modelo: str, usage: dict[str, int]) -> None:
    """Registra a taxa de acerto do prompt cache do Groq.

    CACHE-CEGO (31/07): a reorganização de prefixo de 25/07 foi feita às cegas —
    o projeto nunca leu `cached_tokens`, então nenhuma afirmação sobre cache era
    verificável. Hoje o cache do Groq só existe para a família `openai/gpt-oss`
    (20b / 120b / safeguard-20b); em `llama-3.3-70b-versatile` a taxa é sempre 0.
    Este log serve para PROVAR isso com número, não para alarmar.

    MEDIDO na primeira corrida (31/07, prefixo idêntico repetido com 1s de
    intervalo, ~1,3-2k tokens): `prompt_tokens_details` voltou **None** nos TRÊS
    degraus — inclusive no gpt-oss. Ou seja: 0% de cache em toda a cascata, e o
    campo vem nulo, não zero. Antes de otimizar prefixo, olhe este log numa
    sessão real: prefixo de produção é maior e pode cruzar o piso do cache.

    Silencioso quando não há prompt_tokens: chamada de teste ou usage ausente não
    polui o log nem levanta exceção — telemetria nunca derruba turno.
    """
    prompt_tok = usage.get("prompt_tokens", 0)
    if prompt_tok <= 0:
        return
    cached = usage.get("cached_tokens", 0)
    log.info(
        "groq_cache",
        modelo=modelo,
        prompt_tokens=prompt_tok,
        cached_tokens=cached,
        taxa_cache=round(cached / prompt_tok * 100, 1),
    )


class GroqProvider(BaseLLMProvider):
    """Provider Groq — uma instância por modelo (70B, 8B etc.)."""

    # MODELOS DE RACIOCÍNIO (auditoria 24/07): a família `openai/gpt-oss` gasta
    # tokens num campo `reasoning` ANTES de emitir `content` — mesma armadilha
    # documentada no CLAUDE.md pro gemini-2.5-flash "full". Medido: com
    # max_tokens=120 e o esforço default, 447 chars foram pro raciocínio e o
    # content voltou VAZIO (finish=length). O projeto tem chamadas em 120 (o
    # gerador de dossiê de NPC, entre elas), então migrar sem isto quebraria a
    # narração de forma intermitente e silenciosa. Com effort="low": 25 chars de
    # raciocínio e o texto sai normal.
    _RACIOCINIO_LOW = ("gpt-oss",)

    def _extras(self) -> dict[str, str]:
        """kwargs específicos do modelo (vazio pros modelos comuns)."""
        if any(marca in self._modelo for marca in self._RACIOCINIO_LOW):
            return {"reasoning_effort": "low"}
        return {}

    def __init__(self, *, nome: str, modelo: str) -> None:
        self.nome = nome
        self._modelo = modelo
        self._client: AsyncGroq | None = None
        # Usage da última chamada (ver `_extrair_usage`). Vazio até a primeira.
        # Desde 31/07 o caminho de STREAM também popula isto: o chunk final com
        # `choices=[]` (habilitado por stream_options.include_usage) carrega o
        # usage do stream inteiro.
        self.ultimo_usage: dict[str, int] = {}
        # Setado pelo router quando a cena ativa e_cena_sombria() ou
        # dm_profile="sombrio". Habilita detecção de amarelada no buffer.
        self._cena_sombria: bool = False

    def set_cena_sombria(self, val: bool) -> None:
        """Habilita/desabilita detecção de amarelada no buffer de stream."""
        self._cena_sombria = val

    @property
    def disponivel(self) -> bool:
        return bool(settings.GROQ_API_KEY)

    def _get_client(self) -> AsyncGroq:
        if self._client is None:
            # timeout aplicado tanto à chamada REST quanto ao read entre chunks
            # do streaming. Sem isso, TPM exaurido pode emitir tokens em rate
            # baixíssimo (1/30s) e travar o turno por minutos sem disparar erro.
            #
            # max_retries=0 — DESLIGAR retry interno do SDK. O default de 2 com
            # backoff cego espera 34s em 429 (visto no log de 27/05). O LLMRouter
            # já faz cascade pro próximo provider em <100ms quando lança
            # LLMRetriable — isso é literalmente o motivo do router existir.
            # Retry duplo só atrasa cascade e prende o usuário.
            self._client = AsyncGroq(
                api_key=settings.GROQ_API_KEY,
                timeout=settings.LLM_PROVIDER_TIMEOUT,
                max_retries=0,
            )
        return self._client

    async def completar(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> str:
        try:
            resp = await self._get_client().chat.completions.create(
                model=self._modelo,
                messages=mensagens,  # type: ignore[arg-type]
                temperature=temperatura,
                max_tokens=max_tokens,
                **self._extras(),
            )
            texto = resp.choices[0].message.content or ""
            # TOKENS-CEGOS (26/07): o projeto media latência e chars, nunca TOKENS
            # — então "quantos turnos cabem no TPD" era conta de guardanapo, e o
            # custo REAL dos modelos de raciocínio (gpt-oss gasta tokens em
            # `reasoning` ANTES do `content`) nunca foi observado. Sem isto não dá
            # pra decidir a ordem da cascata: o 200K TPD do gpt-oss vale o dobro do
            # 70b só se ele não gastar o dobro por turno.
            self.ultimo_usage = _extrair_usage(resp)
            _logar_cache(self._modelo, self.ultimo_usage)
        except _ERROS_RECUPERAVEIS as e:
            raise LLMRetriable(
                f"groq[{self._modelo}] erro recuperável: {e!s}"[:200],
                categoria="rate_limit" if isinstance(e, RateLimitError) else "rede",
                causa=e,
            ) from e
        except APIError as e:
            # Erro de API não na tupla explícita — pode ser 413 TPM (rate limit
            # disfarçado) ou um 400 legítimo. Só converte em LLMRetriable se
            # tiver pegada de quota; caso contrário propaga (não é fallback-able).
            if _e_quota_disfarcada(e):
                raise LLMRetriable(
                    f"groq[{self._modelo}] quota disfarçada: {e!s}"[:200],
                    categoria="rate_limit",
                    causa=e,
                ) from e
            if _e_falha_do_modelo(e):
                raise LLMRetriable(
                    f"groq[{self._modelo}] falha do modelo: {e!s}"[:200],
                    categoria="modelo",
                    causa=e,
                ) from e
            raise

        if _e_recusa(texto):
            raise LLMRetriable(
                f"groq[{self._modelo}] safety refusal: {texto[:80]!r}",
                categoria="refusal",
            )
        return texto

    async def completar_stream(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        try:
            stream = await self._get_client().chat.completions.create(
                model=self._modelo,
                messages=mensagens,  # type: ignore[arg-type]
                temperature=temperatura,
                max_tokens=max_tokens,
                stream=True,
                # Sem isto o caminho de PRODUÇÃO (stream) não devolve usage
                # nenhum — e produção é justamente onde o cache importa. O preço
                # é um chunk final com choices=[] (ver o guard no loop abaixo).
                #
                # ARMADILHA (medida em 31/07 contra a API real): o SDK pinado
                # (groq==1.1.2) NÃO tem o kwarg `stream_options` — passá-lo
                # direto levanta TypeError e derruba TODO turno de stream, que é
                # o caminho do jogo. `extra_body` é a escotilha do SDK: o campo
                # entra no JSON da requisição sem o cliente precisar conhecê-lo.
                # Se um dia o SDK subir e ganhar o kwarg nativo, isto continua
                # válido — não trocar sem rodar contra a API de verdade.
                extra_body={"stream_options": {"include_usage": True}},
                **self._extras(),
            )
        except _ERROS_RECUPERAVEIS as e:
            raise LLMRetriable(
                f"groq[{self._modelo}] stream abertura: {e!s}"[:200],
                categoria="rate_limit" if isinstance(e, RateLimitError) else "rede",
                causa=e,
            ) from e
        except APIError as e:
            if _e_quota_disfarcada(e):
                raise LLMRetriable(
                    f"groq[{self._modelo}] stream quota disfarçada: {e!s}"[:200],
                    categoria="rate_limit",
                    causa=e,
                ) from e
            if _e_falha_do_modelo(e):
                raise LLMRetriable(
                    f"groq[{self._modelo}] stream falha do modelo: {e!s}"[:200],
                    categoria="modelo",
                    causa=e,
                ) from e
            raise

        # Buffer pra detectar refusal antes de emitir qualquer token. Quebra
        # no buffer = ainda dá pra cascatear; quebra após emissão = propaga.
        buffer = ""
        liberado = False
        pendentes: list[str] = []

        try:
            async for chunk in stream:
                # Com include_usage=True o Groq manda um chunk FINAL sem choices,
                # carregando o usage do stream inteiro. Tocar em choices[0] aqui
                # é IndexError — e IndexError no meio do stream derruba o turno.
                # Este guard é a PRIMEIRA coisa do loop de propósito.
                if not chunk.choices:
                    self.ultimo_usage = _extrair_usage(chunk)
                    _logar_cache(self._modelo, self.ultimo_usage)
                    continue

                delta = chunk.choices[0].delta.content
                if not delta:
                    continue

                if not liberado:
                    buffer += delta
                    pendentes.append(delta)
                    if len(buffer) >= _BUFFER_RECUSA:
                        liberado = True
                        if _e_recusa(buffer):
                            raise LLMRetriable(
                                f"groq[{self._modelo}] stream refusal: {buffer[:80]!r}",
                                categoria="refusal",
                            )
                        if self._cena_sombria and e_amarelada(buffer):
                            raise LLMRetriable(
                                f"groq[{self._modelo}] stream amarelada: {buffer[:80]!r}",
                                categoria="amarelada",
                            )
                        for c in pendentes:
                            yield c
                        pendentes.clear()
                else:
                    yield delta
        except _ERROS_RECUPERAVEIS as e:
            # Erro durante streaming — antes ou depois de emitir?
            if not liberado:
                raise LLMRetriable(
                    f"groq[{self._modelo}] stream quebrou pré-emissão: {e!s}"[:200],
                    categoria="rate_limit" if isinstance(e, RateLimitError) else "rede",
                    causa=e,
                ) from e
            # Pós-emissão: propaga. Trocar provider mid-frase quebra a narrativa.
            log.error("groq_stream_quebrou_pos_emissao", modelo=self._modelo, erro=str(e)[:160])
            raise
        except APIError as e:
            # Quota disfarçada (ex: 413 TPM) durante o stream — mesma lógica.
            if not liberado and _e_quota_disfarcada(e):
                raise LLMRetriable(
                    f"groq[{self._modelo}] stream quota disfarçada: {e!s}"[:200],
                    categoria="rate_limit",
                    causa=e,
                ) from e
            # TOOL-FANTASMA-1: foi AQUI que o turno morreu no playtest de 01/08 —
            # o 400 chega depois do 200 OK da abertura, já dentro do stream.
            if not liberado and _e_falha_do_modelo(e):
                raise LLMRetriable(
                    f"groq[{self._modelo}] stream falha do modelo: {e!s}"[:200],
                    categoria="modelo",
                    causa=e,
                ) from e
            raise

        # Stream terminou dentro do buffer
        if not liberado:
            if _e_recusa(buffer):
                raise LLMRetriable(
                    f"groq[{self._modelo}] stream refusal curto: {buffer[:80]!r}",
                    categoria="refusal",
                )
            if self._cena_sombria and e_amarelada(buffer):
                raise LLMRetriable(
                    f"groq[{self._modelo}] stream amarelada curta: {buffer[:80]!r}",
                    categoria="amarelada",
                )
            for c in pendentes:
                yield c
