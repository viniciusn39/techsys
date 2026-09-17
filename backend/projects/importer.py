"""Importa a EAP de um projeto a partir de um CSV — o mesmo formato que a tela exporta.

Colunas (pelo cabeçalho, em qualquer ordem; só "Atividade" é obrigatória):
EAP · Atividade · Responsável · Fase · Início · Fim · Situação · Avanço %
A hierarquia vem da coluna EAP (1, 1.1, 1.1.1…); sem ela, tudo entra no primeiro nível.
"""
import csv
import io
import unicodedata
from datetime import date, datetime

from django.db import transaction
from django.db.models import Max, Q

from accounts.models import User

from .models import Andamento, ProjectActivity

LIMITE_LINHAS = 2000


def _chave(texto):
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return "".join(c for c in sem_acento.lower() if c.isalnum())


COLUNAS = {
    "eap": "eap", "wbs": "eap", "item": "eap",
    "atividade": "titulo", "atividades": "titulo", "nome": "titulo", "titulo": "titulo",
    "responsavel": "responsavel", "fase": "fase", "fases": "fase",
    "inicio": "inicio", "datainicial": "inicio", "datadeinicio": "inicio",
    "fim": "fim", "datafinal": "fim", "datadefim": "fim",
    "situacao": "situacao", "andamento": "situacao", "status": "situacao",
    "avanco": "avanco", "avancopct": "avanco", "andamentopct": "avanco", "progresso": "avanco",
    "descricao": "descricao",
}
FASES = {_chave(rotulo): valor for valor, rotulo in ProjectActivity.Phase.choices}
SITUACOES = {_chave(rotulo): valor for valor, rotulo in Andamento.choices} | {"concluido": Andamento.FINALIZADO, "concluida": Andamento.FINALIZADO}


def _data(texto):
    texto = (texto or "").strip()
    if not texto or texto == "—":
        return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(texto)


def _ler(conteudo: bytes):
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1")          # CSV salvo pelo Excel em português
    primeira = texto.split("\n", 1)[0]
    separador = ";" if primeira.count(";") >= primeira.count(",") else ","
    return list(csv.reader(io.StringIO(texto), delimiter=separador))


def importar_atividades(project, conteudo: bytes):
    """Devolve {"criadas": n, "avisos": [...]}. Erro de estrutura levanta ValueError; nada é gravado pela metade."""
    linhas = [l for l in _ler(conteudo) if any(c.strip() for c in l)]
    if len(linhas) < 2:
        raise ValueError("A planilha precisa do cabeçalho e de pelo menos uma atividade.")
    if len(linhas) - 1 > LIMITE_LINHAS:
        raise ValueError(f"Máximo de {LIMITE_LINHAS} atividades por importação.")
    cabecalho = [COLUNAS.get(_chave(c)) for c in linhas[0]]
    if "titulo" not in cabecalho:
        raise ValueError('Não encontrei a coluna "Atividade" no cabeçalho.')

    tenant = project.tenant
    pessoas = {}
    for u in User.objects.filter(Q(tenant=tenant) | Q(extra_tenants=tenant), is_active=True).distinct():
        for apelido in (u.get_full_name(), u.first_name, u.email):
            if apelido:
                pessoas.setdefault(_chave(apelido), u)

    avisos, registros = [], []
    for n, linha in enumerate(linhas[1:], start=2):
        d = {nome: (linha[i].strip() if i < len(linha) else "") for i, nome in enumerate(cabecalho) if nome}
        if not d.get("titulo"):
            avisos.append(f"Linha {n}: sem nome de atividade — ignorada.")
            continue
        r = {"linha": n, "eap": d.get("eap", "").strip(". "), "titulo": d["titulo"][:250], "descricao": d.get("descricao", "")}
        if d.get("responsavel") and d["responsavel"] != "—":
            r["responsavel"] = pessoas.get(_chave(d["responsavel"]))
            if r["responsavel"] is None:
                avisos.append(f"Linha {n}: responsável “{d['responsavel']}” não encontrado — ficou em branco.")
        r["fase"] = FASES.get(_chave(d.get("fase")), ProjectActivity.Phase.INICIACAO)
        for campo in ("inicio", "fim"):
            try:
                r[campo] = _data(d.get(campo))
            except ValueError as e:
                r[campo] = None
                avisos.append(f"Linha {n}: data “{e}” não reconhecida (use dd/mm/aaaa).")
        if r["inicio"] and r["fim"] and r["fim"] < r["inicio"]:
            avisos.append(f"Linha {n}: fim antes do início — o fim foi descartado.")
            r["fim"] = None
        try:
            pct = int(float((d.get("avanco") or "0").replace("%", "").replace(",", ".").strip() or 0))
        except ValueError:
            pct = 0
            avisos.append(f"Linha {n}: avanço “{d.get('avanco')}” não é número — ficou 0%.")
        r["pct"] = max(0, min(100, pct))
        r["status"] = SITUACOES.get(_chave(d.get("situacao")))
        if r["status"] is None:
            r["status"] = Andamento.FINALIZADO if r["pct"] >= 100 else Andamento.EM_ANDAMENTO if r["pct"] > 0 else Andamento.NAO_INICIADO
        if r["status"] == Andamento.FINALIZADO:
            r["pct"] = 100
        registros.append(r)

    if not registros:
        raise ValueError("Nenhuma atividade válida na planilha.")

    with transaction.atomic():
        por_eap = {}
        ordem = {None: ProjectActivity.objects.filter(project=project, parent=None).aggregate(m=Max("order"))["m"] or 0}
        for r in registros:
            pai = None
            if "." in r["eap"]:
                pai = por_eap.get(r["eap"].rsplit(".", 1)[0])
                if pai is None:
                    avisos.append(f"Linha {r['linha']}: não achei a atividade-mãe de “{r['eap']}” — entrou no primeiro nível.")
            chave_pai = pai.id if pai else None
            ordem[chave_pai] = ordem.get(chave_pai, 0) + 1
            atividade = ProjectActivity.objects.create(
                project=project, parent=pai, title=r["titulo"], description=r["descricao"], responsible=r.get("responsavel"),
                phase=r["fase"], start_date=r["inicio"], end_date=r["fim"], status=r["status"], progress_pct=r["pct"], order=ordem[chave_pai],
            )
            if r["eap"]:
                por_eap[r["eap"]] = atividade
    return {"criadas": len(registros), "avisos": avisos[:50], "hoje": date.today()}
