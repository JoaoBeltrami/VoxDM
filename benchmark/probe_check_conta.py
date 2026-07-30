"""E2E: o jogador PEDE um check, ROLA, e a conta volta no payload."""
import asyncio, json, httpx, websockets
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
