"""
Identidade para ferramentas que rodam FORA de uma request — demos, benchmark, dashboard.

Por que existe: a memória de jogo exige `Owner` em toda leitura e escrita, e
    um script de terminal não tem JWT do Cloudflare. Em vez de cada script
    inventar um email (e gravar memória num dono que ninguém vai reencontrar),
    todos usam a MESMA identidade local que a API usa em DEBUG.
Dependências: config
Armadilha: sem `DEV_USER_EMAIL` no `.env` isto levanta — de propósito. Cair
    num email padrão faria o script gravar memória no balde de outra pessoa
    assim que o projeto tiver mais de um jogador.

Exemplo:
    dono = owner_local()
    # → Owner(email="voce@example.com", is_admin=...)
"""

from config import settings
from engine.auth.identity import DonoObrigatorio, Owner, is_admin


def owner_local() -> Owner:
    """Owner da máquina de desenvolvimento, lido de `DEV_USER_EMAIL`."""
    email = (settings.DEV_USER_EMAIL or "").strip().lower()
    if not email:
        raise DonoObrigatorio(
            "defina DEV_USER_EMAIL no .env — ferramentas locais precisam de uma "
            "identidade para ler e gravar memória de jogo"
        )
    return Owner(email=email, is_admin=is_admin(email, settings.ADMIN_EMAILS))
