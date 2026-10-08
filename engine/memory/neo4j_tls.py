"""
Configuração TLS do driver Neo4j com as raízes de certificado do certifi.

Por que existe: o driver Neo4j valida o certificado do Aura contra a loja de
    certificados do sistema. No Windows essa loja é preenchida sob demanda e
    pode não ter a raiz que a instância usa — em 07/10/26 a instância nova do
    Aura veio assinada pela raiz SSL.com e TODA conexão falhou com
    "self-signed certificate in certificate chain", enquanto o httpx (que usa
    o certifi) falava com o Qdrant normalmente. Aqui o esquema `+s` vira
    "criptografado + raízes do certifi": a verificação continua ESTRITA, só
    muda de onde vem a lista de raízes confiáveis (a da Mozilla, a mesma de
    todo o resto do projeto).
Dependências: neo4j, certifi
Armadilha: NÃO trocar por `neo4j+ssc://` pra "fazer funcionar" — o `ssc`
    aceita qualquer certificado e abre a porta pra interceptação. E o driver
    recusa `encrypted`/`trusted_certificates` junto de um esquema `+s`/`+ssc`
    (ConfigurationError), por isso a URI é reescrita pra `neo4j://`/`bolt://`.

Exemplo:
    uri, tls = config_tls_neo4j("neo4j+s://abcd1234.databases.neo4j.io")
    # → ("neo4j://abcd1234.databases.neo4j.io",
    #    {"encrypted": True, "trusted_certificates": TrustCustomCAs(<certifi>)})
    driver = AsyncGraphDatabase.driver(uri, auth=(usuario, senha), **tls)
"""

from typing import Any

import certifi
from neo4j import TrustCustomCAs

# Esquemas que pedem TLS com verificação completa → esquema base equivalente.
_ESQUEMAS_VERIFICADOS: dict[str, str] = {
    "neo4j+s://": "neo4j://",
    "bolt+s://": "bolt://",
}


def config_tls_neo4j(uri: str) -> tuple[str, dict[str, Any]]:
    """Devolve (uri, kwargs) prontos pro `AsyncGraphDatabase.driver`.

    `neo4j+s://` e `bolt+s://` viram o esquema base com TLS verificado pelo
    certifi. Qualquer outro esquema (`neo4j://` local, `+ssc` explícito) passa
    intacto e sem kwargs: quem escolheu outra coisa, escolheu de propósito.
    """
    for prefixo, base in _ESQUEMAS_VERIFICADOS.items():
        if uri.startswith(prefixo):
            return base + uri[len(prefixo):], {
                "encrypted": True,
                "trusted_certificates": TrustCustomCAs(certifi.where()),
            }
    return uri, {}


def argumentos_driver_neo4j() -> dict[str, Any]:
    """URI, credenciais e TLS do settings, prontos pra `driver(**args, ...)`.

    Fonte única: todo lugar que abre driver (engine, ingestão, health, scripts)
    passa por aqui, pra correção de TLS não precisar ser repetida em oito
    arquivos da próxima vez.
    """
    from config import settings

    uri, tls = config_tls_neo4j(settings.NEO4J_URI)
    return {"uri": uri, "auth": (settings.NEO4J_USER, settings.NEO4J_PASSWORD), **tls}
