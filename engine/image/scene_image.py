"""
Geração de imagem de cena para fundo visual — fire-and-forget.

Por que existe: enriquecer a imersão visual sem quebrar o fluxo de voz.
    Pollinations.ai oferece geração FLUX gratuita sem API key.
    A latência (~5-10s) é aceitável pois a imagem vai para o background.

Dependências: httpx (já usado no projeto)
Armadilha: NUNCA await este módulo no caminho crítico de resposta.
    Sempre usar asyncio.create_task() para não bloquear o streaming.

Exemplo:
    task = asyncio.create_task(
        gerar_e_enviar_imagem(websocket, "taverna, noite, fantasia", "taverna-drevamor")
    )
"""

import hashlib
import urllib.parse
from typing import TYPE_CHECKING

import httpx
import structlog

if TYPE_CHECKING:
    from fastapi import WebSocket

log = structlog.get_logger()

# Cache em memória por processo: prompt_hash → URL já confirmada pelo Pollinations.
# Evita checar novamente a mesma cena durante uma sessão (e entre sessões no mesmo processo).
_cache: dict[str, str] = {}

_POLLINATIONS_BASE = (
    "https://image.pollinations.ai/prompt/{prompt}"
    "?width=1024&height=576&model=flux&nologo=true"
)

# Tempo máximo de espera pela resposta do Pollinations. O serviço pode ser lento
# (~5-10s), mas não deixamos esperar mais que 15s para não segurar recursos.
_TIMEOUT_S: float = 15.0


def _prompt_hash(prompt: str) -> str:
    """Gera hash SHA-1 curto do prompt para usar como chave de cache."""
    return hashlib.sha1(prompt.encode()).hexdigest()[:12]


def _montar_url(prompt: str) -> str:
    """Codifica o prompt e monta a URL do Pollinations.ai."""
    encoded = urllib.parse.quote(prompt, safe="")
    return _POLLINATIONS_BASE.format(prompt=encoded)


async def gerar_e_enviar_imagem(
    websocket: "WebSocket",
    prompt_cena: str,
    cache_key: str,
) -> None:
    """Gera imagem para a cena e envia via WebSocket como mensagem 'scene_image'.

    Fire-and-forget — o caller deve usar asyncio.create_task().
    Falhas são silenciosas (log warning, sem raise) — o jogo continua normalmente
    com o fundo anterior se qualquer etapa falhar.

    Args:
        websocket: canal ativo para enviar a URL da imagem gerada
        prompt_cena: texto descritivo da cena em inglês para o modelo FLUX
        cache_key: chave de cache (normalmente location_id + combate)
    """
    key = _prompt_hash(cache_key)

    if key in _cache:
        url = _cache[key]
        log.debug("scene_image_cache_hit", key=key, url=url[:80])
    else:
        url = _montar_url(prompt_cena)

        # Pollinations gera a imagem ao acessar a URL — verificamos se o endpoint
        # responde com sucesso antes de enviar ao frontend. HEAD evita baixar os bytes.
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT_S, follow_redirects=True
            ) as client:
                resp = await client.head(url)
                if resp.status_code not in (200, 301, 302):
                    log.warning(
                        "scene_image_falhou",
                        status=resp.status_code,
                        url=url[:80],
                    )
                    return
        except Exception as exc:
            log.warning("scene_image_erro", erro=str(exc)[:120])
            return

        _cache[key] = url
        log.info("scene_image_gerada", key=key, prompt=prompt_cena[:80], url=url[:80])

    # Envia a URL ao frontend para que ele aplique como fundo da <main>.
    # Se o WebSocket já fechou (jogador desconectou durante a geração), falha silenciosa.
    try:
        from api.models.schemas import MensagemWS  # import lazy — evita ciclo

        await websocket.send_text(
            MensagemWS(tipo="scene_image", conteudo=url).model_dump_json()
        )
    except Exception as exc:
        log.warning("scene_image_send_falhou", erro=str(exc)[:80])


async def construir_prompt_cena(
    location_nome: str,
    time_of_day: str,
    em_combate: bool,
    weather: str = "",
) -> str:
    """Monta um prompt de imagem em inglês a partir dos atributos da cena.

    Não faz chamada LLM — usa template determinístico para garantir
    latência zero e evitar dependência extra no caminho crítico.

    Args:
        location_nome: nome legível do local (ex: "Taverna do Lobo Cinzento")
        time_of_day: hora do dia em PT-BR (ex: "noite", "manhã")
        em_combate: se verdadeiro, adiciona atmosfera de tensão/combate
        weather: clima opcional (ex: "neve", "chuva") — ignorado se vazio

    Returns:
        Prompt em inglês para o Pollinations.ai (máx ~120 chars)
    """
    partes: list[str] = []

    # Nome do local como ancora principal do prompt
    partes.append(location_nome)

    # Hora do dia → descrição de iluminação em inglês
    hora_map: dict[str, str] = {
        "manhã": "morning light",
        "manha": "morning light",
        "tarde": "afternoon",
        "anoitecer": "dusk, golden hour",
        "noite": "night, dark atmosphere",
        "meia-noite": "midnight, moonlight",
        "meia noite": "midnight, moonlight",
        "aurora": "dawn",
    }
    iluminacao = hora_map.get(time_of_day.lower().strip(), time_of_day)
    partes.append(iluminacao)

    # Clima — adicionado apenas quando relevante (não vazio e não "normal")
    if weather and weather.lower().strip() not in ("normal", ""):
        clima_map: dict[str, str] = {
            "frio": "cold, frost",
            "neve": "snow, winter",
            "chuva": "rain, wet",
            "tempestade": "storm, lightning",
            "nevoeiro": "fog, mist",
            "calor": "heat haze",
        }
        partes.append(clima_map.get(weather.lower().strip(), weather))

    # Combate → atmosfera dramática de tensão
    if em_combate:
        partes.append("combat, dramatic tension, fire and smoke, action")
    else:
        partes.append("atmospheric, immersive, peaceful")

    # Qualidade e estilo — palavras-chave de arte fantástica
    partes += ["fantasy art", "detailed", "cinematic lighting", "no text", "no ui"]

    return ", ".join(partes)
