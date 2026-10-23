# Blue Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Apply the approved Metais Glória blue interface to the existing Streamlit order auditor on teste.
**Architecture:** Keep the business engine and persistence unchanged. Add pure HTML/view helpers, a local stylesheet and Streamlit theme, then adapt existing views. Preserve completed results in the current authenticated session for presentation-only reruns.
**Tech Stack:** Python, Streamlit, pandas, existing PostgreSQL layer and unittest/AppTest.
**Spec:** docs/superpowers/specs/2026-10-23-blue-design-system.md

## Global Constraints

- Colors #0A4BB3 / #0B1B3D / #F5F7FB / #1B293D.
- No changes to parser, database, audit, price or order workflow modules.
- No main integration; PR targets teste.
- No live database writes during tests.

## Review Focus

- Unsafe HTML in PDF descriptions or user names must render as text.
- Mixed/absent statuses must never appear approved in the summary.
- Filter/download reruns must not lose results or write another audit.
- New uploads and logout must not reveal stale results.
- Non-admin navigation and maintenance controls retain existing restrictions.

### Task 1: Presentation components
**Files:** ui_components.py, assets/design-system.css, .streamlit/config.toml, tests/test_ui_components.py.
**Interfaces:** resumo_lote(df: DataFrame) -> dict; filtrar_itens(df, filtro: str, pedido: str='Todos') -> DataFrame; cabecalho_item_html(row: Mapping) -> str; painel_diagnostico_html(etapa, status, diagnostico) -> str; render helpers consume escaped text and return static HTML.
- [x] Add tests that reject a false approval for expired/equal prices, incomplete statuses and fiscal divergences, and keep codes/text intact in filtered results.
- [x] Run unittest test_ui_components, expect missing-module failure before implementation.
- [x] Implement pure formatting/filtering helpers and stylesheet/theme.
- [x] Run component tests and full baseline suite, expect PASS.

### Task 2: Connect all screens
**Files:** app.py, tests/test_app_design.py.
**Interfaces:** native widgets retain current callbacks and labels for confirmation. Results are stored under resultados_processados/assinatura_resultados only after the existing workflow completes.
- [x] Add AppTest integration cases for profile navigation, login, cached result filtering and both re-audit confirmations. Mock external database calls only, keep app and widgets real.
- [x] Run AppTest cases before integration, expect missing result/filter behavior.
- [x] Apply branding, headers, cards, two-step diagnostics, grouped forms, log filters and session presentation persistence.
- [x] Verify auth/logout, invalidation, exports, admin-only menus and existing workflow suite. Expect no AppTest exceptions and full green suite.

### Task 3: Review and delivery
**Files:** docs/design-system/*, .github/workflows/test.yml, implementation docs.
- [x] Run compilation, full unittest discovery and diff whitespace checks.
- [ ] Review every changed file and browser-check desktop/mobile if supported.
- [ ] Request fresh-context code review; fix material findings and verify regressions.
- [ ] Push feature branch, create PR to teste, verify safe merge, integrate and inspect Render deploy state.
