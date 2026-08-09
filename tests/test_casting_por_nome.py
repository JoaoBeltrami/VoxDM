"""
P16 passo 2 — a engine passa a VER a conjuração (ADR-007, decisão 2).

Por que existe: no playtest de 09/08 um Clérigo nível 3 conjurou a sessão inteira
    e a engine registrou ZERO eventos. Os slots terminaram intactos (4/4 e 2/2) e
    o Beltrami disse *"o mestre ficou burro… 2 turnos pra entender que eu usei uma
    magia que eu tenho na ficha"*. A causa era simples: o gatilho era uma lista de
    seis verbos, e "abençoo" não é nenhum deles.
Dependências: nenhuma (função pura).
Armadilha: o teste que MAIS importa aqui não é o que prova que detecta — é o que
    prova que NÃO detecta. Nome de magia solto é prosa comum ("a luz da tocha"),
    e um detector ávido demais transforma narração em conjuração e queima slot do
    jogador sem ele ter pedido nada.

Exemplo:
    uv run pytest tests/test_casting_por_nome.py -q
"""

from engine.magic.casting import detectar_conjuracao

# A ficha real do playtest de 09/08: Garruk, Clérigo nível 3.
FICHA_CLERIGO = [
    "Abençoar", "Curar Ferimentos", "Luz", "Chama Sagrada",
    "Palavra de Cura", "Guia", "Santuário", "Detectar Magia",
]


# ── O caso que falhou em jogo ────────────────────────────────────────────────


def test_o_clerigo_que_abencoa_e_detectado():
    """O caso literal do playtest. Se este teste falhar, o item não existe."""
    assert detectar_conjuracao("abençoo o grupo antes de avançar", FICHA_CLERIGO) == "Abençoar"


def test_conjugacoes_do_nome_verbo():
    for fala in ("abençoo o grupo", "abençoei meus aliados", "abençoa o guerreiro"):
        assert detectar_conjuracao(fala, FICHA_CLERIGO) == "Abençoar", fala


def test_nome_composto_dispensa_verbo():
    """'Curar Ferimentos' ninguém diz por acaso."""
    assert detectar_conjuracao(
        "curar ferimentos no bárbaro", FICHA_CLERIGO
    ) == "Curar Ferimentos"


def test_verbo_novo_que_o_regex_antigo_nao_cobria():
    assert detectar_conjuracao("canalizo Chama Sagrada no carniçal", FICHA_CLERIGO) == "Chama Sagrada"


# ── O que NÃO pode virar conjuração ──────────────────────────────────────────


def test_nome_ambiguo_sozinho_nao_conta():
    """'Luz' está na ficha do clérigo — e é prosa comum. Sem verbo, não é cast."""
    assert detectar_conjuracao("a luz da tocha tremeluz na parede", FICHA_CLERIGO) is None


def test_nome_ambiguo_com_verbo_conta():
    assert detectar_conjuracao("conjuro Luz na ponta do cajado", FICHA_CLERIGO) == "Luz"


def test_outro_ambiguo_da_ficha():
    assert detectar_conjuracao("peço conselho ao velho taverneiro", FICHA_CLERIGO) is None
    assert detectar_conjuracao("lanço Guia no batedor", FICHA_CLERIGO) == "Guia"


def test_magia_fora_da_ficha_nao_conta():
    """A mitigação do ADR contra NPC/lugar com nome de magia — e contra o jogador
    conjurar o que não tem. Negar continua sendo o comportamento (decisão 6)."""
    assert detectar_conjuracao("lanço Bola de Fogo no grupo", FICHA_CLERIGO) is None


def test_personagem_sem_magia_nunca_conjura():
    assert detectar_conjuracao("abençoo o grupo", []) is None
    assert detectar_conjuracao("abençoo o grupo", None) is None


def test_texto_vazio():
    assert detectar_conjuracao("", FICHA_CLERIGO) is None


# ── Desambiguação ────────────────────────────────────────────────────────────


def test_o_nome_mais_especifico_ganha():
    """'Palavra de Cura' e 'Curar Ferimentos' coexistem na ficha; a fala mais
    específica não pode cair na mais curta."""
    assert detectar_conjuracao(
        "uso Palavra de Cura no arqueiro", FICHA_CLERIGO
    ) == "Palavra de Cura"


def test_acento_e_caixa_nao_importam():
    """A transcrição de voz não é confiável com acento nem com maiúscula."""
    for fala in ("SANTUARIO", "santuário", "Santuario"):
        assert detectar_conjuracao(f"conjuro {fala}", FICHA_CLERIGO) == "Santuário", fala


def test_nome_parcial_nao_casa_por_substring():
    """'Guia' não pode casar dentro de 'guiando' por acidente de substring —
    o limite de palavra existe pra isso."""
    assert detectar_conjuracao("sigo guiando o grupo pela trilha", FICHA_CLERIGO) is None
