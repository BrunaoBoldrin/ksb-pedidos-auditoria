# Precificação por NCM e navegação

Escopo: ambiente teste e seu banco isolado. Não promover para produção.

Cada cálculo atual da folha busca o NCM do cadastro técnico e a regra fiscal ativa mais recente. ICMS e IPI vêm dessa regra; PIS/COFINS e a conversão de bruto para líquido seguem o contrato já usado pelo analisador. A carga usada na formação é `1 - divisor fiscal`, evitando uma segunda regra independente para o mesmo preço. IPI é mostrado separadamente, acrescido ao preço com ICMS e PIS/COFINS. Não se consultam serviços externos nem se presumem alíquotas para NCM ausente.

Remover a navegação e os campos de perfis. Eficiência, margem, comissão e arredondamento pertencem à folha. Perfis antigos permanecem apenas como registros históricos; não controlam os tributos dos cálculos atuais. Rascunhos podem mostrar preço calculado sem confirmação manual da base comercial. A publicação continua explícita e valida custos, unidades, permissões e versão. Snapshots históricos são imutáveis.

Destacar no início da folha custo unitário, preço final unitário sem IPI, líquido unitário KSB e total com IPI. Informar quando é uma prévia ainda não publicada. NCM ou regra ausente impedem o preço, com indicação do cadastro a corrigir. O cadastro técnico continua sem preço manual.

Usar botões nativos para navegação e filtros. Reduzir consultas repetidas de permissão, agrupar leitura dos custos, reutilizar conexões com isolamento entre transações e evitar gerar novamente o mesmo Excel. Não usar cache de autorização nem reutilizar preços vencidos para análise comercial.

Validação: testes financeiros com Decimal, NCM ausente/inválido, regras alteradas, histórico, publicação concorrente e propagação de custos; AppTest para navegação, prévia visível e edição; PostgreSQL em CI. Dados reais e credenciais nunca entram no repositório público.
