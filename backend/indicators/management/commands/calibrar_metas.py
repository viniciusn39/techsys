"""Calibra as metas dos indicadores ligados ao ERP a partir do histórico real.

Meta digitada "no chute" (ou herdada do seed) vira farol vermelho em tudo e
esconde o que importa. Este comando olha os últimos N meses completos já
calculados do espelho, tira a MEDIANA (robusta a mês parcial) e grava, para
cada mês do ano, a meta = mediana melhorada em X % na direção da polaridade
(maior é melhor: +X %; menor é melhor: −X %). Indicador cuja meta vem do ERP
(`erp_target`) não é tocado. Metas manuais só são substituídas com
--sobrescrever. Depois recalcula os faróis.

Exemplos:
  manage.py calibrar_metas --tenant nordesteboi --meses 6 --melhoria 5 --sobrescrever
  manage.py calibrar_metas --tenant nordesteboi --plugar CLI_VENC_PCT=3,PESO_VENDIDO=9 --desativar REC,OTIF
  manage.py calibrar_metas --tenant nordesteboi --limpar-desvios
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from statistics import median

from django.core.management.base import BaseCommand, CommandError

from accounts.models import OrgUnit, Tenant
from indicators.models import Indicator, IndicatorTarget, IndicatorValue
from indicators.services import recompute_indicator


class Command(BaseCommand):
    help = "Calibra metas dos indicadores do ERP pelo histórico; pluga KPIs do catálogo; limpa desvios obsoletos."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="slug da empresa")
        parser.add_argument("--meses", type=int, default=6, help="meses completos de histórico (padrão 6)")
        parser.add_argument("--melhoria", type=float, default=5.0, help="%% de melhoria sobre a mediana (padrão 5)")
        parser.add_argument("--ano", type=int, default=None, help="ano das metas (padrão: corrente)")
        parser.add_argument("--sobrescrever", action="store_true", help="substitui metas já cadastradas")
        parser.add_argument("--apenas", default="", help="só estes códigos (vírgula)")
        parser.add_argument("--plugar", default="", help="KPIs do catálogo: CODE=objetivo_id,CODE2=objetivo_id (objetivo opcional)")
        parser.add_argument("--desativar", default="", help="códigos de indicadores a desativar (vírgula)")
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

        if o["recalcular"]:
            from erp.tasks import calcular_indicadores_erp, sincronizar_metas_erp

            self.stdout.write("recalculando valores do ERP (12 meses)…")
            calcular_indicadores_erp(tenant_id=tenant.id, meses=12)
            sincronizar_metas_erp(tenant_id=tenant.id, meses=12)

        if not o["sem_metas"]:
            apenas = {c.strip().upper() for c in o["apenas"].split(",") if c.strip()}
            self.calibrar(o["meses"], Decimal(str(o["melhoria"])), o["ano"] or date.today().year, o["sobrescrever"], apenas)

        if o["limpar_desvios"]:
            self.limpar_desvios()

    # ------------------------------------------------------------------ metas
    def calibrar(self, meses, melhoria, ano, sobrescrever, apenas):
        hoje = date.today()
        mes_corrente = hoje.replace(day=1)
        qs = Indicator.objects.filter(tenant=self.tenant, is_active=True).exclude(erp_metric="").filter(erp_target="")
        if apenas:
            qs = qs.filter(code__in=apenas)
        self.stdout.write(f"{'código':14} {'base (mediana)':>16} {'meses':>5} {'meta/mês':>16}  obs")
        for ind in qs.order_by("code"):
            historico = list(
                IndicatorValue.objects.filter(indicator=ind, period__lt=mes_corrente)
                .order_by("-period").values_list("value", flat=True)[:meses]
            )
            historico = [Decimal(v) for v in historico if v is not None]
            obs = ""
            if len(historico) >= 2:
                base = Decimal(str(median(historico)))
            else:
                atual = IndicatorValue.objects.filter(indicator=ind, period=mes_corrente).values_list("value", flat=True).first()
                if atual is None:
                    self.stdout.write(f"{ind.code:14} {'—':>16} {len(historico):>5} {'—':>16}  sem histórico: pulado")
                    continue
                base = Decimal(atual)
                obs = "fotografia: base = valor de hoje"
            if ind.polarity == Indicator.Polarity.MAIOR_MELHOR:
                if base <= 0:
                    self.stdout.write(f"{ind.code:14} {base:>16.2f} {len(historico):>5} {'—':>16}  base zero em 'maior é melhor': pulado")
                    continue
                meta = base * (1 + melhoria / 100)
            else:
                meta = base * (1 - melhoria / 100)
                if meta < 0:
                    meta = Decimal("0")
            q = Decimal(1).scaleb(-int(ind.decimals))
            meta = meta.quantize(q, rounding=ROUND_HALF_UP)
            gravadas = 0
            for m in range(1, 13):
                periodo = date(ano, m, 1)
                existente = IndicatorTarget.objects.filter(indicator=ind, period=periodo).first()
                if existente and not sobrescrever:
                    continue
                if existente:
                    existente.target_value = meta
                    existente.save(update_fields=["target_value"])
                else:
                    IndicatorTarget.objects.create(indicator=ind, period=periodo, target_value=meta)
                gravadas += 1
            recompute_indicator(ind)
            self.stdout.write(f"{ind.code:14} {base:>16.2f} {len(historico):>5} {meta:>16}  {gravadas} meses gravados{(' · ' + obs) if obs else ''}")

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
                tenant=self.tenant, code=t.code, name=t.name, description=descricao,
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
