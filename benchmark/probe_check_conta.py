"""E2E do ciclo de check: pedir → o dado abrir → rolar → a CONTA voltar.

Por que existe: os três pedaços foram shippados separados (CHECK-JOGADOR-ZERO,
    CHECK-GRUDENTO-1, CHECK-INVISIVEL-1) e só juntos formam a experiência. Este
    probe roda o ciclo inteiro contra a API local, sem browser e sem o Beltrami.
Dependências: httpx, websockets; a API precisa estar no ar (127.0.0.1:8000).
Armadilha: gasta 3 turnos de cota real do LLM — não rodar em loop.

Exemplo:
    uv run python benchmark/probe_check_conta.py
"""

import asyncio
import json

import httpx
import websockets

API = "http://127.0.0.1:8000"

async def turno(ws, txt):
    await ws.send(json.dumps({"tipo": "turno", "texto": txt}))
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
        if m.get("tipo") == "fim":
            return m
        if m.get("tipo") == "erro":
            raise RuntimeError(m.get("conteudo"))

async def main():
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{API}/session/start", json={
            "player_name": "Probe", "player_class": "Ladino", "player_level": 3,
            "wis_score": 14, "skill_profs": ["Percepção"]})
        sid = r.json()["session_id"]
    async with websockets.connect(f"ws://127.0.0.1:8000/ws/game/{sid}", max_size=16*1024*1024) as ws:
        await ws.send(json.dumps({"tipo": "init"}))
        while True:
            if json.loads(await asyncio.wait_for(ws.recv(), timeout=120)).get("tipo") == "fim":
                break
        f1 = await turno(ws, "quero rolar Percepção")
        print("pedido -> check_pedido:", repr(f1.get("check_pedido")))
        f2 = await turno(ws, "[Rolagem: d20 = 14]")
        print("rolagem -> check_resolvido:", json.dumps(f2.get("check_resolvido"), ensure_ascii=False))
        f3 = await turno(ws, "Sigo em frente.")
        print("turno seguinte -> limpo?:", f3.get("check_resolvido") in ({}, None))

asyncio.run(main())
