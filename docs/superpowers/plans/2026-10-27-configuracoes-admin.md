# Configurações Administrativas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar uma página administrativa que persiste e aplica três regras variáveis de diagnóstico, inicialmente na branch `teste`.

**Architecture:** Defaults e validação ficam em um módulo puro; o repositório PostgreSQL persiste os valores e metadados; o Streamlit carrega uma única configuração por execução e a injeta nas regras de preço e no parser. A tela administrativa salva os três campos atomicamente.

**Tech Stack:** Python, Streamlit, pandas, psycopg2, unittest, PostgreSQL/Neon.

**Spec:** `docs/superpowers/specs/2026-10-27-configuracoes-admin-design.md`

## Global Constraints

- Defaults: 90 dias, R$ 0,01 para preço e R$ 1,00 para fiscal.
- Somente `ADMIN` consulta ou altera configurações.
- PIS/COFINS, ICMS/IPI e confirmações de reauditoria não mudam.
- Configurações inválidas nunca podem interromper o diagnóstico; usar defaults.
- Entrega somente na branch `teste` nesta etapa.

## Review Focus

- Banco sem linhas de configuração deve usar exatamente os três defaults.
- Valores nulos, texto inválido, negativos e fora do limite devem ser rejeitados ou normalizados com segurança.
- Alterar prazo deve afetar igualmente o diagnóstico e a lista de preços desatualizados.
- Alterar tolerâncias nos limites exatos deve manter o comportamento inclusivo atual (`diferença > tolerância`).
- Usuários não administradores não podem acessar a página nem executar a gravação.

---

### Task 1: Modelo puro e validade por dias

**Files:**
- Create: `system_settings.py`
- Modify: `price_rules.py`
- Test: `tests/test_system_settings.py`
- Test: `tests/test_price_rules.py`

**Interfaces:**
- Produces: `SystemSettings`, `DEFAULT_SYSTEM_SETTINGS`, `normalize_system_settings(values)`, `is_price_outdated(value, today=None, max_age_days=90)`.

- [ ] Escrever testes falhando para defaults, limites, entradas inválidas e fronteira de 90 dias.
- [ ] Executar os testes e confirmar falha pela ausência das interfaces/comportamento.
- [ ] Implementar modelo, normalização e validade baseada em `timedelta(days=max_age_days)`.
- [ ] Executar testes até aprovação.
- [ ] Commitar modelo e regras puras.

### Task 2: Persistência transacional no Neon

**Files:**
- Modify: `database.py`
- Test: `tests/test_database_settings.py`

**Interfaces:**
- Consumes: `SystemSettings`, `normalize_system_settings`.
- Produces: `buscar_configuracoes_sistema() -> SystemSettings`, `salvar_configuracoes_sistema(settings, usuario)`, `listar_metadados_configuracoes() -> dict`.

- [ ] Escrever testes falhando para schema idempotente, defaults sem registros, leitura e atualização atômica com usuário/data.
- [ ] Executar os testes e confirmar falhas esperadas.
- [ ] Criar `configuracoes_sistema`, semear defaults com `ON CONFLICT DO NOTHING` e implementar as funções.
- [ ] Executar testes até aprovação.
- [ ] Commitar persistência.

### Task 3: Aplicar configurações ao diagnóstico

**Files:**
- Modify: `parser.py`
- Modify: `ui_rules.py`
- Modify: `app.py`
- Test: `tests/test_parser_price_review.py`
- Test: `tests/test_admin_views.py`

**Interfaces:**
- Consumes: `SystemSettings`, `buscar_configuracoes_sistema()`.
- Produces: `processar_pdf(..., settings=None)` e `build_outdated_prices_table(..., review_days=90)` usando os valores injetados.

- [ ] Escrever testes falhando para prazo variável, tolerância de preço e tolerância fiscal, inclusive nos limites exatos.
- [ ] Executar os testes e confirmar falhas esperadas.
- [ ] Injetar uma configuração por lote e substituir somente os três valores fixos aprovados.
- [ ] Executar testes até aprovação.
- [ ] Commitar integração das regras.

### Task 4: Página administrativa de configurações

**Files:**
- Modify: `app.py`
- Modify: `ui_rules.py`
- Test: `tests/test_admin_views.py`
- Test: `tests/test_app_design.py`

**Interfaces:**
- Consumes: funções de persistência e `SystemSettings`.
- Produces: menu `⚙️ Configurações`, formulário com três campos, metadados e confirmação de salvamento.

- [ ] Escrever testes falhando para visibilidade exclusiva do Admin, valores iniciais, salvamento e mensagens explicativas.
- [ ] Executar os testes e confirmar falhas esperadas.
- [ ] Implementar página e validação, sem expor PIS/COFINS ou reauditoria.
- [ ] Executar testes até aprovação.
- [ ] Commitar página administrativa.

### Task 5: Verificação e publicação em teste

**Files:**
- Modify only if verification finds a defect in scope.

**Interfaces:**
- Produces: branch remota e PR integrados em `teste`; deploy de homologação verificado.

- [ ] Executar `python -m unittest discover -s tests -v`.
- [ ] Executar `python -m py_compile app.py parser.py database.py price_rules.py audit_rules.py ui_rules.py ui_components.py system_settings.py`.
- [ ] Executar `git diff --check` e revisar o diff.
- [ ] Publicar `codex/configuracoes-admin`, abrir PR contra `teste` e integrar após verificar mergeabilidade.
- [ ] Acompanhar o deploy do serviço de teste até `live`, verificar HTTP 200 e ausência de erros novos.
