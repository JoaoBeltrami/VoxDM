# Política de Segurança

## Reportar uma vulnerabilidade

**Não abra uma issue pública para vulnerabilidades de segurança.**

Use o **GitHub Private Vulnerability Reporting**: na aba **Security** do repositório
→ **Report a vulnerability**. Isso cria um canal privado com o mantenedor.

Inclua: descrição, passos para reproduzir, impacto potencial e (se possível) uma
sugestão de correção. Resposta esperada em até alguns dias — é um projeto mantido
por uma pessoa, então paciência é apreciada.

## Versões suportadas

| Versão | Suportada |
|--------|-----------|
| `main` (última) | ✅ |
| Tags anteriores | ❌ (atualize para `main`) |

O projeto está em desenvolvimento ativo (0.x). Correções de segurança vão para `main`.

## Postura de segurança atual

- **Sem segredos no repositório.** `.env` é gitignored; só `.env.example` é versionado.
  O histórico foi reescrito uma vez para remover dados pessoais expostos.
- **CI/CD:** `gitleaks` (varredura de segredos) + `pip-audit` (CVEs de dependências)
  rodam no GitHub Actions a cada push.
- **Camada de auth** (`engine/auth/`): JWT RS256 via Cloudflare Access, validação de
  `aud`, rejeição de `alg:none`/HS256. Endpoints `/debug/*` exigem admin.
- **Isolamento multi-tenant:** dados filtrados por `owner_email` (SQLite + Qdrant);
  rate limit por identidade autenticada.
- **Exposição de rede:** projetada para Cloudflare Tunnel + Access (Zero Trust), não
  para porta aberta na internet. `API_HOST` default é `127.0.0.1`.

## Ao auto-hospedar

- Mantenha `DEBUG=false` em qualquer ambiente exposto (`DEBUG=true` libera `/debug/*`).
- Use chaves de API próprias; nunca commite o `.env`.
- Rotacione credenciais (especialmente a senha do Neo4j AuraDB) periodicamente.
- Mantenha as dependências atualizadas (`pip-audit` ajuda a identificar CVEs).
