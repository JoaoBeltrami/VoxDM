"""
Rate limiter compartilhado entre main e routes.

Por que existe: slowapi precisa da MESMA instância de Limiter no app.state.limiter
    (usado pelo middleware) e nos decoradores @limiter.limit() das rotas. Importar
    de um único módulo evita estados separados que ignoram o limite silenciosamente.
Dependências: slowapi
Armadilha: storage in-memory — limite reseta a cada restart do server. Em produção
    multi-instância, trocar por Redis: `storage_uri="redis://..."`.
    Em dev local (DEBUG=True), fallback para DEV_USER_EMAIL como chave — todos os
    requests compartilham o mesmo bucket, o que é o comportamento desejado em teste.

Exemplo:
    from api.rate_limit import limiter

    @router.post("/foo")
    @limiter.limit("10/minute")
    async def foo(request: Request) -> ...:
        ...
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _get_chave_por_usuario(request: Request) -> str:
    """Chave do rate limiter — usa email autenticado em vez de IP.

    Em produção atrás do Cloudflare Tunnel, todos os requests chegam do
    mesmo IP (o túnel). Usar email previne que um usuário esgote a cota
    de todos os outros.

    Ordem de tentativas:
    1. Header ``Cf-Access-Authenticated-User-Email`` (injetado pelo Tunnel — não forjável).
    2. ``DEV_USER_EMAIL`` da config (só em DEBUG=True).
    3. IP do cliente (fallback de segurança — nunca deve chegar aqui em prod atrás do Tunnel).
    """
    email = request.headers.get("cf-access-authenticated-user-email", "").strip().lower()
    if email:
        return email

    try:
        from config import settings
        if settings.DEBUG and settings.DEV_USER_EMAIL:
            return settings.DEV_USER_EMAIL.strip().lower()
    except Exception:
        pass  # config ausente/corrompida — cai pro fallback por IP, nunca quebra o rate limit

    return get_remote_address(request)


# key_func=_get_chave_por_usuario → 1 contador por usuário autenticado
# Sem default_limits → endpoints sem decorador não têm limite (desejado).
limiter = Limiter(key_func=_get_chave_por_usuario)
