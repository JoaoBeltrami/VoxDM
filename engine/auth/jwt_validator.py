"""
Validador de JWT do Cloudflare Access — RS256 com cache de certs.

Por que existe: Cloudflare Access injeta `Cf-Access-Jwt-Assertion` em toda
    request que passa pelo Tunnel autenticado. Validar esse JWT no backend
    é defense-in-depth (camada extra além do Access bloquear na borda).
    Também permite extrair o email de forma confiável e auditável.

Dependências: pyjwt[crypto] (cryptography pra RS256), httpx

Armadilha CRÍTICA: `algorithms=["RS256"]` é obrigatório. Aceitar HS256 ou
    `none` é a vulnerabilidade "algorithm confusion" — atacante manda JWT
    auto-assinado com chave simétrica e o validador aceita. SEMPRE pin RS256.

Cloudflare rotaciona as chaves de assinatura. Cache de certs tem TTL de 1h;
após isso, re-fetch automaticamente.

Exemplo:
    from engine.auth.jwt_validator import validar_jwt_cf
    owner = await validar_jwt_cf(jwt_token, team_domain, audience)
    # → email validado contra aud + signature + exp
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt as pyjwt
import structlog

log = structlog.get_logger(__name__)


class JWTInvalido(Exception):
    """JWT do Cloudflare Access falhou na validação.

    Razões possíveis:
    - Assinatura inválida (não foi a CF que assinou)
    - `exp` no passado (token expirado)
    - `aud` não bate (token é de outra Access App)
    - `iss` não bate (token é de outro team)
    - Header inválido / não é JWT
    """


# Cache: {team_domain: (certs_json, fetched_at_unix)}
_CERT_CACHE: dict[str, tuple[dict[str, Any], float]] = {}
_CACHE_TTL_SECONDS: float = 3600.0  # 1h — Cloudflare rotaciona aprox 24h


async def _buscar_certs(team_domain: str) -> dict[str, Any]:
    """Busca o JWKS público do Cloudflare Access para o team."""
    url = f"https://{team_domain}.cloudflareaccess.com/cdn-cgi/access/certs"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def _obter_certs(team_domain: str) -> dict[str, Any]:
    """Retorna certs do cache se válido, senão refaz fetch.

    O cache evita hit em cada request — em prod com tráfego médio são
    ~milhões de validações por mês, ZERO valor em pegar cert toda vez.
    """
    agora = time.time()
    cached = _CERT_CACHE.get(team_domain)
    if cached is not None:
        certs, fetched_at = cached
        if agora - fetched_at < _CACHE_TTL_SECONDS:
            return certs

    certs = await _buscar_certs(team_domain)
    _CERT_CACHE[team_domain] = (certs, agora)
    log.info("cf_certs_atualizados", team=team_domain, keys=len(certs.get("keys", [])))
    return certs


async def validar_jwt_cf(
    token: str,
    team_domain: str,
    audience: str,
) -> dict[str, Any]:
    """Valida o JWT do Cloudflare Access e retorna o payload decodificado.

    Args:
        token: valor de `Cf-Access-Jwt-Assertion` (header da request).
        team_domain: subdomínio do team no Cloudflare Zero Trust.
        audience: AUD tag da Access App específica.

    Returns:
        Payload do JWT (dict) — útil pra extrair `email`, `sub`, `iat`, etc.

    Raises:
        JWTInvalido: qualquer falha de validação (assinatura, exp, aud, iss).
    """
    if not token or not team_domain or not audience:
        raise JWTInvalido("token/team_domain/audience vazios")

    try:
        certs = await _obter_certs(team_domain)
    except Exception as e:
        raise JWTInvalido(f"falha ao buscar certs Cloudflare: {e}") from e

    # Encontra o cert certo pelo kid do header
    try:
        unverified = pyjwt.get_unverified_header(token)
    except Exception as e:
        raise JWTInvalido(f"JWT header inválido: {e}") from e

    kid = unverified.get("kid")
    if not kid:
        raise JWTInvalido("JWT sem kid no header")

    chave_cert: dict[str, Any] | None = None
    for key in certs.get("keys", []):
        if key.get("kid") == kid:
            chave_cert = key
            break
    if chave_cert is None:
        raise JWTInvalido(f"kid={kid} não encontrado nos certs do CF")

    # PyJWKClient seria mais elegante, mas requer URL — aqui já temos o dict.
    chave_pub = pyjwt.algorithms.RSAAlgorithm.from_jwk(chave_cert)

    try:
        payload = pyjwt.decode(
            token,
            chave_pub,
            algorithms=["RS256"],  # CRÍTICO: nunca aceitar HS256 / none
            audience=audience,
            issuer=f"https://{team_domain}.cloudflareaccess.com",
        )
    except pyjwt.ExpiredSignatureError as e:
        raise JWTInvalido("token expirado") from e
    except pyjwt.InvalidAudienceError as e:
        raise JWTInvalido("aud não bate — token é de outra Access App") from e
    except pyjwt.InvalidIssuerError as e:
        raise JWTInvalido("iss não bate — token é de outro team") from e
    except pyjwt.InvalidTokenError as e:
        raise JWTInvalido(f"token inválido: {e}") from e

    return payload


def limpar_cache_certs() -> None:
    """Útil em testes — força próximo `validar_jwt_cf` a re-fetch."""
    _CERT_CACHE.clear()
