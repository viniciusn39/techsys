"""Projetos estratégicos da Nordeste Boi, ligados aos objetivos do mapa dela.

Idempotente: projeto que já existe (pelo título) não é recriado nem alterado.

    python manage.py seed_projetos_nordesteboi
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max

from accounts.models import OrgUnit, Tenant, User
from projects.models import ActivityFca, Andamento, Project, ProjectActivity
from strategy.current import mapa_padrao
from strategy.models import StrategicObjective

F = ProjectActivity.Phase
ANO = date.today().year


def d(mes, dia):
    return date(ANO, mes, dia)


# (título, descrição, área, (início, fim), [objetivos], EAP)
# EAP: (atividade, fase, início, fim, %, [subatividades no mesmo formato, sem filhas])
PROJETOS = [
    (
        "Ruptura zero nos itens de giro",
        "Curva ABC revisada, estoque mínimo por filial e sugestão de compra automática para os itens A, a partir dos dados do WinThor.",
        "Compras", (d(7, 1), d(11, 30)),
        ["Zerar ruptura nos itens de giro", "Otimizar estoque e capital de giro", "Gestão orientada por dados em tempo real"],
        [
            ("Diagnóstico da ruptura", F.INICIACAO, d(7, 1), d(7, 31), 0, [
                ("Levantar ruptura por item e filial nos últimos 6 meses", F.INICIACAO, d(7, 1), d(7, 15), 100),
                ("Revisar a curva ABC do CD e das lojas", F.INICIACAO, d(7, 16), d(7, 31), 100),
            ]),
            ("Parâmetros de reposição", F.PLANEJAMENTO, d(8, 1), d(9, 15), 0, [
                ("Definir estoque mínimo e ponto de pedido dos itens A", F.PLANEJAMENTO, d(8, 1), d(8, 31), 100),
                ("Cadastrar os parâmetros no WinThor", F.EXECUCAO, d(9, 1), d(9, 15), 60),
            ]),
            ("Sugestão de compra automática", F.EXECUCAO, d(9, 16), d(10, 31), 0, [
                ("Rotina diária de sugestão para o comprador", F.EXECUCAO, d(9, 16), d(10, 15), 10),
                ("Alerta de ruptura iminente para o CD", F.EXECUCAO, d(10, 1), d(10, 31), 0),
            ]),
            ("Acompanhamento semanal da ruptura", F.MONITORAMENTO, d(11, 1), d(11, 30), 0, []),
        ],
    ),
    (
        "Entrega no prazo: roteirização e nível de serviço",
        "Reorganizar rotas, janelas de entrega e conferência de carga para elevar o OTIF e reduzir devolução por atraso.",
        "Logística", (d(6, 1), d(10, 31)),
        ["Ser a melhor entrega do mercado (nível de serviço)", "Elevar a produtividade logística"],
        [
            ("Mapa das rotas atuais e dos atrasos", F.INICIACAO, d(6, 1), d(6, 30), 100, []),
            ("Novo desenho de rotas", F.PLANEJAMENTO, d(7, 1), d(8, 15), 0, [
                ("Agrupar clientes por região e janela de recebimento", F.PLANEJAMENTO, d(7, 1), d(7, 20), 100),
                ("Simular rotas e ocupação dos veículos", F.PLANEJAMENTO, d(7, 21), d(8, 15), 100),
            ]),
            ("Implantação", F.EXECUCAO, d(8, 16), d(9, 30), 0, [
                ("Rodar as novas rotas na região metropolitana", F.EXECUCAO, d(8, 16), d(9, 10), 80),
                ("Conferência de carga por coletor no CD", F.EXECUCAO, d(9, 1), d(9, 30), 50),
            ]),
            ("Medição do OTIF por rota e motorista", F.MONITORAMENTO, d(10, 1), d(10, 31), 0, []),
        ],
    ),
    (
        "Política comercial: preço, desconto e bonificação",
        "Tabela de preço por canal, alçadas de desconto e regra de bonificação para proteger a margem bruta.",
        "Comercial", (d(8, 1), d(12, 15)),
        ["Proteger a margem bruta", "Disciplina comercial de preço e bonificação", "Crescer o faturamento com rentabilidade"],
        [
            ("Raio-x da margem por vendedor, cliente e departamento", F.INICIACAO, d(8, 1), d(8, 31), 100, []),
            ("Desenho da política", F.PLANEJAMENTO, d(9, 1), d(10, 15), 0, [
                ("Alçadas de desconto por cargo", F.PLANEJAMENTO, d(9, 1), d(9, 30), 70),
                ("Regra e teto mensal de bonificação", F.PLANEJAMENTO, d(9, 15), d(10, 15), 30),
            ]),
            ("Parametrizar bloqueios no WinThor", F.EXECUCAO, d(10, 16), d(11, 15), 0, []),
            ("Treinar a força de vendas", F.EXECUCAO, d(11, 16), d(12, 15), 0, []),
        ],
    ),
    (
        "Crédito e cobrança: inadimplência sob controle",
        "Régua de cobrança, revisão dos limites de crédito e rotina semanal da carteira vencida.",
        "Financeiro", (d(7, 15), d(10, 31)),
        ["Reduzir a inadimplência e o ciclo de caixa"],
        [
            ("Classificar a carteira vencida por faixa de atraso", F.INICIACAO, d(7, 15), d(7, 31), 100, []),
            ("Régua de cobrança", F.EXECUCAO, d(8, 1), d(9, 15), 0, [
                ("Aviso automático 3 dias antes do vencimento", F.EXECUCAO, d(8, 1), d(8, 20), 100),
                ("Cobrança ativa D+5 e D+15", F.EXECUCAO, d(8, 21), d(9, 15), 70),
            ]),
            ("Revisão dos limites de crédito dos 200 maiores clientes", F.EXECUCAO, d(9, 1), d(10, 15), 35, []),
            ("Reunião semanal da carteira vencida", F.MONITORAMENTO, d(9, 16), d(10, 31), 20, []),
        ],
    ),
    (
        "Carteira ativa: reativação e aumento de mix",
        "Recuperar clientes inativos há mais de 60 dias e ampliar o número de departamentos comprados por cliente.",
        "Comercial", (d(9, 1), d(12, 20)),
        ["Ampliar e reter a base de clientes", "Crescer o mix por cliente", "Crescer o faturamento com rentabilidade"],
        [
            ("Lista de clientes inativos por vendedor", F.INICIACAO, d(9, 1), d(9, 15), 100, []),
            ("Campanha de reativação", F.EXECUCAO, d(9, 16), d(11, 15), 0, [
                ("Oferta de retorno para inativos 60–120 dias", F.EXECUCAO, d(9, 16), d(10, 31), 15),
                ("Visita do supervisor aos 50 maiores inativos", F.EXECUCAO, d(10, 1), d(11, 15), 0),
            ]),
            ("Meta de mix por cliente no pedido do vendedor", F.EXECUCAO, d(10, 15), d(12, 20), 0, []),
        ],
    ),
    (
        "Equipe: retenção e produtividade",
        "Reduzir o turnover do CD e das lojas com integração, trilha de treinamento e premiação por produtividade.",
        "Pessoas", (d(8, 15), d(12, 20)),
        ["Reter e engajar a equipe", "Elevar a produtividade logística"],
        [
            ("Entrevistas de desligamento e pesquisa de clima", F.INICIACAO, d(8, 15), d(9, 15), 100, []),
            ("Programa de integração dos novos", F.PLANEJAMENTO, d(9, 16), d(10, 31), 25, []),
            ("Premiação por produtividade", F.EXECUCAO, d(10, 1), d(12, 20), 0, [
                ("Indicadores e regra de premiação do CD", F.PLANEJAMENTO, d(10, 1), d(10, 31), 0),
                ("Piloto na separação e na expedição", F.EXECUCAO, d(11, 1), d(12, 20), 0),
            ]),
        ],
    ),
]

FCAS = {
    "Cadastrar os parâmetros no WinThor": (
        "Parte dos itens A está com embalagem de compra errada no cadastro, o que distorce o ponto de pedido.",
        "Cadastro de produto sem dono: cada comprador altera sem padrão.",
        "Corrigir a embalagem dos 120 itens A e definir Compras como dono do cadastro.",
    ),
    "Rodar as novas rotas na região metropolitana": (
        "Duas rotas novas estouram a jornada do motorista às sextas-feiras.",
        "Volume de sexta é 40% maior e a simulação usou a média da semana.",
        "Criar rota extra às sextas e antecipar parte das entregas para quinta.",
    ),
}


def _status(pct):
    return Andamento.FINALIZADO if pct >= 100 else Andamento.EM_ANDAMENTO if pct > 0 else Andamento.NAO_INICIADO


class Command(BaseCommand):
    help = "Cria os projetos estratégicos da Nordeste Boi, ligados aos objetivos do mapa."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="nordesteboi", help="slug da empresa")

    @transaction.atomic
    def handle(self, *args, **opts):
        tenant = Tenant.objects.filter(slug=opts["tenant"]).first()
        if tenant is None:
            raise CommandError(f"Empresa '{opts['tenant']}' não encontrada.")
        dono = (User.objects.filter(tenant=tenant, role=User.Role.ADMIN, is_active=True).order_by("id").first()
                or User.objects.filter(tenant=tenant, is_active=True).order_by("id").first())
        if dono is None:
            raise CommandError("A empresa não tem usuário ativo para ser o responsável.")
        mapa = mapa_padrao(tenant)
        objetivos = {o.name: o for o in StrategicObjective.objects.filter(tenant=tenant)}
        areas = {u.name: u for u in OrgUnit.objects.filter(tenant=tenant)}
        codigo = Project.objects.filter(tenant=tenant).aggregate(m=Max("code"))["m"] or 0

        criados = 0
        for titulo, descricao, area, (ini, fim), nomes_obj, eap in PROJETOS:
            if Project.objects.filter(tenant=tenant, title=titulo).exists():
                continue
            codigo += 1
            projeto = Project.objects.create(
                tenant=tenant, code=codigo, map=mapa, title=titulo, description=descricao, owner=dono,
                org_unit=areas.get(area), start_date=ini, end_date=fim, status=Andamento.EM_ANDAMENTO,
            )
            ligados = [objetivos[n] for n in nomes_obj if n in objetivos]
            projeto.objectives.set(ligados)
            faltando = [n for n in nomes_obj if n not in objetivos]
            if faltando:
                self.stdout.write(self.style.WARNING(f"  {titulo}: objetivo(s) não encontrado(s): {', '.join(faltando)}"))

            for ordem, (nome, fase, a_ini, a_fim, pct, filhas) in enumerate(eap, start=1):
                andando = pct > 0 or any(f[4] > 0 for f in filhas)
                todas_feitas = bool(filhas) and all(f[4] >= 100 for f in filhas)
                pai = ProjectActivity.objects.create(
                    project=projeto, title=nome, phase=fase, start_date=a_ini, end_date=a_fim, responsible=dono,
                    progress_pct=100 if todas_feitas else pct, order=ordem,
                    status=Andamento.FINALIZADO if todas_feitas else _status(pct) if not filhas else (Andamento.EM_ANDAMENTO if andando else Andamento.NAO_INICIADO),
                )
                for sub_ordem, (s_nome, s_fase, s_ini, s_fim, s_pct) in enumerate(filhas, start=1):
                    ProjectActivity.objects.create(
                        project=projeto, parent=pai, title=s_nome, phase=s_fase, start_date=s_ini, end_date=s_fim,
                        responsible=dono, progress_pct=s_pct, status=_status(s_pct), order=sub_ordem,
                    )
            for atividade in ProjectActivity.objects.filter(project=projeto, title__in=FCAS):
                fato, causa, acao = FCAS[atividade.title]
                ActivityFca.objects.create(activity=atividade, fact=fato, cause=causa, action=acao,
                                           due_date=atividade.end_date, responsible=dono)
            criados += 1

        self.stdout.write(self.style.SUCCESS(f"{tenant.name}: {criados} projeto(s) criado(s), {len(PROJETOS) - criados} já existia(m)."))
