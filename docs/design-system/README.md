# Interface azul Metais Glória

A interface aprovada mantém o Streamlit e usa a estrutura visual de referência do Emerald24: navegação lateral escura, superfícies claras, resumo do lote e diagnóstico por item. Azul principal `#0A4BB3`, azul profundo `#0B1B3D` e fundo `#F5F7FB`. Verde indica somente sucesso.

## Arquivos

- `assets/design-tokens.json` é a referência dos tokens aprovados.
- `assets/design-tokens.css` declara as variáveis e componentes base.
- `assets/design-system.css` adapta os componentes nativos do Streamlit e define as telas responsivas.
- `.streamlit/config.toml` define o tema nativo.
- `ui_components.py` produz HTML com dados escapados e calcula somente resumos/filtros de apresentação.

## Comportamento

O resumo considera aprovado somente o item com fiscal e comercial `OK`. Pendências de revisão de preço mantêm a mensagem completa. Os detalhes técnicos continuam nos expansores de cada item. As exportações sempre contêm o lote completo, independentemente do filtro visual.

Os resultados ficam na sessão autenticada para permitir filtros e downloads sem nova gravação de auditoria. A troca dos arquivos ou o logout elimina os resultados anteriores. O processamento continua usando o fluxo existente. Não há alteração de banco, cálculo, parser ou permissões.

Em telas até 767 px, os formulários e painéis passam para uma coluna. Tabelas continuam com rolagem horizontal. Os controles têm alvo mínimo de 44 px, rótulos nativos, foco visível e respeito à preferência de movimento reduzido.

## Verificação

```sh
python -m unittest discover -s tests -q
```

Os testes de interface usam `streamlit.testing.v1.AppTest`, executam as telas reais e isolam chamadas externas do banco. Cobrem navegação por perfil, filtros, invalidação da sessão, logout e as duas confirmações literais da reanálise. A suíte existente continua cobrindo regras fiscais, revisão de preço, fluxo e logs. Nenhuma credencial de produção é necessária.
