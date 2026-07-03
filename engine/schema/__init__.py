"""
Pacote de schema declarativo de módulos VoxDM.

Por que existe: separar a DEFINIÇÃO do formato de módulo (o que um criador escreve)
    da ingestão (ingestor/) e do runtime (engine/memory/). O Schema v2 é "o formato
    que outros criadores vão querer escrever" — validável, documentado, forward-
    compatível com o v1.2.
Dependências: pydantic v2.

Exemplo:
    from engine.schema import validar_modulo
    modulo = validar_modulo(json.load(open("meu_modulo.json")))
    # → ModuloV2 (lança ValidationError com mensagem clara se malformado)
"""

from engine.schema.v2 import (
    SCHEMA_VERSION,
    ModuloV2,
    validar_modulo,
)

__all__ = ["ModuloV2", "SCHEMA_VERSION", "validar_modulo"]
