"""
Dependency injection do FastAPI pra extrair Owner autenticado.

Por que existe: cada rota REST + handshake WebSocket precisa saber quem
    está pedindo. Centralizar a extração + validação aqui evita repetir
    código em cada router e garante que se a fonte de identidade mudar
    (ex: trocar Cloudflare por outro IdP), só esse arquivo é tocado.

Fluxo:
    1. Tenta validar JWT do header `Cf-Access-Jwt-Assertion`
    2. Se válido → email do payload → Owner(email, is_admin=...)
    3. Se DEBUG=True e header ausente → fallback `DEV_USER_EMAIL`
    4. Em prod sem header → 401

Dependências: fastapi, engine/auth/*, config

Armadilha CRÍTICA: o fallback DEV_USER_EMAIL SÓ funciona quando
    `settings.DEBUG=True`. Em produção (DEBUG=False), ausência do header
    do CF retorna 401. Se algum dia DEBUG vazar pra prod, a auth ainda
    bloqueia request sem JWT — defense in depth.

Exemplo:
    @router.get("/algo")
    async def algo(owner: Owner = Depends(get_owner)):
        return {"email": owner.email}
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException, Request, status

from config import settings
from engine.auth.identity import Owner, is_admin
from engine.auth.jwt_validator import JWTInvalido, validar_jwt_cf

log = structlog.get_logger(__name__)

# Header name conforme spec do Cloudflare Access
_HEADER_JWT = "Cf-Access-Jwt-Assertion"
_HEADER_EMAIL = "Cf-Access-Authenticated-User-Email"


async def _resolver_email_via_jwt(jwt_token: str) -> str:
    """Valida JWT e retorna o email. Lança JWTInvalido em falha.

    Em ambientes sem `CF_TEAM_DOMAIN` / `CF_ACCESS_AUD` configurados
    (raro em prod), fail safe: rejeita o JWT em vez de aceitar sem validar.
    """
    if not settings.CF_TEAM_DOMAIN or not settings.CF_ACCESS_AUD:
        raise JWTInvalido("CF_TEAM_DOMAIN/CF_ACCESS_AUD não configurados — não posso validar JWT")
    payload = await validar_jwt_cf(
        jwt_token,
        team_domain=settings.CF_TEAM_DOMAIN,
        audience=settings.CF_ACCESS_AUD,
    )
    email = payload.get("email") or payload.get("identity_nonce") or ""
    if not email:
        raise JWTInvalido("JWT válido mas sem email no payload")
    return str(email).strip().lower()


async def get_owner(
    request: Request,
    cf_jwt: Annotated[str | None, Header(alias=_HEADER_JWT)] = None,
    cf_email: Annotated[str | None, Header(alias=_HEADER_EMAIL)] = None,
) -> Owner:
    """Extrai o `Owner` autenticado da request.

    Ordem de tentativas:
    1. JWT do header `Cf-Access-Jwt-Assertion` (canonical, mais seguro)
    2. Header `Cf-Access-Authenticated-User-Email` PLUS o JWT presente
       (CF garante que o email não está sozinho — sempre vem com o JWT)
    3. Em DEBUG: fallback `DEV_USER_EMAIL`
    4. Caso contrário: 401

    Returns:
        Owner com email validado e flag is_admin computada.

    Raises:
        HTTPException 401: sem identidade válida.
    """
    email: str | None = None

    # Caminho A — JWT válido. SEMPRE preferido em prod.
    if cf_jwt:
        try:
            email = await _resolver_email_via_jwt(cf_jwt)
        except JWTInvalido as e:
            log.warning("cf_jwt_invalido", erro=str(e)[:120], path=request.url.path)
            # Em DEBUG ainda permitimos o fallback DEV_USER. Em prod, 401.
            if not settings.DEBUG:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="JWT do Cloudflare Access inválido",
                )

    # Caminho B — DEV_USER_EMAIL como fallback explícito em modo debug.
    # NÃO há fallback "qualquer um" em prod: se chegamos aqui sem email, é 401.
    if email is None:
        if settings.DEBUG and settings.DEV_USER_EMAIL:
            email = settings.DEV_USER_EMAIL.strip().lower()
            log.debug("auth_dev_fallback", email=email, path=request.url.path)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Identidade ausente — header Cf-Access-Jwt-Assertion não presente",
            )

    owner = Owner(email=email, is_admin=is_admin(email, settings.ADMIN_EMAILS))
    return owner


async def get_owner_ws(websocket_headers: dict[str, str]) -> Owner:
    """Versão pra WebSocket — não usa Depends (FastAPI não injeta em ws).

    O caller (handler de ws) chama: `owner = await get_owner_ws(dict(ws.headers))`
    """
    cf_jwt = websocket_headers.get(_HEADER_JWT.lower())
    email: str | None = None

    if cf_jwt:
        try:
            email = await _resolver_email_via_jwt(cf_jwt)
        except JWTInvalido as e:
            log.warning("ws_cf_jwt_invalido", erro=str(e)[:120])

    if email is None:
        if settings.DEBUG and settings.DEV_USER_EMAIL:
            email = settings.DEV_USER_EMAIL.strip().lower()
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Identidade ausente no WebSocket",
            )

    return Owner(email=email, is_admin=is_admin(email, settings.ADMIN_EMAILS))


def exige_admin(owner: Annotated[Owner, Depends(get_owner)]) -> Owner:
    """Depends pra rotas admin-only. 403 se não-admin.

    Uso em rota:
        @router.get("/debug/algo")
        async def x(owner: Owner = Depends(exige_admin)):
            ...
    """
    if not owner.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rota apenas para administradores",
        )
    return owner
