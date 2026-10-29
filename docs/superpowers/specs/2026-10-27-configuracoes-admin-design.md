# Configurações Administrativas — Design aprovado

## Intenção

Permitir que administradores alterem regras operacionais do diagnóstico sem novo deploy, mantendo os valores atuais como padrão e sem expor regras fiscais ou de auditoria que possam comprometer a segurança do processo.

## Escopo aprovado

- Criar a página administrativa `⚙️ Configurações`.
- Persistir no PostgreSQL/Neon, com usuário e data/hora da última alteração:
  - validade da revisão de preço em dias, padrão `90`;
  - tolerância da diferença de preço em reais, padrão `0,01`;
  - tolerância da diferença fiscal em reais, padrão `1,00`.
- Aplicar a validade configurada tanto no diagnóstico do pedido quanto no painel de preços desatualizados.
- Aplicar as tolerâncias configuradas nas decisões comercial e fiscal.
- Restringir consulta e alteração da página ao perfil `ADMIN`.
- Publicar primeiro na branch `teste` para homologação do usuário.

## Fora do escopo

- PIS e COFINS continuam protegidos no código.
- ICMS e IPI continuam sendo administrados por NCM em `Regras Fiscais`.
- As duas confirmações de reauditoria continuam obrigatórias.
- Nenhuma outra regra existente será alterada.

## Abordagens consideradas

1. **Somente prazo variável:** menor mudança, mas não atende à avaliação de outras regras úteis.
2. **Conjunto conservador persistido (escolhida):** prazo e duas tolerâncias, com defaults seguros e auditoria da alteração.
3. **Painel irrestrito:** incluir tributos e confirmações; rejeitada pelo risco de aprovação fiscal ou reauditoria indevida.

## Arquitetura

Uma tabela `configuracoes_sistema` guarda os três valores e seus metadados. Um módulo puro normaliza, valida e fornece defaults quando o banco ainda não tem dados. A aplicação carrega a configuração no início de cada execução autenticada e a injeta no parser e no painel de revisão, evitando consultas ao banco por item.

## Regras de segurança

- Valores ausentes ou inválidos retornam aos defaults sem interromper diagnósticos.
- Prazo permitido: 1 a 3650 dias.
- Tolerâncias permitidas: 0 a 1.000.000 de reais.
- Atualização dos três valores ocorre em uma única transação.
- O formulário informa os efeitos de cada campo antes de salvar.
