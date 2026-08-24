"""
M1: o repositório não pode nascer com "todo mundo é admin".

Por que existe (auditoria de segurança de 28/06, corrigida em 17/08): tanto
    `DEV_USER_EMAIL` quanto `ADMIN_EMAILS` tinham default `admin@localhost` —
    a MESMA string. Em `DEBUG=True`, toda requisição sem header do Cloudflare
    vira `DEV_USER_EMAIL`; como esse email estava na lista de admins, qualquer
    um que alcançasse a URL (um túnel aberto basta) era admin e lia `/debug/*`:
    prompt inteiro, estado de sessão, memória episódica. O comentário no
    `config.py` ainda afirmava que "o default genérico não dá acesso admin".
Dependências: nenhuma — lê os defaults declarados e o `.env.example`.
Armadilha: NÃO testar `settings.ADMIN_EMAILS`. O `conftest` injeta valores de
    teste por env var, e env var vence o default — o teste passaria verde
    medindo a configuração do próprio teste. O que importa é o default DECLARADO
    na classe, que é o que um clone novo recebe.

Exemplo:
    uv run pytest tests/test_admin_por_padrao.py -q
"""

import pathlib
import re

from config import Settings

_RAIZ = pathlib.Path(__file__).resolve().parents[1]


def _default(campo: str) -> str:
    """O default DECLARADO na classe — não o valor efetivo desta execução."""
    return str(Settings.model_fields[campo].default)


def test_identidade_nao_tem_default_no_repositorio():
    """Identidade é configuração de AMBIENTE, não default de código."""
    assert _default("DEV_USER_EMAIL") == "", (
        "DEV_USER_EMAIL voltou a ter default. Em DEBUG isso dá identidade "
        "válida a qualquer requisição sem header."
    )
    assert _default("ADMIN_EMAILS") == "", (
        "ADMIN_EMAILS voltou a ter default. Lista de admin embutida no "
        "repositório é admin-por-padrão em toda instalação."
    )


def test_o_par_perigoso_nao_pode_voltar():
    """A falha do M1 não era um valor — era os DOIS serem iguais."""
    dev, admins = _default("DEV_USER_EMAIL"), _default("ADMIN_EMAILS")
    if not dev or not admins:
        return  # vazio já é seguro; o par nem se forma
    lista = [e.strip().lower() for e in admins.split(",") if e.strip()]
    assert dev.strip().lower() not in lista, (
        f"o default de DEV_USER_EMAIL ({dev!r}) está na lista de ADMIN_EMAILS: "
        "em DEBUG, todo mundo vira admin."
    )


def test_env_example_nao_entrega_o_footgun_pronto():
    """O caminho DOCUMENTADO também não pode gerar admin-por-padrão.

    Trocar só o default do código adiantaria pouco: quem clona copia o
    `.env.example`, e era ele que trazia os dois campos com o mesmo email.
    """
    texto = (_RAIZ / ".env.example").read_text(encoding="utf-8")

    def valor(chave: str) -> str:
        m = re.search(rf"^{chave}=(.*)$", texto, re.MULTILINE)
        return (m.group(1).strip() if m else "")

    dev, admins = valor("DEV_USER_EMAIL"), valor("ADMIN_EMAILS")
    if not admins:
        return  # vazio é o estado desejado
    lista = [e.strip().lower() for e in admins.split(",") if e.strip()]
    assert dev.lower() not in lista, (
        ".env.example entrega DEV_USER_EMAIL dentro de ADMIN_EMAILS — quem "
        "copiar o exemplo roda admin-por-padrão em DEBUG."
    )


def test_lista_vazia_significa_ninguem_e_admin():
    """O guard que torna o default vazio SEGURO, e não só ausente."""
    from engine.auth.identity import is_admin

    assert is_admin("qualquer@um.com", "") is False
    assert is_admin("", "") is False
