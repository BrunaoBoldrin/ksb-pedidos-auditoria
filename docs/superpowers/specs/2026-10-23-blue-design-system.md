# Design system azul Metais Glória — aprovado

Aprovação do usuário em 23/10/2026: implementar o design apresentado na branch teste. PR e integração para o deploy automático no Render também autorizados. Mockups: PDF Design-System-Pedidos, 20 pranchas v1.1, e apresentações https://chatgpt.com/space/page_13fe165c357081919c9dd81edaa72e51 e https://chatgpt.com/space/page_ce6e97f1b52c8191ae91a41eb4e1d5ea.

## Decisões

- Azul #0A4BB3, navegação #0B1B3D, fundo #F5F7FB, texto #1B293D. Verde apenas como indicação semântica de sucesso.
- Streamlit nativo com tema e CSS local, sem migração de framework e sem dependências externas de fonte. Nimbus Sans/Arial/sans-serif.
- Login com área de marca, navegação lateral, cabeçalhos consistentes, resumo do lote, linhas de item e diagnósticos fiscal/comercial separados.
- Filtro visual de resultados e acesso a detalhes preservam o lote em sessão. Alterar o filtro ou baixar exportações não reprocessa nem grava uma nova auditoria. Trocar arquivos ou sair da conta elimina a apresentação do resultado anterior.
- Cadastros, revisão de preços, regras fiscais, Log, usuários e manutenção recebem o mesmo tratamento visual. Formulários em colunas no desktop e uma coluna em mobile.
- Componentes personalizados escapam texto de PDFs, cadastros e usuários. Mensagens de diagnóstico completas, códigos textuais e campos técnicos permanecem disponíveis.
- Preservar integralmente parser.py, database.py, price_rules.py, audit_rules.py e order_workflow.py. Não mudar permissões, cálculos, tolerâncias, regra de três meses-calendário, confirmações, gravações ou exportações.
- Logs e revisão de preços apenas ADMIN. Não recriar Histórico de Auditorias.
- Acessibilidade: rótulos, foco visível, contraste de texto, alvos de toque 44 px, mensagens com texto e cor e movimento reduzido.

## Aceite

Suite existente verde e testes reais da UI com banco substituído apenas na fronteira externa. Navegação de todos os perfis, filtragem sem nova persistência, revisão vencida com preço igual, confirmações de reavaliação e exports preservados. Revisão independente antes de integrar em teste. Nunca integrar em main neste trabalho.
