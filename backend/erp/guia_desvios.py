"""Guia de tratamento de desvio por indicador.

Quando um farol fica vermelho, o gestor precisa de três coisas além do número:
o que aquele desvio custa para a empresa (impacto), onde normalmente está a
causa (causas comuns) e por onde começar a agir (dicas). O texto vem daqui,
por métrica do catálogo; métricas sem verbete próprio caem no verbete do
grupo (Vendas, Financeiro, Estoque…) e, por fim, num genérico pela polaridade.
"""
from datetime import date

_G = {
    # ------------------------------------------------------------------ Vendas
    "faturamento": dict(
        impacto="Cada real abaixo da meta reduz a diluição dos custos fixos e aperta a margem e o caixa dos próximos meses.",
        causas=["Positivação caiu (menos clientes comprando)", "Ticket médio menor: mix pobre ou desconto alto", "Ruptura de itens de giro", "Pedidos presos em bloqueio de crédito ou corte na separação"],
        dicas=["Abra o faturamento por filial e por RCA para achar onde caiu (o desvio raramente é geral).",
               "Cruze com Positivação e Ticket médio: se foi cliente, é cobertura; se foi ticket, é mix/preço.",
               "Confira Ruptura e Venda perdida por falta dos 50 itens que mais vendem.",
               "Olhe a Venda bloqueada e o Corte: pode ser venda feita que não virou nota.",
               "Defina uma ação de recuperação por semana (campanha, mix, visita) com responsável e valor esperado."]),
    "ticket_medio": dict(
        impacto="Ticket menor com o mesmo esforço de venda e entrega encarece cada pedido e derruba a margem por cliente.",
        causas=["Mix concentrado em itens baratos", "Desconto ou bonificação acima do padrão", "Pedidos fracionados (cliente pede mais vezes com menos itens)", "Perda dos clientes grandes"],
        dicas=["Compare Itens por nota e Mix por cliente: ticket cai com menos itens ou com item mais barato?",
               "Reveja a política de pedido mínimo e de bonificação por faixa de compra.",
               "Monte combos e sugestão de pedido para o RCA no força de vendas.",
               "Veja se os 10 maiores clientes reduziram: Concentração nos 10 maiores explica boa parte."]),
    "positivacao": dict(
        impacto="Menos clientes comprando é o sinal mais precoce de perda de faturamento: a base encolhe antes de o total cair.",
        causas=["RCA não visitou a carteira (roteiro furado)", "Clientes bloqueados por crédito ou inadimplência", "Concorrência com preço melhor", "Ruptura recorrente afastou o cliente"],
        dicas=["Liste os clientes positivados no mês anterior que não compraram neste; é a lista de recuperação.",
               "Cheque Clientes bloqueados e Clientes sem crédito: parte da queda pode ser cadastro/crédito.",
               "Cobre o roteiro: Clientes positivados por RCA mostra quem parou de cobrir a carteira.",
               "Crie uma ação de reativação com oferta de entrada e prazo de 15 dias."]),
    "clientes_ativos": dict(
        impacto="Base ativa menor significa menos oportunidades de venda todo mês e maior dependência de poucos clientes.",
        causas=["Churn maior que a entrada de novos clientes", "Carteira mal distribuída entre RCAs", "Inadimplência bloqueando reposição"],
        dicas=["Compare Novos clientes e Clientes perdidos no mês: o problema é entrada ou saída?",
               "Segmente a base inativa por tempo sem compra e ataque primeiro os 30 a 60 dias.",
               "Distribua clientes órfãos (sem RCA ativo) em até uma semana."]),
    "novos_clientes": dict(
        impacto="Sem entrada de clientes a base envelhece e o crescimento fica refém de quem já compra.",
        causas=["Prospecção sem meta por RCA", "Cadastro travado no crédito", "Área sem cobertura"],
        dicas=["Defina meta semanal de cadastros e primeira compra por RCA.",
               "Meça o tempo entre cadastro e liberação de crédito; acima de 2 dias o cliente esfria.",
               "Mapeie praças sem cliente ativo usando a rota e monte roteiro de prospecção."]),
    "churn_clientes_pct": dict(
        impacto="Perder cliente custa mais que manter: cada ponto de churn precisa ser reposto com prospecção nova.",
        causas=["Falha de entrega ou atraso recorrente", "Preço fora do mercado", "Troca de RCA na carteira", "Ruptura dos itens que o cliente compra"],
        dicas=["Ligue para uma amostra dos clientes perdidos e registre o motivo (preço, entrega, atendimento).",
               "Cruze com Entregas com ocorrência e Devoluções: serviço ruim aparece antes no churn.",
               "Crie alerta de cliente sem compra há 45 dias para o RCA agir antes da perda."]),
    "mix_skus": dict(
        impacto="Mix menor concentra a venda em poucos itens e deixa margem e giro do estoque na mesa.",
        causas=["RCA vendendo só o carro-chefe", "Itens novos sem argumento de venda", "Ruptura de itens secundários"],
        dicas=["Defina um mix mínimo por cliente por segmento e acompanhe no força de vendas.",
               "Crie campanha de introdução para 5 itens de boa margem com baixa cobertura.",
               "Confira Ruptura: não dá para vender mix que não tem em estoque."]),
    "desconto_medio_pct": dict(
        impacto="Cada ponto de desconto acima do padrão sai direto da margem; em distribuição costuma ser o maior vazamento de resultado.",
        causas=["Alçada de desconto frouxa no força de vendas", "Desconto usado para bater volume no fim do mês", "Tabela de preço desatualizada frente ao mercado"],
        dicas=["Liste os 20 pedidos com maior desconto e quem autorizou.",
               "Reveja alçadas por RCA e supervisor e exija justificativa acima do limite.",
               "Troque desconto por bonificação condicionada a mix ou volume.",
               "Compare com Margem bruta para dimensionar o custo do desconto."]),
    "bonificacao_pct": dict(
        impacto="Bonificação além do planejado é venda sem receita: consome estoque e margem sem contrapartida.",
        causas=["Bonificação sem contrapartida de volume", "Uso para compensar avaria ou atraso", "Verba de fornecedor não repassada"],
        dicas=["Separe bonificação comercial de troca/avaria: cada uma tem um dono.",
               "Condicione bonificação a meta de mix ou volume no mês.",
               "Confira Verba de fornecedor a receber: parte pode ser recuperada."]),
    "devolucoes_pct": dict(
        impacto="Devolução custa frete duas vezes, retrabalho no armazém e, às vezes, o cliente.",
        causas=["Erro de separação ou conferência", "Avaria no transporte", "Pedido digitado errado", "Prazo de validade curto"],
        dicas=["Classifique as devoluções do mês por motivo e ataque o maior primeiro.",
               "Cruze com Erros de conferência e Ocorrências de entrega.",
               "Bloqueie a saída de itens com validade abaixo do mínimo aceito pelo cliente."]),
    "carteira_pedidos": dict(
        impacto="Carteira presa é venda feita que não virou receita: o cliente espera, o caixa também.",
        causas=["Fila de bloqueio de crédito", "Falta de estoque para faturar", "Capacidade de separação/expedição"],
        dicas=["Abra a carteira por motivo: bloqueio, sem estoque, aguardando carga.",
               "Reduza o tempo de liberação de crédito (Tempo médio em fila de bloqueio).",
               "Priorize faturar os pedidos mais antigos e de maior valor."]),
    "conversao_pedido_nota_pct": dict(
        impacto="Pedido que não vira nota é venda perdida com custo de venda já pago.",
        causas=["Bloqueio de crédito", "Ruptura na separação (corte)", "Cancelamento pelo cliente por atraso"],
        dicas=["Liste os pedidos não faturados do mês por motivo de cancelamento.",
               "Cruze com Corte e Pedidos bloqueados.",
               "Combine com o comercial regra de estoque disponível no força de vendas para não vender o que não tem."]),
    "corte_pct": dict(
        impacto="Corte é venda perdida na porta do armazém e frustra o cliente que já esperava o produto.",
        causas=["Estoque disponível errado (divergência física)", "Reserva de pedido sem baixa", "Compra atrasada"],
        dicas=["Liste os 20 itens mais cortados e confira saldo físico versus sistema.",
               "Verifique Pedidos de compra atrasados e Itens abaixo do mínimo.",
               "Ajuste o parâmetro de estoque disponível no força de vendas."]),
    "margem_bruta_pct": dict(
        impacto="Margem menor com o mesmo volume reduz o lucro na proporção direta; é o indicador que mais rápido afeta o resultado.",
        causas=["Desconto e bonificação acima do padrão", "Custo de compra subiu sem repasse", "Mix concentrado em itens de margem baixa"],
        dicas=["Abra a margem por produto e por RCA: 20% dos itens costumam explicar a queda.",
               "Compare Desconto médio e Bonificação com os meses anteriores.",
               "Reveja preço de venda dos itens cujo custo subiu (Custo médio por kg ajuda).",
               "Defina margem mínima por item no força de vendas."]),
    "cmv": dict(
        impacto="CMV acima do previsto com venda igual é margem perdida ou custo de compra mal negociado.",
        causas=["Compra em condição pior", "Perda e avaria contabilizadas no custo", "Mix desloca para itens de custo alto"],
        dicas=["Compare Custo médio por kg e Preço médio por kg no mês.",
               "Renegocie os 5 maiores fornecedores (Concentração nos 5 maiores).",
               "Confira Estoque bloqueado e avarias."]),
    "despesas_competencia": dict(
        impacto="Despesa acima do orçado consome resultado mesmo com a venda na meta.",
        causas=["Frete e combustível", "Horas extras", "Despesas não orçadas"],
        dicas=["Abra por conta e centro de custo; os 5 maiores grupos explicam quase tudo.",
               "Cruze com Frete sobre faturamento e Folha sobre faturamento.",
               "Estabeleça alçada de aprovação para despesas fora do orçamento."]),
    "folha_pct_faturamento": dict(
        impacto="Folha pesando mais no faturamento indica produtividade em queda ou venda encolhendo mais rápido que o quadro.",
        causas=["Faturamento caiu e o quadro ficou", "Horas extras", "Contratações sem retorno em venda"],
        dicas=["Compare com Faturamento por funcionário para separar efeito venda de efeito quadro.",
               "Reveja escala e horas extras da operação.",
               "Congele reposição de vagas não críticas até a venda recuperar."]),
    "recebido": dict(
        impacto="Receber menos que o previsto aperta o caixa e força captação cara.",
        causas=["Inadimplência", "Prazo de venda alongado", "Faturamento menor no mês anterior"],
        dicas=["Cruze com A receber vencido e Atraso médio dos recebimentos.",
               "Priorize a régua de cobrança dos títulos entre 1 e 30 dias de atraso.",
               "Reveja prazo médio concedido por RCA."]),
    "geracao_caixa": dict(
        impacto="Caixa negativo no mês obriga a usar limite bancário ou atrasar fornecedor.",
        causas=["Recebimento abaixo do previsto", "Compras concentradas", "Despesas fora do orçado"],
        dicas=["Compare Entradas e Saídas de caixa com o mês anterior para achar o lado do problema.",
               "Monte o fluxo dos próximos 30 dias (A pagar e A receber nos próximos 30 dias).",
               "Negocie prazo com os maiores fornecedores antes de atrasar."]),
    "saldo_caixa": dict(
        impacto="Saldo abaixo do mínimo deixa a operação sem folga para pagar fornecedor e folha.",
        causas=["Geração de caixa negativa", "Capital parado em estoque", "Inadimplência"],
        dicas=["Verifique Capital parado e Cobertura de estoque: estoque em excesso é caixa preso.",
               "Antecipe recebíveis só depois de esgotar a cobrança.",
               "Reveja o calendário de pagamentos da semana."]),
    "a_receber_vencido": dict(
        impacto="Vencido em aberto é venda sem caixa; quanto mais velho, menor a chance de receber.",
        causas=["Régua de cobrança fraca", "Crédito concedido acima da capacidade do cliente", "Títulos prorrogados sem critério"],
        dicas=["Abra o vencido por faixa de atraso e por RCA.",
               "Bloqueie novas vendas para clientes com título vencido acima de X dias.",
               "Cobre os 20 maiores títulos pessoalmente esta semana.",
               "Reveja Títulos prorrogados e quem autoriza."]),
    "inadimplencia_pct": dict(
        impacto="Inadimplência alta transforma venda em prejuízo e contamina o limite de crédito da carteira.",
        causas=["Análise de crédito frouxa", "Cobrança tardia", "Clientes em dificuldade"],
        dicas=["Liste os clientes com maior valor vencido e defina ação por cliente (acordo, protesto, suspensão).",
               "Reveja limite de crédito dos clientes com atraso recorrente.",
               "Acompanhe Clientes com título vencido semanalmente."]),
    "prazo_medio_recebimento": dict(
        impacto="Cada dia a mais de prazo é capital de giro financiado pela empresa.",
        causas=["Prazo de venda alongado por RCA", "Atraso no pagamento", "Prorrogações"],
        dicas=["Separe prazo concedido de atraso (Atraso médio dos recebimentos).",
               "Limite o prazo por faixa de cliente e exija aprovação acima disso.",
               "Ofereça desconto financeiro para pagamento à vista onde compensar."]),
    # ----------------------------------------------------------------- Estoque
    "estoque_valor": dict(
        impacto="Estoque acima do necessário é caixa parado, além de risco de perda e obsolescência.",
        causas=["Compra em volume por preço", "Itens sem giro", "Previsão de venda otimista"],
        dicas=["Veja Capital parado e Itens sem giro para separar excesso de estoque saudável.",
               "Suspenda compra dos itens com cobertura acima de 45 dias.",
               "Crie ação de queima para itens sem giro há mais de 90 dias."]),
    "cobertura_estoque_dias": dict(
        impacto="Cobertura alta prende caixa; cobertura baixa gera ruptura. Fora da faixa, um dos dois já está acontecendo.",
        causas=["Compra desalinhada da venda", "Venda caiu e a compra não", "Itens sazonais"],
        dicas=["Ajuste estoque mínimo e máximo por curva ABC.",
               "Confira Excesso sobre o estoque máximo e Itens abaixo do mínimo.",
               "Alinhe compras e comercial numa reunião semanal de reposição."]),
    "ruptura_pct": dict(
        impacto="Ruptura é venda perdida direta e a principal razão de cliente trocar de fornecedor.",
        causas=["Compra atrasada", "Estoque mínimo desatualizado", "Divergência física", "Pico de venda"],
        dicas=["Liste os itens zerados com giro e compre os de curva A hoje.",
               "Verifique Pedidos de compra atrasados por fornecedor.",
               "Revise o estoque mínimo dos itens que romperam neste mês.",
               "Meça Venda perdida por falta para dimensionar o prejuízo."]),
    "giro_estoque": dict(
        impacto="Giro baixo significa capital parado e custo de armazenagem por real vendido maior.",
        causas=["Estoque alto", "Venda em queda", "Itens sem giro"],
        dicas=["Compare com Cobertura de estoque e Itens sem giro.",
               "Reduza lote de compra dos itens de curva C.",
               "Promova a saída dos itens com mais de 60 dias."]),
    "venda_perdida_qtd": dict(
        impacto="É demanda real que a empresa não atendeu: o cliente queria comprar e não havia produto.",
        causas=["Ruptura", "Compra atrasada", "Estoque disponível errado"],
        dicas=["Liste os itens com mais venda perdida e a causa (sem estoque, bloqueado, divergência).",
               "Cruze com Ruptura e Pedidos de compra atrasados.",
               "Corrija o parâmetro de disponibilidade no força de vendas."]),
    "compras_valor": dict(
        impacto="Comprar além do planejado consome caixa e alimenta estoque parado.",
        causas=["Compra antecipada por preço", "Venda projetada acima do real", "Fornecedor com lote mínimo alto"],
        dicas=["Compare com Compras sobre faturamento e Cobertura de estoque.",
               "Exija aprovação para compra acima do estoque máximo.",
               "Negocie lotes menores com entregas mais frequentes."]),
    # --------------------------------------------------------------- Logística
    "cargas_expedidas": dict(
        impacto="Menos cargas com a mesma venda significa entrega mais lenta e pedido esperando no pátio.",
        causas=["Frota indisponível", "Roteirização segurando carga", "Falta de motorista"],
        dicas=["Cruze com Carteira de pedidos e Cargas em rota.",
               "Confira Motoristas ativos e CNH vencendo.",
               "Reveja o corte de montagem de carga (horário limite de pedido)."]),
    "notas_por_carga": dict(
        impacto="Carga com poucas notas encarece o frete por entrega e ocupa mal o veículo.",
        causas=["Roteirização por praça sem consolidação", "Pedidos pequenos e frequentes", "Frota grande demais para a demanda"],
        dicas=["Compare com Ocupação do veículo e Frete por nota entregue.",
               "Consolide entregas por rota em dias fixos.",
               "Revise pedido mínimo por praça distante."]),
    "peso_entregue_ton": dict(
        impacto="Peso entregue abaixo do esperado indica venda menor ou pedido preso na expedição.",
        causas=["Venda caiu", "Corte na separação", "Cargas atrasadas"],
        dicas=["Cruze com Peso vendido: se a venda está na meta, o gargalo é expedição.",
               "Verifique Cargas além do prazo de rota e OS de saída pendentes."]),
    "frete_pct_faturamento": dict(
        impacto="Frete pesando mais no faturamento corrói a margem líquida sem aparecer na margem bruta.",
        causas=["Carga mal ocupada", "Entregas distantes com pouco volume", "Combustível e manutenção"],
        dicas=["Abra Frete por kg e Frete por nota entregue por rota.",
               "Reveja rotas de baixa densidade e o pedido mínimo delas.",
               "Confira Cargas sem odômetro: sem km não há controle de custo."]),
    # ----------------------------------------------------------------- Pessoas
    "headcount": dict(
        impacto="Quadro fora do planejado afeta custo (acima) ou capacidade de atendimento (abaixo).",
        causas=["Contratações fora do plano", "Desligamentos não repostos"],
        dicas=["Compare com Faturamento por funcionário para ver se o quadro acompanha a venda.",
               "Reveja o plano de vagas com cada gestor."]),
    "turnover_pct": dict(
        impacto="Rotatividade alta custa recrutamento, treinamento e produtividade, e piora a entrega ao cliente.",
        causas=["Liderança", "Remuneração abaixo do mercado", "Sobrecarga e horas extras", "Seleção mal feita"],
        dicas=["Entreviste quem saiu e agrupe motivos por área.",
               "Veja Tempo médio de casa: se está caindo, o problema é retenção nos primeiros meses.",
               "Compare a rotatividade por gestor."]),
    "desligamentos": dict(
        impacto="Cada desligamento leva conhecimento e obriga a recomeçar o treinamento.",
        causas=["Pedidos de demissão por clima ou salário", "Desligamentos por baixa performance", "Sazonalidade"],
        dicas=["Separe voluntários de involuntários e trate cada grupo.",
               "Cheque Usuários ativos de funcionários desligados para fechar acessos."]),
}

_GRUPO = {
    "Vendas": dict(
        impacto="Desvio de vendas reduz a receita e a diluição dos custos fixos, e aparece no caixa nos meses seguintes.",
        causas=["Cobertura de clientes", "Mix e ticket", "Ruptura", "Pedidos presos"],
        dicas=["Abra por filial e por RCA.", "Cruze com Positivação, Ticket médio e Ruptura.", "Defina ação semanal com responsável."]),
    "Clientes": dict(
        impacto="Perda de clientes é o sinal mais precoce de queda de venda e o mais caro de reverter.",
        causas=["Serviço (entrega, ruptura)", "Preço", "Cobertura da carteira"],
        dicas=["Liste os clientes que saíram e os motivos.", "Ative régua de reativação.", "Cruze com Entregas com ocorrência."]),
    "Financeiro": dict(
        impacto="Desvio financeiro afeta o caixa e o custo de capital; quanto mais tempo aberto, mais caro.",
        causas=["Inadimplência", "Prazos", "Despesa fora do orçado"],
        dicas=["Abra por conta ou cliente.", "Monte o fluxo dos próximos 30 dias.", "Aja primeiro nos 20 maiores valores."]),
    "Estoque": dict(
        impacto="Estoque fora da faixa é caixa preso (excesso) ou venda perdida (falta).",
        causas=["Compra desalinhada da venda", "Parâmetros de mínimo e máximo", "Divergência física"],
        dicas=["Revise mínimo e máximo por curva ABC.", "Confira compras atrasadas.", "Faça inventário dos itens críticos."]),
    "Compras": dict(
        impacto="Compra fora do plano consome caixa ou gera ruptura.",
        causas=["Previsão de venda", "Lote mínimo", "Fornecedor atrasado"],
        dicas=["Alinhe compras e comercial semanalmente.", "Exija aprovação acima do estoque máximo."]),
    "Logística": dict(
        impacto="Desvio logístico encarece a entrega e compromete o nível de serviço ao cliente.",
        causas=["Ocupação da frota", "Roteirização", "Capacidade de separação"],
        dicas=["Abra por rota e por veículo.", "Cruze frete, ocupação e entregas por carga.", "Revise o pedido mínimo das rotas caras."]),
    "Pessoas": dict(
        impacto="Desvio de pessoas afeta custo e capacidade de entrega ao mesmo tempo.",
        causas=["Liderança", "Remuneração", "Sobrecarga"],
        dicas=["Abra por gestor e área.", "Entreviste quem saiu.", "Reveja o plano de vagas."]),
    "Fiscal": dict(
        impacto="Erro fiscal atrasa a entrega e gera multa; nota rejeitada é venda que não sai.",
        causas=["Cadastro de produto ou cliente", "Certificado ou SEFAZ", "Parametrização tributária"],
        dicas=["Liste as rejeições por código de erro.", "Corrija cadastros na origem."]),
}

_GENERICO = {
    "maior_melhor": dict(
        impacto="O resultado ficou abaixo do que a empresa planejou; se persistir, compromete o objetivo estratégico ligado a este indicador.",
        causas=["Volume ou frequência abaixo do esperado", "Processo com gargalo", "Meta desalinhada da capacidade atual"],
        dicas=["Abra o indicador por filial, área ou responsável para localizar o desvio.", "Compare com os 3 meses anteriores: é queda ou sazonalidade?", "Defina uma contramedida com dono e prazo e acompanhe no Kanban."]),
    "menor_melhor": dict(
        impacto="O valor passou do limite planejado; cada mês acima consome margem, caixa ou capacidade.",
        causas=["Controle ou alçada frouxa", "Evento pontual (avaria, atraso, sazonalidade)", "Parâmetro do processo desatualizado"],
        dicas=["Liste as 20 maiores ocorrências do mês e quem as autorizou.", "Verifique se foi um evento pontual ou tendência (3 meses).", "Ajuste o parâmetro ou a alçada e acompanhe semanalmente."]),
}


def _texto_base(indicator):
    metric_key = indicator.erp_metric or ""
    if metric_key in _G:
        return _G[metric_key], "metrica"
    from .metrics import get_metric

    metric = get_metric(metric_key) if metric_key else None
    grupo = metric.group if metric else ""
    if grupo in _GRUPO:
        return _GRUPO[grupo], "grupo"
    return _GENERICO.get(indicator.polarity, _GENERICO["maior_melhor"]), "generico"


def guia_desvio(deviation):
    """Texto de apoio ao tratamento do desvio + números do gap e da recorrência."""
    from erp.models import KpiTemplate

    ind = deviation.indicator
    val = deviation.indicator_value
    texto, origem = _texto_base(ind)

    tpl = None
    if ind.erp_metric:
        tpl = KpiTemplate.objects.filter(code=ind.code, is_active=True).first() \
            or KpiTemplate.objects.filter(erp_metric=ind.erp_metric, is_active=True).first()

    meta = ind.targets.filter(period=val.period).first()
    from indicators.services import meta_proporcional

    alvo = meta_proporcional(ind, val.period, meta.target_value, val.source) if meta else None
    diferenca = (float(val.value) - float(alvo)) if alvo is not None else None

    # Recorrência: quantos meses seguidos (até este) fechados em vermelho, e a tendência.
    anteriores = list(ind.values.filter(period__lt=val.period).order_by("-period")[:6])
    seguidos = 1
    for v in anteriores:
        if v.status == "vermelho":
            seguidos += 1
        else:
            break
    # Mês em curso de um indicador de fluxo (soma) é parcial: comparar com meses
    # cheios só assusta. A comparação vale para meses fechados ou saldos/médias.
    hoje = date.today()
    mes_corrente = val.period.year == hoje.year and val.period.month == hoje.month
    from indicators.services import PRORATA_EXTRA

    fluxo = ind.aggregation == "soma" or ind.erp_metric in PRORATA_EXTRA
    ultimos = [] if (mes_corrente and fluxo) else [float(v.value) for v in reversed(anteriores[:3])]
    media_3m = sum(ultimos) / len(ultimos) if ultimos else None
    variacao_pct = ((float(val.value) - media_3m) / media_3m * 100) if media_3m else None

    return {
        "origem": origem,
        "descricao": (ind.description or "").split("\n\nComo é calculado:")[0].strip() or (tpl.description if tpl else ""),
        "como_calcula": tpl.explanation if tpl else "",
        "por_que_importa": tpl.importance if tpl else "",
        "impacto": texto["impacto"],
        "causas": texto["causas"],
        "dicas": texto["dicas"],
        "numeros": {
            "unidade": ind.unit, "decimais": ind.decimals, "polaridade": ind.polarity,
            "realizado": str(val.value), "meta": (str(alvo) if alvo is not None else None),
            "meta_cheia": (str(meta.target_value) if meta else None),
            "meta_proporcional": bool(meta and alvo is not None and float(alvo) != float(meta.target_value)),
            "diferenca": (str(round(diferenca, 4)) if diferenca is not None else None),
            "meses_seguidos_vermelho": seguidos,
            "media_3m": (str(round(media_3m, 4)) if media_3m is not None else None),
            "variacao_vs_media_pct": (str(round(variacao_pct, 1)) if variacao_pct is not None else None),
            "mes_corrente": mes_corrente,
        },
    }
