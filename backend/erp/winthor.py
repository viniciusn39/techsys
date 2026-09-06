"""Plano de coleta do WinThor para o TechSys Gestão.

Derivado do plano validado do vsystems-mi6 (83 entidades, bases RECIFEDOCES e
MAKFRIOS), mas ENXUTO de propósito: planejamento estratégico precisa de poucas
entidades e de poucas colunas. Cada consulta abaixo traz apenas o que alguma
métrica de `metrics.py` consome — o banco é do cliente, e varrer tabela que
ninguém lê é custo para ele sem valor para nós.

Duas metades que andam juntas:
  WINTHOR_QUERIES -> servido ao agente em GET /api/coletor/plan/ (roda no Oracle
                     do cliente; aliases em MAIÚSCULAS, datas por TO_CHAR).
  DEFAULT_SYNC    -> mapa {campo_nosso: ALIAS} usado pelo ingest (sync.py).

Regras herdadas do mi6 que valem aqui:
  - comentário NUNCA dentro do SELECT (o agente remove coluna ausente cortando
    por vírgula, e vírgula em comentário quebra o SQL);
  - :since = marca d'água (NULL na 1ª vez); :janela = meses de backfill gradual;
  - cadastros antes de movimentos (o ingest resolve FK por código).
"""

# O que alimenta o painel de resultados primeiro. Numa carga inicial o agente
# coleta nesta ordem, e é isso que decide o que o cliente vê nas primeiras horas.
ORDEM_DE_VALOR = [
    "branch", "salesrep", "supplier", "employee", "customer", "product",
    "sales_invoice", "sales_invoice_item", "title_receivable", "title_payable",
    "financial_snapshot", "bank_account", "cash_movement", "stock", "order",
    "purchase", "load", "target", "target_daily",
    "order_block", "fv_order", "customer_credit", "credit_auth", "card_settlement",
    "pos_daily", "purchase_order", "supplier_credit", "mdfe",
    "wms_os", "route_load", "delivery_event",
]

WINTHOR_QUERIES = [
    {  # PCFILIAL — minúscula: recarga cheia
        "entity": "branch",
        "label": "Filiais (PCFILIAL)",
        "every_minutes": 720,
        "sql": """
SELECT CODIGO, RAZAOSOCIAL, FANTASIA, CGC, CIDADE, UF,
       CASE WHEN DTEXCLUSAO IS NULL THEN 1 ELSE 0 END AS IS_ACTIVE
FROM PCFILIAL
""",
    },
    {  # PCUSUARI (+ PCSUPERV) — dimensão de vendas; watermark DTULTALTERACAO
        "entity": "salesrep",
        "label": "Vendedores / RCA (PCUSUARI)",
        "every_minutes": 360,
        "incremental": True,
        "since_column": "DTULTALTERACAO",
        "sql": """
SELECT U.CODUSUR, U.NOME, U.TIPOVEND, U.CODEQUIPE, S.NOME AS SUPERVISOR,
       U.VLVENDAPREV, U.VLCORRENTE, U.VLLIMCRED,
       CASE WHEN NVL(U.BLOQUEIO,'N') = 'N' AND U.DTEXCLUSAO IS NULL THEN 1 ELSE 0 END AS IS_ACTIVE,
       TO_CHAR(U.DTULTALTERACAO,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTERACAO
FROM PCUSUARI U
LEFT JOIN PCSUPERV S ON S.CODSUPERVISOR = U.CODSUPERVISOR
WHERE (:since IS NULL OR U.DTULTALTERACAO > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCFORNEC — dimensão de compras/pagar; watermark DTULTALTER
        "entity": "supplier",
        "label": "Fornecedores (PCFORNEC)",
        "every_minutes": 360,
        "incremental": True,
        "since_column": "DTULTALTER",
        "sql": """
SELECT F.CODFORNEC, F.FORNECEDOR, F.FANTASIA, F.CGC, F.CIDADE, F.ESTADO, F.TIPOFORNEC,
       F.PRAZOENTREGA,
       TO_CHAR(F.DTULTCOMPRA,'YYYY-MM-DD') AS DTULTCOMPRA,
       CASE WHEN NVL(F.EXCLUIDO,'N') = 'N' AND NVL(F.BLOQUEIO,'N') = 'N' THEN 1 ELSE 0 END AS IS_ACTIVE,
       TO_CHAR(F.DTULTALTER,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTER
FROM PCFORNEC F
WHERE (:since IS NULL OR F.DTULTALTER > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCEMPR — turnover e headcount. NUNCA senha/biometria; salário fora.
        "entity": "employee",
        "label": "Funcionários (PCEMPR)",
        "every_minutes": 360,
        "incremental": True,
        "since_column": "DTULTALTER",
        "sql": """
SELECT E.MATRICULA, E.NOME, E.FUNCAO, E.CODSETOR, E.CODFILIAL,
       TO_CHAR(E.ADMISSAO,'YYYY-MM-DD') AS ADMISSAO,
       TO_CHAR(E.DTDEMISSAO,'YYYY-MM-DD') AS DTDEMISSAO,
       CASE WHEN E.TIPOMOTORISTA IS NOT NULL THEN 1 ELSE 0 END AS IS_DRIVER,
       TO_CHAR(E.DTVALIDADECNH,'YYYY-MM-DD') AS DTVALIDADECNH,
       CASE WHEN E.USUARIOBD IS NOT NULL THEN 1 ELSE 0 END AS HAS_DB_USER,
       CASE WHEN NVL(E.SITUACAO,'A') = 'A' AND E.DT_EXCLUSAO IS NULL THEN 1 ELSE 0 END AS IS_ACTIVE,
       TO_CHAR(E.DTULTALTER,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTER
FROM PCEMPR E
WHERE (:since IS NULL OR E.DTULTALTER > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCCLIENT (+ PCPRACA) — base de clientes ativos/novos/churn; watermark DTULTALTER
        "entity": "customer",
        "label": "Clientes (PCCLIENT)",
        "every_minutes": 60,
        "incremental": True,
        "since_column": "DTULTALTER",
        "sql": """
SELECT C.CODCLI, C.CLIENTE, C.FANTASIA, C.CGCENT, C.TIPOFJ, C.MUNICENT, C.ESTENT,
       C.CODATV1, P.PRACA, P.ROTA, NVL(P.NUMREGIAO, C.NUMREGIAOCLI) AS NUMREGIAO,
       C.LIMCRED, C.CODUSUR1,
       CASE WHEN NVL(C.BLOQUEIO,'N') = 'S' OR C.DTEXCLUSAO IS NOT NULL THEN 1 ELSE 0 END AS BLOCKED,
       TO_CHAR(C.DTCADASTRO,'YYYY-MM-DD') AS DTCADASTRO,
       TO_CHAR(C.DTPRIMCOMPRA,'YYYY-MM-DD') AS DTPRIMCOMPRA,
       TO_CHAR(C.DTULTCOMP,'YYYY-MM-DD') AS DTULTCOMP,
       TO_CHAR(C.DTULTALTER,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTER
FROM PCCLIENT C
LEFT JOIN PCPRACA P ON P.CODPRACA = C.CODPRACA
WHERE (:since IS NULL OR C.DTULTALTER > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCPRODUT + hierarquia — dimensão de mix/estoque; watermark DTALTERC5 (trigger)
        "entity": "product",
        "label": "Produtos (PCPRODUT)",
        "every_minutes": 120,
        "incremental": True,
        "since_column": "DTALTERC5",
        "sql": """
SELECT P.CODPROD, P.DESCRICAO, P.CODAUXILIAR, P.UNIDADE, P.EMBALAGEM,
       M.MARCA, D.DESCRICAO AS DEPARTAMENTO, S.DESCRICAO AS SECAO,
       CAT.CATEGORIA, P.CODFORNEC, P.CLASSE, P.PESOLIQ,
       E.CUSTOREAL, T.PVENDA,
       CASE WHEN P.DTEXCLUSAO IS NULL THEN 1 ELSE 0 END AS IS_ACTIVE,
       TO_CHAR(P.DTALTERC5,'YYYY-MM-DD HH24:MI:SS') AS DTALTERC5
FROM PCPRODUT P
LEFT JOIN PCMARCA M       ON M.CODMARCA = P.CODMARCA
LEFT JOIN PCDEPTO D       ON D.CODEPTO = P.CODEPTO
LEFT JOIN PCSECAO S       ON S.CODSEC = P.CODSEC
LEFT JOIN PCCATEGORIA CAT ON CAT.CODSEC = P.CODSEC AND CAT.CODCATEGORIA = P.CODCATEGORIA
LEFT JOIN PCEST E         ON E.CODPROD = P.CODPROD AND E.CODFILIAL = '1'
LEFT JOIN PCTABPR T       ON T.CODPROD = P.CODPROD AND T.NUMREGIAO = 1
WHERE (:since IS NULL OR P.DTALTERC5 > TO_TIMESTAMP(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCNFSAID — o FATO do faturamento. Backfill gradual de 24 meses (2 por ciclo).
        "entity": "sales_invoice",
        "label": "Notas de venda (PCNFSAID)",
        "every_minutes": 30,
        "incremental": True,
        "since_column": "DTSAIDA",
        "batch": 1000,
        "backfill_meses": 12,
        "backfill_passo": 2,
        "sql": """
SELECT N.NUMTRANSVENDA, N.NUMNOTA, N.SERIE, N.CODFILIAL, N.CODCLI, N.CODUSUR,
       N.CONDVENDA, N.TIPOVENDA, N.NUMPED, N.NUMCAR,
       N.VLTOTAL, N.VLTOTGER, N.VLDESCONTO, N.VLFRETE, N.VLIPI, N.VLICMS,
       N.SITUACAONFE, N.ESPECIE,
       TO_CHAR(N.DTSAIDA,'YYYY-MM-DD') AS DTSAIDA,
       TO_CHAR(N.DTCANCEL,'YYYY-MM-DD') AS DTCANCEL
FROM PCNFSAID N
WHERE N.DTSAIDA >= ADD_MONTHS(TRUNC(SYSDATE), -:janela)
  AND (:since IS NULL OR N.DTSAIDA >= TRUNC(SYSDATE) - 7)
""",
    },
    {  # PCMOV — item da nota com custo: base da margem, devolução e mix.
       # Só operações com valor de gestão (venda, devolução, bonificação, transferência,
       # perda e avaria); consumo interno/remessa/comodato ficam de fora.
        "entity": "sales_invoice_item",
        "label": "Itens de nota (PCMOV)",
        "every_minutes": 60,
        "incremental": True,
        "since_column": "DTMOV",
        "batch": 1000,
        "backfill_meses": 12,
        "backfill_passo": 1,
        "sql": """
SELECT M.NUMTRANSITEM, M.NUMTRANSVENDA, M.NUMNOTA, M.CODOPER, M.CODFILIAL,
       M.CODPROD, M.CODCLI, M.CODUSUR, M.CODEPTO, M.CODSEC,
       M.QT, M.QTCX, M.PUNIT, M.PTABELA, M.VLDESCONTO,
       M.CUSTOREAL, M.CUSTOFIN, M.NUMPED,
       TO_CHAR(M.DTMOV,'YYYY-MM-DD') AS DTMOV
FROM PCMOV M
WHERE M.DTCANCEL IS NULL
  AND M.CODOPER IN ('S','SL','SB','ST','SD','SV','EL','E1','ED','EX','ET','EB')
  AND M.DTMOV >= ADD_MONTHS(TRUNC(SYSDATE), -:janela)
  AND (:since IS NULL OR M.DTMOV >= TRUNC(SYSDATE) - 7)
""",
    },
    {  # PCPREST — contas a receber (inadimplência, DSO); watermark DTULTALTER
        "entity": "title_receivable",
        "label": "Contas a receber (PCPREST)",
        "every_minutes": 30,
        "incremental": True,
        "since_column": "DTULTALTER",
        "batch": 2000,
        # PCPREST guarda a vida inteira da empresa (33 milhões de linhas numa
        # distribuidora). Carga gradual pela emissão, no máximo 12 meses.
        "backfill_meses": 12,
        "backfill_passo": 3,
        "sql": """
SELECT P.NUMTRANSVENDA || '-' || P.PREST AS EXTERNAL_ID,
       P.DUPLIC, P.PREST, P.CODCLI, P.CODFILIAL, P.NUMPED, P.VALOR, P.CODCOB,
       TO_CHAR(P.DTEMISSAO,'YYYY-MM-DD') AS DTEMISSAO,
       TO_CHAR(P.DTVENC,'YYYY-MM-DD') AS DTVENC,
       TO_CHAR(P.DTPAG,'YYYY-MM-DD') AS DTPAG,
       P.VPAGO, P.VALORMULTA, P.VALORDESC,
       TO_CHAR(P.DTVENCANTERIOR,'YYYY-MM-DD') AS DTVENCANTERIOR,
       CASE WHEN P.DTCANCEL IS NOT NULL THEN 'canceled'
            WHEN P.DTPAG IS NOT NULL THEN 'paid'
            ELSE 'open' END AS STATUS,
       TO_CHAR(P.DTULTALTER,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTER
FROM PCPREST P
WHERE P.DTEMISSAO >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -:janela)
  AND (:since IS NULL OR P.DTULTALTER > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCLANC (PCPAGAR não existe) + PCCONTA — contas a pagar / despesas
        "entity": "title_payable",
        "label": "Contas a pagar (PCLANC)",
        "every_minutes": 30,
        "incremental": True,
        "since_column": "DTULTALTER",
        "batch": 2000,
        "backfill_meses": 12,
        "backfill_passo": 3,
        "sql": """
SELECT L.RECNUM, L.CODFORNEC, L.NUMNOTA, L.HISTORICO, CT.CONTA, L.TIPOSERVICO,
       L.FORMAPGTO, L.CODFILIAL, L.VALOR,
       TO_CHAR(L.DTEMISSAO,'YYYY-MM-DD') AS DTEMISSAO,
       TO_CHAR(L.DTCOMPETENCIA,'YYYY-MM-DD') AS DTCOMPETENCIA,
       TO_CHAR(L.DTVENC,'YYYY-MM-DD') AS DTVENC,
       TO_CHAR(L.DTPAGTO,'YYYY-MM-DD') AS DTPAGTO,
       L.VPAGO, L.CODFUNCAUTOR1, L.CODFUNCAUTOR2,
       CASE WHEN NVL(L.ADIANTAMENTO,'N') = 'S' THEN 1 ELSE 0 END AS IS_ADVANCE,
       L.VLRUTILIZADOADIANTFORNEC,
       CASE WHEN L.DTCANCEL IS NOT NULL OR NVL(L.LANCEXCLUIDO,'N') = 'S' THEN 'canceled'
            WHEN L.DTPAGTO IS NOT NULL THEN 'paid'
            ELSE 'open' END AS STATUS,
       TO_CHAR(L.DTULTALTER,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTER
FROM PCLANC L
LEFT JOIN PCCONTA CT ON CT.CODCONTA = L.CODCONTA
WHERE L.DTEMISSAO >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -:janela)
  AND (:since IS NULL OR L.DTULTALTER > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCFINANC — fotografia diária: caixa, bancos, CR, CP, estoque, CMV. Janela 120 dias.
        "entity": "financial_snapshot",
        "label": "Fotografia financeira diária (PCFINANC)",
        "every_minutes": 120,
        "incremental": True,
        "since_column": "DATA",
        "sql": """
SELECT F.CODFILIAL || '-' || TO_CHAR(F.DATA,'YYYY-MM-DD') AS EXTERNAL_ID,
       F.CODFILIAL, F.SALDOBCO, F.SALDOCX, F.SALDOAPLI, F.SALDOCR, F.SALDOCP,
       F.SALDOESTFIN, F.SALDOREAL, F.VENDAREAL, F.RECEBREAL, F.CMVREAL,
       TO_CHAR(F.DATA,'YYYY-MM-DD') AS DATA
FROM PCFINANC F
WHERE F.DATA >= ADD_MONTHS(TRUNC(SYSDATE), -12)
  AND (:since IS NULL OR F.DATA >= TRUNC(SYSDATE) - 7)
""",
    },
    {  # PCBANCO (+ saldo PCESTCR) — pequena: recarga cheia
        "entity": "bank_account",
        "label": "Contas bancárias (PCBANCO)",
        "every_minutes": 120,
        "sql": """
SELECT B.CODBANCO, B.NOME, B.NUMBANCO, B.AGENCIA, B.CONTA, B.TIPOCXBCO, B.CODFILIAL,
       (SELECT SUM(E.VALOR) FROM PCESTCR E WHERE E.CODBANCO = B.CODBANCO) AS SALDO
FROM PCBANCO B
""",
    },
    {  # PCMOVCR — extrato de conta corrente: entradas (D) e saídas (C) reais de caixa.
       # Carga gradual até 12 meses; reprocessa 7 dias por ciclo (estornos somem via DTESTORNO).
        "entity": "cash_movement",
        "label": "Extrato bancário (PCMOVCR)",
        "every_minutes": 60,
        "incremental": True,
        "since_column": "DATA",
        "batch": 2000,
        "backfill_meses": 12,
        "backfill_passo": 3,
        "sql": """
SELECT M.NUMTRANS || '-' || M.CODBANCO || '-' || M.CODCOB AS EXTERNAL_ID,
       M.NUMTRANS, TO_CHAR(M.DATA,'YYYY-MM-DD') AS DATA, M.CODBANCO, M.CODCOB,
       M.CODFILIAL, M.VALOR, M.TIPO, M.HISTORICO, M.VLSALDO, M.CODCLI, M.CODROTINALANC,
       TO_CHAR(M.DTCONCIL,'YYYY-MM-DD') AS DTCONCIL,
       TO_CHAR(M.DTCOMPENSACAO,'YYYY-MM-DD') AS DTCOMPENSACAO
FROM PCMOVCR M
WHERE M.DTESTORNO IS NULL
  AND M.DATA >= ADD_MONTHS(TRUNC(SYSDATE), -:janela)
  AND (:since IS NULL OR M.DATA >= TRUNC(SYSDATE) - 7)
""",
    },
    {  # PCEST — saldo por produto×filial. Leitura CHEIA: a marca DTULTALTERSRVPRC
       # só é mexida pelo servidor de preços, não pela venda (congelava o saldo).
        "entity": "stock",
        "label": "Estoque por filial (PCEST)",
        "every_minutes": 120,
        "batch": 2000,
        "sql": """
SELECT E.CODFILIAL || '-' || E.CODPROD AS EXTERNAL_ID,
       E.CODPROD, E.CODFILIAL, NVL(E.QTEST,0) AS QTEST, NVL(E.QTRESERV,0) AS QTRESERV,
       NVL(E.QTBLOQUEADA,0) AS QTBLOQUEADA,
       E.ESTMIN, E.ESTMAX, E.ESTIDEAL, E.CUSTOREAL, E.CUSTOULTENT, E.CUSTOREP,
       E.QTVENDMES, E.QTGIRODIA, E.QTVENDAPERDIDA,
       TO_CHAR(E.DTULTENT,'YYYY-MM-DD') AS DTULTENT,
       TO_CHAR(E.DTULTSAIDA,'YYYY-MM-DD') AS DTULTSAIDA,
       TO_CHAR(E.DTULTINVENT,'YYYY-MM-DD') AS DTULTINVENT
FROM PCEST E
""",
    },
    {  # PCPEDC — carteira e conversão pedido→nota. Janela deslizante de 7 dias; 12 meses.
        "entity": "order",
        "label": "Pedidos de venda (PCPEDC)",
        "every_minutes": 30,
        "incremental": True,
        "since_column": "DATA",
        "batch": 1000,
        "backfill_meses": 12,
        "backfill_passo": 2,
        "sql": """
SELECT C.NUMPED, C.CODFILIAL, C.CODCLI, C.CODUSUR, C.CONDVENDA, C.CODPLPAG,
       C.VLDESCONTO, C.VLFRETE, C.TOTPESO, C.VLCUSTOREAL, C.VLTOTAL, C.NUMNOTA,
       TO_CHAR(C.DTENTREGA,'YYYY-MM-DD') AS DTENTREGA,
       TO_CHAR(C.DTFAT,'YYYY-MM-DD') AS DTFAT,
       CASE WHEN C.DTCANCEL IS NOT NULL OR C.POSICAO = 'C' THEN 'canceled'
            WHEN C.POSICAO = 'F' OR C.DTFAT IS NOT NULL THEN 'shipped'
            ELSE 'pending' END AS STATUS,
       C.POSICAO AS POSICAO,
       (SELECT SUM(NVL(I.QTFALTA,0)) FROM PCPEDI I WHERE I.NUMPED = C.NUMPED) AS QTFALTA,
       TO_CHAR(C.DATA,'YYYY-MM-DD') AS DATA
FROM PCPEDC C
WHERE C.DATA >= ADD_MONTHS(TRUNC(SYSDATE), -:janela)
  AND (:since IS NULL OR C.DATA >= TRUNC(SYSDATE) - 7)
""",
    },
    {  # PCNFENT — compras; agrega por NUMTRANSENT (PK real tem CODCONT)
        "entity": "purchase",
        "label": "Notas de entrada (PCNFENT)",
        "every_minutes": 60,
        "incremental": True,
        "since_column": "DTLANCTO",
        "sql": """
SELECT N.NUMTRANSENT, MAX(N.NUMNOTA) AS NUMNOTA, MAX(N.SERIE) AS SERIE,
       MAX(N.CODFORNEC) AS CODFORNEC, MAX(N.CODFILIAL) AS CODFILIAL,
       TO_CHAR(MAX(N.DTEMISSAO),'YYYY-MM-DD') AS DTEMISSAO,
       TO_CHAR(MAX(N.DTENT),'YYYY-MM-DD') AS DTENT,
       MAX(N.VLTOTAL) AS VLTOTAL, MAX(N.VLICMS) AS VLICMS,
       MAX(N.VLIPI) AS VLIPI, MAX(N.VLFRETE) AS VLFRETE,
       TO_CHAR(MAX(N.DTLANCTO),'YYYY-MM-DD HH24:MI:SS') AS DTLANCTO
FROM PCNFENT N
WHERE N.DTENT >= ADD_MONTHS(TRUNC(SYSDATE), -12)
  AND (:since IS NULL OR N.DTLANCTO > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS') - 7)
GROUP BY N.NUMTRANSENT
""",
    },
    {  # PCCARREG — cargas/entregas (volume, peso, frete); watermark DTULTALTER
        "entity": "load",
        "label": "Carregamentos (PCCARREG)",
        "every_minutes": 60,
        "incremental": True,
        "since_column": "DTULTALTER",
        "sql": """
SELECT C.NUMCAR, C.CODFILIALSAIDA, E.NOME AS MOTORISTA, V.PLACA, C.CODROTAPRINC,
       C.DESTINO, C.NUMNOTAS, C.NUMENT, C.NUMCID, C.KMINICIAL, C.KMFINAL,
       C.TOTPESO, C.VLTOTAL, C.VLFRETE,
       TO_CHAR(C.DTSAIDA,'YYYY-MM-DD') AS DTSAIDA,
       TO_CHAR(C.DTRETORNO,'YYYY-MM-DD') AS DTRETORNO,
       TO_CHAR(C.DATAMON,'YYYY-MM-DD HH24:MI:SS') AS DATAMON,
       TO_CHAR(C.DATACONF,'YYYY-MM-DD HH24:MI:SS') AS DATACONF,
       TO_CHAR(C.DTFECHA,'YYYY-MM-DD HH24:MI:SS') AS DTFECHA,
       R.PRAZOPREVENT,
       CASE WHEN C.DT_CANCEL IS NOT NULL THEN 'canceled'
            WHEN C.DTRETORNO IS NOT NULL THEN 'returned'
            WHEN C.DTSAIDA IS NOT NULL THEN 'dispatched'
            ELSE 'open' END AS STATUS,
       TO_CHAR(C.DTULTALTER,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTER
FROM PCCARREG C
LEFT JOIN PCEMPR E    ON E.MATRICULA = C.CODMOTORISTA
LEFT JOIN PCVEICUL V  ON V.CODVEICULO = C.CODVEICULO
LEFT JOIN PCROTAEXP R ON R.CODROTA = C.CODROTAPRINC
WHERE C.DTSAIDA >= ADD_MONTHS(TRUNC(SYSDATE), -12)
  AND (:since IS NULL OR C.DTULTALTER > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCMETA — metas cadastradas no ERP por filial × RCA × mês. Alimenta a
       # meta dos indicadores marcados com erp_target. Recoleta 3 meses (ajustes).
        "entity": "target",
        "label": "Metas do ERP (PCMETA)",
        "every_minutes": 720,
        "incremental": True,
        "since_column": "DATA",
        "sql": """
SELECT M.CODFILIAL || '-' || M.CODUSUR || '-' || M.TIPOMETA || '-' || TO_CHAR(M.DATA,'YYYYMM')
         || '-' || NVL(M.CODIGO, 0) AS EXTERNAL_ID,
       M.CODFILIAL, M.CODUSUR, M.TIPOMETA,
       TO_CHAR(TRUNC(M.DATA,'MM'),'YYYY-MM-DD') AS DATA,
       M.VLVENDAPREV, M.QTVENDAPREV, M.MIXPREV, M.CLIPOSPREV, M.PERCLIPOSPREV,
       M.MARGEMPREV, M.PEDIDOSPREV, M.VLMEDIOPEDIDO, M.QTDCLIENTESATIVO
FROM PCMETA M
WHERE M.DATA >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -12)
  AND (NVL(M.VLVENDAPREV,0) > 0 OR NVL(M.CLIPOSPREV,0) > 0 OR NVL(M.MIXPREV,0) > 0
       OR NVL(M.MARGEMPREV,0) > 0 OR NVL(M.PEDIDOSPREV,0) > 0)
  AND (:since IS NULL OR M.DATA >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -3))
""",
    },
    {  # PCMETARCA — meta DIÁRIA por filial × RCA (é onde a rotina de metas do
       # WinThor de fato grava). Soma do mês = meta mensal; dia/semana exatos.
        "entity": "target_daily",
        "label": "Metas diárias do ERP (PCMETARCA)",
        "every_minutes": 360,
        "incremental": True,
        "since_column": "DTMXSALTER",
        "sql": """
SELECT R.CODFILIAL || '-' || R.CODUSUR || '-' || TO_CHAR(R.DATA,'YYYYMMDD') AS EXTERNAL_ID,
       R.CODFILIAL, R.CODUSUR,
       TO_CHAR(R.DATA,'YYYY-MM-DD') AS DATA,
       SUM(NVL(R.VLVENDAPREV,0)) AS VLVENDAPREV, SUM(NVL(R.NUMCLIPOS,0)) AS NUMCLIPOS,
       SUM(NVL(R.QTPEDPREV,0)) AS QTPEDPREV, SUM(NVL(R.QTITENSPEDPREV,0)) AS QTITENSPEDPREV,
       MAX(R.PERVENDAPREV) AS PERVENDAPREV,
       TO_CHAR(MAX(NVL(R.DTMXSALTER, R.DATA)),'YYYY-MM-DD HH24:MI:SS') AS DTMXSALTER
FROM PCMETARCA R
WHERE R.DATA >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -12)
GROUP BY R.CODFILIAL, R.CODUSUR, R.DATA
HAVING (SUM(NVL(R.VLVENDAPREV,0)) > 0 OR SUM(NVL(R.NUMCLIPOS,0)) > 0 OR SUM(NVL(R.QTPEDPREV,0)) > 0)
   AND (:since IS NULL OR MAX(NVL(R.DTMXSALTER, R.DATA)) > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCBLOQUEIOSPEDIDO — fila de bloqueio de pedidos. Carga CHEIA de 3 meses:
       # a Integradora apaga a linha ao liberar, e a linha que some deixa de ser
       # atualizada aqui (synced_at velho = saiu da fila).
        "entity": "order_block",
        "label": "Bloqueios de pedido (PCBLOQUEIOSPEDIDO)",
        "every_minutes": 60,
        "opcional": True,
        "sql": """
SELECT TO_CHAR(B.CODIGO) AS CODIGO, TO_CHAR(B.NUMPED) AS NUMPED, B.CODMOTIVO,
       NVL(M.DESCRICAO, B.MOTIVO) AS MOTIVO_DESC, B.STATUS, B.TIPO, B.CODFUNCLIBERA,
       TO_CHAR(B.DTINCLUSAO,'YYYY-MM-DD HH24:MI:SS') AS DTINCLUSAO,
       TO_CHAR(B.DTLIBERA,'YYYY-MM-DD HH24:MI:SS') AS DTLIBERA
FROM PCBLOQUEIOSPEDIDO B
LEFT JOIN PCMOTBLOQUEIO M ON M.CODMOTIVO = B.CODMOTIVO
WHERE B.DTINCLUSAO >= ADD_MONTHS(TRUNC(SYSDATE), -3)
""",
    },
    {  # PCPEDCFV — caixa de entrada do força de vendas (o que o RCA transmitiu).
       # Carga cheia de 2 meses; pendente = IMPORTADO = 0 e sem NUMPED.
        "entity": "fv_order",
        "label": "Pedidos do força de vendas (PCPEDCFV)",
        "every_minutes": 30,
        "opcional": True,
        "sql": """
SELECT F.CODUSUR || '-' || F.NUMPEDRCA AS EXTERNAL_ID,
       TO_CHAR(F.NUMPEDRCA) AS NUMPEDRCA, F.CODUSUR, F.CODCLI, F.CODFILIAL,
       TO_CHAR(F.NUMPED) AS NUMPED, NVL(F.IMPORTADO, 0) AS IMPORTADO, F.POSICAO_ATUAL,
       TO_CHAR(F.DTINCLUSAO,'YYYY-MM-DD HH24:MI:SS') AS DTINCLUSAO,
       TO_CHAR(F.DTALTERACAO,'YYYY-MM-DD HH24:MI:SS') AS DTALTERACAO
FROM PCPEDCFV F
WHERE F.DTINCLUSAO >= ADD_MONTHS(TRUNC(SYSDATE), -2)
""",
    },
    {  # PCCRECLI — créditos de cliente (devolução, cashback). Reprocessa 7 dias
       # por lançamento, uso, estorno ou cancelamento.
        "entity": "customer_credit",
        "label": "Créditos de cliente (PCCRECLI)",
        "every_minutes": 120,
        "incremental": True,
        "since_column": "DTLANC",
        "batch": 1000,
        "opcional": True,
        "sql": """
SELECT NVL(TO_CHAR(C.CODIGO), C.CODCLI || '-' || NVL(C.NUMTRANSVENDA, 0) || '-' || TO_CHAR(C.DTLANC,'YYYYMMDDHH24MISS')) AS EXTERNAL_ID,
       C.CODCLI, C.CODFILIAL, C.VALOR, C.ORIGEM, C.SITUACAO, TO_CHAR(C.NUMNOTA) AS NUMNOTA,
       TO_CHAR(C.DTLANC,'YYYY-MM-DD') AS DTLANC,
       TO_CHAR(C.DTDESCONTO,'YYYY-MM-DD') AS DTDESCONTO,
       TO_CHAR(C.DTVENC,'YYYY-MM-DD') AS DTVENC,
       TO_CHAR(C.DTCANCEL,'YYYY-MM-DD') AS DTCANCEL,
       TO_CHAR(C.DTESTORNO,'YYYY-MM-DD') AS DTESTORNO,
       CASE WHEN NVL(C.CASHBACK,'N') = 'S' THEN 1 ELSE 0 END AS IS_CASHBACK,
       TO_CHAR(C.DTVALIDADECASHBACK,'YYYY-MM-DD') AS DTVALIDADECASHBACK
FROM PCCRECLI C
WHERE C.DTLANC >= ADD_MONTHS(TRUNC(SYSDATE), -12)
  AND (:since IS NULL OR C.DTLANC >= TRUNC(SYSDATE) - 7 OR C.DTDESCONTO >= TRUNC(SYSDATE) - 7
       OR C.DTESTORNO >= TRUNC(SYSDATE) - 7 OR C.DTCANCEL >= TRUNC(SYSDATE) - 7
       OR (C.DTDESCONTO IS NULL AND C.DTCANCEL IS NULL AND C.DTESTORNO IS NULL))
""",
    },
    {  # PCAUTORC — autorizações de crédito acima do limite.
        "entity": "credit_auth",
        "label": "Autorizações de crédito (PCAUTORC)",
        "every_minutes": 120,
        "incremental": True,
        "since_column": "DATA",
        "opcional": True,
        "sql": """
SELECT A.NUMPEDIDO || '-' || TO_CHAR(A.DATA,'YYYYMMDDHH24MISS') AS EXTERNAL_ID,
       TO_CHAR(A.NUMPEDIDO) AS NUMPEDIDO, A.CODCLI, A.CODUSUR, A.CODFUNC,
       TO_CHAR(A.DATA,'YYYY-MM-DD') AS DATA, A.LIMCRED, A.VLPENDENTE, A.VLLIBERADO,
       TO_CHAR(A.DTUTILIZACAO,'YYYY-MM-DD') AS DTUTILIZACAO,
       TO_CHAR(A.NUMPEDUTILIZACAO) AS NUMPEDUTILIZACAO
FROM PCAUTORC A
WHERE A.DATA >= ADD_MONTHS(TRUNC(SYSDATE), -12)
  AND (:since IS NULL OR A.DATA >= TRUNC(SYSDATE) - 7 OR A.DTUTILIZACAO >= TRUNC(SYSDATE) - 7)
""",
    },
    {  # PCBAIXACARTAOI (+ C) — parcelas de cartão conciliadas: bruto × líquido.
        "entity": "card_settlement",
        "label": "Conciliação de cartão (PCBAIXACARTAOI)",
        "every_minutes": 120,
        "incremental": True,
        "since_column": "DATA",
        "batch": 2000,
        "opcional": True,
        "backfill_meses": 12,
        "backfill_passo": 3,
        "sql": """
SELECT TO_CHAR(I.CODBAIXAITEM) AS CODBAIXAITEM, C.CODFILIAL, I.CODCLI,
       TO_CHAR(I.DATA,'YYYY-MM-DD') AS DATA,
       TO_CHAR(I.DATACREDITO,'YYYY-MM-DD') AS DATACREDITO,
       TO_CHAR(I.DTBAIXA,'YYYY-MM-DD') AS DTBAIXA,
       I.PARCELA, I.QTTOTALPARCELAS, I.VALORPARCELA, I.VALORPARCELALIQUIDO, I.TAXA,
       I.CODREDE, I.CODBANDEIRA, I.TIPOPRODUTO, NVL(I.STATUS, I.SITUACAO) AS STATUS
FROM PCBAIXACARTAOI I
LEFT JOIN PCBAIXACARTAOC C ON C.CODBAIXACARTAO = I.CODBAIXACARTAO
WHERE I.DATA >= ADD_MONTHS(TRUNC(SYSDATE), -:janela)
  AND (:since IS NULL OR I.DATA >= TRUNC(SYSDATE) - 7 OR I.DTBAIXA >= TRUNC(SYSDATE) - 7)
""",
    },
    {  # PCCUPOMFISCALZ — redução Z: cupons e venda bruta por ECF × dia (lojas).
        "entity": "pos_daily",
        "label": "Redução Z do PDV (PCCUPOMFISCALZ)",
        "every_minutes": 120,
        "incremental": True,
        "since_column": "DTEMISSAO",
        "opcional": True,
        "sql": """
SELECT Z.CODFILIAL || '-' || Z.NUMECF || '-' || TO_CHAR(Z.DTEMISSAO,'YYYYMMDD') || '-' || NVL(Z.NUMREDUCAOZ, 0) AS EXTERNAL_ID,
       Z.CODFILIAL, TO_CHAR(Z.NUMECF) AS NUMECF,
       TO_CHAR(Z.DTEMISSAO,'YYYY-MM-DD') AS DTEMISSAO,
       GREATEST(NVL(Z.NUMCUPOMFIM, 0) - NVL(Z.NUMCUPOMINICIO, 0) + 1, 0) AS CUPONS,
       Z.VENDABRUTA, Z.VLCONTABIL
FROM PCCUPOMFISCALZ Z
WHERE Z.DTEMISSAO >= ADD_MONTHS(TRUNC(SYSDATE), -12)
  AND (:since IS NULL OR Z.DTEMISSAO >= TRUNC(SYSDATE) - 7)
""",
    },
    {  # PCPEDIDO (+ PCITEM agregado) — pedidos de compra: previsão × entrega.
       # Reprocessa 7 dias e TODOS os que ainda não entregaram por completo.
        "entity": "purchase_order",
        "label": "Pedidos de compra (PCPEDIDO)",
        "every_minutes": 120,
        "incremental": True,
        "since_column": "DTEMISSAO",
        "opcional": True,
        "sql": """
SELECT TO_CHAR(P.NUMPED) AS NUMPED, P.CODFORNEC, P.CODFILIAL, P.CODCOMPRADOR,
       TO_CHAR(P.DTEMISSAO,'YYYY-MM-DD') AS DTEMISSAO,
       TO_CHAR(P.DTPREVENT,'YYYY-MM-DD') AS DTPREVENT,
       TO_CHAR(P.DTENTRADAESTOQUE,'YYYY-MM-DD') AS DTENTRADAESTOQUE,
       P.VLTOTAL, P.VLENTREGUE,
       (SELECT COUNT(*) FROM PCITEM I WHERE I.NUMPED = P.NUMPED) AS ITENS,
       (SELECT SUM(NVL(I.QTPEDIDA,0)) FROM PCITEM I WHERE I.NUMPED = P.NUMPED) AS QTPEDIDA,
       (SELECT SUM(NVL(I.QTENTREGUE,0)) FROM PCITEM I WHERE I.NUMPED = P.NUMPED) AS QTENTREGUE
FROM PCPEDIDO P
WHERE P.DTEMISSAO >= ADD_MONTHS(TRUNC(SYSDATE), -12)
  AND (:since IS NULL OR P.DTEMISSAO >= TRUNC(SYSDATE) - 7 OR NVL(P.VLENTREGUE,0) < NVL(P.VLTOTAL,0) * 0.99)
""",
    },
    {  # PCVERBA — verbas de fornecedor (acordos comerciais). Reprocessa as abertas.
        "entity": "supplier_credit",
        "label": "Verbas de fornecedor (PCVERBA)",
        "every_minutes": 240,
        "incremental": True,
        "since_column": "DTEMISSAO",
        "opcional": True,
        "sql": """
SELECT TO_CHAR(V.NUMVERBA) AS NUMVERBA, V.CODFORNEC, V.CODFILIAL, V.TIPO, V.ORIGEM,
       TO_CHAR(V.DTEMISSAO,'YYYY-MM-DD') AS DTEMISSAO,
       TO_CHAR(V.DTVENC,'YYYY-MM-DD') AS DTVENC,
       V.VALOR, V.VPAGO,
       TO_CHAR(V.DTQUITACAO,'YYYY-MM-DD') AS DTQUITACAO,
       TO_CHAR(V.DTCANCEL,'YYYY-MM-DD') AS DTCANCEL
FROM PCVERBA V
WHERE V.DTEMISSAO >= ADD_MONTHS(TRUNC(SYSDATE), -12)
  AND (:since IS NULL OR V.DTEMISSAO >= TRUNC(SYSDATE) - 7 OR (V.DTQUITACAO IS NULL AND V.DTCANCEL IS NULL))
""",
    },
    {  # PCMANIFESTOELETRONICOC — MDF-e gerado × autorizado. Reprocessa os sem protocolo.
        "entity": "mdfe",
        "label": "MDF-e (PCMANIFESTOELETRONICOC)",
        "every_minutes": 120,
        "incremental": True,
        "since_column": "DATAHORAGERACAO",
        "opcional": True,
        "sql": """
SELECT M.NUMMDFE || '-' || M.CODFILIAL AS EXTERNAL_ID, TO_CHAR(M.NUMMDFE) AS NUMMDFE, M.CODFILIAL,
       TO_CHAR(M.DATAHORAGERACAO,'YYYY-MM-DD HH24:MI:SS') AS DATAHORAGERACAO,
       TO_CHAR(M.DATAHORAAUTORSEFAZ,'YYYY-MM-DD HH24:MI:SS') AS DATAHORAAUTORSEFAZ,
       M.SITUACAOMDFE, M.PROTOCOLOMDFE,
       CASE WHEN M.JUSTIFICATIVACANCEL IS NOT NULL THEN 1 ELSE 0 END AS IS_CANCELED,
       TO_CHAR(M.DATAHORAEVENTO,'YYYY-MM-DD HH24:MI:SS') AS DATAHORAEVENTO
FROM PCMANIFESTOELETRONICOC M
WHERE M.DATAHORAGERACAO >= ADD_MONTHS(TRUNC(SYSDATE), -12)
  AND (:since IS NULL OR M.DATAHORAGERACAO >= TRUNC(SYSDATE) - 7 OR M.PROTOCOLOMDFE IS NULL)
""",
    },
    {  # PCMOVENDPEND — a OS do WMS, agregada por NUMOS (uma linha por produto no
       # ERP). Só clientes com WMS: `opcional` faz o agente desistir em silêncio
       # se a tabela não existir ou não tiver GRANT. Janela curta (3 meses): é a
       # tabela mais movimentada do armazém. Reprocessa 3 dias por ciclo.
        "entity": "wms_os",
        "label": "OS do WMS (PCMOVENDPEND)",
        "every_minutes": 60,
        "incremental": True,
        "since_column": "DATA",
        "batch": 1000,
        "opcional": True,
        "backfill_meses": 3,
        "backfill_passo": 1,
        "sql": """
SELECT TO_CHAR(M.NUMOS) AS NUMOS, MAX(M.TIPOOS) AS TIPOOS, MAX(M.CODOPER) AS CODOPER,
       MAX(M.CODFILIAL) AS CODFILIAL, MAX(M.NUMPED) AS NUMPED, MAX(M.NUMCAR) AS NUMCAR,
       TO_CHAR(MIN(M.DATA),'YYYY-MM-DD') AS DATA, MAX(M.POSICAO) AS POSICAO,
       COUNT(*) AS LINHAS,
       SUM(NVL(M.QT,0)) AS QT, SUM(NVL(M.QTSEPARADA,0)) AS QTSEPARADA,
       SUM(NVL(M.QTCONFERIDA,0)) AS QTCONFERIDA, SUM(NVL(M.QTCANCEL,0)) AS QTCANCEL,
       SUM(NVL(M.QTERROS,0)) AS QTERROS,
       TO_CHAR(MIN(M.DTINICIOOS),'YYYY-MM-DD HH24:MI:SS') AS DTINICIOOS,
       TO_CHAR(CASE WHEN COUNT(*) = COUNT(M.DTFIMSEPARACAO) THEN MAX(M.DTFIMSEPARACAO) END,'YYYY-MM-DD HH24:MI:SS') AS DTFIMSEPARACAO,
       TO_CHAR(MIN(M.DTINICIOCONFERENCIA),'YYYY-MM-DD HH24:MI:SS') AS DTINICIOCONFERENCIA,
       TO_CHAR(CASE WHEN COUNT(*) = COUNT(M.DTFIMCONFERENCIA) THEN MAX(M.DTFIMCONFERENCIA) END,'YYYY-MM-DD HH24:MI:SS') AS DTFIMCONFERENCIA,
       MAX(M.CODFUNCOS) AS CODFUNCOS, MAX(M.CODFUNCCONF) AS CODFUNCCONF
FROM PCMOVENDPEND M
WHERE M.DTESTORNO IS NULL
  AND M.DATA >= ADD_MONTHS(TRUNC(SYSDATE), -:janela)
  AND (:since IS NULL OR M.DATA >= TRUNC(SYSDATE) - 3)
GROUP BY M.NUMOS
""",
    },
    {  # FusionTrak — cargas enviadas ao roteirizador (schema FUSIONT). Opcional:
       # só existe em quem usa FusionTrak; precisa de GRANT no schema FUSIONT.
        "entity": "route_load",
        "label": "Cargas roteirizadas (FusionTrak)",
        "every_minutes": 120,
        "incremental": True,
        "since_column": "T10_DATA_SAIDA",
        "opcional": True,
        "sql": """
SELECT TO_CHAR(C.CODIGO_INT) AS CODIGO_INT, C.CARGAS_GERADAS_ERP, C.T43_CODIGO_FILIAL_ERP,
       TO_CHAR(C.T10_DATA_SAIDA,'YYYY-MM-DD') AS T10_DATA_SAIDA,
       TO_CHAR(R.DTROTEIRIZACAO,'YYYY-MM-DD') AS DTROTEIRIZACAO,
       C.T06_CODIGO_ERP, C.T05_CODIGO_ERP, C.CODROTAPRINC,
       C.PESO, C.VOLUME, C.T06_PESO_MAX_ENTREGAS, C.T06_VOLUME_MAX_ENTREGAS, C.VALORTOTAL,
       C.NUMITENS, C.NUMCLIENTES, C.NUMCIDADES, C.STATUS_INT
FROM FUSIONT.FUSIONTRAK_INT_CARGA C
LEFT JOIN FUSIONT.FUSIONTRAK_CARGAS_ROTEIRIZADAS R ON TO_CHAR(R.NUMCAR) = C.CARGAS_GERADAS_ERP
WHERE C.T10_DATA_SAIDA >= ADD_MONTHS(TRUNC(SYSDATE), -12)
  AND (:since IS NULL OR C.T10_DATA_SAIDA >= TRUNC(SYSDATE) - 7)
""",
    },
    {  # FusionTrak — o que aconteceu na rua (ocorrências, km, posição).
        "entity": "delivery_event",
        "label": "Eventos de entrega (FusionTrak)",
        "every_minutes": 60,
        "incremental": True,
        "since_column": "DATA_EVENTO",
        "opcional": True,
        "sql": """
SELECT TO_CHAR(E.ID_PK) AS ID_PK, E.TIPO, TO_CHAR(E.DATA_EVENTO,'YYYY-MM-DD') AS DATA_EVENTO,
       E.SEQ_PEDIDO_ERP, E.CARGA_ERP, E.MOTORISTA_CODIGO_ERP, E.VEICULO_PLACA, E.KMATUAL,
       E.LATITUDE, E.LONGITUDE, E.MOTIVO_DEVOL_REENT_ID, E.OBS_MOTORISTA
FROM FUSIONT.FUSIONTRAK_INT_EVENTOS E
WHERE E.DATA_EVENTO >= ADD_MONTHS(TRUNC(SYSDATE), -12)
  AND (:since IS NULL OR E.DATA_EVENTO >= TRUNC(SYSDATE) - 7)
""",
    },
]

# Mapa campo_nosso -> ALIAS do SQL. Campo-FK recebe o CÓDIGO do ERP e o ingest
# resolve a instância local por external_id (ver sync.py).
DEFAULT_SYNC = {
    "branch": {"fields": {
        "external_id": "CODIGO", "code": "CODIGO", "name": "RAZAOSOCIAL",
        "trade_name": "FANTASIA", "cnpj": "CGC", "city": "CIDADE", "uf": "UF",
        "is_active": "IS_ACTIVE",
    }},
    "salesrep": {"fields": {
        "external_id": "CODUSUR", "code": "CODUSUR", "name": "NOME", "type": "TIPOVEND",
        "team": "CODEQUIPE", "supervisor": "SUPERVISOR", "sales_target": "VLVENDAPREV",
        "flex_balance": "VLCORRENTE", "flex_limit": "VLLIMCRED",
        "is_active": "IS_ACTIVE",
    }},
    "supplier": {"fields": {
        "external_id": "CODFORNEC", "name": "FORNECEDOR", "trade_name": "FANTASIA",
        "document": "CGC", "city": "CIDADE", "uf": "ESTADO", "type": "TIPOFORNEC",
        "lead_time_days": "PRAZOENTREGA", "last_purchase_at": "DTULTCOMPRA",
        "is_active": "IS_ACTIVE",
    }},
    "employee": {"fields": {
        "external_id": "MATRICULA", "registration": "MATRICULA", "name": "NOME",
        "role": "FUNCAO", "department": "CODSETOR", "branch": "CODFILIAL",
        "admission_date": "ADMISSAO", "dismissal_date": "DTDEMISSAO",
        "is_driver": "IS_DRIVER", "cnh_expires_at": "DTVALIDADECNH", "has_db_user": "HAS_DB_USER",
        "is_active": "IS_ACTIVE",
    }},
    "customer": {"fields": {
        "external_id": "CODCLI", "name": "CLIENTE", "trade_name": "FANTASIA",
        "document": "CGCENT", "person_type": "TIPOFJ", "city": "MUNICENT", "uf": "ESTENT",
        "activity": "CODATV1", "praca": "PRACA", "route": "ROTA", "region": "NUMREGIAO",
        "credit_limit": "LIMCRED", "sales_rep": "CODUSUR1", "blocked": "BLOCKED",
        "registered_at": "DTCADASTRO", "first_purchase_at": "DTPRIMCOMPRA",
        "last_purchase_at": "DTULTCOMP",
    }},
    "product": {"fields": {
        "external_id": "CODPROD", "code": "CODPROD", "name": "DESCRICAO", "ean": "CODAUXILIAR",
        "unit": "UNIDADE", "packaging": "EMBALAGEM", "brand": "MARCA",
        "department": "DEPARTAMENTO", "section": "SECAO", "category": "CATEGORIA",
        "supplier": "CODFORNEC", "abc_class": "CLASSE", "cost_price": "CUSTOREAL",
        "price": "PVENDA", "net_weight": "PESOLIQ", "is_active": "IS_ACTIVE",
    }},
    "sales_invoice": {"fields": {
        "external_id": "NUMTRANSVENDA", "number": "NUMNOTA", "series": "SERIE",
        "branch": "CODFILIAL", "customer": "CODCLI", "sales_rep": "CODUSUR",
        "sale_type": "CONDVENDA", "operation": "TIPOVENDA", "order_number": "NUMPED",
        "load_number": "NUMCAR", "issued_at": "DTSAIDA", "canceled_at": "DTCANCEL",
        "total": "VLTOTAL", "total_general": "VLTOTGER", "discount": "VLDESCONTO",
        "freight": "VLFRETE", "ipi_value": "VLIPI", "icms_value": "VLICMS",
        "nfe_status": "SITUACAONFE", "kind": "ESPECIE",
    }},
    "sales_invoice_item": {"fields": {
        "external_id": "NUMTRANSITEM", "invoice": "NUMTRANSVENDA", "invoice_number": "NUMNOTA",
        "operation": "CODOPER", "branch": "CODFILIAL", "product": "CODPROD",
        "customer": "CODCLI", "sales_rep": "CODUSUR", "department": "CODEPTO",
        "section": "CODSEC", "quantity": "QT", "boxes": "QTCX", "unit_price": "PUNIT",
        "table_price": "PTABELA", "discount": "VLDESCONTO", "cost_real": "CUSTOREAL",
        "cost": "CUSTOFIN", "order_number": "NUMPED", "moved_at": "DTMOV",
    }},
    "title_receivable": {"fields": {
        "external_id": "EXTERNAL_ID", "number": "DUPLIC", "installment": "PREST",
        "customer": "CODCLI", "branch": "CODFILIAL", "order": "NUMPED", "amount": "VALOR",
        "collection_type": "CODCOB", "issue_date": "DTEMISSAO", "due_date": "DTVENC",
        "paid_at": "DTPAG", "amount_paid": "VPAGO", "fine": "VALORMULTA", "status": "STATUS",
        "discount_paid": "VALORDESC", "previous_due_date": "DTVENCANTERIOR",
    }},
    "title_payable": {"fields": {
        "external_id": "RECNUM", "supplier": "CODFORNEC", "number": "NUMNOTA",
        "description": "HISTORICO", "account": "CONTA", "tax_type": "TIPOSERVICO",
        "payment_method": "FORMAPGTO", "branch": "CODFILIAL", "amount": "VALOR",
        "issue_date": "DTEMISSAO", "accrual_date": "DTCOMPETENCIA", "due_date": "DTVENC",
        "paid_at": "DTPAGTO", "amount_paid": "VPAGO", "status": "STATUS",
        "authorizer1": "CODFUNCAUTOR1", "authorizer2": "CODFUNCAUTOR2",
        "is_advance": "IS_ADVANCE", "advance_used": "VLRUTILIZADOADIANTFORNEC",
    }},
    "financial_snapshot": {"fields": {
        "external_id": "EXTERNAL_ID", "branch": "CODFILIAL", "date": "DATA",
        "bank_balance": "SALDOBCO", "cash_balance": "SALDOCX", "investments": "SALDOAPLI",
        "receivables": "SALDOCR", "payables": "SALDOCP", "stock_value": "SALDOESTFIN",
        "net_position": "SALDOREAL", "sales_real": "VENDAREAL",
        "received_real": "RECEBREAL", "cmv_real": "CMVREAL",
    }},
    "bank_account": {"fields": {
        "external_id": "CODBANCO", "name": "NOME", "bank_number": "NUMBANCO",
        "agency": "AGENCIA", "account": "CONTA", "account_type": "TIPOCXBCO",
        "branch": "CODFILIAL", "balance": "SALDO",
    }},
    "cash_movement": {"fields": {
        "external_id": "EXTERNAL_ID", "transaction": "NUMTRANS", "moved_at": "DATA",
        "bank_account": "CODBANCO", "currency": "CODCOB", "branch": "CODFILIAL",
        "amount": "VALOR", "kind": "TIPO", "history": "HISTORICO", "balance_after": "VLSALDO",
        "customer": "CODCLI", "routine": "CODROTINALANC", "reconciled_at": "DTCONCIL",
        "settled_at": "DTCOMPENSACAO",
    }},
    "stock": {"fields": {
        "external_id": "EXTERNAL_ID", "product": "CODPROD", "branch": "CODFILIAL",
        "quantity": "QTEST", "reserved": "QTRESERV", "blocked": "QTBLOQUEADA",
        "min_stock": "ESTMIN", "max_stock": "ESTMAX", "ideal_stock": "ESTIDEAL",
        "avg_cost": "CUSTOREAL", "last_entry_cost": "CUSTOULTENT",
        "replacement_cost": "CUSTOREP", "qty_sold_month": "QTVENDMES",
        "daily_turnover": "QTGIRODIA", "qty_lost_sales": "QTVENDAPERDIDA",
        "last_entry_at": "DTULTENT", "last_exit_at": "DTULTSAIDA", "last_inventory_at": "DTULTINVENT",
    }},
    "order": {"fields": {
        "external_id": "NUMPED", "number": "NUMPED", "branch": "CODFILIAL",
        "customer": "CODCLI", "sales_rep": "CODUSUR", "status": "STATUS",
        "erp_position": "POSICAO", "erp_cut_qty": "QTFALTA", "sale_type": "CONDVENDA",
        "payment_term": "CODPLPAG", "discount": "VLDESCONTO", "freight": "VLFRETE",
        "total_weight": "TOTPESO", "cost_total": "VLCUSTOREAL", "total": "VLTOTAL",
        "order_date": "DATA", "delivery_date": "DTENTREGA", "invoiced_at": "DTFAT",
        "invoice_number": "NUMNOTA",
    }},
    "purchase": {"fields": {
        "external_id": "NUMTRANSENT", "number": "NUMNOTA", "series": "SERIE",
        "supplier": "CODFORNEC", "branch": "CODFILIAL", "issue_date": "DTEMISSAO",
        "entry_date": "DTENT", "total": "VLTOTAL", "icms_value": "VLICMS",
        "ipi_value": "VLIPI", "freight": "VLFRETE",
    }},
    "load": {"fields": {
        "external_id": "NUMCAR", "number": "NUMCAR", "branch": "CODFILIALSAIDA",
        "driver": "MOTORISTA", "vehicle_plate": "PLACA", "route": "CODROTAPRINC",
        "destination": "DESTINO", "departure_date": "DTSAIDA", "return_date": "DTRETORNO",
        "num_invoices": "NUMNOTAS", "num_customers": "NUMENT", "num_cities": "NUMCID",
        "km_start": "KMINICIAL", "km_end": "KMFINAL",
        "total_weight": "TOTPESO", "total_value": "VLTOTAL",
        "freight": "VLFRETE", "status": "STATUS",
        "assembled_at": "DATAMON", "checked_at": "DATACONF", "closed_at": "DTFECHA",
        "route_lead_days": "PRAZOPREVENT",
    }},
    "order_block": {"fields": {
        "external_id": "CODIGO", "order_number": "NUMPED", "reason_code": "CODMOTIVO",
        "reason": "MOTIVO_DESC", "status": "STATUS", "kind": "TIPO", "released_by": "CODFUNCLIBERA",
        "blocked_at": "DTINCLUSAO", "released_at": "DTLIBERA",
    }},
    "fv_order": {"fields": {
        "external_id": "EXTERNAL_ID", "rca_order_number": "NUMPEDRCA", "sales_rep": "CODUSUR",
        "customer": "CODCLI", "branch": "CODFILIAL", "order_number": "NUMPED", "imported": "IMPORTADO",
        "position": "POSICAO_ATUAL", "received_at": "DTINCLUSAO", "changed_at": "DTALTERACAO",
    }},
    "customer_credit": {"fields": {
        "external_id": "EXTERNAL_ID", "customer": "CODCLI", "branch": "CODFILIAL", "amount": "VALOR",
        "origin": "ORIGEM", "situation": "SITUACAO", "invoice_number": "NUMNOTA",
        "launched_at": "DTLANC", "used_at": "DTDESCONTO", "expires_at": "DTVENC",
        "canceled_at": "DTCANCEL", "reversed_at": "DTESTORNO",
        "is_cashback": "IS_CASHBACK", "cashback_expires_at": "DTVALIDADECASHBACK",
    }},
    "credit_auth": {"fields": {
        "external_id": "EXTERNAL_ID", "order_number": "NUMPEDIDO", "customer": "CODCLI",
        "sales_rep": "CODUSUR", "authorized_by": "CODFUNC", "date": "DATA",
        "credit_limit": "LIMCRED", "pending_value": "VLPENDENTE", "released_value": "VLLIBERADO",
        "used_at": "DTUTILIZACAO", "used_order_number": "NUMPEDUTILIZACAO",
    }},
    "card_settlement": {"fields": {
        "external_id": "CODBAIXAITEM", "branch": "CODFILIAL", "customer": "CODCLI", "date": "DATA",
        "credit_date": "DATACREDITO", "settled_at": "DTBAIXA", "installment": "PARCELA",
        "installments": "QTTOTALPARCELAS", "gross": "VALORPARCELA", "net": "VALORPARCELALIQUIDO",
        "fee_pct": "TAXA", "network": "CODREDE", "brand": "CODBANDEIRA", "product_type": "TIPOPRODUTO",
        "status": "STATUS",
    }},
    "pos_daily": {"fields": {
        "external_id": "EXTERNAL_ID", "branch": "CODFILIAL", "ecf_number": "NUMECF", "date": "DTEMISSAO",
        "coupons": "CUPONS", "gross_sales": "VENDABRUTA", "accounting_value": "VLCONTABIL",
    }},
    "purchase_order": {"fields": {
        "external_id": "NUMPED", "number": "NUMPED", "supplier": "CODFORNEC", "branch": "CODFILIAL",
        "buyer": "CODCOMPRADOR", "issue_date": "DTEMISSAO", "expected_at": "DTPREVENT",
        "stock_entry_at": "DTENTRADAESTOQUE", "total": "VLTOTAL", "delivered_value": "VLENTREGUE",
        "items": "ITENS", "qty_ordered": "QTPEDIDA", "qty_delivered": "QTENTREGUE",
    }},
    "supplier_credit": {"fields": {
        "external_id": "NUMVERBA", "supplier": "CODFORNEC", "branch": "CODFILIAL", "kind": "TIPO",
        "origin": "ORIGEM", "issue_date": "DTEMISSAO", "due_date": "DTVENC", "amount": "VALOR",
        "paid": "VPAGO", "settled_at": "DTQUITACAO", "canceled_at": "DTCANCEL",
    }},
    "mdfe": {"fields": {
        "external_id": "EXTERNAL_ID", "number": "NUMMDFE", "branch": "CODFILIAL",
        "generated_at": "DATAHORAGERACAO", "authorized_at": "DATAHORAAUTORSEFAZ",
        "situation": "SITUACAOMDFE", "protocol": "PROTOCOLOMDFE", "is_canceled": "IS_CANCELED",
        "event_at": "DATAHORAEVENTO",
    }},
    "target": {"fields": {
        "external_id": "EXTERNAL_ID", "branch": "CODFILIAL", "sales_rep": "CODUSUR",
        "kind": "TIPOMETA", "period": "DATA", "sales_value": "VLVENDAPREV",
        "sales_qty": "QTVENDAPREV", "mix": "MIXPREV", "positivation": "CLIPOSPREV",
        "positivation_pct": "PERCLIPOSPREV", "margin_pct": "MARGEMPREV",
        "orders": "PEDIDOSPREV", "avg_order_value": "VLMEDIOPEDIDO",
        "active_customers": "QTDCLIENTESATIVO",
    }},
    "target_daily": {"fields": {
        "external_id": "EXTERNAL_ID", "branch": "CODFILIAL", "sales_rep": "CODUSUR",
        "period": "DATA", "sales_value": "VLVENDAPREV", "positivation": "NUMCLIPOS",
        "orders": "QTPEDPREV", "sales_qty": "QTITENSPEDPREV", "positivation_pct": "PERVENDAPREV",
    }},
    "wms_os": {"fields": {
        "external_id": "NUMOS", "number": "NUMOS", "os_type": "TIPOOS", "operation": "CODOPER",
        "branch": "CODFILIAL", "order_number": "NUMPED", "load_number": "NUMCAR", "date": "DATA",
        "position": "POSICAO", "lines": "LINHAS", "qty": "QT", "qty_picked": "QTSEPARADA",
        "qty_checked": "QTCONFERIDA", "qty_canceled": "QTCANCEL", "errors": "QTERROS",
        "picking_start": "DTINICIOOS", "picking_end": "DTFIMSEPARACAO",
        "check_start": "DTINICIOCONFERENCIA", "check_end": "DTFIMCONFERENCIA",
        "picker": "CODFUNCOS", "checker": "CODFUNCCONF",
    }},
    "route_load": {"fields": {
        "external_id": "CODIGO_INT", "load_number": "CARGAS_GERADAS_ERP", "branch": "T43_CODIGO_FILIAL_ERP",
        "departure_date": "T10_DATA_SAIDA", "routed_at": "DTROTEIRIZACAO", "vehicle_code": "T06_CODIGO_ERP",
        "driver_code": "T05_CODIGO_ERP", "route": "CODROTAPRINC", "weight": "PESO", "volume": "VOLUME",
        "max_weight": "T06_PESO_MAX_ENTREGAS", "max_volume": "T06_VOLUME_MAX_ENTREGAS", "total_value": "VALORTOTAL",
        "num_items": "NUMITENS", "num_customers": "NUMCLIENTES", "num_cities": "NUMCIDADES", "status": "STATUS_INT",
    }},
    "delivery_event": {"fields": {
        "external_id": "ID_PK", "event_type": "TIPO", "occurred_at": "DATA_EVENTO", "order_number": "SEQ_PEDIDO_ERP",
        "load_number": "CARGA_ERP", "driver_code": "MOTORISTA_CODIGO_ERP", "vehicle_plate": "VEICULO_PLACA",
        "km": "KMATUAL", "latitude": "LATITUDE", "longitude": "LONGITUDE", "reason_id": "MOTIVO_DEVOL_REENT_ID",
        "note": "OBS_MOTORISTA",
    }},
}


def queries_do_plano(connector=None):
    """Consultas efetivas para um conector, na ordem de valor.

    `config.entidades_indisponiveis` tira do plano tabelas que não existem
    neste ERP; `config.historico_meses` encurta o backfill; `config.queries`
    substitui o plano inteiro (caso extremo de cliente muito diferente).
    """
    cfg = (connector.config or {}) if connector is not None else {}
    if cfg.get("queries"):
        return list(cfg["queries"])

    desativadas = set(cfg.get("entidades_indisponiveis") or [])
    queries = [dict(q) for q in WINTHOR_QUERIES if q["entity"] not in desativadas]

    hist = int(cfg.get("historico_meses") or 0)
    if hist:
        for q in queries:
            if int(q.get("backfill_meses") or 0) > hist:
                q["backfill_meses"] = hist

    posicao = {e: i for i, e in enumerate(ORDEM_DE_VALOR)}
    return sorted(queries, key=lambda q: posicao.get(q["entity"], len(posicao)))


# Ritmo da carga: o agente respeita isto para nunca pesar no servidor do ERP.
#   pausa_ms      — descanso entre lotes
#   batch_max     — teto de linhas por lote
#   load_max      — load por CPU acima do qual o agente PAUSA (0 = desligado)
#   load_retomar  — load por CPU abaixo do qual ele volta
#   horas_carga_inicial — janela "19-07" só para o histórico; incremental segue livre
RITMO_PADRAO = {"pausa_ms": 1000, "batch_max": 500, "load_max": 0.6, "load_retomar": 0.4,
                "horas_carga_inicial": ""}


def ritmo_do_conector(connector=None):
    cfg = (connector.config or {}) if connector is not None else {}
    ritmo = dict(RITMO_PADRAO)
    for k, v in (cfg.get("ritmo") or {}).items():
        if k in ritmo and v not in (None, ""):
            ritmo[k] = v
    return ritmo


def winthor_tables():
    """Tabelas que o plano toca — base do script de GRANTs para o DBA."""
    import re

    tables = set()
    for q in WINTHOR_QUERIES:
        # PC* do schema do ERP e tabelas de outros schemas (FUSIONT.X) usadas por
        # entidades opcionais — o DBA dá GRANT só nas que existem no cliente.
        tables.update(re.findall(r"(?:FROM|JOIN)\s+((?:[A-Z_]+\.)?PC\w+|[A-Z_]+\.[A-Z_]+)", q["sql"], re.IGNORECASE))
    return sorted(t.upper() for t in tables)


def oracle_user_script(usuario="TECHSYS"):
    """Script para o DBA: usuário somente-leitura + GRANT tabela a tabela.

    Nada de SELECT ANY TABLE. Sinônimos são opcionais: o agente aponta a sessão
    para o schema dono (ALTER SESSION SET CURRENT_SCHEMA) e consulta sem prefixo.
    """
    tables = winthor_tables()
    grants = "\n".join(
        (f"GRANT SELECT ON {t} TO {usuario};  -- opcional: só se o schema existir" if "." in t
         else f"GRANT SELECT ON __DONO__.{t} TO {usuario};")
        for t in tables
    )
    return f"""-- ============================================================================
-- Usuário {usuario} (somente leitura) no Oracle do WinThor — rode como DBA.
-- Schema dono das tabelas: __DONO__   (confira com:
--   SELECT owner FROM all_tables WHERE table_name = 'PCPEDC';)
-- ============================================================================
CREATE USER {usuario} IDENTIFIED BY "__SENHA__"
  DEFAULT TABLESPACE USERS
  TEMPORARY TABLESPACE TEMP
  QUOTA 0 ON USERS
  ACCOUNT UNLOCK;

GRANT CREATE SESSION TO {usuario};

-- Leitura SOMENTE nas {len(tables)} tabelas que o agente coleta:
{grants}

-- O agente nunca grava no ERP: não há GRANT de INSERT/UPDATE/DELETE.
"""
