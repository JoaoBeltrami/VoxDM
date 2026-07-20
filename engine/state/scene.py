"""
Estado da cena atual — local, hora, NPCs presentes, diálogo recente, trust.

Por que existe: tudo que muda quando o jogador troca de local fica aqui.
    NPCs presentes, suas emoções, confiança, e a janela de diálogo recente
    (MAX_DIALOGOS=6) que vai pro LLM como pares user/assistant.

Dependências: apenas stdlib + helper _id_para_nome de working_memory (export)

Armadilha: npcs_apresentados é set — NPCs do local mas que não foram nomeados
    pelo mestre ainda. Só os apresentados aparecem no HUD do frontend.
"""

import re
import time
from dataclasses import dataclass, field

# Janela deslizante de diálogo
MAX_DIALOGOS = 6

# Cap de estados emocionais (locais antigos não devem inflar prompt)
_MAX_ESTADOS = 15


@dataclass
class DialogueTurn:
    """Uma linha de diálogo na cena atual."""
    falante: str   # "player" ou id do NPC
    texto: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SceneState:
    """Tudo que pertence à cena atual."""

    location_id: str = ""
    location_nome: str = ""
    time_of_day: str = "Dia"
    weather: str = "Limpo"

    # NPCs no local (todos os ids)
    npcs_presentes: list[str] = field(default_factory=list)

    # NPCs que foram apresentados ao jogador (subset de npcs_presentes)
    npcs_apresentados: set[str] = field(default_factory=set)

    # Diretor de Arco (passo 3b): estado que os finais avaliam ao longo da
    # CAMPANHA (não do turno). secrets_revelados = segredos que já vieram à tona
    # (NPC contou por confiança/suborno, OU o jogador declarou). quests_completas
    # = quests que chegaram à última stage. Alimentam F4 (segredo) e F2 (trégua).
    secrets_revelados: set[str] = field(default_factory=set)
    quests_completas: set[str] = field(default_factory=set)

    # Identidade única de NPC (05/07) — fonte canônica de UMA chave por pessoa.
    # npc_registro: canônico → {"nome": str, "retrato_seed": str}. A seed nasce
    # = id de criação e NUNCA muda (rename preserva o rosto Pollinations).
    # npc_aliases: id antigo/falado → canônico. API em engine/npc/identity.py;
    # persistem via dm_state (name-reveal não pode "desfazer" num restart).
    npc_registro: dict[str, dict] = field(default_factory=dict)
    npc_aliases: dict[str, str] = field(default_factory=dict)

    # Estado emocional atual de cada NPC (cap de 15)
    npc_estados_emocionais: dict[str, str] = field(default_factory=dict)

    # Relação jogador↔NPC: 0-3 (Schema v1.2)
    trust_levels: dict[str, int] = field(default_factory=dict)

    # Facções e standings
    faction_standings: dict[str, int] = field(default_factory=dict)

    # Janela deslizante de diálogo
    dialogo_recente: list[DialogueTurn] = field(default_factory=list)

    # Flag transiente: True quando o último marcador [CENA] trocou o LOCAL.
    # Lido-e-resetado pelo caller async (websocket / REST) para disparar a
    # re-inferência de NPCs via Neo4j. NÃO é serializado — é sinal de turno.
    cena_mudou_local: bool = False

    # GRIM-REATIVA-1 (07/07) — gatilho (c) do roadmap anti-amarelada: quando o
    # LLM amarelou (fade/moralização) numa cena sombria, o RESTO DA CENA roteia
    # pra cascata NARRATIVE_GRIM (garantia uncensored) mesmo que o turno
    # seguinte não tenha keyword de atrocidade. Limpa quando o local muda
    # (turn_pipeline, junto com o fim de combate por mudança de cena). Escopo
    # de cena — de propósito NÃO serializa em dm_state (restart recomeça limpo).
    cena_sombria_reativa: bool = False

    # Transiente (escopo de turno): ids adicionados via [NPC: id|Nome] neste
    # turno. A re-inferência de cena (que SUBSTITUI npcs_presentes) faz união
    # com estes para não apagar NPC improvisado pelo mestre. Limpo no início
    # do step 17b de cada pipeline. NÃO é serializado.
    npcs_introduzidos_turno: list[str] = field(default_factory=list)

    # Transiente (escopo de turno): EventoRelacao decididos pela engine no
    # pipeline SYNC (ex: companion novo → trust sobe) — o websocket drena via
    # drenar_eventos_relacao() pra emitir toasts + aplicar afeto Neo4j.
    # Eventos decididos direto no websocket (ataque) não passam por aqui.
    # NÃO é serializado. Tipo Any pra não acoplar o substate ao authority.
    eventos_relacao_turno: list = field(default_factory=list)

    # Mundo Vivo P2 — ecos de consequência: locais por onde o jogador já
    # passou (persiste via dm_state). Voltar a um deles seta o flag one-shot
    # abaixo, e o prompt obriga o mestre a mostrar que o local LEMBRA dele.
    locais_visitados: set[str] = field(default_factory=set)
    retorno_local_conhecido: bool = False

    # Anti-repetição do clima (FRIO-DREVAMOR-1): o clima estático do local
    # (ex.: weather="frio") era injetado como "Clima: frio" em TODO turno,
    # re-primando o clichê que o master_system.md proíbe ("o frio de Drevamor"
    # a cada resposta). Esta chave guarda o "local|clima" já escrito no prompt;
    # o clima entra UMA vez ao chegar no local (ou quando o clima muda de fato)
    # e some nos turnos seguintes — a Hora (que muda) permanece. Transiente:
    # NÃO é serializado (a persistência restaura só location_id/nome).
    _clima_no_prompt_chave: str = ""

    # ── Operações ────────────────────────────────────────────────────────────

    def aplicar_cena(self, location_id: str, location_nome: str = "", time_of_day: str = "") -> bool:
        """Atualiza local/nome/hora a partir do marcador [CENA: id|nome|hora].

        Trocar de LOCAL (id diferente do atual) seta `cena_mudou_local` para que
        o caller re-infira os NPCs do novo local. Mudar só nome ou hora (mesmo id,
        ex.: anoiteceu no mesmo lugar) atualiza sem disparar re-inferência.

        Retorna True se o LOCAL mudou (id diferente) — útil para log no caller.
        """
        novo_id = (location_id or "").strip().lower()
        if not novo_id:
            return False
        mudou_local = novo_id != self.location_id
        if mudou_local:
            # Ecos (P2): o local que estamos deixando vira "visitado"; se o
            # destino já foi visitado antes, é um RETORNO — flag one-shot pro
            # prompt obrigar o mestre a referenciar a passagem anterior.
            if self.location_id:
                self.locais_visitados.add(self.location_id)
            if novo_id in self.locais_visitados:
                self.retorno_local_conhecido = True
            self.cena_mudou_local = True
            self.location_id = novo_id
        if location_nome.strip():
            self.location_nome = location_nome.strip()
        if time_of_day.strip():
            self.time_of_day = time_of_day.strip()
        return mudou_local

    def consumir_cena_mudou(self) -> bool:
        """Lê e reseta o flag de mudança de local (one-shot)."""
        v = self.cena_mudou_local
        self.cena_mudou_local = False
        return v

    def drenar_eventos_relacao(self) -> list:
        """Lê e limpa os eventos de relação do turno (one-shot)."""
        eventos = list(self.eventos_relacao_turno)
        self.eventos_relacao_turno.clear()
        return eventos

    def consumir_retorno_local(self) -> bool:
        """Lê e reseta o flag de retorno a local conhecido (one-shot)."""
        v = self.retorno_local_conhecido
        self.retorno_local_conhecido = False
        return v

    def registrar_fala(self, falante: str, texto: str) -> None:
        """Adiciona fala à janela deslizante."""
        self.dialogo_recente.append(DialogueTurn(falante=falante, texto=texto))
        if len(self.dialogo_recente) > MAX_DIALOGOS:
            self.dialogo_recente.pop(0)

    def atualizar_trust(self, npc_id: str, delta: int) -> None:
        """Ajusta trust [0, 3]. Interação implica apresentação."""
        atual = self.trust_levels.get(npc_id, 0)
        self.trust_levels[npc_id] = max(0, min(3, atual + delta))
        self.npcs_apresentados.add(npc_id)

    def apresentar_npc(self, npc_id: str) -> None:
        """Marca NPC como apresentado — aparece no HUD."""
        self.npcs_apresentados.add(npc_id)

    def apresentar_npcs_mencionados(self, texto: str) -> None:
        """Varre texto e marca como apresentado qualquer NPC mencionado.

        Match por PALAVRA INTEIRA (não substring): sem isto, um NPC 'ana-bela'
        era marcado como apresentado quando o Mestre dizia 'semana' (contém
        'ana'), poluindo o HUD com NPCs nunca apresentados. O 1º nome só conta se
        tiver ≥3 letras (evita casar artigo/fragmento curto tipo 'o', 'a').
        """
        texto_lower = texto.lower()
        for npc_id in self.npcs_presentes:
            if npc_id in self.npcs_apresentados:
                continue
            primeiro_nome = npc_id.split("-")[0]
            nome_completo = npc_id.replace("-", " ")
            por_primeiro = len(primeiro_nome) >= 3 and re.search(
                rf"\b{re.escape(primeiro_nome)}\b", texto_lower
            )
            por_completo = re.search(rf"\b{re.escape(nome_completo)}\b", texto_lower)
            if por_primeiro or por_completo:
                self.npcs_apresentados.add(npc_id)

    def atualizar_estado_emocional(self, npc_id: str, estado: str) -> None:
        """Atualiza estado emocional com cap de 15 (eviction oldest)."""
        self.npc_estados_emocionais[npc_id] = estado
        if len(self.npc_estados_emocionais) > _MAX_ESTADOS:
            oldest = next(iter(self.npc_estados_emocionais))
            if oldest != npc_id:
                del self.npc_estados_emocionais[oldest]

    # ── Serialização ─────────────────────────────────────────────────────────

    def to_prompt(self) -> str:
        """Bloco de cena para o system prompt.

        Teste ao vivo 10/06: listar TODOS os presentes nominalmente fazia o LLM
        tratar a cena como assembleia — todo NPC do local "falava" toda resposta
        e as falas estouravam max_tokens. Agora só presentes∩apresentados entram
        por nome; o resto vira contagem anônima "(+N ao fundo)" — figurante até
        o mestre apresentar (via fala ou marcador [NPC]).
        """
        from engine.memory.working_memory import _id_para_nome  # evita ciclo

        linhas = [f"Local: {self.location_nome} ({self.location_id})"]
        # Clima estático entra só quando é NOVO (local ou clima mudou) — evita
        # re-primar o clichê todo turno (FRIO-DREVAMOR-1). Hora sempre entra.
        chave_clima = f"{self.location_id}|{self.weather}"
        if self.weather and chave_clima != self._clima_no_prompt_chave:
            linhas.append(f"Hora: {self.time_of_day} | Clima: {self.weather}")
            self._clima_no_prompt_chave = chave_clima
        else:
            linhas.append(f"Hora: {self.time_of_day}")

        if self.npcs_presentes:
            conhecidos = [n for n in self.npcs_presentes if n in self.npcs_apresentados]
            fundo = [n for n in self.npcs_presentes if n not in self.npcs_apresentados]
            partes: list[str] = []
            if conhecidos:
                # CANON-MORTOS (decisão 12/07): morto FICA na cena como corpo,
                # mas o LLM precisa saber que ele não fala nem age — sem isto,
                # o inimigo abatido na taverna seguia listado como presente
                # vivo e podia até ganhar diálogo.
                def _rotulo(n: str) -> str:
                    canon = self.npc_aliases.get(n, n)
                    entrada = self.npc_registro.get(canon, {})
                    if entrada.get("morto"):
                        return f"{n} (MORTO — corpo na cena; não fala, não age)"
                    # Dossiê de personalidade (decisão 12/07): traços DISTINTOS
                    # inline — é o que impede todo NPC de convergir pro tom do
                    # Mestre. Gerados no 1º encontro (engine/npc/dossie.py).
                    tracos = entrada.get("tracos") or []
                    if tracos:
                        return f"{n} [{'; '.join(tracos[:3])}]"
                    return n
                partes.append(", ".join(_rotulo(n) for n in conhecidos))
            # Teste #3 (12/06): esconder os NOMES do fundo deixou o LLM sem ter
            # como USAR os NPCs reais do local — ele improvisava NPCs fora do
            # grafo e o HUD ficava vazio pra sempre. Os ids voltam ao prompt em
            # forma neutra: disponíveis pra puxar pra cena, mas sem fala ativa.
            if fundo:
                partes.append(
                    f"(ao fundo, disponíveis se a cena pedir — sem fala até "
                    f"interagirem: {', '.join(fundo)})"
                )
            linhas.append(f"\nNPCs presentes: {' '.join(partes)}")

        if self.npc_estados_emocionais:
            em_cena = set(self.npcs_presentes) & self.npcs_apresentados
            estados_em_cena = {
                npc_id: estado
                for npc_id, estado in self.npc_estados_emocionais.items()
                if npc_id in em_cena
            }
            if estados_em_cena:
                linhas.append("Estados emocionais:")
                for npc_id, estado in estados_em_cena.items():
                    trust = self.trust_levels.get(npc_id, 0)
                    linhas.append(f"  {_id_para_nome(npc_id)}: {estado} (confiança: {trust}/3)")

        return "\n".join(linhas)
