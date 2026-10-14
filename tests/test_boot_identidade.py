"""
P11 parte 3: a API recusa subir com DEBUG=false e Cloudflare Access vazio.

Por que existe: sem fallback de DEV_USER_EMAIL e sem CF_TEAM_DOMAIN/CF_ACCESS_AUD,
    nenhum JWT valida e toda requisição vira 401 — a API subia "saudável" e
    nada funcionava. O teste cobre a função pura; o lifespan só a chama.
Dependências: nenhuma externa.
"""

from api.main import identidade_mal_configurada


def test_debug_ligado_sobe_sem_cloudflare() -> None:
    assert identidade_mal_configurada(True, "", "") is None


def test_producao_com_cloudflare_completo_sobe() -> None:
    assert identidade_mal_configurada(False, "time.cloudflareaccess.com", "aud123") is None


def test_producao_sem_cloudflare_recusa_dizendo_o_que_falta() -> None:
    motivo = identidade_mal_configurada(False, "", "aud123")
    assert motivo is not None and "CF_TEAM_DOMAIN" in motivo and "CF_ACCESS_AUD" not in motivo.split(":")[0]
    motivo = identidade_mal_configurada(False, "  ", "")
    assert motivo is not None and "CF_TEAM_DOMAIN, CF_ACCESS_AUD" in motivo


def test_lifespan_chama_a_checagem_antes_dos_warmups() -> None:
    import inspect

    import api.main as main

    fonte = inspect.getsource(main.lifespan)
    assert fonte.index("identidade_mal_configurada(") < fonte.index("VOXDM_SKIP_WARMUP")
