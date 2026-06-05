# Contribuindo com o VoxDM

Obrigado pelo interesse! O VoxDM é um projeto pessoal desenvolvido **ao vivo no
[YouTube](https://www.youtube.com/@Beltramidev)**. Contribuições são bem-vindas, mas
o ritmo e a direção são guiados pelo mantenedor e pelo conteúdo do canal — então
**abra uma issue para discutir antes de um PR grande**.

## Antes de começar

1. Leia a [ARCHITECTURE.md](./ARCHITECTURE.md) para entender os subsistemas.
2. Rode o projeto seguindo o [Quickstart do README](./README.md#quickstart).
3. Confirme que a suíte passa: `uv run pytest tests/ -q` e `cd frontend && npx tsc --noEmit`.

## Convenções de código (obrigatórias)

Estas convenções valem para todo o backend Python:

- **Python 3.12.x** — nunca 3.14 (faltam wheels de CTranslate2).
- **`async/await`** em toda operação de I/O, sem exceção.
- **Type hints** em todas as funções, métodos e variáveis de módulo.
- **Comentários em português brasileiro.**
- Configuração via **`from config import settings`** — nunca `os.getenv()` direto.
- Logs via **`structlog.get_logger()`** — nunca `print()` nem `logging` direto.
- Clientes de API externa usam **`tenacity`** com backoff exponencial.
- HTTP via **`httpx`** assíncrono — nunca `requests`.
- **Tratamento de erro explícito** — nunca `except: pass`.
- **IDs em kebab-case:** `strahd-von-zarovich`, `barovia-village`.
- Gerenciador de pacotes: **`uv`** — nunca `pip` direto.
- Arquivo Python novo começa com um **docstring de módulo** (o que faz / por que existe /
  armadilha / exemplo).

Frontend: TypeScript estrito (`tsc --noEmit` precisa passar), Next.js 14 + Tailwind.

## Testes

- Testes em `tests/`, espelhando a estrutura de `engine/` e `api/`.
- **Todo PR precisa de testes verdes** (`pytest`) e **tsc limpo** se mexer no frontend.
- Mudanças sensíveis a qualidade (prompt, RAG, voz) são validadas **ao vivo** pelo
  mantenedor antes de fechar — descreva no PR o que precisa ser validado em jogo.

## Conteúdo e copyright

- Apenas conteúdo **SRD aberto** (OGL/CC-BY). Nada de Product Identity da WotC nem de
  produtos licenciados/fechados (ex.: Curse of Strahd). Veja [NOTICE](./NOTICE).

## Licença

Ao contribuir, você concorda que sua contribuição é licenciada sob a
**AGPL-3.0** (veja [LICENSE](./LICENSE)).

## Commits

- Mensagens descritivas, prefixo de tipo (`feat:`, `fix:`, `perf:`, `docs:`, `chore:`).
- PRs pequenos e focados são mais fáceis de revisar (e de validar ao vivo).
