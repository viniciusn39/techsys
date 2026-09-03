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
]

WINTHOR_QUERIES = [
    {  # PCFILIAL — minúscula: recarga cheia
        "entity": "branch",
        "every_minutes": 720,
        "sql": """
SELECT CODIGO, RAZAOSOCIAL, FANTASIA, CGC, CIDADE, UF,
       CASE WHEN DTEXCLUSAO IS NULL THEN 1 ELSE 0 END AS IS_ACTIVE
FROM PCFILIAL
""",
    },
    {  # PCUSUARI (+ PCSUPERV) — dimensão de vendas; watermark DTULTALTERACAO
        "entity": "salesrep",
        "every_minutes": 360,
        "incremental": True,
        "since_column": "DTULTALTERACAO",
        "sql": """
SELECT U.CODUSUR, U.NOME, U.TIPOVEND, U.CODEQUIPE, S.NOME AS SUPERVISOR,
       U.VLVENDAPREV,
       CASE WHEN NVL(U.BLOQUEIO,'N') = 'N' AND U.DTEXCLUSAO IS NULL THEN 1 ELSE 0 END AS IS_ACTIVE,
       TO_CHAR(U.DTULTALTERACAO,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTERACAO
FROM PCUSUARI U
LEFT JOIN PCSUPERV S ON S.CODSUPERVISOR = U.CODSUPERVISOR
WHERE (:since IS NULL OR U.DTULTALTERACAO > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCFORNEC — dimensão de compras/pagar; watermark DTULTALTER
        "entity": "supplier",
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
        "every_minutes": 360,
        "incremental": True,
        "since_column": "DTULTALTER",
        "sql": """
SELECT E.MATRICULA, E.NOME, E.FUNCAO, E.CODSETOR, E.CODFILIAL,
       TO_CHAR(E.ADMISSAO,'YYYY-MM-DD') AS ADMISSAO,
       TO_CHAR(E.DTDEMISSAO,'YYYY-MM-DD') AS DTDEMISSAO,
       CASE WHEN E.TIPOMOTORISTA IS NOT NULL THEN 1 ELSE 0 END AS IS_DRIVER,
       CASE WHEN NVL(E.SITUACAO,'A') = 'A' AND E.DT_EXCLUSAO IS NULL THEN 1 ELSE 0 END AS IS_ACTIVE,
       TO_CHAR(E.DTULTALTER,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTER
FROM PCEMPR E
WHERE (:since IS NULL OR E.DTULTALTER > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCCLIENT (+ PCPRACA) — base de clientes ativos/novos/churn; watermark DTULTALTER
        "entity": "customer",
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
        "every_minutes": 120,
        "incremental": True,
        "since_column": "DTALTERC5",
        "sql": """
SELECT P.CODPROD, P.DESCRICAO, P.CODAUXILIAR, P.UNIDADE, P.EMBALAGEM,
       M.MARCA, D.DESCRICAO AS DEPARTAMENTO, S.DESCRICAO AS SECAO,
       CAT.CATEGORIA, P.CODFORNEC, P.CLASSE,
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
        "every_minutes": 30,
        "incremental": True,
        "since_column": "DTSAIDA",
        "batch": 1000,
        "backfill_meses": 24,
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
        "every_minutes": 30,
        "incremental": True,
        "since_column": "DTULTALTER",
        "batch": 2000,
        # PCPREST guarda a vida inteira da empresa (33 milhões de linhas numa
        # distribuidora). Carga gradual: títulos emitidos na janela + tudo que
        # está em aberto (a inadimplência precisa dos antigos ainda não pagos).
        "backfill_meses": 24,
        "backfill_passo": 3,
        "sql": """
SELECT P.NUMTRANSVENDA || '-' || P.PREST AS EXTERNAL_ID,
       P.DUPLIC, P.PREST, P.CODCLI, P.CODFILIAL, P.NUMPED, P.VALOR, P.CODCOB,
       TO_CHAR(P.DTEMISSAO,'YYYY-MM-DD') AS DTEMISSAO,
       TO_CHAR(P.DTVENC,'YYYY-MM-DD') AS DTVENC,
       TO_CHAR(P.DTPAG,'YYYY-MM-DD') AS DTPAG,
       P.VPAGO, P.VALORMULTA,
       CASE WHEN P.DTCANCEL IS NOT NULL THEN 'canceled'
            WHEN P.DTPAG IS NOT NULL THEN 'paid'
            ELSE 'open' END AS STATUS,
       TO_CHAR(P.DTULTALTER,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTER
FROM PCPREST P
WHERE (P.DTEMISSAO >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -:janela)
       OR (P.DTPAG IS NULL AND P.DTCANCEL IS NULL))
  AND (:since IS NULL OR P.DTULTALTER > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCLANC (PCPAGAR não existe) + PCCONTA — contas a pagar / despesas
        "entity": "title_payable",
        "every_minutes": 30,
        "incremental": True,
        "since_column": "DTULTALTER",
        "batch": 2000,
        "backfill_meses": 24,
        "backfill_passo": 3,
        "sql": """
SELECT L.RECNUM, L.CODFORNEC, L.NUMNOTA, L.HISTORICO, CT.CONTA, L.TIPOSERVICO,
       L.FORMAPGTO, L.CODFILIAL, L.VALOR,
       TO_CHAR(L.DTEMISSAO,'YYYY-MM-DD') AS DTEMISSAO,
       TO_CHAR(L.DTCOMPETENCIA,'YYYY-MM-DD') AS DTCOMPETENCIA,
       TO_CHAR(L.DTVENC,'YYYY-MM-DD') AS DTVENC,
       TO_CHAR(L.DTPAGTO,'YYYY-MM-DD') AS DTPAGTO,
       L.VPAGO,
       CASE WHEN L.DTCANCEL IS NOT NULL OR NVL(L.LANCEXCLUIDO,'N') = 'S' THEN 'canceled'
            WHEN L.DTPAGTO IS NOT NULL THEN 'paid'
            ELSE 'open' END AS STATUS,
       TO_CHAR(L.DTULTALTER,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTER
FROM PCLANC L
LEFT JOIN PCCONTA CT ON CT.CODCONTA = L.CODCONTA
WHERE (L.DTEMISSAO >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -:janela)
       OR (L.DTPAGTO IS NULL AND L.DTCANCEL IS NULL AND NVL(L.LANCEXCLUIDO,'N') = 'N'))
  AND (:since IS NULL OR L.DTULTALTER > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
""",
    },
    {  # PCFINANC — fotografia diária: caixa, bancos, CR, CP, estoque, CMV. Janela 120 dias.
        "entity": "financial_snapshot",
        "every_minutes": 120,
        "incremental": True,
        "since_column": "DATA",
        "sql": """
SELECT F.CODFILIAL || '-' || TO_CHAR(F.DATA,'YYYY-MM-DD') AS EXTERNAL_ID,
       F.CODFILIAL, F.SALDOBCO, F.SALDOCX, F.SALDOAPLI, F.SALDOCR, F.SALDOCP,
       F.SALDOESTFIN, F.SALDOREAL, F.VENDAREAL, F.RECEBREAL, F.CMVREAL,
       TO_CHAR(F.DATA,'YYYY-MM-DD') AS DATA
FROM PCFINANC F
WHERE F.DATA >= TRUNC(SYSDATE) - 120
  AND (:since IS NULL OR F.DATA >= TRUNC(SYSDATE) - 7)
""",
    },
    {  # PCBANCO (+ saldo PCESTCR) — pequena: recarga cheia
        "entity": "bank_account",
        "every_minutes": 120,
        "sql": """
SELECT B.CODBANCO, B.NOME, B.NUMBANCO, B.AGENCIA, B.CONTA, B.TIPOCXBCO, B.CODFILIAL,
       (SELECT SUM(E.VALOR) FROM PCESTCR E WHERE E.CODBANCO = B.CODBANCO) AS SALDO
FROM PCBANCO B
""",
    },
    {  # PCMOVCR — extrato de conta corrente: entradas (D) e saídas (C) reais de caixa.
       # Janela 180 dias, reprocessa 7 dias por ciclo (estornos somem via DTESTORNO).
        "entity": "cash_movement",
        "every_minutes": 60,
        "incremental": True,
        "since_column": "DATA",
        "batch": 1000,
        "sql": """
SELECT M.NUMTRANS || '-' || M.CODBANCO || '-' || M.CODCOB AS EXTERNAL_ID,
       M.NUMTRANS, TO_CHAR(M.DATA,'YYYY-MM-DD') AS DATA, M.CODBANCO, M.CODCOB,
       M.CODFILIAL, M.VALOR, M.TIPO, M.HISTORICO, M.VLSALDO, M.CODCLI, M.CODROTINALANC,
       TO_CHAR(M.DTCONCIL,'YYYY-MM-DD') AS DTCONCIL,
       TO_CHAR(M.DTCOMPENSACAO,'YYYY-MM-DD') AS DTCOMPENSACAO
FROM PCMOVCR M
WHERE M.DTESTORNO IS NULL
  AND M.DATA >= TRUNC(SYSDATE) - 180
  AND (:since IS NULL OR M.DATA >= TRUNC(SYSDATE) - 7)
""",
    },
    {  # PCEST — saldo por produto×filial. Leitura CHEIA: a marca DTULTALTERSRVPRC
       # só é mexida pelo servidor de preços, não pela venda (congelava o saldo).
        "entity": "stock",
        "every_minutes": 120,
        "batch": 2000,
        "sql": """
SELECT E.CODFILIAL || '-' || E.CODPROD AS EXTERNAL_ID,
       E.CODPROD, E.CODFILIAL, NVL(E.QTEST,0) AS QTEST, NVL(E.QTRESERV,0) AS QTRESERV,
       NVL(E.QTBLOQUEADA,0) AS QTBLOQUEADA,
       E.ESTMIN, E.ESTMAX, E.ESTIDEAL, E.CUSTOREAL, E.CUSTOULTENT, E.CUSTOREP,
       E.QTVENDMES, E.QTGIRODIA, E.QTVENDAPERDIDA,
       TO_CHAR(E.DTULTENT,'YYYY-MM-DD') AS DTULTENT,
       TO_CHAR(E.DTULTSAIDA,'YYYY-MM-DD') AS DTULTSAIDA
FROM PCEST E
""",
    },
    {  # PCPEDC — carteira e conversão pedido→nota. Janela deslizante de 7 dias; 12 meses.
        "entity": "order",
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
        "every_minutes": 60,
        "incremental": True,
        "since_column": "DTULTALTER",
        "sql": """
SELECT C.NUMCAR, C.CODFILIALSAIDA, E.NOME AS MOTORISTA, V.PLACA, C.CODROTAPRINC,
       C.DESTINO, C.NUMNOTAS, C.TOTPESO, C.VLTOTAL, C.VLFRETE,
       TO_CHAR(C.DTSAIDA,'YYYY-MM-DD') AS DTSAIDA,
       TO_CHAR(C.DTRETORNO,'YYYY-MM-DD') AS DTRETORNO,
       CASE WHEN C.DT_CANCEL IS NOT NULL THEN 'canceled'
            WHEN C.DTRETORNO IS NOT NULL THEN 'returned'
            WHEN C.DTSAIDA IS NOT NULL THEN 'dispatched'
            ELSE 'open' END AS STATUS,
       TO_CHAR(C.DTULTALTER,'YYYY-MM-DD HH24:MI:SS') AS DTULTALTER
FROM PCCARREG C
LEFT JOIN PCEMPR E   ON E.MATRICULA = C.CODMOTORISTA
LEFT JOIN PCVEICUL V ON V.CODVEICULO = C.CODVEICULO
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
WHERE M.DATA >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -24)
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
WHERE R.DATA >= ADD_MONTHS(TRUNC(SYSDATE,'MM'), -13)
GROUP BY R.CODFILIAL, R.CODUSUR, R.DATA
HAVING (SUM(NVL(R.VLVENDAPREV,0)) > 0 OR SUM(NVL(R.NUMCLIPOS,0)) > 0 OR SUM(NVL(R.QTPEDPREV,0)) > 0)
   AND (:since IS NULL OR MAX(NVL(R.DTMXSALTER, R.DATA)) > TO_DATE(:since,'YYYY-MM-DD HH24:MI:SS'))
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
        "is_driver": "IS_DRIVER", "is_active": "IS_ACTIVE",
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
        "price": "PVENDA", "is_active": "IS_ACTIVE",
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
    }},
    "title_payable": {"fields": {
        "external_id": "RECNUM", "supplier": "CODFORNEC", "number": "NUMNOTA",
        "description": "HISTORICO", "account": "CONTA", "tax_type": "TIPOSERVICO",
        "payment_method": "FORMAPGTO", "branch": "CODFILIAL", "amount": "VALOR",
        "issue_date": "DTEMISSAO", "accrual_date": "DTCOMPETENCIA", "due_date": "DTVENC",
        "paid_at": "DTPAGTO", "amount_paid": "VPAGO", "status": "STATUS",
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
        "last_entry_at": "DTULTENT", "last_exit_at": "DTULTSAIDA",
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
        "num_invoices": "NUMNOTAS", "total_weight": "TOTPESO", "total_value": "VLTOTAL",
        "freight": "VLFRETE", "status": "STATUS",
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


def winthor_tables():
    """Tabelas que o plano toca — base do script de GRANTs para o DBA."""
    import re

    tables = set()
    for q in WINTHOR_QUERIES:
        tables.update(re.findall(r"(?:FROM|JOIN)\s+(PC\w+)", q["sql"], re.IGNORECASE))
    return sorted(tables)


def oracle_user_script(usuario="TECHSYS"):
    """Script para o DBA: usuário somente-leitura + GRANT tabela a tabela.

    Nada de SELECT ANY TABLE. Sinônimos são opcionais: o agente aponta a sessão
    para o schema dono (ALTER SESSION SET CURRENT_SCHEMA) e consulta sem prefixo.
    """
    tables = winthor_tables()
    grants = "\n".join(f"GRANT SELECT ON __DONO__.{t} TO {usuario};" for t in tables)
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
