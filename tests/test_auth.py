"""Testes do módulo de identidade + JWT validator (sem rede real)."""

import pytest

from engine.auth.identity import Owner, is_admin


# ── Owner ──────────────────────────────────────────────────────────────────────


def test_owner_admin_ve_qualquer_dado():
    admin = Owner(email="joao@x.com", is_admin=True)
    assert admin.pode_ver("outro@x.com") is True
    assert admin.pode_ver(None) is True
    assert admin.pode_ver("") is True


def test_owner_comum_so_ve_proprio():
    user = Owner(email="amigo@x.com", is_admin=False)
    assert user.pode_ver("amigo@x.com") is True
    assert user.pode_ver("Amigo@X.com") is True  # case-insensitive
    assert user.pode_ver("outro@x.com") is False
    assert user.pode_ver(None) is False
    assert user.pode_ver("") is False


def test_owner_e_frozen():
    user = Owner(email="a@x.com")
    with pytest.raises(Exception):
        user.email = "b@x.com"  # type: ignore[misc]


# ── is_admin helper ────────────────────────────────────────────────────────────


def test_is_admin_email_na_lista():
    assert is_admin("joao@x.com", "joao@x.com") is True


def test_is_admin_case_insensitive():
    assert is_admin("Joao@X.COM", "joao@x.com") is True
    assert is_admin("joao@x.com", "JOAO@X.COM, outro@y.com") is True


def test_is_admin_email_nao_na_lista():
    assert is_admin("zezinho@x.com", "joao@x.com,maria@y.com") is False


def test_is_admin_lista_vazia():
    assert is_admin("joao@x.com", "") is False
    assert is_admin("joao@x.com", "   ") is False


def test_is_admin_email_vazio():
    assert is_admin("", "joao@x.com") is False


def test_is_admin_tolera_espacos():
    assert is_admin("joao@x.com", "  joao@x.com  ,  outro@y.com  ") is True


# ── JWT validator (smoke — falhas básicas, sem mockar httpx real) ──────────────


@pytest.mark.asyncio
async def test_validar_jwt_token_vazio():
    from engine.auth.jwt_validator import JWTInvalido, validar_jwt_cf
    with pytest.raises(JWTInvalido):
        await validar_jwt_cf("", "team", "aud")


@pytest.mark.asyncio
async def test_validar_jwt_team_vazio():
    from engine.auth.jwt_validator import JWTInvalido, validar_jwt_cf
    with pytest.raises(JWTInvalido):
        await validar_jwt_cf("token", "", "aud")


@pytest.mark.asyncio
async def test_validar_jwt_audience_vazio():
    from engine.auth.jwt_validator import JWTInvalido, validar_jwt_cf
    with pytest.raises(JWTInvalido):
        await validar_jwt_cf("token", "team", "")


@pytest.mark.asyncio
async def test_validar_jwt_header_malformado():
    """Token não-JWT deve falhar antes de tentar buscar certs."""
    from engine.auth.jwt_validator import JWTInvalido, validar_jwt_cf
    # Forçamos falha cedo passando token claramente malformado mas team válido —
    # como o cache de certs vai tentar http real, mockamos via team inexistente
    # que dispara erro de DNS, que vira JWTInvalido (catch genérico no fetch).
    with pytest.raises(JWTInvalido):
        await validar_jwt_cf(
            "naoehjwt",
            team_domain="this-team-does-not-exist-x9z8.invalid",
            audience="aud",
        )
