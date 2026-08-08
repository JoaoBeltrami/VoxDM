"""
P4 — nenhuma regex de detecção pode ter duas definições.

Por que existe: `api/turn_pipeline.py` carregava um cabeçalho dizendo que suas
    regexes "espelham os do websocket.py". Espelhar é o problema: são duas cópias
    que ninguém garante iguais, e o CLAUDE.md registra essa classe de bug como a
    mais cara do projeto ("prompt e código que o consome DERIVAM em silêncio",
    4 ocorrências em 2 dias). Quando este teste foi escrito a duplicação JÁ não
    existia — o websocket importa do pipeline. O teste existe pra que ela não
    volte, e pra que o próximo a ler o arquivo não recrie a cópia por acreditar
    no comentário.
Dependências: nenhuma (lê o fonte como texto, não importa os módulos).
Armadilha: ler o FONTE em vez de importar é proposital. Importar veria o nome
    re-exportado no namespace do websocket e acusaria uma duplicata que não
    existe — o que importa é onde o `re.compile` está ESCRITO.

Exemplo:
    uv run pytest tests/test_regex_unica.py -q
"""

import re
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]

# Os três módulos que historicamente competiram pela mesma detecção.
_MODULOS: tuple[str, ...] = (
    "api/websocket.py",
    "api/turn_pipeline.py",
    "engine/llm/types.py",
)

# `_RE_X = re.compile(` ou `RE_X = re.compile(` no nível do módulo.
_RE_DEFINICAO = re.compile(r"^(_?RE_[A-Z0-9_]+)\s*=\s*re\.compile", re.MULTILINE)


def _definicoes(caminho: str) -> set[str]:
    return set(_RE_DEFINICAO.findall((_RAIZ / caminho).read_text(encoding="utf-8")))


def test_nenhuma_regex_definida_em_dois_modulos():
    por_nome: dict[str, list[str]] = {}
    for modulo in _MODULOS:
        for nome in _definicoes(modulo):
            por_nome.setdefault(nome, []).append(modulo)

    duplicadas = {n: m for n, m in por_nome.items() if len(m) > 1}
    assert not duplicadas, (
        "Regex com definição duplicada — extraia para um módulo único e importe: "
        f"{duplicadas}"
    )


def test_o_dono_das_regexes_de_combate_e_o_turn_pipeline():
    """Trava a DIREÇÃO da dependência, não só a ausência de cópia.

    Se alguém mover a definição de volta pro websocket, o teste acima continua
    passando (ainda seria definição única) mas o endpoint REST `/turn` perderia
    a implementação compartilhada — que é o motivo pelo qual ela mora aqui.
    """
    pipeline = _definicoes("api/turn_pipeline.py")
    for nome in ("_RE_ALVO_ATAQUE", "_RE_INIMIGO_MORTO", "_RE_INIMIGO_GRAVE",
                 "_RE_INIMIGO_FERIDO", "_RE_LAMPEJO"):
        assert nome in pipeline, f"{nome} deixou de ser definido em api/turn_pipeline.py"

    fonte_ws = (_RAIZ / "api/websocket.py").read_text(encoding="utf-8")
    assert "from api.turn_pipeline import" in fonte_ws


def test_o_cabecalho_declara_dono_unico():
    """O cabeçalho da seção precisa dizer que ali é a definição ÚNICA.

    Ele dizia "espelham os do websocket.py", o que já era falso e convidava o
    próximo leitor a recriar a cópia por acreditar que ela existia.

    Casar a frase antiga literalmente NÃO funciona como teste: o comentário novo
    a cita pra explicar o que mudou, e o assert acusaria a própria explicação.
    Por isso o teste afirma o que o cabeçalho DEVE dizer, não o que não pode.
    """
    fonte = (_RAIZ / "api/turn_pipeline.py").read_text(encoding="utf-8")
    cabecalho = next(
        (ln for ln in fonte.splitlines() if ln.startswith("# ─── Regexes de detecção")),
        "",
    )
    assert cabecalho, "sumiu o cabeçalho da seção de regexes"
    assert "DEFINIÇÃO ÚNICA" in cabecalho, cabecalho
