"""
Sessão longa no ESTILO DO BELTRAMI + correlação "fôlego pedido × entregue".

Por que existe: a medição de 24/07 (benchmark/run_tells) fechou o tell B mas
    deixou C em aberto, com uma ressalva honesta — desvio-padrão sobre 6 turnos
    é ruído. Este script ataca as duas pontas:
      1. CORPUS REALISTA — 16 turnos no jeito que o Beltrami joga de verdade
         (perguntas curtas a NPC, ação tática longa, exploração, combate,
         rolagem solta, OOC), colhidos dos playtests reais.
      2. DIAGNÓSTICO DE C — pra cada turno, lê no prompt QUAL fôlego a engine
         pediu (a linha TOM:) e compara com quantas frases o Mestre ENTREGOU.
         Se não houver correlação, a instrução não está pegando — e aí o
         problema não é o texto da regra, é a alavanca.
Dependências: httpx + websockets + API no ar com DEBUG=true (usa /debug/*).
Armadilha: `/debug/ultimo-turno` devolve o prompt do ÚLTIMO turno processado —
    tem que ser consultado logo após o `fim` daquele turno, antes do próximo.

Exemplo:
    uv run python benchmark/investiga_ritmo.py
"""

import asyncio
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.quality.tells import (  # noqa: E402
    _sentencas,
    emocao_rotulada,
    medir_ritmo,
    renarra_acao_do_jogador,
)

API = "http://127.0.0.1:8000"

# ── Corpus no ESTILO REAL do Beltrami ────────────────────────────────────────
# Colhido do jeito que ele joga nos playtests: mistura pergunta seca a NPC,
# ação tática descrita em detalhe, exploração, dúvida de regra (OOC), rolagem
# solta e combate. É essa variedade que estressa o ritmo do Mestre.
TURNOS: list[str] = [
    "Pergunto ao taverneiro sobre a guerra entre Tharnvik e Kaelmünd.",
    "Quem é o dono desse lugar?",
    "Eu me aproximo do forasteiro encapuzado no andar de cima e sento na mesa dele sem pedir licença.",
    "O que ele está bebendo?",
    "Ofereço uma rodada e pergunto o que ele sabe sobre os Kael.",
    "Quero saber sobre Vyrmathax.",
    "[OOC] eu consigo usar minha proficiência em Enganação aqui?",
    "Minto dizendo que sou enviado dos Tharn pra fechar um acordo de ferro.",
    "Saio da taverna e vou até a forja no fim da rua.",
    "Pergunto ao ferreiro quanto custa reforçar minha adaga.",
    "Ofereço ajuda em troca do serviço — digo que escolto o próximo carregamento.",
    "Sigo pela estrada com o carregamento, andando atrás da carroça e observando as árvores dos dois lados.",
    "Alguma coisa se move ali?",
    "Puxo a adaga devagar e me abaixo atrás da roda da carroça, esperando pra ver o que sai do mato.",
    "Ataco o primeiro que aparecer.",
    "[Rolagem: d20 = 17]",
]


async def rodar() -> list[dict]:
    import httpx
    import websockets

    async with httpx.AsyncClient() as cli:
        sid = (await cli.post(f"{API}/session/start", timeout=90, json={
            "player_name": "Sylas", "player_race": "tiefling", "player_class": "ladino",
            "player_level": 3, "location_id": "kaelmund", "location_nome": "Kaelmund",
        })).json()["session_id"]
        print(f"sessão: {sid}\n", flush=True)

        registros: list[dict] = []
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

            await ate_fim()  # abertura

            for i, fala in enumerate(TURNOS, 1):
                await ws.send(json.dumps({"tipo": "turno", "texto": fala}))
                narracao = await ate_fim()

                # Qual fôlego a ENGINE pediu neste turno? (verdade do prompt)
                pedido = "?"
                try:
                    ult = (await cli.get(f"{API}/debug/ultimo-turno/{sid}", timeout=30)).json()
                    sysmsg = ult["mensagens_groq"][0]["content"]
                    m_tom = re.search(r"TOM: ([^\n]+)", sysmsg)
                    if m_tom:
                        linha = m_tom.group(1)
                        if "UMA frase" in linha:
                            pedido = "curto"
                        elif "RESPIRAR" in linha:
                            pedido = "longo"
                        elif "momento-chave" in linha:
                            pedido = "epico"
                        else:
                            pedido = "medio"
                except Exception as e:  # nunca derruba a corrida
                    print(f"  (debug indisponível: {str(e)[:40]})", flush=True)

                frases = len(_sentencas(narracao))
                registros.append({
                    "n": i, "fala": fala, "narracao": narracao,
                    "pedido": pedido, "frases": frases,
                    "palavras": len(narracao.split()),
                    "rotulos": emocao_rotulada(narracao),
                    "renarracao": renarra_acao_do_jogador(narracao, fala),
                })
                print(f"  {i:2}. pedido={pedido:6} → {frases} frases / "
                      f"{len(narracao.split()):3} palavras  | {fala[:42]}", flush=True)
        return registros


def relatorio(regs: list[dict]) -> None:
    print("\n" + "=" * 76)
    print("CORRELAÇÃO — o fôlego que a engine PEDE chega no que o Mestre ENTREGA?")
    print("=" * 76)
    por_pedido: dict[str, list[int]] = defaultdict(list)
    for r in regs:
        por_pedido[r["pedido"]].append(r["frases"])

    for pedido in ("curto", "medio", "longo", "epico", "?"):
        vals = por_pedido.get(pedido)
        if not vals:
            continue
        print(f"  pedido={pedido:6} n={len(vals):2}  frases: "
              f"média {statistics.mean(vals):.1f}  min {min(vals)}  max {max(vals)}  {vals}")

    curtos_pedidos = por_pedido.get("curto", [])
    if curtos_pedidos:
        obedeceu = sum(1 for v in curtos_pedidos if v <= 2)
        print(f"\n  ADESÃO ao 'curto' (≤2 frases): {obedeceu}/{len(curtos_pedidos)}")
    longos = por_pedido.get("longo", [])
    if longos:
        obedeceu_l = sum(1 for v in longos if v >= 4)
        print(f"  ADESÃO ao 'longo' (≥4 frases):  {obedeceu_l}/{len(longos)}")

    todas = [r["frases"] for r in regs]
    print(f"\n  distribuição geral de frases: {todas}")
    print(f"  desvio-padrão: {statistics.pstdev(todas):.2f}  "
          f"(quanto MAIOR, mais variado o ritmo)")

    r = medir_ritmo([x["narracao"] for x in regs])
    print(f"  formas de abertura distintas: {int(r['formas_distintas'])}  "
          f"dominância {r['dominancia_abertura']:.2f}  curtos {r['curtos']:.2f}")

    rot = [x for r_ in regs for x in r_["rotulos"]]
    ren = [r_["renarracao"] for r_ in regs if r_["renarracao"]]
    print(f"\n  B emoção rotulada: {len(rot)} em {len(regs)} turnos "
          f"({len(rot) / len(regs):.2f}/turno)")
    for x in rot[:5]:
        print(f"     • {x}")
    print(f"  A renarração: {len(ren)} ({len(ren) / len(regs):.2f}/turno)")
    for x in ren[:3]:
        print(f"     • {x[:70]}")

    # Amostra pro olho humano julgar depois
    print("\n  — amostra (o turno mais curto e o mais longo) —")
    for r_ in (min(regs, key=lambda x: x["frases"]), max(regs, key=lambda x: x["frases"])):
        print(f"  [{r_['pedido']}, {r_['frases']}f] {r_['fala'][:44]}")
        print(f"     → {r_['narracao'][:190]}")


async def main() -> None:
    regs = await rodar()
    relatorio(regs)
    saida = Path(__file__).parent / "results_ritmo.json"
    saida.write_text(json.dumps(regs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n(bruto em {saida.name})")


if __name__ == "__main__":
    asyncio.run(main())
