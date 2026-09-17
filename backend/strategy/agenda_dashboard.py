"""Números do painel da agenda: volume, horas, carga por pessoa, conflitos e evolução."""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from .models import Meeting

DURACAO_PADRAO = timedelta(hours=1)   # reunião sem hora de fim conta como 1 h
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _nome(user):
    return user.get_full_name() or user.first_name or user.email


def _fim(m):
    return m.ends_at if m.ends_at and m.ends_at > m.starts_at else m.starts_at + DURACAO_PADRAO


def _horas(m):
    """Agenda de vários dias (ex.: 08:00 de segunda às 18:00 de quarta) conta a jornada de cada dia, não as noites."""
    ini, fim = timezone.localtime(m.starts_at), timezone.localtime(_fim(m))
    dias = (fim.date() - ini.date()).days
    if dias <= 0:
        return (fim - ini).total_seconds() / 3600
    jornada = (datetime.combine(ini.date(), fim.time()) - datetime.combine(ini.date(), ini.time())).total_seconds() / 3600
    return (jornada if jornada > 0 else 8) * (dias + 1)


def _pessoas(m):
    """Organizador e participantes, sem repetir."""
    pessoas = {u.id: u for u in m.participants.all()}
    if m.organizer_id:
        pessoas[m.organizer_id] = m.organizer
    return list(pessoas.values())


def _intervalo(de, ate):
    tz = timezone.get_current_timezone()
    return (timezone.make_aware(datetime.combine(de, time.min), tz),
            timezone.make_aware(datetime.combine(ate, time.max), tz))


def painel_agenda(qs, de, ate, participante=None, tipo=None, total_usuarios=0):
    """`qs` já vem filtrado pela empresa. Canceladas ficam de fora de tudo."""
    base = qs.exclude(status=Meeting.Status.CANCELADA)
    if participante:
        base = (base.filter(participants=participante) | base.filter(organizer=participante)).distinct()
    if tipo:
        base = base.filter(kind=tipo)

    ini, fim = _intervalo(de, ate)
    reunioes = list(base.filter(starts_at__range=(ini, fim)).order_by("starts_at"))

    dias = (ate - de).days + 1
    ant_ini, ant_fim = _intervalo(de - timedelta(days=dias), de - timedelta(days=1))
    anterior = base.filter(starts_at__range=(ant_ini, ant_fim)).count()
    variacao = None if anterior == 0 else round((len(reunioes) - anterior) / anterior * 100)

    carga = defaultdict(lambda: {"reunioes": 0, "horas": 0.0})
    agenda_de = defaultdict(list)
    for m in reunioes:
        for u in _pessoas(m):
            carga[(u.id, _nome(u))]["reunioes"] += 1
            carga[(u.id, _nome(u))]["horas"] += _horas(m)
            agenda_de[u.id].append(m)

    # Conflito: a mesma pessoa em duas reuniões que se sobrepõem.
    conflitos, vistos = [], set()
    for uid, lista in agenda_de.items():
        lista.sort(key=lambda m: m.starts_at)
        for a, b in zip(lista, lista[1:]):
            if b.starts_at < _fim(a) and (a.id, b.id) not in vistos:
                vistos.add((a.id, b.id))
                quem = next(n for (i, n) in carga if i == uid)
                conflitos.append({"pessoa": quem, "a": a.title, "b": b.title, "quando": b.starts_at})

    agora = timezone.now()
    local = timezone.localtime
    rotulos = dict(Meeting.Kind.choices)
    por_tipo = Counter(m.kind for m in reunioes)
    por_dia_semana = Counter(local(m.starts_at).weekday() for m in reunioes)

    hoje = date.today()
    meses = []
    for k in range(5, -1, -1):
        ano, mes = hoje.year, hoje.month - k
        while mes <= 0:
            ano, mes = ano - 1, mes + 12
        meses.append((ano, mes))
    evolucao = [
        {"mes": f"{a}-{m:02d}", "reunioes": base.filter(starts_at__year=a, starts_at__month=m).count()}
        for a, m in meses
    ]

    def resumo(m):
        return {"id": m.id, "title": m.title, "kind": m.kind, "kind_label": rotulos.get(m.kind, m.kind), "status": m.status,
                "starts_at": m.starts_at, "ends_at": m.ends_at, "location": m.location,
                "pessoas": [_nome(u) for u in _pessoas(m)]}

    return {
        "de": de, "ate": ate,
        "total": len(reunioes), "anterior": anterior, "variacao_pct": variacao,
        "horas": round(sum(_horas(m) for m in reunioes), 1),
        "realizadas": sum(1 for m in reunioes if m.status == Meeting.Status.REALIZADA),
        "pessoas_envolvidas": len(carga), "total_usuarios": total_usuarios,
        "conflitos": conflitos,
        "carga": sorted(
            ({"id": i, "nome": n, "reunioes": v["reunioes"], "horas": round(v["horas"], 1)} for (i, n), v in carga.items()),
            key=lambda c: -c["horas"],
        ),
        "por_tipo": [{"kind": k, "label": rotulos.get(k, k), "total": n} for k, n in por_tipo.most_common()],
        "por_dia_semana": [{"dia": DIAS[i], "total": por_dia_semana.get(i, 0)} for i in range(7)],
        "proximas": [resumo(m) for m in reunioes if m.starts_at >= agora and m.status == Meeting.Status.AGENDADA][:8],
        "reunioes": [resumo(m) for m in reunioes],
        "evolucao": evolucao,
    }
