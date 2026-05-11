"""
Rate limiter compartilhado entre main e routes.

Por que existe: slowapi precisa da MESMA instância de Limiter no app.state.limiter
    (usado pelo middleware) e nos decoradores @limiter.limit() das rotas. Importar
    de um único módulo evita estados separados que ignoram o limite silenciosamente.
Dependências: slowapi
Armadilha: storage in-memory — limite reseta a cada restart do server. Em produção
    multi-instância, trocar por Redis: `storage_uri="redis://..."`.

Exemplo:
    from api.rate_limit import limiter

    @router.post("/foo")
    @limiter.limit("10/minute")
    async def foo(request: Request) -> ...:
        ...
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# key_func=get_remote_address → 1 contador por IP cliente
# Sem default_limits → endpoints sem decorador não têm limite (desejado).
limiter = Limiter(key_func=get_remote_address)
