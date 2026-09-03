"""Prompts em pt-BR da camada de IA."""
import json

SYSTEM_PROMPT = (
    "Você é um analista sênior de planejamento estratégico do TechSys Gestão, "
    "um software de gestão de desempenho (BSC, OKR, PDCA). Responda sempre em "
    "português brasileiro, de forma objetiva, estruturada em markdown e orientada "
    "a gestão. Baseie-se apenas nos dados fornecidos; se faltar dado, diga o que falta."
)


def _fmt(obj):
    return json.dumps(obj, ensure_ascii=False, default=str)


def prompt_analise_indicador(indicator, series, ytd):
    return (
        f"Analise o indicador abaixo e produza: 1) leitura da tendência; "
        f"2) avaliação do atingimento das metas (farol); 3) riscos para o restante do ano; "
        f"4) recomendações práticas de gestão.\n\n"
        f"Indicador: {indicator.code} - {indicator.name} "
        f"(unidade: {indicator.unit or 'n/d'}; polaridade: {indicator.get_polarity_display()}; "
        f"agregação YTD: {indicator.get_aggregation_display()})\n"
        f"Série do ano (período, meta, realizado, atingimento %, farol):\n{_fmt(series)}\n"
        f"Acumulado do ano (YTD): {_fmt(ytd)}"
    )


def prompt_analise_desvio(deviation, series, plans):
    value = deviation.indicator_value
    indicator = deviation.indicator
    return (
        f"O indicador {indicator.code} - {indicator.name} ficou com farol VERMELHO em "
        f"{value.period:%m/%Y} (realizado {value.value}, atingimento "
        f"{value.achievement_pct or 0}% da meta).\n"
        f"Histórico do ano:\n{_fmt(series)}\n"
        f"Planos de ação já existentes para este desvio:\n{_fmt(plans)}\n"
        f"Análise de causa registrada pelo gestor: {deviation.root_cause or 'nenhuma'}\n\n"
        f"Produza: 1) hipóteses de causa raiz (estilo Ishikawa resumido: método, máquina, "
        f"mão de obra, material, medição, meio ambiente — só as aplicáveis); "
        f"2) contramedidas sugeridas no formato 5W2H (o quê, por quê, quem, onde, quando, "
        f"como, quanto custa aproximado); 3) como verificar a eficácia (etapa Check do PDCA)."
    )


def prompt_sugestao_mapa(tenant, strategic_map, perspectives, indicators):
    """Pede um rascunho do mapa estratégico em JSON estrito."""
    return (
        f"Monte um rascunho de mapa estratégico (BSC) para a empresa "
        f"\"{tenant.name}\".\n\n"
        f"Missão: {strategic_map.mission or 'não informada'}\n"
        f"Visão: {strategic_map.vision or 'não informada'}\n"
        f"Valores: {strategic_map.values_text or 'não informados'}\n"
        f"Horizonte: {strategic_map.year_start} a {strategic_map.year_end}\n\n"
        f"Perspectivas existentes (use EXATAMENTE estes nomes):\n{_fmt(perspectives)}\n\n"
        f"Indicadores já cadastrados (use para ancorar os objetivos na realidade "
        f"da empresa):\n{_fmt(indicators)}\n\n"
        "Regras:\n"
        "- 2 a 3 objetivos por perspectiva, com nome curto (máx. 60 caracteres), "
        "no infinitivo (ex.: \"Reduzir custo por pedido\").\n"
        "- Descreva cada objetivo em uma frase.\n"
        "- Ligue os objetivos por causa e efeito, sempre subindo: Aprendizado e "
        "Crescimento sustenta Processos Internos, que sustenta Clientes, que "
        "sustenta Financeira. Não crie ciclos nem ligações descendo.\n"
        "- Sugira, para cada objetivo, o código de um indicador já existente que o "
        "meça, ou null se nenhum servir.\n\n"
        "Responda SOMENTE com JSON válido, sem markdown e sem comentários, "
        "neste formato exato:\n"
        '{"objectives": [{"perspective": "<nome exato da perspectiva>", '
        '"name": "<nome do objetivo>", "description": "<uma frase>", '
        '"indicator_code": "<código ou null>"}], '
        '"links": [{"from": "<nome do objetivo origem>", '
        '"to": "<nome do objetivo destino>"}]}'
    )


def prompt_chat_system(context):
    return (
        SYSTEM_PROMPT
        + "\n\nContexto atual dos resultados da empresa (JSON):\n"
        + _fmt(context)
        + "\n\nUse esse contexto para responder às perguntas do usuário sobre "
        "indicadores, metas, desvios e planos de ação."
    )
