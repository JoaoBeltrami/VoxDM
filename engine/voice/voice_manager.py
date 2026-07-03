"""
Gerenciador de vozes por sessão — atribuição, cache e detecção de NPC falante.

Por que existe: centraliza tudo que envolve "qual voz usar para esta sentença"
    em um objeto com estado por sessão. O websocket consulta apenas este manager;
    não precisa saber de registry, gênero, raça ou regex.
Dependências: engine/voice/voice_registry (sem I/O externo).
Armadilha: _re_nomes é inválido (None) até que ao menos um NPC seja registrado.
    Chamar voz_para_sentenca antes disso retorna sempre a voz do narrador — correto.

Exemplo:
    vm = VoiceManager(narrator_voz="pt-BR-FranciscaNeural")
    vm.carregar_npcs([
        {"id": "valdrek", "name": "Valdrek", "gender": "male", "race": "humano"},
        {"id": "grukk",   "name": "Grukk",   "gender": "male", "race": "orc"},
    ])
    voz, rate, pitch = vm.voz_para_sentenca(
        'Valdrek murmura: "você não deveria estar aqui."'
    )
    # → ("pt-BR-AntonioNeural", "-12%", "+0Hz")
"""

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from engine.memory.working_memory import _id_para_nome
from engine.voice.voice_registry import VERBOS_FALA, PerfilVoz, selecionar_perfil

log = structlog.get_logger(__name__)

# Rate/pitch padrão para o narrador (espelham EDGE_RATE/EDGE_PITCH em tts.py)
# Bump 27/05: -12% -> +3% pra responder feedback de "soa lento" em sessão real.
_NARRATOR_RATE = "+3%"
_NARRATOR_PITCH = "+0Hz"

# Regex pré-compilada para verbos de fala — reutilizada em todas as instâncias
_RE_VERBOS = re.compile(
    r"\b(" + "|".join(re.escape(v) for v in sorted(VERBOS_FALA, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Detecta aspas curvas/retas — indica diálogo mesmo sem verbo de fala explícito
# “=" ”=" ‘=' ’='  (aspas tipográficas PT)
_RE_ASPAS = re.compile('[“”‘’"\']')


@dataclass
class VoiceManager:
    """
    Gerencia vozes de NPCs para uma sessão de jogo.

    Instanciar uma vez por sessão (em SessaoAtiva) e reutilizar.
    Reconstrução da regex de detecção ocorre apenas ao registrar novos NPCs,
    não a cada chamada de voz_para_sentenca.
    """

    narrator_voz: str = "pt-BR-FranciscaNeural"

    # npc_id → perfil de voz atribuído
    _perfis: dict[str, PerfilVoz] = field(default_factory=dict)

    # nome_lower → npc_id  (ex: "fael valdreksson" → "fael-valdreksson")
    # Inclui variantes: nome completo, primeiro nome, apelidos quando disponíveis.
    _nome_para_id: dict[str, str] = field(default_factory=dict)

    # Regex compilada com todos os nomes conhecidos — None até o primeiro registro
    _re_nomes: re.Pattern | None = field(default=None, init=False)

    # ── Carga de NPCs ─────────────────────────────────────────────────────────

    def carregar_npcs(self, npc_dados: list[dict[str, Any]]) -> None:
        """Carrega em bulk os NPCs com seus dados de gênero e raça.

        Args:
            npc_dados: Lista de dicts com ao menos "id". Campos "name", "gender"
                       e "race" são usados quando presentes.
        """
        for dado in npc_dados:
            npc_id: str = dado.get("id") or dado.get("npc_id", "")
            if not npc_id:
                continue
            self.registrar_npc(
                npc_id=npc_id,
                nome=str(dado.get("name") or dado.get("nome") or ""),
                genero=str(dado.get("gender") or dado.get("genero") or ""),
                raca=str(dado.get("race") or dado.get("raca") or ""),
                reconstruir_regex=False,  # fazemos em batch ao final
            )
        self._reconstruir_regex()
        log.info("voice_manager_carregado", npcs=len(self._perfis))

    def registrar_npc(
        self,
        npc_id: str,
        nome: str = "",
        genero: str = "",
        raca: str = "",
        reconstruir_regex: bool = True,
    ) -> PerfilVoz:
        """Registra um NPC e atribui perfil de voz (idempotente por npc_id).

        Args:
            npc_id:            ID kebab-case (ex: "fael-valdreksson").
            nome:              Nome de exibição (ex: "Fael Valdreksson").
            genero:            "male"/"female" ou variantes PT.
            raca:              Raça em qualquer capitalização (ex: "Humano", "orc").
            reconstruir_regex: False para cargas em bulk — chamar _reconstruir_regex()
                               manualmente depois.

        Returns:
            Perfil de voz atribuído.
        """
        if npc_id not in self._perfis:
            self._perfis[npc_id] = selecionar_perfil(npc_id, genero, raca)
            log.debug("voice_manager_npc", npc_id=npc_id, voz=self._perfis[npc_id]["voz"])

        # Indexa variantes de nome para lookup por sentença
        nome_display = nome.strip() or _id_para_nome(npc_id)
        self._indexar_nome(nome_display, npc_id)

        if reconstruir_regex:
            self._reconstruir_regex()

        return self._perfis[npc_id]

    # ── Detecção por sentença ─────────────────────────────────────────────────

    def voz_para_sentenca(
        self,
        sentenca: str,
    ) -> tuple[str, str, str]:
        """Retorna (voz, rate, pitch) adequados para a sentença.

        Estratégia em ordem de custo crescente:
        1. Sem regex → narrador (custo: nenhum)
        2. Regex não encontra NPC → narrador (custo: uma operação de regex)
        3. NPC encontrado mas sem verbo/aspas → narrador (custo: dois regex)
        4. NPC com fala detectada → voz do NPC (O(1) em _nome_para_id)

        Returns:
            Tupla (voz, rate, pitch) — nunca lança exceção.
        """
        if self._re_nomes is None:
            return self.narrator_voz, _NARRATOR_RATE, _NARRATOR_PITCH

        m = self._re_nomes.search(sentenca)
        if not m:
            return self.narrator_voz, _NARRATOR_RATE, _NARRATOR_PITCH

        nome_encontrado = m.group(0).lower()
        npc_id = self._nome_para_id.get(nome_encontrado)
        if not npc_id:
            return self.narrator_voz, _NARRATOR_RATE, _NARRATOR_PITCH

        # Confirmação de fala DIRETA: exige aspas. VOZ-NPC-1 (teste 09/06):
        # verbo sozinho ("Aldric responde que a mina é perigosa") é discurso
        # INDIRETO = narração — tocava a sentença inteira na voz do NPC e o
        # jogador percebia "alternância aleatória de voz/gênero". Precisão >
        # recall: sem aspas, é o narrador (mesmo princípio do quote-dominance
        # do _detectar_voz_npc no websocket).
        if not _RE_ASPAS.search(sentenca):
            return self.narrator_voz, _NARRATOR_RATE, _NARRATOR_PITCH

        perfil = self._perfis.get(npc_id)
        if not perfil:
            return self.narrator_voz, _NARRATOR_RATE, _NARRATOR_PITCH

        return perfil["voz"], perfil["rate"], perfil["pitch"]

    def npcs_registrados(self) -> list[str]:
        """Lista de npc_ids registrados neste manager."""
        return list(self._perfis.keys())

    # ── Internos ──────────────────────────────────────────────────────────────

    def _indexar_nome(self, nome: str, npc_id: str) -> None:
        """Indexa nome completo e primeiro token para detecção rápida."""
        if not nome:
            return
        self._nome_para_id[nome.lower()] = npc_id
        # Primeiro token sozinho (ex: "Fael" de "Fael Valdreksson")
        primeiro = nome.split()[0] if nome.split() else ""
        if len(primeiro) >= 3:  # evita false positive em artigos "O", "A"
            self._nome_para_id[primeiro.lower()] = npc_id

    def _reconstruir_regex(self) -> None:
        """Recompila regex de detecção com todos os nomes indexados."""
        if not self._nome_para_id:
            self._re_nomes = None
            return
        # Ordena do mais longo para o mais curto — garante greedy match correto
        nomes_ordenados = sorted(self._nome_para_id.keys(), key=len, reverse=True)
        pattern = r"\b(" + "|".join(re.escape(n) for n in nomes_ordenados) + r")\b"
        self._re_nomes = re.compile(pattern, re.IGNORECASE)
