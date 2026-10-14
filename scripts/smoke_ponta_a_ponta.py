"""
Smoke de ponta a ponta contra a API REAL e os bancos REAIS — e limpa o que criou.

Por que existe: teste verde prova mecanismo com cliente fake; ele não prova que
    o Qdrant Cloud aceita o índice de tenant, que o `MERGE` do afeto roda no
    AuraDB, nem que um turno atravessa o WebSocket. Em 14/10 foi este smoke que
    achou o AFETO-ID-CURTO-1 (rancor gravado num id que ninguém lia).
Dependências: httpx, websockets, qdrant-client, neo4j, config. A API precisa
    estar de pé (scripts/exec/start.bat) com DEBUG=true.
Armadilha: em DEBUG a API entra como DEV_USER_EMAIL — que é VOCÊ. Sem a
    limpeza, o smoke deixaria na SUA memória de jogo um resumo episódico de um
    personagem de teste e um rancor do Bjorn, e o Mestre "lembraria" disso na
    próxima sessão de verdade. Por isso a limpeza roda por padrão: apaga só o
    que tem os session_ids criados nesta execução, e devolve o afeto do dono ao
    valor de antes. `--manter` pula a limpeza (para inspecionar à mão).
Armadilha: gasta cota real de LLM (~4 aberturas/turnos + resumo). Não rode em
    loop.

Exemplo:
    uv run python scripts/smoke_ponta_a_ponta.py
    # → [OK] turnos_sem_erro {"total": 3} ... ; exit 1 se alguma etapa falhou
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

import httpx  # noqa: E402
import websockets  # noqa: E402

API: str = "http://localhost:8000"
WS: str = "ws://localhost:8000"
NPC_DO_TESTE: str = "bjorn-tharnsson"
FALAS: tuple[str, ...] = (
    "Eu me aproximo do Bjorn e pergunto o que ele sabe sobre os Carniçais da Cinza",
    "Eu cuspo no chão perto do Bjorn e chamo ele de covarde na frente de todo mundo",
    "Eu respiro fundo e peço desculpas ao Bjorn, dizendo que estou com medo da guerra",
)


class Relatorio:
    """Etapas OK/FALHA com evidência — o que o smoke devolve."""

    def __init__(self) -> None:
        self.etapas: dict[str, dict[str, Any]] = {}
        self.turnos: list[dict[str, Any]] = []

    def marcar(self, nome: str, ok: bool, **evidencia: Any) -> None:
        self.etapas[nome] = {"ok": ok, **evidencia}
        linha = json.dumps(evidencia, ensure_ascii=False, default=str)[:300]
        sys.stdout.write(f"[{'OK' if ok else 'FALHA'}] {nome} {linha}\n")
        sys.stdout.flush()

    @property
    def falhas(self) -> list[str]:
        return [k for k, v in self.etapas.items() if not v["ok"]]


async def _ler_ate_fim(ws: Any, limite_s: float = 120.0) -> dict[str, Any]:
    texto: list[str] = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < limite_s:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=limite_s))
        if msg.get("tipo") == "token":
            texto.append(msg.get("conteudo", ""))
        elif msg.get("tipo") == "erro":
            return {"erro": msg, "texto": "".join(texto)}
        elif msg.get("tipo") == "fim":
            return {"fim": msg, "texto": "".join(texto), "segundos": round(time.perf_counter() - t0, 1)}
    return {"erro": "timeout", "texto": "".join(texto)}


# ── estado do dono antes/depois (para a limpeza devolver o afeto) ────────────


async def _afeto_do_dono(driver: Any, dono: str) -> dict[str, dict[str, Any]]:
    async with driver.session() as s:
        linhas = await (await s.run(
            "MATCH (e:EstadoNPC {owner_email: $d}) RETURN e.npc_id AS n, properties(e) AS p",
            {"d": dono},
        )).data()
    return {str(r["n"]): dict(r["p"]) for r in linhas}


async def restaurar_afeto(driver: Any, dono: str, antes: dict[str, dict[str, Any]]) -> int:
    """Devolve cada :EstadoNPC do dono ao snapshot. Retorna quantos mexeu."""
    depois = await _afeto_do_dono(driver, dono)
    mexidos = 0
    async with driver.session() as s:
        for npc, props in depois.items():
            if npc not in antes:
                await s.run(
                    "MATCH (e:EstadoNPC {owner_email: $d, npc_id: $n}) DELETE e",
                    {"d": dono, "n": npc},
                )
                mexidos += 1
            elif props != antes[npc]:
                await s.run(
                    "MATCH (e:EstadoNPC {owner_email: $d, npc_id: $n}) SET e = $p",
                    {"d": dono, "n": npc, "p": antes[npc]},
                )
                mexidos += 1
    return mexidos


def limpar_qdrant(client: Any, dono: str, sessoes: list[str]) -> int:
    """Apaga os pontos episódicos DESTE dono com os session_ids do smoke."""
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchAny, MatchValue

    if not sessoes or not client.collection_exists("voxdm_episodic"):
        return 0
    filtro = Filter(must=[
        FieldCondition(key="owner_email", match=MatchValue(value=dono)),
        FieldCondition(key="session_id", match=MatchAny(any=sessoes)),
    ])
    pontos, _ = client.scroll("voxdm_episodic", scroll_filter=filtro, limit=100)
    if pontos:
        client.delete("voxdm_episodic", points_selector=FilterSelector(filter=filtro))
    return len(pontos)


def limpar_sqlite(db: Path, dono: str, sessoes: list[str]) -> int:
    if not sessoes or not db.exists():
        return 0
    con = sqlite3.connect(db)
    try:
        marcas = ",".join("?" * len(sessoes))
        cur = con.execute(
            f"DELETE FROM character_state WHERE owner_email = ? AND session_id IN ({marcas})",
            (dono, *sessoes),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def limpar_arquivos_debug(pasta: Path, sessoes: list[str]) -> int:
    apagados = 0
    for sid in sessoes:
        alvo = pasta / f"{sid}.json"
        if alvo.exists():
            alvo.unlink()
            apagados += 1
    return apagados


# ── roteiro ──────────────────────────────────────────────────────────────────


async def rodar(manter: bool) -> Relatorio:
    from neo4j import AsyncGraphDatabase
    from qdrant_client import QdrantClient

    from config import settings
    from engine.memory.neo4j_tls import argumentos_driver_neo4j

    rel = Relatorio()
    sessoes: list[str] = []
    driver = AsyncGraphDatabase.driver(**argumentos_driver_neo4j())
    qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, check_compatibility=False)
    try:
        async with httpx.AsyncClient(base_url=API, timeout=120) as http:
            saude = (await http.get("/health")).json()
            rel.marcar("api_viva", bool(saude.get("warmup_pronto")))
            dono = (await http.get("/session/me")).json()["email"]
            afeto_antes = await _afeto_do_dono(driver, dono)

            r = await http.post("/session/start", json={
                "player_name": "Smoke", "player_race": "Humano", "player_class": "Guerreiro",
                "location_id": "tharnvik", "location_nome": "Tharnvik",
            })
            rel.marcar("sessao_criada", r.status_code == 201, status=r.status_code)
            sid = r.json()["session_id"]
            sessoes.append(sid)

            async with websockets.connect(f"{WS}/ws/game/{sid}", max_size=None) as ws:
                await ws.send(json.dumps({"tipo": "init"}))
                ab = await _ler_ate_fim(ws)
                rel.marcar("abertura_sincronizacao", (ab.get("fim") or {}).get("sincronizacao") is True,
                           segundos=ab.get("segundos"))
                for fala in FALAS:
                    await ws.send(json.dumps({"texto": fala}))
                    t = await _ler_ate_fim(ws)
                    rel.turnos.append({"fala": fala, "segundos": t.get("segundos"),
                                       "erro": t.get("erro"), "trecho": t.get("texto", "")[:200]})
                    sys.stdout.write(f"  turno {t.get('segundos')}s erro={bool(t.get('erro'))}: {fala}\n")
            rel.marcar("turnos_sem_erro", all(not t["erro"] for t in rel.turnos), total=len(rel.turnos))

            camp = (await http.post("/campanhas", json={"nome": "Smoke automatizado"})).json()
            save = (await http.post(f"/campanhas/{camp['id']}/saves",
                                    json={"session_id": sid, "rotulo": "smoke"})).json()
            rel.marcar("save_gravado", "id" in save)
            rel.marcar("encerrar", (await http.delete(f"/session/{sid}")).status_code == 204)
            await asyncio.sleep(3)

            existe = qdrant.collection_exists("voxdm_episodic")
            esquema = {k: str(v) for k, v in (qdrant.get_collection("voxdm_episodic").payload_schema or {}).items()} if existe else {}
            pontos = qdrant.scroll("voxdm_episodic", limit=200, with_payload=True)[0] if existe else []
            rel.marcar("qdrant_ponto_com_dono", any(
                p.payload.get("session_id") == sid and p.payload.get("owner_email") == dono for p in pontos))
            rel.marcar("qdrant_indice_tenant", "is_tenant=True" in esquema.get("owner_email", ""))

            depois = await _afeto_do_dono(driver, dono)
            rel.marcar("neo4j_afeto_no_id_do_grafo", all(n == NPC_DO_TESTE or n in afeto_antes for n in depois),
                       npcs=sorted(depois), nota="id curto (ex.: 'bjorn') = AFETO-ID-CURTO-1 voltou")

            arq = _RAIZ / ".internal" / "playtest_debug" / f"{sid}.json"
            rel.marcar("debug_arquivo_com_dono", arq.exists() and
                       json.loads(arq.read_text(encoding="utf-8")).get("owner_email") == dono)

            r = await http.post(f"/campanhas/{camp['id']}/saves/{save['id']}/iniciar")
            rel.marcar("iniciar_de_save", r.status_code == 201, status=r.status_code)
            if r.status_code == 201:
                nova = r.json()["session_id"]
                sessoes.append(nova)
                await http.delete(f"/session/{nova}")
            await http.post(f"/campanhas/{camp['id']}/arquivar")

            if not manter:
                await asyncio.sleep(3)  # o Encerrar da 2ª sessão grava episódico em background
                n_q = limpar_qdrant(qdrant, dono, sessoes)
                n_n = await restaurar_afeto(driver, dono, afeto_antes)
                n_s = limpar_sqlite(_RAIZ / "voxdm.db", dono, sessoes)
                n_d = limpar_arquivos_debug(_RAIZ / ".internal" / "playtest_debug", sessoes)
                rel.marcar("limpeza", True, qdrant=n_q, neo4j=n_n, sqlite=n_s, debug=n_d,
                           nota="campanha 'Smoke automatizado' fica ARQUIVADA (saves não se apagam)")
    finally:
        await driver.close()
    return rel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke de ponta a ponta contra API e bancos reais")
    parser.add_argument("--manter", action="store_true", help="não limpa o que o smoke criou")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rel = asyncio.run(rodar(manter=args.manter))
    sys.stdout.write(f"\n{len(rel.etapas) - len(rel.falhas)}/{len(rel.etapas)} etapas OK\n")
    if rel.falhas:
        sys.stdout.write(f"FALHAS: {', '.join(rel.falhas)}\n")
    return 1 if rel.falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
