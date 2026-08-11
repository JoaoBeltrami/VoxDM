"""
P18 frente A — a ficha recebe as escolhas, e o que ela escolheu chega ao jogo.

Por que existe: a rota é o único ponto onde o frontend toca a regra de
    equipamento. Se ela vazar a tabela do D&D em vez de passar pelo RuleSystem,
    a modularidade morre exatamente aqui — e ninguém percebe até existir um
    segundo sistema.
Dependências: FastAPI TestClient.
Armadilha: a ficha manda o RESULTADO da escolha (nomes de itens), não os índices.
    Mandar índices obrigaria o servidor a reproduzir a navegação da UI, e as duas
    versões da navegação divergiriam na primeira mudança de layout.

Exemplo:
    uv run pytest tests/test_rota_equipamento.py -q
"""

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """TestClient com Qdrant/Neo4j/Groq mockados — mesma receita do
    `test_websocket.py`. Local de propósito: a fixture de lá não é global, e
    importar de outro módulo de teste acopla os dois."""
    from engine.llm.prompt_builder import ContextoMontado

    contexto = MagicMock(spec=ContextoMontado)
    contexto.chunks_semanticos = []
    contexto.chunks_regras = []
    contexto.relacoes_grafo = []
    contexto.secrets_visiveis = []
    builder = MagicMock()
    builder.montar = AsyncMock(return_value=contexto)
    builder.inferir_npcs_presentes = AsyncMock(return_value=[])

    with patch("api.routes.session.ContextBuilder", return_value=builder),          patch("api.routes.session.GroqClient", return_value=MagicMock()):
        from api.main import app
        with TestClient(app) as c:
            yield c


def test_a_rota_passa_pelo_rule_system_e_nao_pela_tabela_dnd():
    fonte = (Path(__file__).resolve().parents[1] / "api/routes/session.py")
    texto = fonte.read_text(encoding="utf-8")
    arvore = ast.parse(texto)
    importados = {
        (no.module or "") for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)
    }
    assert "engine.state.escolhas_iniciais" not in importados
    assert "engine.state.equipamento_inicial" not in importados
    assert "obter_sistema()" in texto


def test_a_rota_existe_e_devolve_fixos_e_escolhas(client):
    r = client.get("/session/equipamento-inicial/Guerreiro")
    assert r.status_code == 200
    dados = r.json()
    assert dados["classe"] == "Guerreiro"
    # O Guerreiro é o caso que motivou tudo: TODO o equipamento dele está nas
    # escolhas, então `fixos` vazio aqui é o comportamento CERTO.
    assert dados["fixos"] == []
    assert len(dados["escolhas"]) == 4


def test_cada_opcao_traz_rotulo_para_ler_e_itens_para_aplicar(client):
    """O mesmo dado serve o botão da ficha e a fala do Mestre na criação por voz."""
    dados = client.get("/session/equipamento-inicial/Bardo").json()
    opcao = dados["escolhas"][0]["opcoes"][0]
    assert opcao["rotulo"] == "Rapieira"
    assert opcao["itens"] == [{"nome": "Rapieira", "quantidade": 1}]
    assert "categoria" in opcao


def test_classe_desconhecida_devolve_vazio_sem_erro(client):
    dados = client.get("/session/equipamento-inicial/Necromante").json()
    assert dados["fixos"] == [] and dados["escolhas"] == []


def test_ranger_ja_vem_com_o_fixo(client):
    dados = client.get("/session/equipamento-inicial/Ranger").json()
    assert "Arco longo" in dados["fixos"]
    assert dados["fixos"].count("Flecha") == 20


def test_o_equipamento_escolhido_chega_ao_personagem(client):
    """O fecho do caminho: o que o jogador clicou vira inventário de verdade."""
    from api.state import sessions

    r = client.post("/session/start", json={
        "player_name": "Teste", "player_class": "Guerreiro", "player_level": 3,
        "player_equipamento": ["Cota de malha", "Machadinha", "Machadinha"],
    })
    assert r.status_code == 201
    wm = sessions[r.json()["session_id"]].working_mem
    assert "Cota de malha" in wm.player_inventory
    from engine.state.inventario import buscar
    assert buscar(wm.character.inventario, "Machadinha").quantidade == 2
    # Arma escolhida entra EQUIPADA — obrigar a equipar antes do primeiro golpe
    # transformaria um padrão do SRD em pegadinha.
    assert wm.character.arma_equipada() == "handaxe"


def test_sem_escolha_o_start_continua_funcionando(client):
    """A ficha antiga (ou o jogador que ignorou o bloco) não pode quebrar."""
    r = client.post("/session/start", json={
        "player_name": "Teste", "player_class": "Ranger", "player_level": 3,
    })
    assert r.status_code == 201
