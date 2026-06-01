"""
Camada de autenticação e identidade — cross-cutting concern.

Por que existe: VoxDM passou de single-user local pra multi-tenant via
    Cloudflare Access. A identidade (`Owner`) precisa fluir por todas as
    camadas de persistência (SQLite, Qdrant, Neo4j) sem virar middleware
    mágico. Cada query aceita `Owner` como argumento explícito.

Dependências: pyjwt, httpx (pra buscar certs Cloudflare)

Armadilha: NUNCA aceitar `alg: none` ou HS256 no JWT validator — Cloudflare
    assina com RS256. Aceitar outros algoritmos é a vulnerabilidade clássica
    "algorithm confusion" (atacante manda JWT auto-assinado e o validador aceita).

Exemplo:
    from engine.auth.identity import Owner
    from engine.auth.jwt_validator import validar_jwt_cf

    owner = await validar_jwt_cf(token, settings)
    # → Owner(email="admin@example.com", is_admin=True)
"""

from engine.auth.identity import Owner, is_admin
from engine.auth.jwt_validator import JWTInvalido, validar_jwt_cf

__all__ = ["Owner", "is_admin", "validar_jwt_cf", "JWTInvalido"]
