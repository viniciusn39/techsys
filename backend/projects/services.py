"""Cálculo da EAP (árvore de atividades) e dos números do painel de projetos.

Tudo em memória a partir de uma única leitura das atividades: a árvore não tem
limite de níveis, então calcular avanço nó a nó no banco custaria uma consulta
por atividade.
"""
from collections import Counter, defaultdict
from datetime import date

from django.utils import timezone

from .models import Andamento, ProjectActivity

ENCERRADOS = (Andamento.FINALIZADO, Andamento.CANCELADO)


def calcular_arvore(activities, hoje=None):
    """Devolve as atividades em ordem de EAP, cada uma com numeração (1, 1.1, 1.1.1…),
    nível, avanço efetivo, se tem filhas e se está atrasada.

    Avanço: finalizada = 100; com filhas = média das filhas não canceladas; senão o informado.
    """
    hoje = hoje or date.today()
    filhos = defaultdict(list)
    for a in activities:
        filhos[a.parent_id].append(a)
    for lista in filhos.values():
        lista.sort(key=lambda a: (a.order, a.id))

    linhas = []

    def visitar(a, wbs, depth):
        linha = {"obj": a, "wbs": wbs, "depth": depth, "has_children": bool(filhos.get(a.id))}
        linhas.append(linha)
        avancos = []
        for n, f in enumerate(filhos.get(a.id, []), start=1):
            sub = visitar(f, f"{wbs}.{n}", depth + 1)
            if f.status != Andamento.CANCELADO:
                avancos.append(sub)
        if a.status == Andamento.FINALIZADO:
            progress = 100
        elif avancos:
            progress = round(sum(avancos) / len(avancos))
        elif linha["has_children"]:
            progress = 0
        else:
            progress = int(a.progress_pct or 0)
        linha["progress"] = progress
        linha["late"] = bool(a.end_date and a.end_date < hoje and progress < 100 and a.status not in ENCERRADOS)
        return progress

    for n, raiz in enumerate(filhos.get(None, []), start=1):
        visitar(raiz, str(n), 0)
    return linhas


def resumo_projeto(linhas):
    """Números de um projeto a partir da árvore já calculada."""
    raiz = [l for l in linhas if l["depth"] == 0 and l["obj"].status != Andamento.CANCELADO]
    return {
        "activities_count": sum(1 for l in linhas if l["depth"] == 0),
        "subactivities_count": sum(1 for l in linhas if l["depth"] > 0),
        "done_count": sum(1 for l in linhas if l["progress"] >= 100),
        "late_count": sum(1 for l in linhas if l["late"]),
        "progress": round(sum(l["progress"] for l in raiz) / len(raiz)) if raiz else 0,
    }


def arvores_por_projeto(projects, hoje=None):
    """{project_id: linhas} com uma única consulta para todos os projetos."""
    por_projeto = defaultdict(list)
    ids = [p.id for p in projects]
    for a in ProjectActivity.objects.filter(project_id__in=ids).select_related("responsible"):
        por_projeto[a.project_id].append(a)
    return {pid: calcular_arvore(por_projeto.get(pid, []), hoje) for pid in ids}


def _nome(user):
    if user is None:
        return "Não definido"
    return user.get_full_name() or user.first_name or user.email


def painel(projects, hoje=None):
    """Painel consolidado dos projetos informados."""
    hoje = hoje or date.today()
    arvores = arvores_por_projeto(projects, hoje)
    todas = [l for linhas in arvores.values() for l in linhas]

    por_status = Counter(l["obj"].status for l in todas)
    por_fase = Counter(l["obj"].phase for l in todas)

    meses = defaultdict(lambda: {"iniciadas": 0, "finalizadas": 0})
    for l in todas:
        a = l["obj"]
        if a.start_date:
            meses[a.start_date.strftime("%Y-%m")]["iniciadas"] += 1
        fim = timezone.localtime(a.done_at).date() if a.done_at else (a.end_date if l["progress"] >= 100 else None)
        if fim:
            meses[fim.strftime("%Y-%m")]["finalizadas"] += 1

    ranking = defaultdict(lambda: {"total": 0, "concluidas": 0, "atrasadas": 0})
    for l in todas:
        r = ranking[_nome(l["obj"].responsible)]
        r["total"] += 1
        r["concluidas"] += int(l["progress"] >= 100)
        r["atrasadas"] += int(l["late"])

    visao = []
    for p in projects:
        visao.append({
            "id": p.id, "code": p.code, "title": p.title, "owner_name": _nome(p.owner),
            "status": p.status, "start_date": p.start_date, "end_date": p.end_date,
            **resumo_projeto(arvores[p.id]),
        })

    return {
        "projetos": len(projects),
        "atividades": sum(v["activities_count"] for v in visao),
        "subatividades": sum(v["subactivities_count"] for v in visao),
        "progresso_medio": round(sum(v["progress"] for v in visao) / len(visao)) if visao else 0,
        "concluidas": sum(1 for l in todas if l["progress"] >= 100),
        "atrasadas": sum(1 for l in todas if l["late"]),
        "em_andamento": por_status.get(Andamento.EM_ANDAMENTO, 0),
        "projetos_por_status": dict(Counter(p.status for p in projects)),
        "por_status": {k: por_status.get(k, 0) for k in Andamento.values},
        "por_fase": {k: por_fase.get(k, 0) for k in ProjectActivity.Phase.values},
        "timeline": [{"mes": m, **v} for m, v in sorted(meses.items())],
        "ranking": [
            {"nome": n, **v, "eficiencia": round(100 * v["concluidas"] / v["total"]) if v["total"] else 0}
            for n, v in sorted(ranking.items(), key=lambda kv: -kv[1]["total"])
        ],
        "visao_geral": visao,
    }
