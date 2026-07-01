"""
Formata o resultado da engine de combate em linhas de CONTEXTO pro LLM narrar.

Por que existe: na arquitetura engine-autoritativa (19/06, [[roadmap_combate_engine]]),
    a engine decide e rola; o Mestre só NARRA o que ela decidiu. Pra isso o prompt
    recebe linhas curtas e factuais — "ENGINE: seu ataque ACERTOU Goblin (19 vs CA
    15)" — que o Mestre veste de prosa SEM inventar número, CA ou HP. Estas funções
    são PURAS (sem estado/IO): recebem os resultados do orchestrator e devolvem a
    linha. Ficam separadas do orchestrator (que MUTA a WorkingMemory) pra serem
    trivialmente testáveis e reusadas no websocket (task 7) sem reescrever texto no
    handler. É a peça "a narração do LLM encolhe" do playbook de integração — e é
    independente do fluxo de dado (1 ou 2 passos), que o playtest calibra.
Dependências: engine.combat.resolver (ResultadoAtaque). Sem IO.
Armadilha: estas linhas são CONTEXTO pro LLM, não texto pro jogador — o prefixo
    "ENGINE:" sinaliza "isto é fato, dê corpo, não repita o número cru". O nome do
    alvo entra SEM artigo ("ACERTOU Goblin", não "ACERTOU o Goblin") pra não
    errar gênero (Loba/Goblin); o Mestre concorda o artigo na prosa.

Exemplo:
    linha_ataque_jogador("Goblin", ResultadoAtaque(True, 19, 15, False, False))
    # → "ENGINE: seu ataque ACERTOU Goblin (19 vs CA 15)."
"""

from typing import Any

from engine.combat.resolver import ResultadoAtaque

_PREFIXO = "ENGINE:"


def _nome(alvo_nome: str) -> str:
    """Nome do alvo limpo, com fallback genérico."""
    return (alvo_nome or "").strip() or "o alvo"


def linha_ataque_jogador(alvo_nome: str, r: ResultadoAtaque) -> str:
    """Linha de contexto do ataque do jogador resolvido pela engine.

    Crítico e falha crítica têm tratamento próprio (natural 20/1); senão informa
    total vs CA e se acertou. Gênero-safe (sem artigo antes do nome).
    """
    alvo = _nome(alvo_nome)
    if r.critico:
        return f"{_PREFIXO} ACERTO CRÍTICO em {alvo} (natural 20)."
    if r.falha_critica:
        return f"{_PREFIXO} FALHA CRÍTICA — seu ataque em {alvo} erra feio (natural 1)."
    if r.acertou:
        return f"{_PREFIXO} seu ataque ACERTOU {alvo} ({r.total} vs CA {r.ca_alvo})."
    return f"{_PREFIXO} seu ataque ERROU {alvo} ({r.total} vs CA {r.ca_alvo})."


def linha_dano_jogador(alvo_nome: str, dano: int, estado: str) -> str:
    """Linha de contexto do dano do jogador aplicado (com o novo estado do alvo).

    `estado` é o estado narrativo devolvido por `aplicar_dano_do_jogador`
    ("cambaleando", "ferido", "morto"…). "morto" tem frase própria.
    """
    alvo = _nome(alvo_nome)
    dano = max(0, int(dano))
    est = (estado or "").strip()
    if est == "morto":
        return f"{_PREFIXO} {dano} de dano — {alvo} cai sem vida."
    sufixo = f"; agora {est}" if est else ""
    return f"{_PREFIXO} {dano} de dano em {alvo}{sufixo}."


def linha_turno_inimigos(res: dict[str, Any]) -> str:
    """Linha de contexto do turno dos inimigos (quem acertou/errou, dano, HP do PJ).

    `res` é o retorno de `executar_turno_inimigos` (chaves `ataques` e, opcional,
    `hp_jogador`). Sem inimigos vivos → frase neutra.
    """
    ataques = res.get("ataques", []) or []
    if not ataques:
        return f"{_PREFIXO} nenhum inimigo vivo para agir."
    partes: list[str] = []
    for a in ataques:
        nome = str(a.get("nome") or a.get("id") or "inimigo").strip()
        if a.get("acertou"):
            crit = " crítico" if a.get("critico") else ""
            partes.append(f"{nome} acertou{crit} ({max(0, int(a.get('dano', 0)))} de dano)")
        else:
            partes.append(f"{nome} errou")
    hp = res.get("hp_jogador")
    cauda = f" Seu HP: {int(hp)}." if hp is not None else ""
    return f"{_PREFIXO} turno dos inimigos — " + "; ".join(partes) + "." + cauda


def classificar_tier(
    critico: bool,
    falha_critica: bool,
    estado_alvo: str,
    fim_combate: bool,
    ataques_inimigos: list[dict[str, Any]] | None = None,
) -> str:
    """"epico" se o turno tem um momento-chave, senão "seco" (task 8 do roadmap
    original do combate: "prosa em camadas" — o Mestre já é instruído a variar
    densidade, mas sem um sinal EXPLÍCITO por turno; esta função fornece o sinal.

    Épico: crítico do jogador, falha crítica, abate (estado_alvo=="morto"),
    fim de combate, ou QUALQUER inimigo acertando crítico no jogador. Todo o
    resto (ataque comum acerta/erra, dano sem abate) é seco — 1-2 frases
    mecânicas, sem florear.
    """
    if critico or falha_critica or estado_alvo == "morto" or fim_combate:
        return "epico"
    if ataques_inimigos and any(a.get("critico") for a in ataques_inimigos):
        return "epico"
    return "seco"
