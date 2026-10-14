"""
Permissões explícitas: metadado × conteúdo, e papel por campanha.

Por que existe: `Owner.pode_ver()` diz "admin vê tudo" e a suíte inteira
    depende disso — não muda. Mas a decisão de 13/10 separou duas coisas que o
    `pode_ver` junta: o admin da INSTÂNCIA pode saber que a campanha de outra
    pessoa existe (metadado), e NÃO pode ler a narrativa dela (conteúdo) sem
    quebra-vidro explícito e auditado. Estas funções dizem isso com o nome.
Dependências: engine/auth/identity
Armadilha: admin da instância (`is_admin`, global, vem de ADMIN_EMAILS) ≠ GM
    da mesa (`papel`, por campanha). Uma coisa não implica a outra.
Armadilha: fail-closed. Papel desconhecido, vazio ou None = sem acesso. Nunca
    trate "papel que eu não reconheço" como "provavelmente player".

Exemplo:
    pode_ver_metadado(admin, "bob@x.com")                    # → True
    pode_ver_conteudo(admin, "bob@x.com")                    # → False
    pode_ver_conteudo(admin, "bob@x.com", quebra_vidro=True) # → True (+ auditoria)
"""

from __future__ import annotations

import structlog

from engine.auth.identity import OWNER_LEGADO, Owner

log = structlog.get_logger()

PAPEL_GM: str = "gm"
PAPEL_PLAYER: str = "player"
PAPEIS: frozenset[str] = frozenset({PAPEL_GM, PAPEL_PLAYER})


def _mesmo_dono(owner: Owner, dono: str | None) -> bool:
    return bool(dono) and owner.email.strip().lower() == str(dono).strip().lower()


def pode_ver_metadado(owner: Owner, dono: str | None) -> bool:
    """Existência, data, rótulo, personagens, tamanho. O dono vê; admin vê."""
    return owner.is_admin or _mesmo_dono(owner, dono)


def pode_ver_conteudo(owner: Owner, dono: str | None, quebra_vidro: bool = False) -> bool:
    """Narrativa, estado, resumo. Só o dono — admin apenas com quebra-vidro.

    Quebra-vidro devolver True NÃO basta: quem chama com `quebra_vidro=True`
    é obrigado a gravar a linha em `save_audit` com motivo ANTES de entregar o
    conteúdo (o `CampanhaStore` é o único caminho que faz isso). Aqui fica o
    log de alerta, para o uso aparecer mesmo se a auditoria falhar.
    """
    if _mesmo_dono(owner, dono):
        return True
    # Legado sem dono (vazio ou a marca da migração) é admin-only — decisão
    # travada de 13/10, a mesma do `pode_ver`. Não é narrativa de "outra
    # pessoa": não há outra pessoa a quem pedir licença.
    if not dono or str(dono).strip().lower() == OWNER_LEGADO:
        return owner.is_admin
    if quebra_vidro and owner.is_admin:
        log.warning("quebra_vidro_conteudo_alheio", admin=owner.email, dono=dono)
        return True
    return False


def papel_valido(papel: object) -> bool:
    """Fail-closed: só os papéis conhecidos contam."""
    return isinstance(papel, str) and papel in PAPEIS


def pode_ler_campanha(papel: object) -> bool:
    """Membro com papel válido lê o conteúdo da campanha."""
    return papel_valido(papel)


def pode_salvar_campanha(papel: object) -> bool:
    """Qualquer membro com papel válido grava save da campanha."""
    return papel_valido(papel)


def pode_gerir_campanha(papel: object) -> bool:
    """Só o GM da mesa mexe em membros e no nome da campanha."""
    return papel == PAPEL_GM
