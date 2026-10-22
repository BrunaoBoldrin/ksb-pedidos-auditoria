# Revisão de preços, reavaliação de pedidos e logs — Especificação

## Objetivo

Impedir que pedidos sejam considerados aprovados quando utilizarem preços sem revisão válida nos últimos três meses, oferecer aos administradores uma visão dos preços desatualizados e preservar o histórico de auditorias e alterações reais de preço.

## Escopo

A implementação será feita na branch `teste` do repositório `BrunaoBoldrin/ksb-pedidos-auditoria` e abrange:

1. validação da vigência do preço durante o diagnóstico comercial;
2. painel administrativo de revisão de preços;
3. confirmação obrigatória antes da reavaliação de pedido previamente aprovado;
4. persistência das auditorias de pedidos;
5. log administrativo de auditorias e mudanças de preço.

## Regra de vigência do preço

- A validade termina após três meses-calendário contados da data da última revisão.
- Na própria data-limite o preço ainda é válido; a partir do dia seguinte ele é desatualizado.
- Data ausente, vazia ou inválida torna o preço desatualizado.
- A verificação usa a data corrente do processamento.
- A regra vale mesmo quando o preço do pedido é igual ao preço cadastrado.

### Ordem do diagnóstico comercial

1. material não cadastrado;
2. preço não cadastrado;
3. preço desatualizado;
4. preço divergente;
5. preço válido e igual (`OK`).

Quando o preço estiver desatualizado:

- o status comercial será `PENDENTE - REVISÃO DE PREÇO`;
- o diagnóstico exibirá exatamente `PREÇO NECESSITA DE REVISÃO: ATUALIZE O VALOR DO ITEM.`;
- eventual diferença entre o preço do pedido e o cadastrado continuará disponível nos detalhes;
- o item não será comercialmente aprovado;
- consequentemente, o pedido não será considerado totalmente aprovado nem implantável.

## Painel administrativo “Revisão de Preços”

O menu será visível somente para usuários com perfil `ADMIN`.

A tela exibirá:

- card com o total de produtos desatualizados;
- lista ordenada das revisões mais antigas para as mais recentes;
- código e descrição do material;
- preço atualmente cadastrado;
- data da última revisão;
- usuário responsável pela última revisão;
- situação, incluindo `Sem data de revisão` para datas ausentes ou inválidas.

Materiais sem preço cadastrado permanecem tratados pelo fluxo existente de preço não cadastrado e não integram a contagem de preço vencido.

## Persistência das auditorias

Cada processamento confirmado cria um novo registro de auditoria, sem excluir execuções anteriores. O registro deve preservar:

- número do pedido;
- itens avaliados;
- resultado fiscal e comercial de cada item;
- resultado consolidado do pedido;
- data e hora;
- usuário responsável;
- indicação de primeira análise ou reavaliação;
- confirmações exigidas para a reavaliação.

Um pedido é considerado previamente aprovado quando existir uma auditoria em que todos os seus itens estejam simultaneamente com status fiscal `OK` e status comercial `OK`.

Uma reavaliação posterior pendente não apaga nem invalida o histórico da aprovação anterior. Por isso, novos reenvios do mesmo pedido continuam sujeitos à confirmação.

## Reenvio de pedido aprovado

Antes de executar a auditoria completa, o sistema lê o número do pedido do PDF e consulta o histórico.

Se o pedido já tiver sido totalmente aprovado, o processamento é interrompido e o usuário vê um aviso com duas confirmações obrigatórias:

1. `Estou ciente de que este pedido já foi auditado e desejo reavaliá-lo.`
2. `Confirmei se este pedido já foi emitido/implantado.`

O botão de reavaliação permanece bloqueado até que ambas sejam marcadas. As confirmações representam ciência e verificação pelo usuário; não alteram automaticamente o pedido para “implantado”.

Para envio de vários PDFs, o aviso identifica todos os números previamente aprovados. Após a confirmação, o lote é processado normalmente e cada auditoria é gravada separadamente.

## Histórico de alterações de preço

Será criada uma estrutura própria e imutável para registrar mudanças reais de preço. Cada evento preserva:

- código e descrição do material;
- preço anterior;
- preço novo;
- data e hora;
- usuário responsável;
- origem: `ALTERAÇÃO PELO SISTEMA` ou `IMPORTAÇÃO EXCEL`.

Regras:

- somente uma diferença real entre o preço anterior e o novo gera evento;
- salvar novamente o mesmo preço não gera evento, mesmo que a data de revisão seja renovada;
- o cadastro inicial de um material não é tratado como alteração e não gera evento;
- alterações realizadas pela importação de Excel geram evento com origem própria;
- o histórico permanece disponível mesmo que o material seja posteriormente excluído.

## Tela administrativa “Log”

O menu será visível somente para usuários com perfil `ADMIN` e terá duas guias.

### Auditorias de pedidos

- pedido;
- primeira análise ou reavaliação;
- status fiscal e comercial consolidados;
- usuário;
- data e hora;
- confirmações de reavaliação.

### Revisões de preços

- código e descrição do material;
- preço anterior e preço novo;
- usuário;
- data e hora;
- origem da alteração.

As duas guias terão filtros por pedido ou material, usuário e período.

## Banco de dados

As migrações serão idempotentes e executadas pela inicialização já existente. As tabelas atuais `pedidos`, `pedido_itens` e `auditorias` serão aproveitadas e receberão somente os campos necessários para usuário, tipo de execução, resultado consolidado e confirmações.

Uma nova tabela armazenará o histórico de alterações de preço sem dependência destrutiva do cadastro atual do material.

## Organização do código

- Regras puras de datas e consolidação serão separadas da interface Streamlit para permitir testes determinísticos.
- `parser.py` aplicará a vigência do preço no diagnóstico comercial.
- `database.py` concentrará migrações, consultas e gravações de auditoria e histórico de preço.
- `app.py` controlará as novas telas, filtros e o bloqueio de reavaliação.
- A leitura preliminar do número do pedido ficará no módulo de extração, sem executar ou exibir a auditoria completa antes das confirmações.

## Tratamento de falhas

- Se não for possível identificar o número do pedido, o sistema mantém o erro de extração e não grava uma auditoria incompleta.
- Se a gravação do histórico falhar, o sistema informa o erro e não apresenta o processamento como concluído.
- Datas inválidas de revisão não interrompem a análise; são tratadas como preço desatualizado.
- Uma única confirmação marcada não libera a reavaliação.

## Testes de aceitação

1. preço com exatamente três meses permanece válido;
2. preço com três meses e um dia fica pendente;
3. data vazia ou inválida fica pendente;
4. preço igual ao pedido, porém vencido, exibe a mensagem obrigatória e impede aprovação;
5. preço vigente e igual permanece `OK`;
6. painel de revisão lista apenas materiais com preço cadastrado e revisão vencida;
7. usuário não administrador não recebe acesso aos novos menus;
8. pedido totalmente aprovado é detectado no reenvio;
9. somente as duas confirmações juntas liberam a reavaliação;
10. primeira análise e reavaliação permanecem no histórico;
11. mudança manual real de preço gera log com origem correta;
12. mudança real por Excel gera log com origem correta;
13. salvamento sem alteração de preço não gera log;
14. cadastro inicial não gera log;
15. falha na persistência não resulta em mensagem falsa de conclusão.

## Fora do escopo

- marcar automaticamente o pedido como emitido ou implantado;
- integrar o sistema com ERP externo;
- alterar perfis ou permissões existentes além dos dois novos menus administrativos;
- apagar ou editar registros históricos.
