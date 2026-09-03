"""Regras de negócio do WinThor que os indicadores precisam respeitar.

Fonte única: o que o próprio ERP faz (lido no PL/SQL das bases reais pelo
vsystems-mi6). Trocar um número aqui muda TODO indicador que depende dele.
"""
from django.db.models import Q

# CONDVENDA que NÃO é receita: 4 e 8 (entrega futura/ordem), 10 (transferência
# entre filiais), 13, 20, 98, 99 (ajustes internos).
CONDVENDA_FORA_DO_FATURAMENTO = [4, 8, 10, 13, 20, 98, 99]

# Bonificação / brinde: sai do estoque sem receita.
CONDVENDA_BONIFICACAO = [5, 6, 11, 12]

# PCMOV.CODOPER — operações de saída (venda) e de entrada por devolução.
OPERACOES_VENDA = ["S", "SL", "SB", "SV"]
OPERACOES_DEVOLUCAO = ["E1", "ED", "EL"]
OPERACOES_TRANSFERENCIA = ["ST", "ET"]
OPERACOES_PERDA = ["SD", "SX", "EX", "EB"]


def filtro_notas_faturadas():
    """Notas que contam como receita: não canceladas e fora das condições excluídas."""
    return (
        Q(canceled_at__isnull=True)
        & ~Q(sale_type__in=CONDVENDA_FORA_DO_FATURAMENTO + CONDVENDA_BONIFICACAO)
    )


def filtro_bonificacoes():
    return Q(canceled_at__isnull=True) & Q(sale_type__in=CONDVENDA_BONIFICACAO)
