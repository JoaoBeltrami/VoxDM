"""Script de diagnóstico — mostra resposta bruta do LLM para ver se tem markdown."""
import asyncio
import sys

sys.path.insert(0, ".")


async def main() -> None:
    from engine.memory.working_memory import WorkingMemory
    from engine.memory.context_builder import ContextBuilder
    from engine.llm.groq_client import GroqClient
    from engine.llm.prompt_builder import montar_mensagens
    from engine.voice.tts import _limpar_markdown

    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", session_id="diag")
    builder = ContextBuilder()
    npcs = await builder.inferir_npcs_presentes("tharnvik")
    wm.npcs_presentes = npcs
    wm.registrar_fala("player", "Onde estou e quem esta aqui?")

    ctx = await builder.montar("Onde estou e quem esta aqui?", wm)
    msgs = montar_mensagens(ctx)

    groq = GroqClient()
    resposta = await groq.completar(msgs, temperatura=0.8, max_tokens=200)

    print("\n" + "=" * 60)
    print("RESPOSTA BRUTA DO LLM:")
    print("=" * 60)
    print(resposta)
    print("=" * 60)

    tem_markdown = any(c in resposta for c in ["**", "##", "* ", "- ", "`", "==="])
    print(f"\nTem markdown detectado: {tem_markdown}")

    limpa = _limpar_markdown(resposta)
    print("\nAPOS _limpar_markdown:")
    print("=" * 60)
    print(limpa)
    print("=" * 60)


asyncio.run(main())
