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

# Marca de dado LEGADO — gravado antes de a identidade chegar à camada de
# memória. É uma marcação, não um email: ninguém autentica com ela, e por isso
# o dado legado continua admin-only (regra do `pode_ver`). A migração
# (`scripts/migrar_dono_memoria.py`) escreve esta marca em vez de chutar um dono.
OWNER_LEGADO: str = "__legado__"


class DonoObrigatorio(ValueError):
    """Tentativa de ler ou gravar memória de jogo sem um dono válido."""


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


def exigir_dono(owner: object) -> str:
    """Devolve o email normalizado do dono, ou levanta `DonoObrigatorio`.

    É o portão único das camadas de memória de jogo (Qdrant, Neo4j, saves):
    toda leitura e toda escrita passa por aqui antes de montar o filtro. Recusa
    `None`, string solta, email vazio e a marca de legado — nenhum desses é
    "alguém", e consultar sem alguém é exatamente o vazamento que se quer
    tornar impossível.
    """
    if not isinstance(owner, Owner):
        raise DonoObrigatorio(
            f"memória de jogo exige um Owner; recebi {type(owner).__name__}"
        )
    email = owner.email.strip().lower()
    if not email:
        raise DonoObrigatorio("memória de jogo exige Owner com email — veio vazio")
    if email == OWNER_LEGADO:
        raise DonoObrigatorio("a marca de legado não é uma identidade")
    return email


def emails_visiveis(owner: Owner) -> list[str]:
    """Donos cujo dado entra numa LEITURA de memória de jogo deste owner.

    Sempre o próprio email. Admin enxerga também o legado sem dono (decisão
    travada: legado é admin-only). Admin NÃO enxerga o dado de outro jogador
    aqui — a narrativa alheia só abre por quebra-vidro auditado, e isso mora em
    `engine/auth/permissoes.py`, não no caminho do turno.
    """
    email = exigir_dono(owner)
    return [email, OWNER_LEGADO] if owner.is_admin else [email]
