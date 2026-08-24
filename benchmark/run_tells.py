"""
Mede os tells de máquina do Mestre: narração de ANTES vs turnos AO VIVO agora.

Por que existe: o ADR-005 travou o gate do single-player na Camada 1 ("o Mestre
    soa humano?") — mas "humano" era um DIAL sem número, e a única validação era
    o Beltrami jogar e sentir. Este bench roda os MESMOS turnos que geraram os
    tells no playtest de 22/07 e compara com o que a engine produz agora,
    usando `engine/quality/tells.py` como régua.
Dependências: httpx + websockets; a API precisa estar no ar (127.0.0.1:8000).
Armadilha: o corpus ANTES é congelado (narração real, colhida antes das
    correções de 23/07). Não re-colher — é o ponto de comparação histórico. O
    DEPOIS é gerado ao vivo, então varia entre execuções: LLM é estocástico.
    Rode 2-3 vezes antes de concluir que uma mudança piorou algo.

Exemplo:
    uv run python benchmark/run_tells.py
    # → tabela ANTES vs DEPOIS por tell + veredito
"""

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Console do Windows abre em cp1252 e o "✓" do progresso derruba a corrida INTEIRA
# com UnicodeEncodeError — depois de já ter gasto cota de LLM. Mesmo remédio que
# `demo/query_demo.py` usa. (Mordeu em 17/08, na 1ª tentativa de medir.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from engine.quality.tells import avaliar_sessao  # noqa: E402

API = "http://127.0.0.1:8000"

# ── Corpus ANTES — narração REAL da engine em 22/07, pré-correções ────────────
# Colhido dos mini-playtests headless daquele dia (sessões do ferreiro/contrato
# e do bandido na taverna). CONGELADO de propósito: é a linha de base.
ANTES: list[tuple[str, str]] = [
    (
        "Pergunto ao ferreiro sobre o contrato de ferro que os Kael querem fechar.",
        "O ferreiro olha em volta nervoso, como se temesse ser ouvido. Em voz baixa, "
        'ele diz: "O contrato de ferro... é um arranjo delicado. Os Kael querem que '
        'nos forneçamos com ferro em grandes quantidades, mas a preço abaixo do mercado." '
        "Ele pausa, observando a sua reação.",
    ),
    (
        "Digo que posso escoltar o carregamento de ferro até a forja. Aceito o trabalho.",
        'O ferreiro assente, um brilho de gratidão nos olhos. "Muito bem, eu... eu '
        'agradeço. O carregamento sai amanhã ao amanhecer." Ele entrega um pedaço de '
        "pergaminho com um selo de cera.",
    ),
    (
        "Sigo com o carregamento pela estrada, atento a emboscada.",
        "A estrada sinuosa serpenteia pela floresta escura, sombras dançando ao redor. "
        "Grimbold guia os cavalos com calma, mas você nota um leve tremor em suas mãos. "
        "De repente, um galho quebra na floresta, fazendo os cavalos relinchar "
        'nervosamente. Grimbold olha em volta, alarmado. "O que foi isso?" ele sussurra.',
    ),
    (
        "Entrego o ferro na forja e cobro a palavra deles sobre a guerra.",
        "O ferreiro de Kaelmünd recebe o carregamento com um aceno de aprovação. "
        '"Bem feito, bem feito. Você é um homem de palavra." Ele olha em volta, '
        "verificando se alguém está ouvindo, e diz em voz baixa: \"Sobre a guerra... "
        'os Kael estão se preparando para algo grande."',
    ),
    (
        "Entro na taverna e provoco o bandido que está bebendo no canto.",
        "O homem ao balcão, que você provoca, olha para você com olhos frios, mas não "
        "parece impressionado. Ele se levanta, passa as costas das mãos nos cabelos, e "
        "caminha em direção a você, um sorriso cruel pintado no rosto.",
    ),
    (
        "Saco minha adaga e ataco o bandido.",
        "Você saca a adaga com um movimento rápido e mira no peito do bandido, enquanto "
        "ele se aproxima com um sorriso cruel. Com a lâmina pronta para atingir seu "
        "alvo, você investe contra o bandido.",
    ),
]

# Os mesmos turnos, pra gerar o corpus DEPOIS na engine atual.
TURNOS_DEPOIS: list[str] = [t for t, _ in ANTES]


async def colher_ao_vivo() -> list[tuple[str, str]]:
    """Roda os turnos na engine atual e devolve [(fala, narração), ...]."""
    import httpx
    import websockets

    async with httpx.AsyncClient() as cli:
        r = await cli.post(f"{API}/session/start", timeout=90, json={
            "player_name": "Sylas", "player_race": "tiefling", "player_class": "ladino",
            "player_level": 3, "location_id": "kaelmund", "location_nome": "Kaelmund",
        })
        sid = r.json()["session_id"]
        print(f"sessão ao vivo: {sid}", flush=True)

        colhido: list[tuple[str, str]] = []
        async with websockets.connect(
            f"ws://127.0.0.1:8000/ws/game/{sid}", max_size=16 * 1024 * 1024
        ) as ws:
            await ws.send(json.dumps({"tipo": "init"}))

            async def ate_fim() -> str:
                texto = ""
                while True:
                    m = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
                    if m.get("tipo") == "token":
                        texto += m.get("conteudo", "")
                    elif m.get("tipo") == "erro":
                        raise RuntimeError(m.get("conteudo"))
                    elif m.get("tipo") == "fim":
                        return texto.strip()

            await ate_fim()  # abertura, descartada (não tem fala do jogador)
            for fala in TURNOS_DEPOIS:
                await ws.send(json.dumps({"tipo": "turno", "texto": fala}))
                narracao = await ate_fim()
                colhido.append((fala, narracao))
                print(f"  ✓ {fala[:48]}…", flush=True)
        return colhido


def _linha(rotulo: str, rel) -> str:
    r = rel.ritmo
    return (
        f"{rotulo:8} | {len(rel.rotulos):2} ({rel.rotulos_por_turno:.2f}/t) "
        f"| {len(rel.renarracoes):2} ({rel.renarracoes_por_turno:.2f}/t) "
        f"| desvio {r['desvio_frases']:.2f}  formas {int(r['formas_distintas'])}  "
        f"dom {r['dominancia_abertura']:.2f}  curtos {r['curtos']:.2f}"
    )


async def main() -> None:
    """N execuções do corpus DEPOIS; compara MEDIANAS com o ANTES congelado.

    N>1 não é luxo: a primeira medição de 24/07 deu 0.67 rótulos/turno e a
    segunda 1.17, com a mesma engine e o mesmo prompt. A variância do LLM é
    MAIOR que o efeito que se quer medir — uma execução isolada mente nas duas
    direções. Mediana de 3 é o mínimo pra afirmar alguma coisa.
    """
    n_runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    t0 = time.perf_counter()
    antes = avaliar_sessao(ANTES)

    corridas = []
    for i in range(n_runs):
        print(f"\n— corrida {i + 1}/{n_runs} —", flush=True)
        corridas.append(avaliar_sessao(await colher_ao_vivo()))

    # Linha de detalhe: a corrida MEDIANA em B (representa o caso típico).
    depois = sorted(corridas, key=lambda r: r.rotulos_por_turno)[len(corridas) // 2]
    med_rot = statistics.median([c.rotulos_por_turno for c in corridas])
    med_ren = statistics.median([c.renarracoes_por_turno for c in corridas])
    med_desvio = statistics.median([c.ritmo["desvio_frases"] for c in corridas])
    med_dom = statistics.median([c.ritmo["dominancia_abertura"] for c in corridas])
    print(f"\ncorridas B/turno: {[c.rotulos_por_turno for c in corridas]}")
    print(f"corridas A/turno: {[c.renarracoes_por_turno for c in corridas]}")

    print("\n" + "=" * 78)
    print(f"{'':8} | {'B: emoção rotulada':^18} | {'A: renarração':^15} | C: ritmo")
    print("-" * 78)
    print(_linha("ANTES", antes))
    print(_linha("DEPOIS", depois))
    print("=" * 78)

    def delta(a: float, d: float, menor_melhor: bool = True) -> str:
        if a == d:
            return "="
        melhor = (d < a) if menor_melhor else (d > a)
        return f"{'✓' if melhor else '✗'} {a:.2f} → {d:.2f}"

    print(f"\n— veredito por MEDIANA de {n_runs} corridas —")
    print(f"B (emoção rotulada/turno): {delta(antes.rotulos_por_turno, med_rot)}")
    print(f"A (renarração/turno):      {delta(antes.renarracoes_por_turno, med_ren)}")
    print(f"C (desvio de ritmo):       "
          f"{delta(antes.ritmo['desvio_frases'], med_desvio, menor_melhor=False)}")
    print(f"C (dominância abertura):   "
          f"{delta(antes.ritmo['dominancia_abertura'], med_dom)}")

    if depois.rotulos:
        print("\nEmoções ainda rotuladas (DEPOIS):")
        for r in depois.rotulos[:6]:
            print(f"  • {r}")
    if depois.renarracoes:
        print("\nRenarrações restantes (DEPOIS):")
        for r in depois.renarracoes[:4]:
            print(f"  • {r[:80]}")

    print(f"\n({time.perf_counter() - t0:.0f}s)")


if __name__ == "__main__":
    asyncio.run(main())
