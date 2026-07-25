"""
Testes para o pipeline de naturalidade TTS — Passo 1 (normalização de pontuação).

Passo 2 (SSML) foi descartado: edge_tts.Communicate faz escape() do input,
tornando tags SSML literais no áudio. Naturalidade adicional virá de outras
fontes (rate/pitch globais, futuras assinaturas por NPC, etc.).
"""

from engine.voice.tts import _adicionar_nuances_pontuacao, _normalizar_para_tts


class TestNormalizarParaTTS:
    def test_em_dash_com_espacos_vira_virgula(self):
        resultado = _normalizar_para_tts("Avance — mas com cuidado.")
        assert " — " not in resultado
        assert "," in resultado

    def test_em_dash_sem_espacos_vira_virgula(self):
        resultado = _normalizar_para_tts("Cuidado—perigo à frente.")
        assert "—" not in resultado

    def test_en_dash_vira_virgula(self):
        resultado = _normalizar_para_tts("Correu–parou.")
        assert "–" not in resultado

    def test_multiplas_exclamacoes_normalizadas(self):
        resultado = _normalizar_para_tts("Cuidado!!!")
        assert resultado == "Cuidado!"

    def test_multiplas_interrogacoes_normalizadas(self):
        resultado = _normalizar_para_tts("Quem é você??")
        assert resultado == "Quem é você?"

    def test_reticencias_longas_normalizadas(self):
        resultado = _normalizar_para_tts("Então....... ele avançou.")
        assert "......" not in resultado
        assert "..." in resultado

    def test_quebra_de_linha_vira_espaco(self):
        resultado = _normalizar_para_tts("Primeiro.\nSegundo.")
        assert "\n" not in resultado
        assert "Primeiro. Segundo." == resultado

    def test_multiplas_quebras_de_linha(self):
        resultado = _normalizar_para_tts("A.\n\n\nB.")
        assert "\n" not in resultado

    def test_espacos_duplos_colapsados(self):
        resultado = _normalizar_para_tts("Um  dois   três.")
        assert "  " not in resultado

    def test_texto_limpo_sem_alteracao_substancial(self):
        texto = "O guerreiro avançou. O goblin recuou."
        resultado = _normalizar_para_tts(texto)
        assert "guerreiro" in resultado
        assert "goblin" in resultado

    def test_texto_vazio_retorna_vazio(self):
        assert _normalizar_para_tts("") == ""

    def test_strip_aplicado(self):
        resultado = _normalizar_para_tts("  Olá mundo.  ")
        assert resultado == "Olá mundo."


class TestNuancesPontuacao:
    def test_de_repente_ganha_virgula_antes(self):
        resultado = _adicionar_nuances_pontuacao("Caminhei calmamente de repente algo grita.")
        assert ", de repente" in resultado

    def test_mas_no_meio_da_frase_ganha_virgula(self):
        resultado = _adicionar_nuances_pontuacao("Você abre a porta mas algo se move.")
        assert ", mas" in resultado

    def test_subitamente_ganha_virgula(self):
        resultado = _adicionar_nuances_pontuacao("O sino toca subitamente para de tocar.")
        assert ", subitamente" in resultado

    def test_sussurro_ganha_reticencias(self):
        resultado = _adicionar_nuances_pontuacao("Lyssa sussurra algo no seu ouvido.")
        assert "..." in resultado

    def test_murmurou_ganha_reticencias(self):
        resultado = _adicionar_nuances_pontuacao("Ele murmurou uma prece curta.")
        assert "..." in resultado

    def test_cuidado_seguido_de_palavra_ganha_virgula(self):
        resultado = _adicionar_nuances_pontuacao("Cuidado atrás de você!")
        assert "Cuidado," in resultado

    def test_olhe_seguido_de_palavra_ganha_virgula(self):
        resultado = _adicionar_nuances_pontuacao("Olhe para o leste.")
        assert "Olhe," in resultado

    def test_virgulas_duplicadas_colapsam(self):
        resultado = _adicionar_nuances_pontuacao(",, de repente algo move,, mas para.")
        # Não pode ter ",," consecutivos no resultado
        assert ",," not in resultado

    def test_na_verdade_ganha_reticencias(self):
        resultado = _adicionar_nuances_pontuacao("Ele sorriu na verdade nunca esteve aqui.")
        assert "..." in resultado
        assert "na verdade" in resultado

    def test_a_verdade_e_ganha_reticencias(self):
        resultado = _adicionar_nuances_pontuacao("Toda a aldeia sabe a verdade é que ele fugiu.")
        assert "..." in resultado

    def test_mas_afinal_ganha_reticencias(self):
        resultado = _adicionar_nuances_pontuacao("Você esperava uma recompensa mas afinal nada.")
        assert "..." in resultado

    def test_revelacao_apos_pontuacao_nao_duplica(self):
        # Após ponto/vírgula não deve gerar reticências (lookbehind protege)
        resultado = _adicionar_nuances_pontuacao("Você sabia. na verdade isso já era esperado.")
        # Pode ou não ter ... — o lookbehind `(?<=[^.!?,])` bloqueia pós-ponto
        # Principal garantia: sem duplicação de "..."
        assert "......" not in resultado

    def test_texto_sem_gatilhos_inalterado(self):
        original = "O guerreiro caminhou pela floresta com cautela."
        resultado = _adicionar_nuances_pontuacao(original)
        assert resultado == original

    def test_sussurro_ja_com_reticencias_nao_duplica(self):
        # Se já tem "..." antes, não adiciona outro
        resultado = _adicionar_nuances_pontuacao("... ela sussurra docemente.")
        # Não pode ter "... ... " consecutivos
        assert "... ..." not in resultado




# ── LEMBRETE-VAZA-1 (review 24/07) ───────────────────────────────────────────
#
# O strip do TTS casava `[LEMBRETE DE SAÍDA`, texto que não existe mais — o
# marcador real é `[LEMBRETE]`. Quando o LLM ecoava o lembrete, o jogador OUVIA
# a instrução interna ("PT-BR falado, sem markdown, listas, asteriscos…").
# Este teste amarra o strip ao lembrete REAL: se alguém reescrever um sem o
# outro, ele quebra.

def test_lembrete_real_nunca_chega_ao_tts():
    from engine.llm.prompt_builder import _lembrete_saida
    from engine.voice.tts import _limpar_markdown

    narracao = "O ferreiro cospe no chão e vira as costas."
    for ritmo in ("curto", "medio", "longo"):
        limpo = _limpar_markdown(narracao + _lembrete_saida(ritmo))
        assert limpo.strip() == narracao, f"lembrete '{ritmo}' vazou: {limpo!r}"


def test_eco_parcial_do_lembrete_sem_colchete_e_removido():
    """O LLM às vezes ecoa as linhas sem o marcador — o strip pega por linha."""
    from engine.voice.tts import _limpar_markdown

    narracao = "A porta range e cede um palmo."
    eco = (
        f"{narracao}\n"
        "PT-BR falado — sem markdown, listas, asteriscos.\n"
        "Máximo 80 palavras nesta resposta.\n"
        "Comece DIRETO na narração, sem prefácio."
    )
    assert _limpar_markdown(eco).strip() == narracao


# ── UNICODE-EXOTICO-1 (A/B de modelo, 24/07) ─────────────────────────────────
#
# A família openai/gpt-oss — agora o FALLBACK da cascata — emite tipografia
# exótica que o Edge TTS não pronuncia bem. Colhido da saída REAL do
# gpt-oss-120b: "Bem‑vindo" com U+2011 (hífen não-quebrável), que atravessava
# todo o strip e chegava ao sintetizador.

def test_hifen_nao_quebravel_do_gpt_oss_vira_ascii():
    from engine.voice.tts import _normalizar_para_tts

    saida_real = "Bem‑vindo ao Salão dos Sussurros."
    limpo = _normalizar_para_tts(saida_real)
    assert "‑" not in limpo
    assert "Bem-vindo" in limpo


def test_outros_invisiveis_tambem_somem():
    from engine.voice.tts import _normalizar_para_tts

    sujo = "O ferreiro​ ergue o ‘martelo’."
    limpo = _normalizar_para_tts(sujo)
    for exotico in (" ", "​", "‘", "’"):
        assert exotico not in limpo, f"sobreviveu: {exotico!r}"
    assert "O ferreiro ergue o 'martelo'." == limpo
