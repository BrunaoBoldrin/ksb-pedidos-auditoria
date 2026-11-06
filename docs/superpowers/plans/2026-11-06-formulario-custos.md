# Formulário de custos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Editar preços em um formulário de cartões e adicionar campos sem permitir remoção de custos vinculados.
**Architecture:** Reutilizar o serviço e o buffer Decimal existentes; substituir somente a apresentação da central e acrescentar contagens de vínculos ao snapshot do catálogo.
**Tech Stack:** Python, Streamlit, pandas, PostgreSQL, unittest/AppTest.
**Spec:** docs/superpowers/specs/2026-11-06-formulario-custos-design.md

## Global Constraints
- Nenhuma alteração em produção.
- Salvar o conjunto em uma transação; sem gravação parcial ao adicionar campos.
- Preservar campos vinculados a qualquer revisão e revalidar os vínculos no servidor.
- Exemplos publicados são sintéticos.

## Review Focus
- Adicionar campo enquanto há preços digitados conserva os valores e a versão original.
- Custo vinculado apenas a revisão arquivada também não pode ser removido.
- Nomes repetidos entre cartões não compartilham identidade de widget.
- Salvamento inválido ou recusado não perde o formulário digitado.
- Valores com vírgula e mais de duas casas mantêm precisão e propagação.

### Task 1: Formulário e proteção de vínculos
**Files:** pricing_catalog_ui.py, pricing_repository.py, tests/test_pricing_ui.py, tests/test_pricing_catalog.py.
**Interfaces:** manter render_catalog(actor,service=None,profiles_only=False), workspace_changes e publish_catalog. catalog() acrescenta usage_count aos custos e perfis.
- [ ] AppTest altera dois preços e perfil, adiciona campo, conserva os valores e salva uma única vez; sem grades de edição.
- [ ] AppTest custo vinculado mostra campo de preço editável e remoção desabilitada; custo livre permite remoção ao salvar.
- [ ] PostgreSQL conta vínculos atuais e históricos e confirma rejeição de exclusão no servidor.
- [ ] Executar RED, implementar e confirmar GREEN; commit.

### Task 2: Revisão e publicação em teste
- [ ] Executar suíte local e PostgreSQL de CI, revisão independente e regressões necessárias.
- [ ] PR com base teste, acompanhar deploy automático, conferir saúde e preservar produção.
- [ ] Informar o formulário entregue e registrar evidências.
