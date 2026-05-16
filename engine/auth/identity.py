"""
Dataclass Owner — identidade do dono de uma sessão/dado no VoxDM.

Por que existe: separa "quem está pedindo" da lógica de cada camada. Sem
    isso, `owner_email` viraria string passada como kwarg opcional em cada
    função, levando a `None` esquecido e leak entre usuários. Como dataclass
    explícito, qualquer função que aceita Owner deixa claro que precisa
    decidir o que fazer baseado em quem é.

Dependências: nenhuma — pure Python.

Armadilha: `is_admin` é derivado de `settings.ADMIN_EMAILS` no momento da
    construção. Se a lista de admins muda em runtime (raro), reconstruir
    o Owner. Não cachear estado de admin em outros lugares.

Exemplo:
    owner = Owner(email="admin@example.com", is_admin=True)
    if owner.is_admin:
        return tudo()
    return apenas_de(owner.email)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Owner:
    """Identidade do solicitante autenticado.

    `frozen=True` previne mutação acidental do email durante a request
    (anti-padrão: escalar privilégio reescrevendo o owner em algum middleware).
    """
    email: str
    is_admin: bool = False

    def pode_ver(self, outro_email: str | None) -> bool:
        """True se este owner pode ler dado pertencente a `outro_email`.

        Regra: admin vê tudo (inclusive sessões sem dono — NULL). Não-admin
        só vê o que é dele. Dados com owner_email vazio/None são considerados
        admin-only (legado pré-auth).
        """
        if self.is_admin:
            return True
        if not outro_email:
            return False
        return self.email.lower() == outro_email.lower()


def is_admin(email: str, admin_emails_csv: str) -> bool:
    """Resolve admin a partir do CSV de settings.ADMIN_EMAILS.

    Case-insensitive. Espaços em volta são tolerados. Lista vazia = ninguém é admin.
    """
    if not email or not admin_emails_csv:
        return False
    alvo = email.strip().lower()
    admins = [e.strip().lower() for e in admin_emails_csv.split(",") if e.strip()]
    return alvo in admins
