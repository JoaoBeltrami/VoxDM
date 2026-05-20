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

    def test_texto_sem_gatilhos_inalterado(self):
        original = "O guerreiro caminhou pela floresta com cautela."
        resultado = _adicionar_nuances_pontuacao(original)
        assert resultado == original

    def test_sussurro_ja_com_reticencias_nao_duplica(self):
        # Se já tem "..." antes, não adiciona outro
        resultado = _adicionar_nuances_pontuacao("... ela sussurra docemente.")
        # Não pode ter "... ... " consecutivos
        assert "... ..." not in resultado


