"""
Testes do roteador de TaskType narrativo.

Por que existe: bug 26/05 — threshold antigo (pacing <= 2.0) nunca disparava em
sessão real porque pacing parte de 3.0 e decai lentamente. NARRATIVE_LIGHT
ficou morto, 70B usado todo turno.
Dependências: pytest.
Armadilha: thresholds estão acoplados ao decay de pacing em
engine/state/narrative.py — mexer num lado sem o outro descalibra.
"""


from engine.llm.tasks import (
    TaskType,
    cascata_para,
    escolher_task_type_narrativo,
)


class TestEscolherTaskTypeNarrativo:
    def test_default_em_pacing_intermediario(self):
        # Pacing 4-6 fora de combate → NARRATIVE
        assert escolher_task_type_narrativo(em_combate=False, pacing_nivel=4.0) == TaskType.NARRATIVE
        assert escolher_task_type_narrativo(em_combate=False, pacing_nivel=5.5) == TaskType.NARRATIVE
        assert escolher_task_type_narrativo(em_combate=False, pacing_nivel=6.9) == TaskType.NARRATIVE

    def test_light_em_pacing_baixo(self):
        # Pacing <= 3.0 fora de combate → LIGHT (regressão do bug 26/05)
        assert escolher_task_type_narrativo(em_combate=False, pacing_nivel=3.0) == TaskType.NARRATIVE_LIGHT
        assert escolher_task_type_narrativo(em_combate=False, pacing_nivel=2.1) == TaskType.NARRATIVE_LIGHT
        assert escolher_task_type_narrativo(em_combate=False, pacing_nivel=2.4) == TaskType.NARRATIVE_LIGHT
        assert escolher_task_type_narrativo(em_combate=False, pacing_nivel=2.7) == TaskType.NARRATIVE_LIGHT

    def test_light_por_turnos_sem_tensao(self):
        # Mesmo com pacing alto, 3+ turnos sem tensão sinaliza filler
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=5.0, turnos_sem_tensao=3
        ) == TaskType.NARRATIVE_LIGHT
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=4.5, turnos_sem_tensao=5
        ) == TaskType.NARRATIVE_LIGHT

    def test_light_nao_dispara_em_combate(self):
        # Combate nunca vira LIGHT, mesmo com pacing baixo
        assert escolher_task_type_narrativo(em_combate=True, pacing_nivel=2.0) == TaskType.NARRATIVE
        assert escolher_task_type_narrativo(
            em_combate=True, pacing_nivel=1.0, turnos_sem_tensao=10
        ) == TaskType.NARRATIVE

    def test_climax_em_combate_denso(self):
        # Combate + pacing >= 7 → CLIMAX
        assert escolher_task_type_narrativo(em_combate=True, pacing_nivel=7.0) == TaskType.NARRATIVE_CLIMAX
        assert escolher_task_type_narrativo(em_combate=True, pacing_nivel=9.5) == TaskType.NARRATIVE_CLIMAX

    def test_climax_em_cliffhanger(self):
        # Cliffhanger pendente força CLIMAX independente de combate/pacing
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=2.0, cliffhanger_pendente=True
        ) == TaskType.NARRATIVE_CLIMAX
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=8.0, cliffhanger_pendente=True
        ) == TaskType.NARRATIVE_CLIMAX

    def test_combate_pacing_medio_e_narrative_normal(self):
        # Combate com pacing < 7 e sem cliffhanger → NARRATIVE
        assert escolher_task_type_narrativo(em_combate=True, pacing_nivel=4.0) == TaskType.NARRATIVE
        assert escolher_task_type_narrativo(em_combate=True, pacing_nivel=6.9) == TaskType.NARRATIVE

    def test_pacing_inicial_padrao_e_light(self):
        # Sessão recém-iniciada com pacing 3.0 default → LIGHT (8B)
        # Justificativa: abertura/exploração inicial não justifica 70B.
        assert escolher_task_type_narrativo(em_combate=False, pacing_nivel=3.0) == TaskType.NARRATIVE_LIGHT


class TestHibridoQualidadeMestre:
    """Calibração 02/06 — NPC na cena força 70B + cap anti-robô no 8B.

    Origem: 1º teste ao vivo (01/06) — mestre virou robô em cena social longa,
    travado no 8B. Ver memory/teste_ao_vivo_01062026.md (CONTEXT-ROT-8B).
    """

    def test_npc_na_cena_forca_70b_mesmo_com_pacing_baixo(self):
        # Cena social/RP: NPC presente puxa qualidade máxima, nunca 8B.
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=2.0, npc_na_cena=True
        ) == TaskType.NARRATIVE
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=0.2, npc_na_cena=True
        ) == TaskType.NARRATIVE

    def test_npc_na_cena_forca_70b_mesmo_com_turnos_sem_tensao(self):
        # O caso exato do bug: pacing despencou em cena social longa.
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=1.0, turnos_sem_tensao=10, npc_na_cena=True
        ) == TaskType.NARRATIVE

    def test_sem_npc_ainda_vira_light(self):
        # Exploração genuína sem NPC: economia de TPM preservada.
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=2.0, npc_na_cena=False
        ) == TaskType.NARRATIVE_LIGHT

    def test_cap_forca_70b_apos_light_consecutivos(self):
        # 2 turnos LIGHT seguidos → o 3º é forçado a 70B (reset de estilo).
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=2.0, light_consecutivos=2
        ) == TaskType.NARRATIVE
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=2.0, light_consecutivos=5
        ) == TaskType.NARRATIVE

    def test_cap_permite_light_abaixo_do_teto(self):
        # 0 ou 1 LIGHT seguidos ainda permite mais um LIGHT.
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=2.0, light_consecutivos=0
        ) == TaskType.NARRATIVE_LIGHT
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=2.0, light_consecutivos=1
        ) == TaskType.NARRATIVE_LIGHT

    def test_cliffhanger_vence_npc_e_cap(self):
        # CLIMAX tem prioridade sobre tudo.
        assert escolher_task_type_narrativo(
            em_combate=False, pacing_nivel=2.0,
            cliffhanger_pendente=True, npc_na_cena=True, light_consecutivos=5,
        ) == TaskType.NARRATIVE_CLIMAX


class TestCascataPara:
    def test_narrative_light_prefere_8b(self):
        cascata = cascata_para(TaskType.NARRATIVE_LIGHT)
        assert cascata[0] == "groq-8b"

    def test_narrative_climax_pula_8b(self):
        cascata = cascata_para(TaskType.NARRATIVE_CLIMAX)
        # 70B primeiro, Gemini segundo, 8B só depois
        assert cascata[0] == "groq-70b"
        assert cascata.index("gemini-flash") < cascata.index("groq-8b")

    def test_task_desconhecida_cai_em_default(self):
        # Garantia: tipo sem entrada explícita não quebra (cai no _DEFAULT)
        for task in TaskType:
            assert cascata_para(task)  # cascata não-vazia
