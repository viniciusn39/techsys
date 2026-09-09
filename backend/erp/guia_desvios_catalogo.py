"""Verbetes de tratamento de desvio para o restante do catálogo do ERP.

Complementa erp/guia_desvios.py (que traz os indicadores mais usados). Cada
verbete: impacto do desvio, causas mais comuns e por onde começar a agir.
"""


def _v(impacto, causas, dicas):
    return {"impacto": impacto, "causas": causas, "dicas": dicas}


GUIA_CATALOGO = {
    # ------------------------------------------------------------------ Vendas
    "qtd_notas": _v(
        "Menos notas com o mesmo faturamento significa menos clientes atendidos ou pedidos maiores e mais raros; menos notas com faturamento menor é queda de demanda.",
        ["Positivação caiu", "Pedidos não faturados (bloqueio, corte)", "Cliente comprando com menos frequência"],
        ["Cruze com Positivação e Frequência de compra.", "Confira a Carteira de pedidos e a Conversão pedido → nota.", "Cheque se houve dia sem faturamento (feriado, parada do sistema)."]),
    "qtd_pedidos": _v(
        "Pedido digitado é o primeiro sinal da venda: menos pedidos hoje é menos faturamento amanhã.",
        ["RCAs sem visita ou sem rota", "Força de vendas com pedidos não integrados", "Cliente sem crédito"],
        ["Abra por RCA e compare com o mês anterior.", "Verifique Pedidos do força de vendas aguardando integração.", "Cheque Clientes sem crédito disponível."]),
    "pedido_medio": _v(
        "Pedido menor encarece a venda e a entrega por real vendido.",
        ["Mix pobre", "Pedidos fracionados", "Desconto ou bonificação alta"],
        ["Compare com Itens por nota e Mix por cliente.", "Reveja o pedido mínimo e as faixas de bonificação.", "Sugira mix no força de vendas."]),
    "pedidos_cancelados_pct": _v(
        "Pedido cancelado é custo de venda pago sem receita e, muitas vezes, cliente insatisfeito.",
        ["Prazo de entrega longo", "Falta de estoque", "Erro na digitação ou no preço"],
        ["Classifique os cancelamentos por motivo.", "Cruze com Tempo médio em fila de bloqueio e Corte.", "Ajuste a disponibilidade de estoque no força de vendas."]),
    "rcas_ativos": _v(
        "Menos vendedores vendendo é capacidade comercial parada e carteira descoberta.",
        ["Afastamentos e desligamentos", "RCAs sem carteira ou sem rota", "Cadastro de RCA inativo sem baixa"],
        ["Liste os RCAs ativos sem venda no mês.", "Redistribua carteiras órfãs.", "Confira o cadastro de RCAs no ERP."]),
    "venda_media_por_rca": _v(
        "Produtividade menor por vendedor significa que o custo comercial cresce mais que a venda.",
        ["Carteira mal dimensionada", "RCAs novos em curva de aprendizado", "Ruptura ou bloqueio derrubando a venda de todos"],
        ["Ordene os RCAs por venda e compare com a meta individual.", "Veja se a queda é geral (ruptura, crédito) ou de poucos RCAs.", "Ajuste carteira e rota dos RCAs abaixo da média."]),
    "clientes_por_rca": _v(
        "Vendedor cobrindo menos clientes deixa carteira sem visita e abre espaço para o concorrente.",
        ["Roteiro não cumprido", "Carteira grande demais", "Clientes bloqueados"],
        ["Compare positivação por RCA com o tamanho da carteira.", "Cobre o cumprimento do roteiro no força de vendas.", "Cheque bloqueios de crédito na carteira."]),
    "notas_por_cliente": _v(
        "Cliente comprando menos vezes no mês está comprando do concorrente ou reduzindo o negócio.",
        ["Visita menos frequente", "Ruptura na hora da compra", "Prazo de entrega longo"],
        ["Compare a frequência por segmento de cliente.", "Cruze com Ruptura e Entregas com ocorrência.", "Ajuste o roteiro dos clientes de maior potencial."]),
    "itens_por_nota": _v(
        "Menos itens por nota é mix pobre: a mesma entrega poderia carregar mais margem.",
        ["RCA vendendo poucos itens", "Ruptura de itens secundários", "Catálogo sem novidade"],
        ["Defina mix mínimo por segmento no força de vendas.", "Confira Ruptura dos itens de curva B e C.", "Crie campanha de mix com bonificação condicionada."]),
    "concentracao_top10_clientes_pct": _v(
        "Depender de poucos clientes expõe a empresa: perder um deles derruba o mês.",
        ["Base pequena de clientes médios", "Prospecção parada", "Grandes contas crescendo mais que a base"],
        ["Defina meta de venda para clientes fora do top 10.", "Cruze com Novos clientes e Cobertura da base.", "Monte plano de relacionamento para as 10 maiores contas (não perder) e de crescimento para as demais."]),
    "concentracao_top_rca_pct": _v(
        "Depender de um vendedor é risco: se ele sai, leva a carteira.",
        ["Carteira desbalanceada", "Regiões sem cobertura", "RCAs novos com pouca carteira"],
        ["Redistribua carteira com critério de potencial.", "Compare a venda por RCA com o tamanho da carteira.", "Documente os clientes-chave no CRM ou no ERP."]),
    "crescimento_faturamento_yoy_pct": _v(
        "Crescer menos que o planejado (ou cair) frente ao ano anterior indica perda de mercado ou de preço.",
        ["Queda de volume", "Preço abaixo do ano anterior", "Perda de clientes grandes"],
        ["Separe efeito preço (Preço médio por kg) de efeito volume (Peso vendido).", "Compare positivação com o mesmo mês do ano anterior.", "Veja o crescimento por filial."]),
    "venda_perdida_corte": _v(
        "Cada unidade cortada é venda feita que não foi entregue: receita perdida e cliente frustrado.",
        ["Estoque disponível errado", "Compra atrasada", "Reserva de pedidos sem baixa"],
        ["Liste os 20 itens mais cortados.", "Cruze com Itens abaixo do mínimo e Pedidos de compra atrasados.", "Faça inventário rotativo dos itens cortados."]),
    "preco_medio_item": _v(
        "Preço médio caindo com o mesmo mix é desconto ou concorrência; com mix diferente, é deslocamento para itens baratos.",
        ["Desconto acima do padrão", "Mix mais barato", "Reajuste de tabela não aplicado"],
        ["Compare com Desconto médio e Mix de produtos.", "Confira se a tabela de preço foi reajustada após o aumento de custo.", "Reveja alçadas de desconto."]),
    "peso_vendido_ton": _v(
        "Volume abaixo da meta é demanda perdida ou capacidade comercial ociosa; afeta a diluição de frete e armazém.",
        ["Positivação caiu", "Ruptura dos itens de maior volume", "Perda de clientes grandes"],
        ["Abra o peso por filial e por RCA.", "Cruze com Ruptura e Venda perdida.", "Compare com Faturamento: se o valor subiu e o peso caiu, foi efeito preço."]),
    "preco_medio_kg": _v(
        "Preço por quilo abaixo da meta é margem perdida em cada tonelada vendida.",
        ["Desconto alto", "Mix deslocado para cortes baratos", "Custo subiu e o preço não acompanhou"],
        ["Compare com Custo médio por kg para ver a margem por quilo.", "Confira Desconto médio por RCA.", "Reajuste a tabela dos itens cujo custo subiu."]),
    "pdv_cupons": _v(
        "Menos cupons no PDV é menos fluxo na loja.",
        ["Movimento da loja caiu", "PDV fora do ar", "Redução Z não transmitida"],
        ["Compare cupons por dia e por loja.", "Confira se todas as reduções Z estão no ERP.", "Avalie promoções e horário de funcionamento."]),
    "pdv_ticket_medio": _v(
        "Ticket menor na loja é cesta menor por cliente.",
        ["Mix da loja", "Preço promocional", "Ruptura na gôndola"],
        ["Compare o ticket por loja.", "Confira Ruptura das lojas.", "Crie combos e ofertas de cesta."]),
    "fila_bloqueio_valor": _v(
        "Venda parada no bloqueio é caixa e cliente esperando; parte dela vira cancelamento.",
        ["Análise de crédito lenta", "Limites desatualizados", "Alçada de desconto pendente"],
        ["Libere ou recuse hoje os bloqueios com mais de 24 h.", "Reveja limites dos clientes que mais entram em bloqueio.", "Meça o Tempo médio em fila de bloqueio."]),
    "tempo_fila_bloqueio_horas": _v(
        "Cada hora em bloqueio atrasa a entrega e aumenta o cancelamento.",
        ["Um único aprovador", "Análise manual sem regra", "Bloqueios comerciais sem dono"],
        ["Defina alçada e prazo máximo por tipo de bloqueio.", "Automatize a liberação para clientes com histórico bom.", "Acompanhe a fila duas vezes por dia."]),
    "pedidos_fv_pendentes": _v(
        "Pedido não integrado é venda invisível: não fatura, não separa, não entrega.",
        ["Falha de sincronização do força de vendas", "Pedido com erro de cadastro", "RCA sem conexão"],
        ["Liste os pedidos pendentes por RCA e motivo.", "Corrija cadastros que travam a importação.", "Alerte os RCAs com pendência há mais de 1 dia."]),
    "rcas_flex_negativo": _v(
        "RCA com flex negativo vendeu com desconto além do saldo: margem consumida sem cobertura.",
        ["Desconto acima da política", "Flex sem reposição", "Pedidos com preço abaixo da tabela"],
        ["Liste os RCAs negativos e os pedidos que consumiram o flex.", "Bloqueie desconto para RCA com saldo negativo.", "Reveja a política de flex."]),
    # ---------------------------------------------------------------- Clientes
    "creditos_cliente_aberto": _v(
        "Crédito de devolução parado é dinheiro do cliente sem uso, que vira reclamação ou baixa contábil.",
        ["Devoluções sem abatimento na próxima compra", "RCA não usa o crédito no pedido", "Créditos antigos sem baixa"],
        ["Liste os créditos por cliente e idade.", "Oriente o RCA a abater no próximo pedido.", "Baixe os créditos prescritos conforme a política."]),
    "cashback_a_expirar": _v(
        "Cashback expirando sem uso é benefício que não gerou recompra.",
        ["Cliente não sabe do saldo", "Validade curta", "Regra de uso restritiva"],
        ["Avise os clientes com saldo a expirar.", "Oriente o RCA a oferecer o uso no pedido.", "Reveja a validade do programa."]),
    "credito_autorizado": _v(
        "Crédito liberado por autorização acima do normal é limite sendo furado caso a caso.",
        ["Limites desatualizados", "Pressão comercial", "Aprovador sem critério"],
        ["Liste as autorizações por aprovador e cliente.", "Atualize os limites dos clientes recorrentes.", "Defina critério e alçada para autorização."]),
    "base_clientes": _v(
        "Base menor é menos oportunidade de venda todo mês.",
        ["Bloqueios em massa", "Exclusão de cadastros", "Prospecção parada"],
        ["Cruze com Clientes bloqueados e Clientes cadastrados no mês.", "Defina meta de cadastros por RCA.", "Reative clientes inativos."]),
    "clientes_bloqueados_pct": _v(
        "Cliente bloqueado não compra: parte da base está fora da venda.",
        ["Inadimplência", "Bloqueio comercial sem revisão", "Cadastro incompleto"],
        ["Liste os bloqueados por motivo.", "Negocie os bloqueados por atraso pequeno.", "Reveja bloqueios comerciais antigos."]),
    "clientes_inativos_90_pct": _v(
        "Base inativa alta indica que a empresa está perdendo clientes mais rápido do que os repõe.",
        ["Falta de visita", "Ruptura recorrente", "Preço fora do mercado"],
        ["Segmente os inativos por potencial e último RCA.", "Crie ação de reativação com oferta.", "Cruze com Churn e Entregas com ocorrência."]),
    "clientes_cadastrados": _v(
        "Sem cadastro novo, o crescimento depende só de quem já compra.",
        ["Prospecção sem meta", "Cadastro trava no crédito", "Área sem cobertura"],
        ["Defina meta semanal de cadastro por RCA.", "Reduza o tempo de aprovação do cadastro.", "Mapeie praças sem cliente."]),
    "positivacao_pct_base": _v(
        "Cobertura baixa é carteira sem visita: clientes que existem e não estão comprando.",
        ["Roteiro não cumprido", "Carteira grande para o RCA", "Clientes sem crédito"],
        ["Cobre o roteiro por RCA.", "Redistribua carteiras acima da capacidade.", "Cheque Clientes sem crédito disponível."]),
    "recompra_pct": _v(
        "Recompra baixa significa que a venda depende de cliente novo, que custa mais caro.",
        ["Experiência ruim na primeira compra", "Ruptura", "Sem acompanhamento pós-venda"],
        ["Ligue para os clientes que compraram uma vez e não voltaram.", "Cruze com Entregas com ocorrência.", "Crie régua de recompra em 30 dias."]),
    # -------------------------------------------------------------- Financeiro
    "despesas_pagas": _v(
        "Pagar mais que o previsto aperta o caixa do mês.",
        ["Despesas antecipadas", "Compras concentradas", "Títulos vencidos acumulados"],
        ["Abra os pagamentos por fornecedor e conta.", "Compare com Compras (entradas) e Despesas por competência.", "Reprograme pagamentos não urgentes."]),
    "a_receber_aberto": _v(
        "Carteira a receber alta é capital de giro financiado pela empresa.",
        ["Prazo de venda alongado", "Inadimplência", "Faturamento concentrado no fim do mês"],
        ["Separe a vencer de vencido.", "Reveja prazo médio concedido por RCA.", "Priorize cobrança dos maiores títulos."]),
    "a_pagar_aberto": _v(
        "Contas a pagar acima do previsto pressionam o caixa dos próximos dias.",
        ["Compras acima do plano", "Prazo curto com fornecedor", "Despesas não orçadas"],
        ["Monte o fluxo dos próximos 30 dias.", "Negocie prazo com os maiores fornecedores.", "Cruze com Compras sobre faturamento."]),
    "a_pagar_vencido": _v(
        "Fornecedor vencido gera juros, corte de crédito e falta de produto.",
        ["Caixa curto", "Título sem aprovação", "Boleto não recebido"],
        ["Liste os vencidos por fornecedor e negocie hoje.", "Confira Títulos a pagar sem dupla autorização.", "Priorize fornecedores críticos para o estoque."]),
    "lucro_bruto": _v(
        "Lucro bruto abaixo da meta é margem ou volume faltando; é o que paga as despesas.",
        ["Venda menor", "Margem menor (desconto, custo)", "Mix de baixa margem"],
        ["Separe efeito volume (Faturamento) de efeito margem (Margem bruta).", "Abra por filial e por grupo de produto.", "Reveja desconto e custo dos itens principais."]),
    "markup_pct": _v(
        "Markup menor é preço não acompanhando o custo.",
        ["Custo de compra subiu", "Desconto alto", "Tabela desatualizada"],
        ["Liste os itens com markup abaixo do mínimo.", "Reajuste tabela após aumento de custo.", "Reveja alçadas de desconto."]),
    "custo_medio_kg": _v(
        "Custo por quilo subindo sem repasse come a margem de cada venda.",
        ["Fornecedor reajustou", "Compra fora da negociação", "Frete de compra alto"],
        ["Compare com Preço médio por kg.", "Renegocie os 5 maiores fornecedores.", "Confira Frete sobre compras."]),
    "clientes_com_titulo_vencido": _v(
        "Muitos clientes em atraso indicam problema de crédito ou de cobrança, não caso isolado.",
        ["Régua de cobrança fraca", "Crédito concedido sem análise", "Prazo longo"],
        ["Abra por faixa de atraso e RCA.", "Ative a régua D+3/D+10/D+30.", "Bloqueie novas vendas acima de X dias de atraso."]),
    "clientes_com_titulo_vencido_pct": _v(
        "Parcela alta da base em atraso contamina a venda: cada novo pedido vira risco.",
        ["Cobrança tardia", "Limites altos", "Clientes em dificuldade"],
        ["Priorize os clientes com maior valor vencido.", "Reveja limites dos recorrentes.", "Acompanhe semanalmente."]),
    "taxa_cartao_pct": _v(
        "Taxa de cartão acima do negociado sai direto da margem das vendas no cartão.",
        ["Adquirente com taxa alta", "Parcelamento longo", "Bandeiras caras"],
        ["Compare as taxas por adquirente e bandeira.", "Renegocie ou troque de adquirente.", "Limite o parcelamento sem juros."]),
    "titulos_prorrogados": _v(
        "Prorrogar título esconde a inadimplência e alonga o prazo sem custo para o cliente.",
        ["Prorrogação sem critério", "Pressão comercial", "Cliente em dificuldade"],
        ["Liste as prorrogações por aprovador e cliente.", "Defina alçada e limite de prorrogações por cliente.", "Cobre juros na prorrogação."]),
    "desconto_na_baixa": _v(
        "Desconto na baixa é receita já faturada sendo devolvida.",
        ["Acordos de cobrança generosos", "Desconto por antecipação sem regra", "Erro de faturamento corrigido na baixa"],
        ["Liste os descontos por motivo e aprovador.", "Defina alçada para desconto na baixa.", "Corrija na origem os erros de faturamento."]),
    "pagar_sem_dupla_autorizacao": _v(
        "Pagamento sem dupla autorização é risco de fraude e de erro.",
        ["Processo de aprovação não seguido", "Aprovador ausente", "Títulos lançados direto"],
        ["Liste os títulos sem as duas aprovações.", "Bloqueie o pagamento sem dupla autorização no ERP.", "Defina substitutos para os aprovadores."]),
    "adiantamentos_fornecedor_aberto": _v(
        "Adiantamento sem nota é dinheiro fora da empresa sem produto.",
        ["Fornecedor atrasou a entrega", "Nota recebida sem abater o adiantamento", "Adiantamentos antigos"],
        ["Liste os adiantamentos por fornecedor e idade.", "Cobre entrega ou devolução dos antigos.", "Abata o adiantamento na entrada da nota."]),
    "a_receber_vencido_60_pct": _v(
        "Carteira com mais de 60 dias tem baixa chance de recuperação sem ação jurídica.",
        ["Cobrança tardia", "Clientes em dificuldade", "Sem protesto ou negativação"],
        ["Liste os títulos por cliente e valor.", "Negocie acordo ou proteste.", "Bloqueie a venda para esses clientes."]),
    "titulos_pagos_no_prazo_pct": _v(
        "Pagar fora do prazo custa juros e crédito com fornecedor.",
        ["Caixa curto", "Aprovação atrasada", "Boleto não localizado"],
        ["Liste os títulos pagos com atraso e o motivo.", "Antecipe a aprovação dos títulos da semana.", "Monte o fluxo de caixa semanal."]),
    "atraso_medio_recebimento_dias": _v(
        "Cada dia de atraso é capital de giro financiado pela empresa.",
        ["Régua de cobrança fraca", "Clientes acostumados a atrasar", "Prazo mal negociado"],
        ["Ative cobrança em D+1.", "Cobre juros e multa de quem atrasa.", "Reveja prazo dos clientes que sempre atrasam."]),
    "multa_juros_recebidos": _v(
        "Não cobrar multa e juros incentiva o atraso.",
        ["Juros abonados na baixa", "Cobrança sem regra", "Sistema não calcula"],
        ["Verifique se o ERP está aplicando juros na baixa.", "Defina alçada para abono.", "Acompanhe o abono por operador."]),
    "prazo_medio_pagamento": _v(
        "Pagar mais rápido que recebe consome caixa.",
        ["Prazo curto com fornecedor", "Pagamento antecipado", "Compra à vista"],
        ["Compare com Prazo médio de recebimento.", "Negocie prazo com os maiores fornecedores.", "Evite antecipar sem desconto."]),
    "a_pagar_vencido_pct": _v(
        "Parcela alta de vencidos indica caixa insuficiente ou processo de pagamento falho.",
        ["Caixa curto", "Aprovação atrasada", "Títulos em disputa"],
        ["Separe vencidos por motivo.", "Negocie os maiores hoje.", "Monte o fluxo dos próximos 30 dias."]),
    "a_pagar_proximos_30_dias": _v(
        "Volume alto a pagar nos próximos 30 dias exige caixa ou negociação antecipada.",
        ["Compras concentradas", "Vencimentos concentrados", "Despesas não orçadas"],
        ["Compare com A receber nos próximos 30 dias.", "Negocie prazo antes do vencimento.", "Reprograme compras."]),
    "a_receber_proximos_30_dias": _v(
        "Pouco a receber nos próximos 30 dias é caixa fraco à frente.",
        ["Faturamento menor", "Prazo de venda longo", "Concentração de vencimentos depois"],
        ["Compare com A pagar nos próximos 30 dias.", "Acelere o faturamento da carteira de pedidos.", "Ofereça desconto para antecipação."]),
    "liquidez_cr_cp": _v(
        "Liquidez abaixo de 1 significa que o que há a receber não cobre o que há a pagar.",
        ["Compras acima da venda", "Inadimplência", "Prazo de pagamento curto"],
        ["Reveja compras e prazo de fornecedores.", "Acelere a cobrança do vencido.", "Monte o fluxo de caixa semanal."]),
    "dso_dias": _v(
        "DSO alto é venda demorando a virar caixa.",
        ["Prazo de venda longo", "Atraso nos recebimentos", "Faturamento concentrado no fim do mês"],
        ["Compare prazo concedido com atraso médio.", "Limite o prazo por faixa de cliente.", "Ative a régua de cobrança."]),
    "despesas_pct_faturamento": _v(
        "Despesa pesando mais no faturamento é resultado encolhendo mesmo com venda estável.",
        ["Venda caiu e a despesa ficou", "Frete e folha subiram", "Despesas não orçadas"],
        ["Abra por conta e centro de custo.", "Cruze com Frete e Folha sobre faturamento.", "Estabeleça alçada para despesa fora do orçamento."]),
    "resultado_operacional": _v(
        "Resultado operacional abaixo da meta é o lucro da empresa em risco.",
        ["Margem bruta menor", "Despesas acima do orçado", "Venda menor"],
        ["Separe efeito margem, volume e despesa.", "Abra por filial.", "Priorize a maior alavanca (desconto, frete ou folha)."]),
    "resultado_operacional_pct": _v(
        "Margem operacional menor é menos resultado por real vendido.",
        ["Margem bruta caiu", "Despesas subiram", "Mix de baixa margem"],
        ["Compare Margem bruta e Despesas sobre faturamento.", "Abra por filial e grupo de produto.", "Aja na maior alavanca."]),
    "entradas_caixa": _v(
        "Entradas menores que o previsto apertam o caixa.",
        ["Recebimento abaixo do esperado", "Inadimplência", "Faturamento menor"],
        ["Cruze com Recebimentos e A receber vencido.", "Acelere a cobrança.", "Reprograme pagamentos."]),
    "saidas_caixa": _v(
        "Saídas acima do previsto consomem o caixa.",
        ["Compras concentradas", "Despesas fora do orçado", "Antecipação de pagamentos"],
        ["Abra as saídas por conta e fornecedor.", "Compare com Pagamentos e Compras.", "Segure pagamentos não urgentes."]),
    "posicao_liquida_financeira": _v(
        "Posição líquida em queda é a empresa consumindo caixa ou acumulando dívida.",
        ["Geração de caixa negativa", "Estoque alto", "Inadimplência"],
        ["Cruze com Geração de caixa e Capital parado.", "Reduza estoque em excesso.", "Acelere a cobrança."]),
    # ----------------------------------------------------------------- Estoque
    "estoque_financeiro_foto": _v(
        "Estoque acima do necessário é caixa parado.",
        ["Compra em volume", "Venda caiu", "Itens sem giro"],
        ["Veja Capital parado e Itens sem giro.", "Suspenda compra dos itens com cobertura alta.", "Queime itens sem giro."]),
    "capital_parado": _v(
        "Capital parado é caixa em produto que não vende: custa juros, espaço e risco de perda.",
        ["Compra sem giro", "Itens descontinuados", "Estoque mínimo desatualizado"],
        ["Liste os itens sem venda por valor a custo.", "Crie ação de queima para os 20 maiores.", "Zere o estoque mínimo dos descontinuados."]),
    "capital_parado_pct": _v(
        "Parcela alta do estoque sem giro é caixa preso e risco de perda.",
        ["Compra desalinhada da venda", "Itens sazonais fora de época", "Descontinuados em estoque"],
        ["Liste os itens sem giro por valor.", "Suspenda compras desses itens.", "Negocie devolução com o fornecedor."]),
    "itens_sem_giro_pct": _v(
        "Muitos itens sem giro ocupam espaço e capital sem gerar venda.",
        ["Catálogo grande demais", "Itens sem argumento de venda", "Estoque mínimo em item parado"],
        ["Liste os itens sem giro há mais de 60 dias.", "Decida: promover, devolver ou descontinuar.", "Reveja o estoque mínimo."]),
    "excesso_estoque": _v(
        "Estoque acima do máximo é compra além da necessidade: caixa parado.",
        ["Compra em lote por preço", "Estoque máximo desatualizado", "Venda projetada acima do real"],
        ["Liste os itens acima do máximo por valor.", "Suspenda reposição desses itens.", "Reveja o máximo por curva ABC."]),
    "abaixo_minimo_pct": _v(
        "Itens abaixo do mínimo são rupturas prestes a acontecer.",
        ["Compra atrasada", "Pico de venda", "Mínimo desatualizado"],
        ["Liste os itens abaixo do mínimo de curva A.", "Cruze com Pedidos de compra atrasados.", "Revise o mínimo dos itens que oscilam."]),
    "skus_com_estoque": _v(
        "Menos SKUs com estoque é mix indisponível para a venda.",
        ["Compra concentrada", "Ruptura", "Itens descontinuados"],
        ["Liste os itens ativos zerados com giro.", "Cruze com Ruptura.", "Ajuste o mínimo dos itens de curva B."]),
    "estoque_bloqueado": _v(
        "Estoque bloqueado é produto que custou e não pode ser vendido.",
        ["Avaria", "Quarentena sem análise", "Bloqueio sem baixa"],
        ["Liste o bloqueado por motivo e idade.", "Decida destino (devolver, baixar, liberar).", "Cruze com Devoluções e Erros de conferência."]),
    # ----------------------------------------------------------------- Compras
    "qtd_notas_entrada": _v(
        "Menos notas de entrada pode indicar compra travada ou fornecedor atrasado.",
        ["Compra reduzida", "Fornecedor atrasado", "Notas não lançadas"],
        ["Confira Pedidos de compra atrasados.", "Cheque notas recebidas e não lançadas.", "Alinhe a programação de compras."]),
    "fornecedores_ativos": _v(
        "Menos fornecedores ativos concentra risco de abastecimento.",
        ["Compra concentrada", "Fornecedores inativos", "Redução de mix"],
        ["Cruze com Concentração nos 5 maiores fornecedores.", "Homologue fornecedor alternativo para itens críticos.", "Reveja o mix comprado."]),
    "compra_media_por_nota": _v(
        "Nota de compra pequena encarece o frete e o recebimento.",
        ["Compras fracionadas", "Lote mínimo baixo", "Compras de urgência"],
        ["Consolide pedidos de compra por fornecedor.", "Cruze com Frete sobre compras.", "Planeje compras semanalmente."]),
    "compras_pct_faturamento": _v(
        "Comprar mais do que vende infla o estoque e consome caixa.",
        ["Venda caiu e a compra não", "Compra antecipada", "Estoque de segurança alto"],
        ["Compare com Cobertura de estoque.", "Suspenda compra dos itens com cobertura alta.", "Alinhe compras e comercial semanalmente."]),
    "concentracao_top5_fornecedores_pct": _v(
        "Depender de poucos fornecedores é risco de preço e de abastecimento.",
        ["Poucos fornecedores homologados", "Contratos de exclusividade", "Mix concentrado"],
        ["Homologue alternativa para os itens críticos.", "Negocie condição com os 5 maiores.", "Acompanhe o prazo de entrega deles."]),
    "frete_compras_pct": _v(
        "Frete alto na compra encarece o custo do produto.",
        ["Compras fracionadas", "Fornecedor distante", "Frete FOB sem negociação"],
        ["Consolide pedidos.", "Negocie CIF com os maiores fornecedores.", "Compare custo total (produto + frete) por fornecedor."]),
    "itens_sem_inventario_pct": _v(
        "Item sem inventário há muito tempo é saldo em que ninguém confia: gera corte e ruptura fantasma.",
        ["Inventário rotativo parado", "Equipe sem tempo", "Itens de baixo giro esquecidos"],
        ["Monte o calendário de inventário rotativo por curva ABC.", "Comece pelos itens com corte recente.", "Registre a contagem no ERP para zerar o prazo."]),
    "pedidos_compra_atrasados": _v(
        "Compra atrasada vira ruptura e venda perdida.",
        ["Fornecedor sem capacidade", "Pedido sem acompanhamento", "Pagamento pendente travando a entrega"],
        ["Liste os pedidos atrasados por fornecedor.", "Cobre previsão nova e acione alternativa.", "Cruze com Ruptura e Itens abaixo do mínimo."]),
    "verba_fornecedor_aberta": _v(
        "Verba não recebida é margem negociada que não entrou.",
        ["Verba sem cobrança", "Fornecedor contestando", "Apuração não enviada"],
        ["Liste as verbas por fornecedor e idade.", "Envie a apuração e cobre.", "Abata em nota quando permitido."]),
    # --------------------------------------------------------------- Logística
    "pedidos_faturados_no_dia_pct": _v(
        "Pedido que não fatura no dia atrasa a entrega e aumenta o cancelamento.",
        ["Corte de horário cedo", "Bloqueio de crédito", "Capacidade de separação"],
        ["Meça o tempo entre digitação e faturamento por etapa.", "Cruze com Tempo em fila de bloqueio e OS pendentes.", "Reveja o horário de corte."]),
    "ciclo_carga_horas": _v(
        "Ciclo longo da carga atrasa a saída do caminhão e a entrega.",
        ["Separação lenta", "Conferência gargalo", "Cargas montadas cedo demais"],
        ["Meça separação e conferência separadamente (Tempo médio de separação e de conferência).", "Balanceie a equipe entre as etapas.", "Monte a carga mais perto da saída."]),
    "cargas_alem_prazo_rota": _v(
        "Carga além do prazo é entrega atrasada e veículo indisponível.",
        ["Rota mal dimensionada", "Ocorrências na entrega", "Veículo quebrado"],
        ["Liste as cargas atrasadas por rota e motorista.", "Cruze com Entregas com ocorrência.", "Reveja o prazo previsto das rotas."]),
    "valor_medio_por_carga": _v(
        "Carga com pouco valor encarece o frete por real entregue.",
        ["Carga mal consolidada", "Pedidos pequenos", "Rotas de baixa densidade"],
        ["Cruze com Ocupação do veículo e Entregas por carga.", "Consolide entregas por rota e dia.", "Reveja pedido mínimo das rotas caras."]),
    "peso_medio_por_carga_kg": _v(
        "Caminhão saindo leve é frete pago por espaço vazio.",
        ["Roteirização fraca", "Frota grande para a demanda", "Pedidos pequenos"],
        ["Cruze com Ocupação do veículo (peso).", "Consolide rotas.", "Ajuste o tipo de veículo à rota."]),
    "tempo_medio_rota_dias": _v(
        "Rota longa demais é veículo e motorista presos e entrega atrasada.",
        ["Rota mal desenhada", "Muitas cidades por carga", "Ocorrências"],
        ["Cruze com Cidades por carga e Ocorrências.", "Reveja as rotas mais longas.", "Use o roteirizador."]),
    "cargas_em_rota": _v(
        "Muitas cargas em rota ao mesmo tempo pode indicar acerto atrasado ou rotas longas.",
        ["Acerto de carga não feito", "Rotas longas", "Retorno não registrado"],
        ["Confira cargas sem retorno há mais de X dias.", "Cobre o acerto no retorno.", "Cruze com Tempo médio em rota."]),
    "cargas_canceladas_pct": _v(
        "Carga cancelada é separação e montagem perdidas.",
        ["Pedidos cancelados após montagem", "Veículo indisponível", "Erro de montagem"],
        ["Liste os cancelamentos por motivo.", "Confirme pedidos antes de montar a carga.", "Reveja a disponibilidade da frota."]),
    "custo_frete_por_kg": _v(
        "Frete por quilo alto come a margem de produtos de baixo valor.",
        ["Carga leve", "Rotas longas", "Combustível e manutenção"],
        ["Cruze com Ocupação e Km por carga.", "Consolide rotas.", "Compare frota própria e terceiro por rota."]),
    "custo_frete_por_nota": _v(
        "Frete por nota alto indica entregas pequenas ou distantes.",
        ["Pedidos pequenos", "Rotas de baixa densidade", "Reentregas"],
        ["Cruze com Entregas por carga e Ocorrências.", "Reveja pedido mínimo por praça.", "Consolide entregas por dia."]),
    "entregas_por_carga": _v(
        "Poucas entregas por carga é caminhão rodando com pouca densidade.",
        ["Roteirização fraca", "Pedidos grandes e poucos", "Rotas dispersas"],
        ["Cruze com Ocupação e Km por entrega.", "Agrupe entregas por região e dia.", "Use o roteirizador."]),
    "cidades_por_carga_erp": _v(
        "Muitas praças por carga é rota dispersa: mais km e mais tempo.",
        ["Rotas mal desenhadas", "Atender toda praça todo dia", "Pedidos dispersos"],
        ["Defina dias fixos por praça.", "Consolide pedidos por região.", "Use o roteirizador."]),
    "km_por_carga": _v(
        "Km alto por carga é custo de combustível e tempo de motorista.",
        ["Rotas longas", "Praças dispersas", "Desvio de rota"],
        ["Cruze com Cidades por carga.", "Compare km real com km previsto.", "Reveja as rotas mais longas."]),
    "km_por_entrega": _v(
        "Km por entrega alto é baixa densidade: cada cliente custa mais para atender.",
        ["Entregas dispersas", "Poucas entregas por carga", "Rotas longas"],
        ["Agrupe entregas por região.", "Reveja pedido mínimo das praças distantes.", "Use o roteirizador."]),
    "cargas_sem_km_pct": _v(
        "Sem odômetro não há controle de custo de frete nem de desvio de rota.",
        ["Motorista não informa", "Acerto sem exigência", "Veículo sem odômetro funcional"],
        ["Exija km no acerto da carga.", "Liste os motoristas que não informam.", "Corrija veículos com odômetro quebrado."]),
    # ------------------------------------------------------------------ Fiscal
    "nfe_denegadas": _v(
        "Nota denegada ou rejeitada é venda parada e risco fiscal.",
        ["Cadastro de cliente irregular", "Erro de parametrização tributária", "Certificado ou SEFAZ"],
        ["Liste as rejeições por código de erro.", "Corrija cadastro do cliente ou produto.", "Reenvie as notas pendentes."]),
    "mdfe_pendentes": _v(
        "MDF-e não transmitido é carga circulando irregular: multa e apreensão.",
        ["Esquecimento na expedição", "Erro de transmissão", "Certificado vencido"],
        ["Transmita os pendentes hoje.", "Bloqueie a saída da carga sem MDF-e.", "Confira certificado e conexão."]),
    "nfe_autorizadas_pct": _v(
        "Nota não autorizada é venda que não pode sair.",
        ["Rejeições", "SEFAZ instável", "Notas em contingência não regularizadas"],
        ["Liste as notas não autorizadas por situação.", "Regularize as em contingência.", "Corrija as rejeições na origem."]),
    "notas_canceladas_pct": _v(
        "Nota cancelada é retrabalho e possível venda perdida.",
        ["Erro de digitação", "Cliente recusou", "Carga não saiu"],
        ["Classifique os cancelamentos por motivo.", "Confirme pedidos antes de faturar.", "Cruze com Cargas canceladas."]),
    "icms_pct_faturamento": _v(
        "ICMS acima do esperado indica mix, destino ou parametrização diferentes do planejado.",
        ["Mix de produtos com alíquota maior", "Venda interestadual", "Parametrização errada"],
        ["Abra por UF e por produto.", "Confira a parametrização dos itens que mudaram.", "Reveja benefícios fiscais aplicáveis."]),
    "st_pct_faturamento": _v(
        "ST acima do esperado afeta preço e caixa.",
        ["Mix com ST", "Parametrização errada", "Mudança de legislação"],
        ["Abra por produto e UF.", "Confira a parametrização de ST.", "Reveja preço dos itens com ST."]),
    "ipi_pct_faturamento": _v(
        "IPI acima do esperado indica mix ou parametrização diferentes.",
        ["Mix industrializado", "Parametrização errada"],
        ["Abra por produto.", "Confira a parametrização de IPI."]),
    "carga_tributaria_pct": _v(
        "Carga tributária maior reduz a margem líquida.",
        ["Mix e destino das vendas", "Parametrização", "Benefício fiscal não aplicado"],
        ["Abra por UF e produto.", "Reveja a parametrização com a contabilidade.", "Confira benefícios fiscais."]),
    "notas_por_dia_util": _v(
        "Menos notas por dia útil é ritmo de faturamento em queda.",
        ["Venda caiu", "Faturamento concentrado", "Dias sem faturamento"],
        ["Compare o faturamento por dia.", "Cruze com Positivação.", "Cheque paradas do sistema."]),
    # ----------------------------------------------------------------- Pessoas
    "cnh_vencendo_30d": _v(
        "Motorista com CNH vencida não pode dirigir: carga parada e multa.",
        ["Sem controle de validade", "Renovação atrasada"],
        ["Avise os motoristas e agende a renovação.", "Bloqueie escala com CNH vencida.", "Crie alerta de 60 dias."]),
    "usuarios_de_desligados": _v(
        "Usuário ativo de desligado é risco de acesso indevido ao ERP.",
        ["Desligamento sem baixa do usuário", "RH e TI sem integração"],
        ["Desative os usuários hoje.", "Inclua a baixa do usuário no checklist de desligamento.", "Revise mensalmente."]),
    "admissoes": _v(
        "Admissões abaixo do plano deixam vagas abertas e sobrecarregam a equipe.",
        ["Recrutamento lento", "Vagas não aprovadas", "Mercado difícil"],
        ["Liste as vagas abertas e o tempo de cada uma.", "Priorize as vagas críticas.", "Reveja o processo seletivo."]),
    "tempo_medio_casa_anos": _v(
        "Tempo de casa caindo é a empresa perdendo experiência.",
        ["Rotatividade alta", "Crescimento rápido do quadro", "Desligamento de antigos"],
        ["Cruze com Turnover.", "Entreviste quem saiu.", "Crie plano de retenção para os experientes."]),
    "motoristas_ativos": _v(
        "Sem motorista suficiente, carga fica no pátio.",
        ["Desligamentos", "Afastamentos", "CNH vencida"],
        ["Cruze com CNH vencendo.", "Abra vagas com prioridade.", "Reveja a escala."]),
    "faturamento_por_funcionario": _v(
        "Produtividade menor é a folha crescendo mais que a venda.",
        ["Venda caiu", "Quadro cresceu sem retorno", "Horas extras"],
        ["Compare com Folha sobre faturamento.", "Reveja o quadro por área.", "Congele reposições não críticas."]),
    # --------------------------------------------------------- Força de vendas
    "valor_pedidos": _v(
        "Venda transmitida abaixo da meta é sinal antecipado de faturamento menor.",
        ["RCAs sem visita", "Clientes sem crédito", "Ruptura no força de vendas"],
        ["Abra por RCA e dia.", "Cruze com Clientes sem crédito e Ruptura.", "Cobre roteiro e meta diária."]),
    "pedidos_bloqueados_valor": _v(
        "Venda bloqueada é receita parada e cliente esperando.",
        ["Limites de crédito baixos", "Bloqueio comercial pendente", "Aprovação lenta"],
        ["Libere ou recuse os bloqueios de hoje.", "Reveja limites dos clientes recorrentes.", "Defina prazo máximo de análise."]),
    "pedidos_bloqueados_pct": _v(
        "Muitos pedidos bloqueados indicam política de crédito desalinhada da venda.",
        ["Limites desatualizados", "Inadimplência", "Regra de bloqueio rígida"],
        ["Liste os motivos de bloqueio.", "Atualize limites com base no histórico.", "Automatize liberação de baixo risco."]),
    "comissao_valor": _v(
        "Comissão acima do previsto com venda igual indica regra de comissionamento desalinhada.",
        ["Percentual alto em itens de baixa margem", "Comissão sobre venda com desconto", "Regra sem teto"],
        ["Abra a comissão por RCA e produto.", "Atrele a comissão à margem.", "Reveja percentuais por grupo de produto."]),
    "comissao_pct": _v(
        "Comissão pesando mais na venda é custo comercial crescendo.",
        ["Mix de itens com comissão alta", "Regra sem relação com margem"],
        ["Compare com Margem bruta.", "Atrele a comissão à margem.", "Reveja percentuais."]),
    "clientes_curva_a_pct": _v(
        "Poucos clientes A significa venda concentrada e frágil.",
        ["Base de médios fraca", "Prospecção parada"],
        ["Crie plano de crescimento para clientes B.", "Cruze com Concentração nos 10 maiores.", "Proteja as contas A."]),
    "skus_curva_a_pct": _v(
        "Poucos produtos fazendo a venda é catálogo mal aproveitado.",
        ["Mix concentrado", "Itens sem argumento de venda", "Ruptura de secundários"],
        ["Crie campanha de introdução para itens B.", "Defina mix mínimo por cliente.", "Confira Ruptura."]),
    "mix_por_cliente": _v(
        "Mix baixo por cliente é margem e giro deixados na mesa.",
        ["RCA vendendo só o carro-chefe", "Ruptura", "Sem sugestão de pedido"],
        ["Defina mix mínimo por segmento.", "Sugira itens no força de vendas.", "Bonifique mix, não volume."]),
    "credito_disponivel_carteira": _v(
        "Carteira sem crédito disponível não consegue comprar mais.",
        ["Limites baixos", "Títulos em aberto", "Pedidos pendentes consumindo limite"],
        ["Liste os clientes com crédito zerado e bom histórico.", "Reveja limites.", "Acelere a cobrança dos títulos vencidos."]),
    "clientes_sem_credito_pct": _v(
        "Cliente sem crédito é venda travada mesmo com demanda.",
        ["Limites desatualizados", "Inadimplência", "Pedidos presos"],
        ["Reveja limites dos clientes com bom histórico.", "Cobre os vencidos.", "Libere pedidos presos."]),
    "clientes_positivados_delta": _v(
        "Positivação em queda frente ao mês anterior é a base encolhendo.",
        ["Roteiro não cumprido", "Clientes bloqueados", "Sazonalidade"],
        ["Liste quem comprou no mês anterior e não neste.", "Aja em 15 dias com oferta de reativação.", "Cruze com Clientes bloqueados."]),
    "clientes_perdidos_mes": _v(
        "Cada cliente perdido precisa ser reposto com prospecção, que custa mais.",
        ["Serviço ruim", "Preço", "Falta de visita"],
        ["Ligue para os perdidos e registre o motivo.", "Cruze com Entregas com ocorrência.", "Crie alerta de 45 dias sem compra."]),
    "rcas_sem_venda": _v(
        "RCA ativo sem venda é custo sem retorno e carteira descoberta.",
        ["Afastamento", "Carteira vazia", "Cadastro sem baixa"],
        ["Liste os RCAs sem venda e o motivo.", "Redistribua carteira ou desative o cadastro.", "Defina meta mínima semanal."]),
    "carteira_positivada_pct": _v(
        "Carteira pouco positivada é cliente existente sem compra.",
        ["Roteiro não cumprido", "Carteira grande demais", "Clientes sem crédito"],
        ["Cobre roteiro por RCA.", "Redistribua carteiras.", "Cheque crédito."]),
    "carteira_inativa_pct": _v(
        "Carteira inativa alta é perda silenciosa de clientes.",
        ["Falta de visita", "Ruptura", "Preço"],
        ["Segmente os inativos por potencial.", "Ação de reativação com oferta.", "Cruze com Churn."]),
    # --------------------------------------------------------------------- WMS
    "wms_os_concluidas": _v(
        "Menos OS concluídas é separação abaixo da demanda: pedido esperando.",
        ["Equipe reduzida", "Equipamento parado", "OS travadas por corte"],
        ["Cruze com OS pendentes e Linhas por hora.", "Balanceie a equipe entre turnos.", "Resolva as OS travadas."]),
    "wms_tempo_separacao_min": _v(
        "Separação lenta atrasa a carga e a entrega.",
        ["Endereçamento ruim", "Equipe nova", "Equipamento insuficiente"],
        ["Compare o tempo por separador.", "Reveja o endereçamento dos itens de maior giro.", "Cruze com Linhas por hora."]),
    "wms_tempo_conferencia_min": _v(
        "Conferência lenta é gargalo na saída da carga.",
        ["Poucos conferentes", "Muitos erros de separação", "Processo manual"],
        ["Cruze com Erros de conferência.", "Balanceie separadores e conferentes.", "Use coletor na conferência."]),
    "wms_os_pendentes": _v(
        "OS pendentes são pedidos faturados esperando separação.",
        ["Capacidade de separação", "Itens sem endereço", "OS travadas"],
        ["Liste as OS pendentes por idade.", "Resolva as travadas.", "Reforce a equipe no pico."]),
    "wms_linhas_por_hora": _v(
        "Produtividade baixa na separação encarece cada pedido.",
        ["Endereçamento ruim", "Equipe nova", "Deslocamento longo"],
        ["Compare por separador e turno.", "Reveja o endereçamento por giro.", "Treine os abaixo da média."]),
    "wms_corte_pct": _v(
        "Corte na separação é venda perdida na porta do armazém.",
        ["Divergência física", "Endereço errado", "Compra atrasada"],
        ["Liste os itens mais cortados.", "Faça inventário rotativo desses itens.", "Cruze com Ruptura."]),
    "wms_erros_conferencia": _v(
        "Erro de conferência é retrabalho e, se passar, devolução.",
        ["Separador novo", "Endereçamento confuso", "Produtos parecidos"],
        ["Liste os erros por separador e produto.", "Treine e reendereçe os itens confundidos.", "Cruze com Devoluções."]),
    # ------------------------------------------------------------ Roteirização
    "cargas_roteirizadas_pct": _v(
        "Carga sem roteirizador tende a rodar mais km e entregar menos por carga.",
        ["Montagem manual", "Roteirizador fora do processo", "Cargas urgentes"],
        ["Torne o roteirizador obrigatório.", "Liste as cargas manuais e o motivo.", "Compare km e entregas das roteirizadas versus manuais."]),
    "ocupacao_peso_pct": _v(
        "Caminhão com baixa ocupação é frete pago por espaço vazio.",
        ["Rotas de baixa densidade", "Veículo grande para a rota", "Pedidos pequenos"],
        ["Ajuste o tipo de veículo à rota.", "Consolide rotas.", "Reveja pedido mínimo."]),
    "entregas_por_carga_roteirizada": _v(
        "Poucas entregas por carga roteirizada indica parâmetros do roteirizador frouxos.",
        ["Parâmetros de janela e capacidade", "Pedidos dispersos", "Rotas curtas demais"],
        ["Reveja os parâmetros do roteirizador.", "Agrupe entregas por dia e região.", "Cruze com Ocupação."]),
    "cidades_por_carga": _v(
        "Muitas cidades por carga é rota dispersa.",
        ["Atender toda praça todo dia", "Parâmetros do roteirizador", "Pedidos dispersos"],
        ["Defina dias fixos por praça.", "Ajuste o roteirizador.", "Consolide por região."]),
    "ocorrencias_entrega": _v(
        "Cada ocorrência é reentrega, devolução ou cliente insatisfeito.",
        ["Cliente fechado ou sem dinheiro", "Produto avariado ou errado", "Atraso na entrega"],
        ["Classifique as ocorrências por motivo.", "Confirme a entrega com o cliente antes de sair.", "Cruze com Erros de conferência e Cargas além do prazo."]),
    "entregas_com_ocorrencia_pct": _v(
        "Parcela alta de entregas com problema é o nível de serviço caindo.",
        ["Atraso", "Avaria", "Erro de separação"],
        ["Abra por rota e motorista.", "Ataque o motivo mais frequente.", "Cruze com Devoluções."]),
}
