"""
Rotas de campanha e save — continuidade solo, com dono em toda chamada.

Por que existe: expõe o `CampanhaStore` (criar campanha, salvar a sessão ativa,
    listar e restaurar saves) e as duas portas de admin da instância: listar
    METADADO de todo mundo e abrir CONTEÚDO alheio por quebra-vidro auditado.
Dependências: fastapi, api/auth, api/state, engine/persistence/*
Armadilha: "não é seu" responde 404, igual a "não existe". Nunca 403 em dado
    de jogador — 403 confirma que o id é real.
Armadilha: restaurar copia os campos do save PARA DENTRO da WorkingMemory que
    a sessão já tem, sob o lock de turno. Trocar o objeto (`sessao.working_mem
    = nova`) deixaria o WebSocket aberto segurando a referência velha.

Exemplo:
    POST /campanhas {"nome": "Valdrek"}                       → {"id": "camp-…"}
    POST /campanhas/camp-…/saves {"session_id": "…", "rotulo": "antes do dragão"}
    POST /campanhas/camp-…/saves/save-…/restaurar {"session_id": "…"}
"""

from __future__ import annotations

import dataclasses
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import exige_admin, get_owner
from api.state import SessaoAtiva, sessions
from engine.auth.identity import Owner
from engine.persistence.campanha_store import (
    Campanha,
    CampanhaStore,
    NaoEncontrado,
    SaveCorrompido,
    SaveInfo,
)
from engine.persistence.save_envelope import (
    SaveIncompativel,
    montar_envelope,
    restaurar_working_memory,
)

log = structlog.get_logger()

router = APIRouter(prefix="/campanhas", tags=["campanhas"])
router_admin = APIRouter(prefix="/admin", tags=["admin"])


class CriarCampanha(BaseModel):
    nome: str = Field(min_length=1, max_length=120)


class CriarSave(BaseModel):
    session_id: str
    rotulo: str = Field(default="", max_length=120)


class RestaurarSave(BaseModel):
    session_id: str


class QuebraVidro(BaseModel):
    motivo: str = Field(min_length=5, max_length=500)


def _store() -> CampanhaStore:
    return CampanhaStore()


def _404(oque: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{oque} não encontrado")


def _sessao_do_proprio(session_id: str, owner: Owner) -> SessaoAtiva:
    """A sessão ativa tem que ser DO solicitante — aqui nem admin passa.

    Salvar ou restaurar a sessão de outra pessoa grava/sobrescreve o jogo dela;
    isso não é ver dado, é mexer nele, e não há quebra-vidro para isso.
    """
    sessao = sessions.get(session_id)
    if sessao is None or sessao.owner_email.lower() != owner.email.lower():
        raise _404("Sessão")
    return sessao


def _campanha_json(c: Campanha) -> dict[str, Any]:
    return dataclasses.asdict(c)


def _save_json(s: SaveInfo) -> dict[str, Any]:
    return dataclasses.asdict(s)


@router.post("")
async def criar_campanha(
    corpo: CriarCampanha, owner: Annotated[Owner, Depends(get_owner)],
) -> dict[str, Any]:
    return _campanha_json(await _store().criar_campanha(owner, corpo.nome))


@router.get("")
async def listar_campanhas(owner: Annotated[Owner, Depends(get_owner)]) -> list[dict[str, Any]]:
    return [_campanha_json(c) for c in await _store().listar_campanhas(owner)]


@router.get("/{campanha_id}/saves")
async def listar_saves(
    campanha_id: str, owner: Annotated[Owner, Depends(get_owner)],
) -> list[dict[str, Any]]:
    try:
        return [_save_json(s) for s in await _store().listar_saves(owner, campanha_id)]
    except NaoEncontrado as e:
        raise _404("Campanha") from e


@router.post("/{campanha_id}/saves")
async def salvar(
    campanha_id: str, corpo: CriarSave, owner: Annotated[Owner, Depends(get_owner)],
) -> dict[str, Any]:
    sessao = _sessao_do_proprio(corpo.session_id, owner)
    async with sessao.lock_turno:
        envelope = montar_envelope(
            sessao.working_mem,
            owner_email=sessao.owner_email,
            session_id=sessao.session_id,
            campanha_id=campanha_id,
            extras={"spells_conhecidas": list(sessao.spells_conhecidas)},
        )
    try:
        info = await _store().salvar(owner, campanha_id, corpo.rotulo, envelope)
    except NaoEncontrado as e:
        raise _404("Campanha") from e
    return _save_json(info)


@router.post("/{campanha_id}/saves/{save_id}/restaurar")
async def restaurar(
    campanha_id: str, save_id: str, corpo: RestaurarSave,
    owner: Annotated[Owner, Depends(get_owner)],
) -> dict[str, Any]:
    sessao = _sessao_do_proprio(corpo.session_id, owner)
    try:
        envelope = await _store().carregar(owner, campanha_id, save_id)
        nova = restaurar_working_memory(envelope)
    except NaoEncontrado as e:
        raise _404("Save") from e
    except (SaveIncompativel, SaveCorrompido) as e:
        # Falha dizendo o que fazer — nunca muda (doutrina do P11).
        raise HTTPException(status_code=409, detail=str(e)) from e

    async with sessao.lock_turno:
        alvo = sessao.working_mem
        for campo in dataclasses.fields(nova):
            if campo.name == "session_id":
                continue  # a sessão ativa continua sendo ela mesma
            setattr(alvo, campo.name, getattr(nova, campo.name))
        extras = envelope.get("extras") or {}
        if isinstance(extras.get("spells_conhecidas"), list):
            sessao.spells_conhecidas = [str(s) for s in extras["spells_conhecidas"]]
    log.info("save_restaurado", campanha_id=campanha_id, save_id=save_id, session_id=sessao.session_id)
    return {"ok": True, "session_id": sessao.session_id, "player_name": alvo.player_name}


@router_admin.get("/campanhas")
async def admin_listar_metadados(
    owner: Annotated[Owner, Depends(exige_admin)],
) -> list[dict[str, Any]]:
    """Metadado de TODAS as campanhas — nunca narrativa."""
    return await _store().listar_metadados_admin(owner)


@router_admin.post("/saves/{save_id}/quebra-vidro")
async def admin_quebra_vidro(
    save_id: str, corpo: QuebraVidro, owner: Annotated[Owner, Depends(exige_admin)],
) -> dict[str, Any]:
    """Conteúdo de um save alheio. Grava `save_audit` com o motivo ANTES de abrir."""
    try:
        return await _store().carregar_quebra_vidro(owner, save_id, corpo.motivo)
    except NaoEncontrado as e:
        raise _404("Save") from e
