"""Calibra as metas dos indicadores ligados ao ERP a partir do histórico real.

Regra em indicators/calibracao.py: mediana dos últimos 12 meses fechados,
melhorada em 5 % na direção da polaridade, gravada em cada mês do ano. Vale
para todos os indicadores do ERP (a meta do WinThor deixa de ser usada).
Metas já cadastradas só são substituídas com --sobrescrever. Depois recalcula
os faróis. A mesma regra roda sozinha todo dia 1º e ao plugar um KPI.

Exemplos:
  manage.py calibrar_metas --tenant nordesteboi --meses 6 --melhoria 5 --sobrescrever
  manage.py calibrar_metas --tenant nordesteboi --plugar CLI_VENC_PCT=3,PESO_VENDIDO=9 --desativar REC,OTIF
  manage.py calibrar_metas --tenant nordesteboi --limpar-desvios
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from accounts.models import OrgUnit, Tenant
from indicators.models import Indicator, IndicatorTarget, IndicatorValue


class Command(BaseCommand):
    help = "Calibra metas dos indicadores do ERP pelo histórico; pluga KPIs do catálogo; limpa desvios obsoletos."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="slug da empresa")
        parser.add_argument("--meses", type=int, default=12, help="meses completos de histórico (padrão 12)")
        parser.add_argument("--melhoria", type=float, default=5.0, help="%% de melhoria sobre a mediana (padrão 5)")
        parser.add_argument("--ano", type=int, default=None, help="ano das metas (padrão: corrente)")
        parser.add_argument("--sobrescrever", action="store_true", help="substitui metas já cadastradas")
        parser.add_argument("--apenas", default="", help="só estes códigos (vírgula)")
        parser.add_argument("--plugar", default="", help="KPIs do catálogo: CODE=objetivo_id,CODE2=objetivo_id (objetivo opcional)")
        parser.add_argument("--desativar", default="", help="códigos de indicadores a desativar (vírgula)")
        parser.add_argument("--desativar-vazios", action="store_true", help="desativa indicadores ativos sem nenhum lançamento (ficam só no catálogo)")
        parser.add_argument("--limpar-desvios", action="store_true", help="apaga desvios abertos sem plano cujo valor já não é vermelho")
        parser.add_argument("--recalcular", action="store_true", help="recalcula valores do ERP e metas do ERP antes de calibrar")
        parser.add_argument("--sem-metas", action="store_true", help="não calibra metas (só pluga/desativa/limpa)")

    def handle(self, *args, **o):
        tenant = Tenant.objects.filter(slug=o["tenant"]).first()
        if tenant is None:
            raise CommandError(f"empresa '{o['tenant']}' não existe")
        self.tenant = tenant

        if o["plugar"]:
            self.plugar(o["plugar"])
        if o["desativar"]:
            codes = [c.strip().upper() for c in o["desativar"].split(",") if c.strip()]
            n = Indicator.objects.filter(tenant=tenant, code__in=codes).update(is_active=False)
            self.stdout.write(f"desativados: {n} ({', '.join(codes)})")

        if o["desativar_vazios"]:
            vazios = Indicator.objects.filter(tenant=tenant, is_active=True, values__isnull=True)
            codes = list(vazios.values_list("code", flat=True))
            n = Indicator.objects.filter(id__in=vazios).update(is_active=False)
            self.stdout.write(f"desativados sem lançamento: {n} ({', '.join(codes) or '-'})")

        if o["recalcular"]:
            from erp.tasks import calcular_indicadores_erp

            self.stdout.write("recalculando valores do ERP (12 meses)…")
            calcular_indicadores_erp(tenant_id=tenant.id, meses=12)

        if not o["sem_metas"]:
            apenas = {c.strip().upper() for c in o["apenas"].split(",") if c.strip()}
            self.calibrar(o["meses"], Decimal(str(o["melhoria"])), o["ano"] or date.today().year, o["sobrescrever"], apenas)

        if o["limpar_desvios"]:
            self.limpar_desvios()

    # ------------------------------------------------------------------ metas
    def calibrar(self, meses, melhoria, ano, sobrescrever, apenas):
        from indicators.calibracao import calibrar_tenant

        self.stdout.write(f"{'código':14} {'base (mediana)':>16} {'meses':>5} {'meta/mês':>16}  obs")
        for r in calibrar_tenant(self.tenant, ano, meses, melhoria, sobrescrever, apenas or None):
            base = f"{r.base:.2f}" if r.base is not None else "—"
            meta = f"{r.meta}" if r.meta is not None else "—"
            fim = f"{r.gravadas} meses gravados" if r.meta is not None else "pulado"
            self.stdout.write(f"{r.code:14} {base:>16} {r.meses_usados:>5} {meta:>16}  {fim}{(' · ' + r.obs) if r.obs else ''}")

    # ------------------------------------------------------------------ plugar
    def plugar(self, spec):
        from erp.models import Connector, KpiTemplate

        conector = Connector.objects.filter(tenant=self.tenant, is_active=True).first()
        erp = conector.erp if conector else Connector.Erp.WINTHOR
        raiz = OrgUnit.objects.filter(tenant=self.tenant, parent__isnull=True).first()
        for item in spec.split(","):
            item = item.strip()
            if not item:
                continue
            code, _, obj = item.partition("=")
            code = code.strip().upper()
            t = KpiTemplate.objects.filter(erp=erp, is_active=True, code=code).first()
            if t is None:
                self.stdout.write(f"  {code}: fora do catálogo")
                continue
            if Indicator.objects.filter(tenant=self.tenant, code=code).exists():
                ind = Indicator.objects.get(tenant=self.tenant, code=code)
                if obj and not ind.objective_id:
                    ind.objective_id = int(obj)
                    ind.save(update_fields=["objective"])
                self.stdout.write(f"  {code}: já existia")
                continue
            if t.status == KpiTemplate.Status.PLANEJADO:
                self.stdout.write(f"  {code}: planejado (sem métrica), pulado")
                continue
            descricao = t.description
            if t.explanation:
                descricao += f"\n\nComo é calculado: {t.explanation}"
            if t.importance:
                descricao += f"\n\nPor que importa: {t.importance}"
            Indicator.objects.create(
                tenant=self.tenant, code=t.code, name=t.name, description=descricao, sector=t.sector,
                unit=t.unit, decimals=t.decimals, polarity=t.polarity, aggregation=t.aggregation,
                org_unit=raiz, objective_id=int(obj) if obj else None,
                erp_metric=t.erp_metric, erp_filters=dict(t.default_filters or {}), erp_target=t.erp_target,
            )
            self.stdout.write(f"  {code}: criado ({t.name})")

    # ------------------------------------------------------------------ desvios
    def limpar_desvios(self):
        from plans.models import ActionPlan, Deviation

        removidos = 0
        for d in Deviation.objects.filter(tenant=self.tenant, status=Deviation.Status.ABERTO).select_related("indicator_value"):
            if ActionPlan.objects.filter(deviation=d).exists():
                continue
            if d.indicator_value.status != IndicatorValue.Status.VERMELHO:
                d.delete()
                removidos += 1
        self.stdout.write(f"desvios obsoletos removidos: {removidos}")
