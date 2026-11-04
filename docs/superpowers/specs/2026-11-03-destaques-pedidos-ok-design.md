# Destaques dos pedidos aprovados — desenho

## Intenção

Facilitar a leitura operacional do diagnóstico após o processamento dos PDFs, mostrando primeiro os pedidos totalmente aprovados e destacando, em cada item, os dados necessários para implantação e entrega.

## Comportamento aprovado

- A área atual de resultados será agrupada por pedido, sem criar uma segunda lista duplicada.
- Um pedido será classificado como **OK** somente quando todos os seus itens tiverem status fiscal e comercial `OK`. Se qualquer item estiver pendente ou divergente, o pedido completo ficará no grupo **Pedidos com pendências**.
- Os pedidos OK serão exibidos primeiro; os pedidos com pendências virão depois. Dentro de cada pedido, os itens serão ordenados pelo número do item.
- Cada item exibirá em destaque:
  - descrição e código do material do pedido;
  - Código Glória escolhido pelo local de entrega: código interno de Jundiaí para pedidos de Jundiaí e código interno de Várzea para pedidos de Várzea;
  - preço unitário final com impostos, calculado pelo valor total da linha do pedido dividido pela quantidade;
  - lead time em dias, calculado entre a data atual do sistema e a data de entrega do item, com indicação clara para prazo futuro, entrega no dia ou prazo vencido.
- Os diagnósticos fiscal e comercial atuais permanecerão disponíveis no item, sem alteração das regras de validação.
- Os filtros existentes continuarão funcionando. Após o filtro, o resultado visível será agrupado e ordenado pela classificação do pedido completo no lote.

## Casos sem dados

- Unidade de entrega não reconhecida: exibir `Unidade não identificada` no Código Glória.
- Código interno vazio para a unidade reconhecida: exibir `Não cadastrado`.
- Quantidade zero ou valor inválido: exibir `Não disponível` no preço unitário final.
- Data de entrega inválida: exibir `Não disponível` no prazo.

## Limites

- A implementação será feita a partir da branch `teste` e enviada somente para `teste`.
- Não serão alteradas regras fiscais, comerciais, de revisão de preço, auditoria ou implantação de pedidos.
- Não serão alterados cadastros nem o banco de dados; os códigos internos já existentes serão apenas incluídos no resultado do parser.

## Abordagens consideradas

1. **Agrupar a área atual por pedido — escolhida.** Atende ao formato solicitado, evita repetição e preserva os detalhes atuais dentro de cada item.
2. Criar um resumo separado antes da auditoria. Preserva integralmente a tela atual, mas duplica cada item e aumenta a rolagem.
3. Manter a lista plana. É a menor mudança, porém não representa visualmente o agrupamento por pedido solicitado.
