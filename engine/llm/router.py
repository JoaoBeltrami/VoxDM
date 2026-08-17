"""
LLMRouter — orquestra cascata de providers com fallback automático.

Por que existe: a regra "se 70B falhar tenta 8B, depois Gemini, depois Cerebras,
    depois Ollama" foi até agora hardcoded dentro do GroqClient com if/else
    bagunçados. O router centraliza isso e permite cascatas diferentes por
    TaskType (narrative, summarization, etc).
Dependências: providers/*, tasks, structlog, config.
Armadilha: ``override_primario`` é usado pelo set_backend() ao vivo. Quando
    setado, força aquele provider como primeiro da cascata; se ele falhar
    com LLMRetriable, a cascata default ainda segue normalmente. Não força
    "USE APENAS ollama" — força "TENTE ollama PRIMEIRO".

Exemplo:
    router = LLMRouter()
    async for tok in router.completar_stream(msgs, task=TaskType.NARRATIVE,
                                              temperatura=0.8, max_tokens=400):
        ...
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

import structlog

from config import settings
from engine.llm.amarelada import aplicar_reframe, e_amarelada
from engine.llm.providers.base import BaseLLMProvider, LLMRetriable
from engine.llm.providers.gemini import GeminiProvider
from engine.llm.providers.groq import GroqProvider
from engine.llm.providers.ollama import OllamaProvider
from engine.llm.providers.ollama_grim import OllamaGrimProvider
from engine.llm.tasks import (
    PROV_GEMINI,
    PROV_GROQ_120B,
    PROV_GROQ_LEVE,
    PROV_GROQ_PRINCIPAL,
    PROV_OLLAMA,
    PROV_OLLAMA_GRIM,
    TaskType,
    cascata_para,
    modelo_do_slot,
)
from engine.telemetry import emit_llm_decisao

log = structlog.get_logger(__name__)

# Escada de cooldown por rate_limit, em segundos.
#
# COOLDOWN-EXAGERADO-1 (playtest 26/07): a 1ª versão usava 900s FIXO, partindo da
# premissa de que rate_limit = "a cota do dia acabou". Errado: o TPM do Groq
# reseta a cada MINUTO, e com ~5k tokens/turno contra um TPM de 8-12K o limite é
# raspado o tempo todo em jogo normal. Resultado medido em campo: os TRÊS
# providers Groq saíram em 97 segundos (70b 22:30:29, 120b 22:31:38, 8b
# 22:32:06), tudo caiu no Gemini pelo resto da sessão e o p50 do turno dobrou —
# 5,2s → 9,2s. Um estrangulamento de 60s virou um apagão de 15 minutos.
#
# Agora escala: a 1ª batida assume TPM (janela de 1 min) e sai de campo por 75s;
# batidas seguidas SEM sucesso no meio sobem a aposta até 15 min, que é o palpite
# certo pra TPD. Qualquer sucesso zera a escada.
_COOLDOWN_LADDER_S: tuple[float, ...] = (75.0, 240.0, 900.0)

# GRIM-REATIVA-1: categorias de LLMRetriable que significam "o modelo filtrou
# conteúdo" (não erro de infra) — em cena sombria, qualquer uma gruda a
# escalação reativa. "refusal" = Gemini/Groq hard refusal; "recusa" = variante
# PT usada em código legado; "amarelada" = sanitização suave (fade/moralização)
# detectada no buffer do provider ou pós-resposta no router.
_CATEGORIAS_AMARELADA: frozenset[str] = frozenset({"amarelada", "refusal", "recusa"})


class LLMRouter:
    """Roteador de chamadas LLM com fallback em cascata.

    Stateless entre chamadas — não acumula histórico. ``override_primario``
    e ``override_ollama_primeiro`` são hints de sessão repassados pelo
    consumidor (ex: GroqClient.set_backend("ollama")).
    """

    def __init__(self) -> None:
        # Registrados uma vez por processo. Compartilham sem race condition
        # porque cada provider usa httpx.AsyncClient *por chamada*.
        self._providers: dict[str, BaseLLMProvider] = {
            PROV_GROQ_PRINCIPAL: GroqProvider(nome=PROV_GROQ_PRINCIPAL, modelo=settings.GROQ_MODEL),
            # Fora das cascatas desde 17/08 (roda o mesmo modelo do principal),
            # mas REGISTRADO de propósito: é o que permite forçá-lo pelo toggle
            # das Opções e pelo A/B do benchmark.
            PROV_GROQ_120B:   GroqProvider(nome=PROV_GROQ_120B, modelo=settings.GROQ_MODEL_MEIO),
            PROV_GROQ_LEVE:     GroqProvider(nome=PROV_GROQ_LEVE,  modelo=settings.GROQ_MODEL_FALLBACK),
            PROV_GEMINI:      GeminiProvider(),
            PROV_OLLAMA:      OllamaProvider(),
            PROV_OLLAMA_GRIM: OllamaGrimProvider(),
        }
        # ROUTER-SEM-COTA (playtest 26/07): provider → instante (monotonic) até o
        # qual ele fica FORA da cascata por ter estourado cota. Ver `_penalizar`.
        self._penalizado_ate: dict[str, float] = {}
        # Flag de cena sombria para os providers que suportam amarelada check.
        self._cena_sombria: bool = False
        # Override por sessão — quando setado, esse provider vai pra frente da
        # cascata (sem remover os outros).
        self._override_primario: str | None = None
        # Nome do provider que emitiu o primeiro token no último completar_stream().
        # Comparado pelo consumidor com o provider primário da cascata para detectar
        # cascata silenciosa (Groq TPM → Gemini sem feedback visual ao usuário).
        self.ultimo_provider_stream: str | None = None
        # GRIM-REATIVA-1 (07/07): True quando a ÚLTIMA chamada (completar ou
        # stream) detectou amarelada/recusa em cena sombria — em qualquer
        # provider da cascata, mesmo que outro tenha completado depois. O
        # websocket lê após o turno pra "grudar" a cena como sombria (gatilho
        # (c) do roadmap: resto da cena roteia NARRATIVE_GRIM). Resetado no
        # início de cada chamada.
        self.ultima_chamada_amarelou: bool = False

    def set_primario(self, nome: str | None) -> None:
        """Coloca um provider como primeiro da cascata desta instância.

        Args:
            nome: nome canônico (ex: "ollama-local") ou None pra remover override.
        """
        if nome is not None and nome not in self._providers:
            log.warning("router_provider_desconhecido_ignorado", nome=nome)
            return
        self._override_primario = nome
        log.info("router_override_primario", provider=nome)

    def set_cena_sombria(self, val: bool) -> None:
        """Habilita detecção de amarelada para a próxima chamada.

        Propagado para os GroqProviders que suportam a checagem no buffer
        de stream. O websocket.py chama com val=True quando a transcrição
        ativa `e_cena_sombria()` ou dm_profile="sombrio".
        """
        self._cena_sombria = val
        for p in self._providers.values():
            if hasattr(p, "set_cena_sombria"):
                p.set_cena_sombria(val)

    def _cascata_efetiva(self, task: TaskType) -> list[str]:
        """Cascata final: override primário (se houver) seguido pelo default.

        IMPORTANTE: quando o usuário escolhe um provider específico no toggle
        de Opções (frontend), `_override_primario` é setado e DESATIVA o
        roteamento por contexto (TaskType.NARRATIVE_LIGHT/CLIMAX). Todo turno
        passa a usar o provider escolhido como primário, independente do
        estado da cena.

        Para que o roteamento contextual funcione (8B em filler, 70B+Gemini
        em climax), o toggle deve estar em "auto" (default) — nesse caso
        `_override_primario is None` e a cascata vem direto de cascata_para().
        """
        base = cascata_para(task)
        if self._override_primario is None:
            return base
        # Override primeiro, o resto preserva ordem (sem duplicar)
        cauda = [n for n in base if n != self._override_primario]
        return [self._override_primario, *cauda]

    def _emitir_decisao(
        self,
        *,
        task: TaskType,
        provider_primario: str | None,
        provider_efetivo: str | None,
        cascata_disparou: bool,
        t0: float,
        chars_saida: int,
        status: str,
        categoria_erro: str | None,
    ) -> None:
        """Emite telemetria de decisão LLM convertendo t0 (monotonic) em ms.

        Falha de telemetria nunca quebra a chamada LLM — try/except amplo.
        """
        try:
            emit_llm_decisao(
                task=task.value,
                provider_primario=provider_primario,
                provider_efetivo=provider_efetivo,
                cascata_disparou=cascata_disparou,
                latencia_ms=int((time.monotonic() - t0) * 1000),
                chars_saida=chars_saida,
                status=status,
                categoria_erro=categoria_erro,
            )
        except Exception as e:  # noqa: BLE001 — telemetria é best-effort
            log.warning("telemetria_llm_falhou", erro=str(e)[:120])

    def _cooldowns(self) -> dict[str, float]:
        """Mapa provider → fim do cooldown, criado sob demanda.

        Lazy porque parte da suíte monta o router com `LLMRouter.__new__` e
        popula só os campos que o caso precisa (ver tests/test_grimdark.py) —
        um campo novo em `__init__` quebraria esses testes sem que houvesse
        nada de errado com eles.
        """
        atual = getattr(self, "_penalizado_ate", None)
        if atual is None:
            atual = {}
            self._penalizado_ate = atual
        return atual

    def _falhas_rate_limit(self) -> dict[str, int]:
        """Batidas de rate_limit seguidas por provider. Lazy pelo mesmo motivo
        de `_cooldowns` (parte da suíte monta o router via `__new__`)."""
        atual = getattr(self, "_falhas_rl", None)
        if atual is None:
            atual = {}
            self._falhas_rl = atual
        return atual

    def _penalizar(self, nome: str, categoria: str) -> None:
        """Tira da cascata, por um tempo, quem acabou de dizer que está sem cota.

        ROUTER-SEM-COTA (playtest 26/07): `disponivel` responde "tem chave", nunca
        "tem cota". Sem memória de esgotamento, depois que o TPD do groq-70b fechou
        no turno ~14 os 36 turnos seguintes subiram o body INTEIRO (19 KB) só pra
        colher 429 e cair pro próximo degrau — round-trip inútil em todo turno de
        uma sessão de uma hora.

        Só rate_limit penaliza: erro de rede ou 5xx é transitório e o provider deve
        continuar na fila. O TTL é curto porque não dá pra distinguir TPM (janela de
        minuto) de TPD (dia) pela resposta — errar pra menos custa um round-trip,
        errar pra mais desliga um provider bom por horas.
        """
        if categoria != "rate_limit":
            return
        falhas = self._falhas_rate_limit()
        n = falhas.get(nome, 0)
        espera = _COOLDOWN_LADDER_S[min(n, len(_COOLDOWN_LADDER_S) - 1)]
        falhas[nome] = n + 1
        self._cooldowns()[nome] = time.monotonic() + espera
        log.info("provider_em_cooldown", provider=nome, segundos=espera, batida=n + 1)

    def _sucesso(self, nome: str) -> None:
        """Provider respondeu — zera a escada de cooldown dele.

        Sem isto a escada só sobe: um TPM raspado de manhã deixaria o provider
        com 15 min de exílio à noite, mesmo tendo funcionado a tarde inteira.
        """
        self._falhas_rate_limit().pop(nome, None)

    def _providers_disponiveis(self, task: TaskType) -> list[BaseLLMProvider]:
        """Cascata filtrada por disponibilidade — pula sem chave/serviço ou em cooldown.

        Se TODOS estiverem penalizados, ignora o cooldown e devolve a cascata
        cheia: melhor pagar o round-trip do que ficar sem narrador.
        """
        cascata = self._cascata_efetiva(task)
        vivos = [self._providers[n] for n in cascata
                 if n in self._providers and self._providers[n].disponivel]
        agora = time.monotonic()
        penalizados = self._cooldowns()
        sem_cooldown = [p for p in vivos if penalizados.get(p.nome, 0.0) <= agora]
        return sem_cooldown or vivos

    async def completar(
        self,
        mensagens: list[dict[str, str]],
        *,
        task: TaskType = TaskType.NARRATIVE,
        temperatura: float = 0.8,
        max_tokens: int = 400,
    ) -> str:
        """Geração síncrona — cascateia até algum provider responder com sucesso."""
        providers = self._providers_disponiveis(task)
        if not providers:
            raise RuntimeError("nenhum provider LLM disponível — configure GROQ_API_KEY ou GEMINI_API_KEY_V2")

        # Perna 3 — telemetria por TaskType. Primário = cabeça da cascata efetiva.
        provider_primario = providers[0].nome
        t0 = time.monotonic()

        self.ultima_chamada_amarelou = False
        ultimo_erro: LLMRetriable | None = None
        # GRIM-REFRAME-1 (Camada 5): fila de tentativas (provider, mensagens) em
        # vez de iterar providers direto — quando um provider CLOUD amarela em
        # cena sombria, re-enfileiramos o MESMO provider com o reframe literário
        # na frente (1 reframe por chamada). Se ainda amarelar, a cascata segue.
        fila: list[tuple[BaseLLMProvider, list[dict[str, str]]]] = [
            (p, mensagens) for p in providers
        ]
        reframe_usado = False

        def _tentar_reframe(p: BaseLLMProvider) -> bool:
            nonlocal reframe_usado
            if (
                self._cena_sombria
                and not reframe_usado
                and not p.nome.startswith("ollama")  # local não tem filtro corporativo
            ):
                reframe_usado = True
                fila.insert(0, (p, aplicar_reframe(mensagens)))
                log.info("llm_reframe_literario_tentando", provider=p.nome)
                return True
            return False

        while fila:
            p, msgs = fila.pop(0)
            try:
                log.info("llm_provider_tentando", provider=p.nome, modelo=modelo_do_slot(p.nome), task=task.value)
                texto = await p.completar(msgs, temperatura, max_tokens)
                # Detecção de amarelada em cena sombria: se o provider filtrou
                # suavemente (fade-to-black, moralização), cascateia pro próximo.
                if self._cena_sombria and e_amarelada(texto):
                    log.warning(
                        "llm_amarelada_detectada_completar",
                        provider=p.nome,
                        trecho=texto[:80],
                    )
                    self.ultima_chamada_amarelou = True  # GRIM-REATIVA-1
                    ultimo_erro = LLMRetriable(
                        f"{p.nome} amarelou (fade-to-black/moralização)",
                        categoria="amarelada",
                    )
                    _tentar_reframe(p)  # GRIM-REFRAME-1
                    continue
                log.info("llm_provider_ok", provider=p.nome, modelo=modelo_do_slot(p.nome), task=task.value, chars=len(texto))
                cascata_disparou = p.nome != provider_primario
                self._emitir_decisao(
                    task=task, provider_primario=provider_primario,
                    provider_efetivo=p.nome, cascata_disparou=cascata_disparou,
                    t0=t0, chars_saida=len(texto),
                    status="cascade_used" if cascata_disparou else "ok",
                    categoria_erro=ultimo_erro.categoria if ultimo_erro else None,
                )
                self._sucesso(p.nome)
                return texto
            except LLMRetriable as e:
                self._penalizar(p.nome, e.categoria)
                log.warning(
                    "llm_provider_fallback",
                    provider=p.nome,
                    categoria=e.categoria,
                    erro=str(e)[:160],
                )
                # GRIM-REATIVA-1: recusa/amarelada detectada DENTRO do provider
                # (buffer de stream do Groq, refusal do Gemini) também gruda a
                # cena — só conta em cena sombria, senão recusa legítima de
                # prompt malformado viraria escalação grim indevida.
                if self._cena_sombria and e.categoria in _CATEGORIAS_AMARELADA:
                    self.ultima_chamada_amarelou = True
                    _tentar_reframe(p)  # GRIM-REFRAME-1
                ultimo_erro = e

        # Todos cascateados falharam
        log.error("llm_cascata_esgotada", task=task.value, ultimo=str(ultimo_erro)[:160] if ultimo_erro else "")
        self._emitir_decisao(
            task=task, provider_primario=provider_primario, provider_efetivo=None,
            cascata_disparou=True, t0=t0, chars_saida=0,
            status="fallback_all_failed",
            categoria_erro=ultimo_erro.categoria if ultimo_erro else None,
        )
        raise RuntimeError(f"todos os providers LLM falharam — último erro: {ultimo_erro}")

    async def completar_stream(
        self,
        mensagens: list[dict[str, str]],
        *,
        task: TaskType = TaskType.NARRATIVE,
        temperatura: float = 0.8,
        max_tokens: int = 400,
    ) -> AsyncIterator[str]:
        """Streaming — cascateia entre providers ATÉ emitir o primeiro token.

        Quando um provider falha *antes* de emitir, vai pro próximo. Após o
        primeiro token bem-sucedido, mais nenhum fallback é tentado mesmo se
        o stream quebrar (trocar provider mid-frase corrompe a narrativa).
        """
        providers = self._providers_disponiveis(task)
        if not providers:
            raise RuntimeError("nenhum provider LLM disponível — configure GROQ_API_KEY ou GEMINI_API_KEY_V2")

        # Perna 3 — telemetria por TaskType. No stream, latência = tempo até o
        # PRIMEIRO token (proxy de responsividade percebida); chars_saida soma
        # o total emitido pelo provider vencedor.
        provider_primario = providers[0].nome
        t0 = time.monotonic()

        self.ultimo_provider_stream = None
        self.ultima_chamada_amarelou = False
        ultimo_erro: LLMRetriable | None = None
        # GRIM-REFRAME-1 (Camada 5): mesma fila de tentativas do completar() —
        # recusa/amarelada PRÉ-emissão de um provider cloud em cena sombria
        # re-enfileira o mesmo provider com o reframe literário (1 por chamada).
        fila: list[tuple[BaseLLMProvider, list[dict[str, str]]]] = [
            (p, mensagens) for p in providers
        ]
        reframe_usado = False
        while fila:
            p, msgs = fila.pop(0)
            try:
                log.info("llm_provider_tentando_stream", provider=p.nome, modelo=modelo_do_slot(p.nome), task=task.value)
                emitiu = False
                chars_saida = 0
                latencia_primeiro_ms = 0
                async for token in p.completar_stream(msgs, temperatura, max_tokens):
                    if not emitiu:
                        log.info("llm_provider_stream_ok", provider=p.nome, modelo=modelo_do_slot(p.nome), task=task.value)
                        self.ultimo_provider_stream = p.nome
                        latencia_primeiro_ms = int((time.monotonic() - t0) * 1000)
                        emitiu = True
                        # Emitir token É sucesso — zera a escada de cooldown.
                        # Este é o caminho do JOGO (o `completar` não-streaming
                        # cobre só tarefas de bastidor), então sem isto a escada
                        # só subiria em uso real.
                        self._sucesso(p.nome)
                    chars_saida += len(token)
                    yield token
                # Stream terminou sem exceção — provider venceu, sai do for.
                if emitiu:
                    cascata_disparou = p.nome != provider_primario
                    try:
                        emit_llm_decisao(
                            task=task.value, provider_primario=provider_primario,
                            provider_efetivo=p.nome, cascata_disparou=cascata_disparou,
                            latencia_ms=latencia_primeiro_ms, chars_saida=chars_saida,
                            status="cascade_used" if cascata_disparou else "ok",
                            categoria_erro=ultimo_erro.categoria if ultimo_erro else None,
                        )
                    except Exception as e:  # noqa: BLE001 — telemetria é best-effort
                        log.warning("telemetria_llm_stream_falhou", erro=str(e)[:120])
                    return
                # Provider esvaziou sem emitir nada nem lançar erro — trata como retriable
                ultimo_erro = LLMRetriable(f"{p.nome} stream vazio sem erro", categoria="vazio")
                log.warning("llm_provider_stream_vazio", provider=p.nome, modelo=modelo_do_slot(p.nome))
                continue
            except LLMRetriable as e:
                # Defesa de contrato (CASCATA-1): se ESTE provider já emitiu tokens,
                # NÃO cascateia — trocar de provider mid-frase concatenaria dois
                # inícios de narração no ouvido do jogador. Honra a promessa do
                # docstring desta função. Os providers atuais (ver groq.py:236) já
                # propagam erro pós-emissão como exceção genérica (não-LLMRetriable),
                # então este guard é defensivo contra um provider futuro que lance
                # LLMRetriable tarde demais.
                if emitiu:
                    log.error(
                        "llm_stream_retriable_pos_emissao_propagada",
                        provider=p.nome, categoria=e.categoria,
                    )
                    raise
                self._penalizar(p.nome, e.categoria)
                log.warning(
                    "llm_provider_fallback_stream",
                    provider=p.nome,
                    categoria=e.categoria,
                    erro=str(e)[:160],
                )
                # GRIM-REATIVA-1: idem completar() — recusa/amarelada pré-emissão
                # em cena sombria gruda a escalação reativa da cena.
                if self._cena_sombria and e.categoria in _CATEGORIAS_AMARELADA:
                    self.ultima_chamada_amarelou = True
                    # GRIM-REFRAME-1: retry do mesmo provider cloud com reframe
                    # literário, uma vez por chamada.
                    if not reframe_usado and not p.nome.startswith("ollama"):
                        reframe_usado = True
                        fila.insert(0, (p, aplicar_reframe(mensagens)))
                        log.info("llm_reframe_literario_tentando_stream", provider=p.nome)
                ultimo_erro = e
                continue

        log.error("llm_cascata_stream_esgotada", task=task.value, ultimo=str(ultimo_erro)[:160] if ultimo_erro else "")
        try:
            emit_llm_decisao(
                task=task.value, provider_primario=provider_primario, provider_efetivo=None,
                cascata_disparou=True, latencia_ms=int((time.monotonic() - t0) * 1000),
                chars_saida=0, status="fallback_all_failed",
                categoria_erro=ultimo_erro.categoria if ultimo_erro else None,
            )
        except Exception as e:  # noqa: BLE001 — telemetria é best-effort
            log.warning("telemetria_llm_stream_falhou", erro=str(e)[:120])
        raise RuntimeError(f"todos os providers LLM falharam (stream) — último erro: {ultimo_erro}")
