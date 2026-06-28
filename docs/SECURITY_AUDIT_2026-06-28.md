# VoxDM — Auditoria de Segurança (2026-06-28)

> Auditoria abrangente conduzida em modo automatizado (rotina agendada).
> Cobertura: injeção, autenticação/autorização, segredos & configuração,
> segurança de frontend, e CVEs de dependências (Python + frontend).
> Ferramentas executadas ao vivo: `pip-audit` 2.10.1 (PyPI advisory DB),
> `npm audit` (npm advisory DB) contra o lockfile commitado, `git log -S`
> sobre todo o histórico, `git grep` de padrões de segredo.

## Veredito geral

**Postura de segurança forte. 1 achado ALTO (CVEs do Next.js), nenhum
CRÍTICO.** O código próprio (backend Python + lógica de auth/authz) está
limpo nas categorias de injeção, com defesa em profundidade consistente. O
risco acionável real está na **dependência de framework do frontend
(Next.js 14.2.35)**, que carrega advisories ALTOS diretamente relevantes à
arquitetura do VoxDM (WebSockets + App Router + self-hosting atrás de
Cloudflare Tunnel).

| Severidade | Qtd | Itens |
|---|---|---|
| Crítico | 0 | — |
| Alto | 1 | H1 (Next.js CVEs) |
| Médio | 5 | M1–M5 |
| Baixo | 8 | L1–L8 |

---

## ALTO

### H1 — Next.js 14.2.35: 14 advisories (incl. SSRF via WebSocket upgrade, CVSS 8.6)
- **Onde:** `frontend/package.json` → `next 14.2.35` (confirmado por `npm audit`
  contra `frontend/package-lock.json`).
- **Risco:** o `npm audit` ao vivo retornou 14 advisories afetando 14.2.35,
  incluindo várias diretamente no escopo desta aplicação:
  - **SSRF em aplicações que usam upgrades de WebSocket** (VoxDM usa WS
    intensamente — `useGameSession.ts` abre `wss://.../ws/game/{id}`).
  - **DoS via React Server Components** (HTTP request deserialization) e
    **DoS na Image Optimization API / remotePatterns** (self-hosted).
  - **HTTP request smuggling em rewrites** e **cache poisoning / bypass de
    Middleware/Proxy** — relevante atrás de Cloudflare Tunnel.
  - **XSS no App Router com CSP nonces** e **XSS em beforeInteractive scripts**.
- **Importante:** a versão **14.2.35 é a última release da linha 14.2.x** — não
  existe patch dentro do 14.x. As correções estão somente em **15.x
  (atual 15.5.19)** ou **16.x** (`npm audit` aponta fixAvailable `next@16.2.9`,
  semver-major).
- **Remediação:** atualizar Next.js para a última stable suportada (15.5.x ou
  16.x). É uma **mudança breaking** — exige testar build (`next build`), App
  Router, e o fluxo de WebSocket antes de subir. **Não aplicada nesta rotina
  automatizada** justamente por ser breaking e exigir validação humana de
  regressão. Após o bump, rodar `npm audit` novamente até zerar os ALTOS.

---

## MÉDIO

### M1 — Identidade admin insegura por padrão
- **Onde:** `config.py:165-166` — `DEV_USER_EMAIL = "admin@localhost"` e
  `ADMIN_EMAILS = "admin@localhost"` (idênticos).
- **Risco:** o default `DEBUG = False` protege produção (sem JWT → 401). Porém,
  se um operador ligar `DEBUG=True` **sem** configurar `CF_TEAM_DOMAIN`/
  `CF_ACCESS_AUD`, o fallback `DEV_USER_EMAIL` é usado (`api/auth.py:102-105`) e,
  como ele é igual a `ADMIN_EMAILS`, **toda request vira admin** — acesso a
  todas as sessões, personagens e `/debug/*` (que vaza working memory, prompts,
  diálogo). O caminho de menor esforço produz a identidade mais permissiva.
- **Remediação:** mudar os defaults para string vazia. Com `ADMIN_EMAILS`
  vazio, `is_admin()` retorna `False` para todos — um dev box mal configurado
  gera um usuário não-admin, não um super-admin. Adicionar warning de boot se
  `DEBUG=True and not CF_TEAM_DOMAIN`.

### M2 — Fallback de identidade JWT para `identity_nonce`
- **Onde:** `api/auth.py:59` — `email = payload.get("email") or payload.get("identity_nonce") or ""`.
- **Risco:** `identity_nonce` é um valor aleatório por login, não um email. Um
  JWT **sem claim `email`** (ex.: service token de uma Access App) passaria na
  auth com uma identidade-lixo não-vazia, criando/possuindo sessões sob um
  owner inválido.
- **Remediação:** remover o branch `identity_nonce`; exigir um `email` real
  (já existe o raise quando ambos vazios — basta dropar o fallback nonce).

### M3 — Sem Content-Security-Policy nem headers de segurança no frontend
- **Onde:** `frontend/next.config.mjs` está vazio (`const nextConfig = {}`).
- **Risco:** ausência de `frame-ancestors` (clickjacking), de `img-src`/
  `connect-src`/`style-src` (não mitiga M4 na camada de plataforma e vaza
  Referer para hosts de imagem), e de `Referrer-Policy`/`X-Content-Type-Options`/
  `X-Frame-Options`.
- **Remediação:** adicionar bloco `headers()` com `Content-Security-Policy`
  (`default-src 'self'`; `img-src 'self' https://image.pollinations.ai data:`;
  `connect-src 'self' <API> wss://<API>`; `frame-ancestors 'none'`),
  `Referrer-Policy: strict-origin-when-cross-origin`,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`. Em `next export`
  estático (`frontend/out/`) o `headers()` não se aplica — nesse caso setar na
  camada FastAPI StaticFiles ou no Cloudflare.

### M4 — URLs de imagem derivadas do LLM renderizadas sem sanitização
- **Onde:** `frontend/hooks/useGameSession.ts:432-436,500-501` →
  `frontend/components/NpcsPresentes.tsx:64-66` (`<img src={retrato}>`) e
  `frontend/components/AppShell.tsx:98` (CSS `url(${backgroundUrl})`). O schema
  valida apenas `z.string()` (`frontend/lib/ws-schema.ts:60`).
- **Risco:** hoje o host é fixado no servidor (`image.pollinations.ai`,
  hardcoded, com `follow_redirects=False`), então é **latente**, não explorável.
  Mas se o backend algum dia ecoar uma URL escolhida pelo LLM, vira vetor de
  exfiltração/tracking (fetch para host arbitrário + Referer).
- **Remediação:** allowlist client-side — aceitar a URL só se
  `startsWith("https://image.pollinations.ai/")`; reforçar via CSP `img-src`.

### M5 — Cache de certificados sem negative-caching (auto-DoS em outage do CF)
- **Onde:** `engine/auth/jwt_validator.py:48-78` — `_obter_certs` só cacheia em
  sucesso; sem TTL negativo.
- **Risco:** numa indisponibilidade do Cloudflare, cada request de entrada
  dispara um fetch HTTP novo aos JWKS (`timeout=10.0`) — amplificação 1:1 e
  stalls de 10s por request sob carga.
- **Remediação:** negative-cache curto (30-60s) para falhas; servir certs
  recentes (stale-but-recent) se o refresh falhar. Limitar o tamanho do cache
  caso `team_domain` se torne dinâmico no futuro.

---

## BAIXO

- **L1 — `team_domain` interpolado na URL JWKS sem validação** (`jwt_validator.py:55`).
  Hoje é config confiável; validar `^[a-z0-9-]+$` antes de interpolar (evita
  SSRF latente se a origem mudar).
- **L2 — Dashboard Streamlit liga em `0.0.0.0`** (`scripts/exec/monitor.bat:33`,
  default do Streamlit). Expõe estado de sessão/debug na LAN sem auth. Adicionar
  `--server.address 127.0.0.1` e/ou bloquear 8501 no firewall.
- **L3 — CORS `allow_methods=["*"]`/`allow_headers=["*"]` com `allow_credentials=True`**
  (`api/main.py:255-258`). Origens já estão travadas (sem wildcard de origem),
  então baixo impacto; estreitar para listas explícitas.
- **L4 — Rate-limit chaveado no header `Cf-Access-Authenticated-User-Email` bruto**
  (`api/rate_limit.py:39`). Forjável se o app for alcançável fora do Tunnel;
  afeta integridade do rate-limit, não authz. Derivar do email do JWT validado
  ou garantir que o Tunnel sobrescreve o header.
- **L5 — Origin check do WS pulado quando o header `Origin` está ausente**
  (`api/websocket.py`). Clientes não-browser ignoram o guard; o JWT é o portão
  real, então baixo. Logar conexões sem Origin.
- **L6 — Fallback `http://localhost:8000` no frontend** (`frontend/lib/api.ts:1`)
  causa downgrade para `ws://` se `NEXT_PUBLIC_API_URL` não for setado em prod.
  Falhar o build se a env não estiver definida.
- **L7 — Oráculo de existência no WS** (`api/websocket.py`): resposta textual
  para "não existe" vs close silencioso para "existe mas não é seu". UUIDs de
  122 bits tornam brute-force inviável (baixo). Padronizar o close.
- **L8 — Deps de dev-toolchain do frontend com advisories** (`npm audit`):
  `brace-expansion` 5.0.2-5.0.5 (ReDoS), `js-yaml` ≤4.1.1 (DoS), `glob`
  10.2-10.4.5 (command injection via `-c`, só CLI) — todos via
  `eslint-config-next`, somente em dev/lint, não vão para produção. Resolver com
  `npm audit fix` (não-major) / bump do `eslint-config-next`.
- **Nota supply-chain — `torch` não pinado e instalado fora do manifest**
  (`requirements.txt:52-53`, index CUDA do pytorch.org). Não é coberto pelo
  `pip-audit`. torch tem histórico recorrente de CVE (deserialização
  `torch.load`/pickle RCE). Pinar a versão exata e auditar à parte; tratar
  carregamento de checkpoint como entrada não-confiável.

---

## Aprovado (verificado limpo — sem achado)

**Segredos & histórico**
- Zero segredos hardcoded em código-fonte (grep de `gsk_`/`AIza`/`sk-`/
  `-----BEGIN`/credenciais quoted → nada).
- Histórico git limpo: o vazamento passado de email/PAT foi removido via
  `git filter-repo` — `git log --all -S` confirma 0 ocorrências em todas as
  branches.
- `.env` gitignorado e não rastreado; só `*.example` (placeholders) commitados.

**Dependências Python**
- `pip-audit` (DB ao vivo): **nenhuma vulnerabilidade** em todo o grafo
  transitivo (starlette 1.3.1, aiohttp 3.14.1, urllib3 2.7.0, certifi, Jinja2
  3.1.6, requests, anyio — todos limpos).
- Pins de remediação de CVE verificados efetivos: `pydantic-settings 2.14.2`,
  `langsmith 0.8.18`, `python-multipart 0.0.31`, `pyjwt 2.13.0`, `pytest 9.0.3`.
- Sem typosquats (`google-genai` correto, `kokoro` correto); sem git URLs.

**Injeção & operações inseguras (backend)**
- SQL 100% parametrizado (`character_store.py`, único store SQLite); nomes de
  tabela/coluna são constantes estáticas.
- Sem `subprocess`/`os.system`/`shell=True`/`eval`/`exec`/`compile`.
- Desserialização segura: só `yaml.safe_load`; sem `pickle`/`marshal`/`torch.load`.
- Path traversal mitigado: `api/debug_archive.py:_sanitizar_id()` (`[alnum-_]`,
  64 chars); `/transcribe` com cap de 10MB e ownership-first; STT via
  `NamedTemporaryFile`.
- SSRF: hosts fixos hardcoded (`image.pollinations.ai` com
  `follow_redirects=False`); JWKS via config.
- Cypher: a única interpolação runtime (`atualizar_afeto_npc`) é duplamente
  guardada (allowlist `{afeto,medo,respeito,rancor}` + regex upstream).
- Sem ReDoS (todos os ~60 `_RE_*` têm quantificadores limitados); `.format()`
  seguro (template confiável, texto como valor).

**Auth/Authz**
- JWT: `algorithms=["RS256"]` pinado, `aud`+`iss` validados, expiração checada,
  `alg:none`/HS256 rejeitados.
- Session IDs UUID v4 server-side (cliente ignorado) — sem fixation/predição.
- Ownership check em **todas** as rotas de sessão/personagem/turno; `/list`
  filtra por owner; 404 (não 403) anti-enumeração.
- WS: ordem origin → auth → `accept()` → existência → ownership, com auth
  **antes** do accept. Identidade resolvida só do JWT validado (nunca do header
  de email bruto).

**Frontend**
- Sem sinks de HTML (`dangerouslySetInnerHTML`/`innerHTML`/`eval` → 0); texto do
  LLM auto-escapado pelo React.
- Sem cookies/tokens — auth header-based (CF Access), não forjável cross-site;
  CSRF clássico não explorável.
- localStorage só com preferências de UI (sem token/JWT/email); logout limpa
  `voxdm_*`. Sem open-redirect (`/cdn-cgi/access/logout` é path fixo).

**DevSecOps**
- `.github/workflows/security.yml`: gitleaks (bloqueante) + `pip-audit` (cron
  semanal). `.pre-commit-config.yaml` com gitleaks/ruff/large-file. `SECURITY.md`
  com política de disclosure — claims verificados verdadeiros.

---

## Prioridade recomendada

1. **H1** — planejar o upgrade do Next.js (15.5.x ou 16.x) + testar build/WS/App
   Router. Único item ALTO; breaking, decisão humana.
2. **M1** — flipar defaults de `DEV_USER_EMAIL`/`ADMIN_EMAILS` para vazio
   (fix de maior alavancagem, trivial).
3. **M2** — remover fallback `identity_nonce`.
4. **M3 + M4** — CSP/headers + allowlist da URL de imagem (juntos cobrem o
   vetor de imagem na camada plataforma + client).
5. **M5, L1–L8** — hardening incremental.
