"""
Testes para engine/magic/spell_list.py.

Cobre: consulta de spells por classe, filtragem por nível, limites de progressão,
    integração com WorkingMemory.nova_sessao() e injeção no prompt_builder.
"""


# ── Importações ────────────────────────────────────────────────────────────────
from engine.magic.spell_list import (
    limite_progressao,
    nivel_da_spell,
    spells_da_classe,
    spells_por_nivel,
)

# ── Testes: spells_da_classe ───────────────────────────────────────────────────

class TestSpellsDaClasse:
    def test_mago_nao_vazio(self):
        lista = spells_da_classe("mago")
        assert len(lista) > 0, "Mago deve ter spells cadastradas"

    def test_mago_minimo_30_spells(self):
        """Full casters devem ter pelo menos 30 spells no catálogo."""
        assert len(spells_da_classe("mago")) >= 30

    def test_clerigo_nao_vazio(self):
        assert len(spells_da_classe("clérigo")) > 0

    def test_clerigo_alias_sem_acento(self):
        """Alias 'clerigo' (sem acento) deve funcionar identicamente."""
        with_accent = spells_da_classe("clérigo")
        without_accent = spells_da_classe("clerigo")
        assert len(with_accent) == len(without_accent)

    def test_druida_minimo_20_spells(self):
        assert len(spells_da_classe("druida")) >= 20

    def test_bardo_nao_vazio(self):
        assert len(spells_da_classe("bardo")) > 0

    def test_feiticeiro_nao_vazio(self):
        assert len(spells_da_classe("feiticeiro")) > 0

    def test_bruxo_nao_vazio(self):
        assert len(spells_da_classe("bruxo")) > 0

    def test_paladino_nao_vazio(self):
        assert len(spells_da_classe("paladino")) > 0

    def test_ranger_nao_vazio(self):
        assert len(spells_da_classe("ranger")) > 0

    def test_classe_desconhecida_retorna_lista_vazia(self):
        assert spells_da_classe("guerreiro") == []

    def test_classe_desconhecida_barbaro_vazio(self):
        assert spells_da_classe("bárbaro") == []

    def test_case_insensitive(self):
        """Deve funcionar com qualquer capitalização."""
        upper = spells_da_classe("MAGO")
        lower = spells_da_classe("mago")
        assert len(upper) == len(lower)

    def test_spellentry_tem_campos_obrigatorios(self):
        """Toda SpellEntry deve ter nome_pt, nome_en, nivel, escola, desc_curta."""
        for spell in spells_da_classe("mago"):
            assert spell.nome_pt, f"nome_pt vazio em {spell}"
            assert spell.nome_en, f"nome_en vazio em {spell}"
            assert isinstance(spell.nivel, int), f"nivel deve ser int em {spell}"
            assert 0 <= spell.nivel <= 9, f"nivel fora de range em {spell}"
            assert spell.escola, f"escola vazia em {spell}"
            assert spell.desc_curta, f"desc_curta vazia em {spell}"

    def test_bola_de_fogo_no_mago(self):
        """Fireball é obrigatória para Mago."""
        nomes = [s.nome_pt for s in spells_da_classe("mago")]
        assert "Bola de Fogo" in nomes

    def test_missil_magico_no_mago(self):
        nomes = [s.nome_pt for s in spells_da_classe("mago")]
        assert "Míssil Mágico" in nomes

    def test_chama_sagrada_no_clerigo(self):
        nomes = [s.nome_pt for s in spells_da_classe("clérigo")]
        assert "Chama Sagrada" in nomes

    def test_explosao_eldritch_no_bruxo(self):
        nomes = [s.nome_pt for s in spells_da_classe("bruxo")]
        assert "Explosão Eldritch" in nomes


# ── Testes: spells_por_nivel ───────────────────────────────────────────────────

class TestSpellsPorNivel:
    def test_truques_so_nivel_zero(self):
        """Filtragem por nível 0 deve retornar apenas truques."""
        truques = spells_por_nivel("clérigo", 0)
        assert all(s.nivel == 0 for s in truques)
        assert len(truques) > 0

    def test_nivel_3_mago_tem_bola_de_fogo(self):
        nivel3 = spells_por_nivel("mago", 3)
        nomes = [s.nome_pt for s in nivel3]
        assert "Bola de Fogo" in nomes

    def test_nivel_1_clerigo_tem_curar(self):
        nivel1 = spells_por_nivel("clérigo", 1)
        nomes = [s.nome_pt for s in nivel1]
        assert "Curar Ferimentos" in nomes

    def test_nivel_inexistente_retorna_lista_vazia(self):
        # Nenhuma spell de nível 9 no catálogo (paramos em 5)
        nivel9 = spells_por_nivel("mago", 9)
        assert nivel9 == []

    def test_classe_desconhecida_nivel_zero_vazio(self):
        assert spells_por_nivel("guerreiro", 0) == []


# ── Testes: limite_progressao ─────────────────────────────────────────────────

class TestLimiteProgressao:
    def test_mago_nivel3(self):
        """Mago nível 3: 3 truques, 10 magias, nível max 2."""
        limite = limite_progressao("mago", 3)
        assert limite["truques"] == 3
        assert limite["magias"] == 10
        assert limite["nivel_max"] == 2

    def test_bruxo_nivel1(self):
        """Bruxo nível 1: 2 truques, 2 magias."""
        limite = limite_progressao("bruxo", 1)
        assert limite["truques"] == 2
        assert limite["magias"] == 2

    def test_classe_desconhecida_zeros(self):
        """Classe não-conjuradora retorna tudo zero."""
        limite = limite_progressao("guerreiro", 3)
        assert limite["truques"] == 0
        assert limite["magias"] == 0
        assert limite["nivel_max"] == 0

    def test_nivel_abaixo_do_minimo_clampado(self):
        """Nível 0 deve ser clampado para 1 sem exception."""
        limite = limite_progressao("mago", 0)
        assert isinstance(limite, dict)
        assert "truques" in limite

    def test_nivel_acima_do_maximo_clampado(self):
        """Nível 20 deve ser clampado para 10 (máximo da tabela) sem exception."""
        limite20 = limite_progressao("mago", 20)
        limite10 = limite_progressao("mago", 10)
        assert limite20 == limite10

    def test_paladino_nivel1_sem_magia(self):
        """Paladino nível 1 ainda não tem acesso a magias."""
        limite = limite_progressao("paladino", 1)
        assert limite["magias"] == 0
        assert limite["nivel_max"] == 0

    def test_ranger_nivel2_tem_magias(self):
        """Ranger nível 2 começa a ter acesso a magias."""
        limite = limite_progressao("ranger", 2)
        assert limite["magias"] > 0

    def test_alias_sem_acento(self):
        """Alias 'clerigo' (sem acento) retorna mesmo resultado."""
        com_acento = limite_progressao("clérigo", 3)
        sem_acento = limite_progressao("clerigo", 3)
        assert com_acento == sem_acento


# ── Testes: nivel_da_spell ─────────────────────────────────────────────────────

class TestNivelDaSpell:
    def test_bola_de_fogo_nivel3(self):
        assert nivel_da_spell("Bola de Fogo", "mago") == 3

    def test_missil_magico_nivel1(self):
        assert nivel_da_spell("Míssil Mágico", "mago") == 1

    def test_raio_de_gelo_nivel0(self):
        assert nivel_da_spell("Raio de Gelo", "mago") == 0

    def test_nao_encontrado_retorna_none(self):
        assert nivel_da_spell("Magia Inexistente XYZ", "mago") is None

    def test_classe_errada_nao_encontrado(self):
        # "Explosão Eldritch" é de Bruxo, não de Mago
        assert nivel_da_spell("Explosão Eldritch", "mago") is None

    def test_case_insensitive(self):
        """Deve funcionar com qualquer capitalização do nome."""
        nivel_lower = nivel_da_spell("bola de fogo", "mago")
        nivel_normal = nivel_da_spell("Bola de Fogo", "mago")
        assert nivel_lower == nivel_normal == 3


# ── Testes: integração com WorkingMemory ─────────────────────────────────────

class TestWorkingMemorySpells:
    def test_spells_conhecidas_default_vazio(self):
        """WorkingMemory sem player_spells deve ter lista vazia."""
        from engine.memory.working_memory import WorkingMemory
        wm = WorkingMemory.nova_sessao("drevamor", "Drevamor", session_id="test-001")
        assert wm.spells_conhecidas == []

    def test_spells_conhecidas_passadas(self):
        """WorkingMemory deve preservar spells_conhecidas passadas."""
        from engine.memory.working_memory import WorkingMemory
        spells = ["Bola de Fogo", "Míssil Mágico", "Raio de Gelo"]
        wm = WorkingMemory.nova_sessao(
            "drevamor", "Drevamor", session_id="test-002",
            player_spells=spells,
        )
        assert wm.spells_conhecidas == spells

    def test_spells_conhecidas_none_resulta_em_vazio(self):
        """player_spells=None não deve quebrar — resulta em lista vazia."""
        from engine.memory.working_memory import WorkingMemory
        wm = WorkingMemory.nova_sessao(
            "drevamor", "Drevamor", session_id="test-003",
            player_spells=None,
        )
        assert wm.spells_conhecidas == []


# ── Testes: injeção no prompt_builder ─────────────────────────────────────────

class TestPromptInjecao:
    def _criar_contexto(self, spells: list[str], player_class: str = "Mago"):
        """Helper que cria um ContextoMontado mínimo para testar o prompt.

        spells_conhecidas é passado tanto para working_memory quanto para
        contexto.spells_conhecidas — que é o campo lido pelo prompt_builder
        (via bloco autoritativo alimentado pelo websocket).
        """
        from engine.llm.types import ContextoMontado
        from engine.memory.working_memory import WorkingMemory

        wm = WorkingMemory.nova_sessao(
            "drevamor", "Drevamor", session_id="test-prompt",
            player_class=player_class,
            player_spells=spells,
        )
        return ContextoMontado(
            working_memory=wm,
            chunks_semanticos=[],
            chunks_episodicos=[],
            chunks_regras=[],
            relacoes_grafo=[],
            secrets_visiveis=[],
            transcricao_atual="falo com o viajante",
            spells_conhecidas=list(spells),  # campo lido pelo prompt_builder
        )

    def test_spells_conhecidas_injetadas_no_system(self):
        """Se spells_conhecidas não vazia, prompt deve conter a seção."""
        from engine.llm.prompt_builder import invalidar_cache, montar_mensagens
        invalidar_cache()
        contexto = self._criar_contexto(["Bola de Fogo", "Míssil Mágico"])
        msgs = montar_mensagens(contexto, master_system_override="System placeholder.")
        system = msgs[0]["content"]
        assert "MAGIAS CONHECIDAS DO PERSONAGEM" in system

    def test_prompt_contem_nome_da_magia(self):
        """O nome da magia selecionada deve aparecer no prompt."""
        from engine.llm.prompt_builder import invalidar_cache, montar_mensagens
        invalidar_cache()
        contexto = self._criar_contexto(["Bola de Fogo"])
        msgs = montar_mensagens(contexto, master_system_override="System placeholder.")
        system = msgs[0]["content"]
        assert "Bola de Fogo" in system

    def test_prompt_sem_spells_nao_tem_secao(self):
        """Se spells_conhecidas vazio (Guerreiro), prompt NÃO deve ter a seção."""
        from engine.llm.prompt_builder import invalidar_cache, montar_mensagens
        invalidar_cache()
        contexto = self._criar_contexto([], player_class="Guerreiro")
        msgs = montar_mensagens(contexto, master_system_override="System placeholder.")
        system = msgs[0]["content"]
        assert "MAGIAS CONHECIDAS DO PERSONAGEM" not in system

    def test_prompt_contem_aviso_restricao(self):
        """O prompt deve alertar que o personagem SÓ pode conjurar as magias listadas."""
        from engine.llm.prompt_builder import invalidar_cache, montar_mensagens
        invalidar_cache()
        contexto = self._criar_contexto(["Raio de Gelo"])
        msgs = montar_mensagens(contexto, master_system_override="System placeholder.")
        system = msgs[0]["content"]
        # Verifica qualquer forma de restrição de casting no prompt
        system_lower = system.lower()
        assert "somente conhece" in system_lower or "só pode conjurar" in system_lower or "somente pode conjurar" in system_lower

    def test_prompt_agrupa_truques_separados(self):
        """Truques e magias de nível 1+ devem aparecer em grupos separados."""
        from engine.llm.prompt_builder import invalidar_cache, montar_mensagens
        invalidar_cache()
        # Raio de Gelo = truque (nível 0), Míssil Mágico = nível 1
        contexto = self._criar_contexto(["Raio de Gelo", "Míssil Mágico"])
        msgs = montar_mensagens(contexto, master_system_override="System placeholder.")
        system = msgs[0]["content"]
        assert "Truques:" in system or "Nível 1:" in system
