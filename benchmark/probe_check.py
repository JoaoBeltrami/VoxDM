"""Probe headless: o pedido de check do JOGADOR abre o dado?

Valida end-to-end o fix `05ffc7c` (aliases EN de perícia) + `4c1c9a3`
(check_pedido no payload). O playtest 26/07 mostrou o pedido funcionando com
"Percepção" e falhando com "insight" — o classificador era PT-only.

Roda contra a API local; não precisa de browser nem do Beltrami.
"""

import asyncio
import json
import sys

import httpx
import websockets

API = "http://127.0.0.1:8000"


async def turno(ws, texto: str) -> dict:
    """Envia um turno e devolve o payload `fim`."""
    await ws.send(json.dumps({"tipo": "turno", "texto": texto}))
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
        if m.get("tipo") == "fim":
            return m
        if m.get("tipo") == "erro":
            raise RuntimeError(m.get("conteudo"))


async def main() -> None:
    async with httpx.AsyncClient(timeout=60) as cli:
        r = await cli.post(f"{API}/session/start", json={
            "location_id": "drevamor", "location_nome": "Drevamor",
            "player_name": "Probe", "player_class": "Ladino", "player_level": 3,
            "wis_score": 14, "player_hp": 30, "player_hp_max": 30,
        })
        r.raise_for_status()
        sid = r.json()["session_id"]
    print(f"sessao: {sid}", flush=True)

    async with websockets.connect(
        f"ws://127.0.0.1:8000/ws/game/{sid}", max_size=16 * 1024 * 1024
    ) as ws:
        await ws.send(json.dumps({"tipo": "init"}))
        while True:  # consome a abertura
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
            if m.get("tipo") == "fim":
                break

        casos = [
            ("quero rolar insight", "Intuição"),      # o que FALHOU no playtest
            ("quero rolar Percepção", "Percepção"),   # o que funcionou
            ("vou tentar stealth", "Furtividade"),    # alias EN novo
            ("olho em volta com calma", ""),          # sem pedido: não pode abrir
        ]
        ok = True
        for texto, esperado in casos:
            fim = await turno(ws, texto)
            got = fim.get("check_pedido", "")
            marca = "OK " if got == esperado else "FALHA"
            if got != esperado:
                ok = False
            print(f"  [{marca}] {texto!r:32} check_pedido={got!r} (esperado {esperado!r})",
                  flush=True)

    print("\nRESULTADO:", "todos passaram" if ok else "houve falha")
    sys.exit(0 if ok else 1)


asyncio.run(main())
