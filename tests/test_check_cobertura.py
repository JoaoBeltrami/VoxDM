"""
CHECK-SEM-COBERTURA-1 (playtest 09/08): o teste que o MESTRE pede também conta.

Por que existe: 22 turnos jogados e só DOIS testes chegaram à engine. A pendência
    só nascia quando o JOGADOR pedia ("quero rolar Percepção"); quando o MESTRE
    pedia — que é a maioria, *"ele já pede testes de acrobacia e etc"* — não havia
    registro nenhum. A engine tentava ler a perícia da prosa dele só no instante
    em que o d20 chegava; sem rolagem, o teste evaporava sem bônus, sem CD e sem
    consequência do P8. Não era o P8 que estava fraco: era o alcance.
Dependências: `eh_teste_pericia` (a MESMA detecção que já rodava tarde demais).
Armadilha: a cobrança vai pelo canal `fatos_engine`, NUNCA concatenada no texto
    do jogador — foi assim que o Mestre passou a tratar a engine como
    interlocutor (ENGINE-COMO-INTERLOCUTOR-1).

Exemplo:
    uv run pytest tests/test_check_cobertura.py -q
"""

from pathlib import Path

from engine.combat.intent import eh_teste_pericia

_RAIZ = Path(__file__).resolve().parents[1]
_WS = (_RAIZ / "api/websocket.py").read_text(encoding="utf-8")


# ── A detecção já sabia ler o pedido do Mestre ───────────────────────────────


def test_pedido_do_mestre_e_detectavel():
    """Se isto falhar, o problema é anterior à pendência."""
    assert eh_teste_pericia("Faça um teste de Acrobacia para atravessar a viga.")
    assert eh_teste_pericia("Role Percepção.")


def test_prosa_comum_nao_vira_teste():
    assert not eh_teste_pericia("O taverneiro enche sua caneca e sorri.")


# ── A pendência passa a nascer do lado do Mestre ─────────────────────────────


def test_pendencia_nasce_do_pedido_do_mestre():
    assert "check_pedido_pelo_mestre" in _WS
    i = _WS.index("check_pedido_pelo_mestre")
    bloco = _WS[max(0, i - 900):i]
    assert "eh_teste_pericia(resposta_limpa)" in bloco, (
        "a detecção precisa rodar sobre a resposta do MESTRE, não só na rolagem"
    )


def test_pendencia_do_mestre_guarda_o_bonus_da_ficha():
    """Sem o bônus junto, a cobrança obrigaria o Mestre a fazer conta — e
    aritmética por LLM foi o que gerou 'alguns não aplicaram o bônus'."""
    i = _WS.index("check_pedido_pelo_mestre")
    bloco = _WS[max(0, i - 900):i]
    assert "bonus_de_check(sessao.working_mem, _pericia_mestre)" in bloco


def test_pedido_do_jogador_tem_prioridade():
    """O pedido do Mestre só cria pendência se NÃO houver uma viva — senão ele
    sobrescreveria a perícia que o jogador acabou de abrir."""
    i = _WS.index("check_pedido_pelo_mestre")
    bloco = _WS[max(0, i - 900):i]
    assert "if not sessao.check_pendente" in bloco


def test_session_zero_nao_abre_teste():
    """Durante a criação de personagem por voz não existe cena pra testar."""
    i = _WS.index("check_pedido_pelo_mestre")
    bloco = _WS[max(0, i - 900):i]
    assert "session_zero_ativa" in bloco


# ── A cobrança ───────────────────────────────────────────────────────────────


def test_pendencia_viva_e_cobrada():
    assert "check_pendente_cobrado" in _WS


def test_cobranca_vai_pelo_canal_de_fatos_e_nao_pelo_texto_do_jogador():
    """ENGINE-COMO-INTERLOCUTOR-1: fato da engine tem canal próprio. Concatenar
    no texto do jogador faz o Mestre narrar a engine de volta."""
    i = _WS.index("check_pendente_cobrado")
    bloco = _WS[max(0, i - 1200):i]
    assert "_fatos_engine.append(" in bloco
    assert "texto_jogador +=" not in bloco


def test_cobranca_leva_o_bonus_ja_calculado():
    """⚠️ REESCRITO em 12/08: a versão anterior assertava a linha
    `_b = int(_p.get("bonus")` — ou seja, FIXAVA O BUG. `bonus_de_check` devolve
    uma TUPLA `(número, explicação)`, e aquele `int()` derrubou o turno inteiro
    no playtest com "int() argument must be ... not 'tuple'". Um teste que trava
    a implementação em vez do comportamento vira cúmplice do defeito.
    """
    i = _WS.index("check_pendente_cobrado")
    bloco = _WS[max(0, i - 2200):i]
    assert "isinstance(_bruto, (tuple, list))" in bloco, (
        "a pendência guarda a tupla de `bonus_de_check` — desempacotar, não converter"
    )
    assert "{_b:+d}" in bloco, "o sinal explícito (+3/-1) evita o Mestre inverter"


def test_a_pendencia_ainda_expira():
    """Cobrar pra sempre seria pior que não cobrar: o dado ficaria aberto na
    perícia errada (o bug que criou o _MAX_TURNOS_CHECK)."""
    # Janela larga de propósito: comentário novo entre a expiração e a cobrança
    # empurra a âncora pra fora e o teste falha sem nada ter regredido — foi o
    # que aconteceu em 12/08. Se você precisa da janela, deixe folga.
    i = _WS.index("check_pendente_cobrado")
    bloco = _WS[max(0, i - 3000):i]
    assert "_MAX_TURNOS_CHECK" in bloco
    assert "check_pendente_expirado" in bloco
