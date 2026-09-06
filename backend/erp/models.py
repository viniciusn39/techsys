"""Espelho canônico dos dados do ERP do cliente + infraestrutura do agente.

Duas metades:

1. **Conector/agente** — `Connector` (uma instalação do agente numa empresa),
   `ConnectorLog` (toda comunicação), `EntitySyncState` (última carga por
   entidade) e `AgentCommand` (tarefas que a plataforma manda o agente rodar).

2. **Dados de negócio** — as tabelas normalizadas que recebem o que o agente
   extrai. O schema é independente de ERP (nomes em inglês, tipos nossos); o que
   muda por ERP é o plano de coleta (`winthor.py`) e o mapa campo→coluna. Todo
   registro carrega `external_id` (a chave do ERP) e é gravado por upsert, então
   reprocessar é inofensivo.

Derivado do schema validado do vsystems-mi6 contra bases WinThor reais.
"""
from django.db import models

from accounts.models import Tenant, TenantOwnedModel


# ============================================================================
# Conector / agente
# ============================================================================

class Connector(TenantOwnedModel):
    class Erp(models.TextChoices):
        WINTHOR = "winthor", "TOTVS WinThor"

    class Perfil(models.TextChoices):
        DISTRIBUICAO = "distribuicao", "Distribuição / atacado"
        VAREJO = "varejo", "Varejo"
        MISTO = "misto", "Atacarejo (misto)"

    name = models.CharField("nome", max_length=120, default="WinThor")
    erp = models.CharField(max_length=20, choices=Erp.choices, default=Erp.WINTHOR)
    perfil = models.CharField(max_length=20, choices=Perfil.choices, default=Perfil.DISTRIBUICAO)
    # Token opaco que o agente manda no header X-Coletor-Token. É a identidade
    # do agente E da empresa — por isso é único e pode ser rotacionado.
    ingest_token = models.CharField(max_length=80, unique=True, db_index=True)
    # Ajustes por cliente que sobrescrevem o plano padrão:
    #   interval (s), historico_meses, entidades_indisponiveis [..], queries [..]
    config = models.JSONField(default=dict, blank=True)
    # Último heartbeat: oracle_ok, oracle_erro, agent_version, schema, cpu/mem...
    health = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.tenant})"

    @property
    def online(self):
        from datetime import timedelta

        from django.utils import timezone

        return bool(self.last_seen_at and self.last_seen_at >= timezone.now() - timedelta(minutes=5))

    @property
    def agent_version(self):
        return (self.health or {}).get("agent_version", "")


class ConnectorLog(TenantOwnedModel):
    class Kind(models.TextChoices):
        INGEST = "ingest", "Carga"
        HEARTBEAT = "heartbeat", "Heartbeat"
        ERROR = "error", "Erro"
        UPDATE = "update", "Atualização"
        PLAN = "plan", "Plano"
        COMMAND = "command", "Comando"
        RESULT = "result", "Resultado"

    connector = models.ForeignKey(Connector, on_delete=models.CASCADE, related_name="logs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    summary = models.CharField(max_length=240)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "connector", "created_at"])]


class EntitySyncState(TenantOwnedModel):
    """Última carga recebida por entidade — o que a tela de sincronização mostra."""

    connector = models.ForeignKey(Connector, on_delete=models.CASCADE, related_name="entities")
    entity = models.CharField(max_length=40)
    last_ingest_at = models.DateTimeField(null=True, blank=True)
    rows_received = models.PositiveIntegerField(default=0)
    rows_imported = models.PositiveIntegerField(default=0)
    total_imported = models.PositiveBigIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["connector", "entity"], name="uniq_sync_state_entity")
        ]
        ordering = ["entity"]


class AgentCommand(TenantOwnedModel):
    """Tarefa enfileirada para o agente executar no cliente (long-poll)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        SENT = "sent", "Enviado"
        DONE = "done", "Concluído"
        ERROR = "error", "Erro"

    connector = models.ForeignKey(Connector, on_delete=models.CASCADE, related_name="commands")
    command = models.CharField(max_length=40)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    leased_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


# ============================================================================
# Base dos dados de negócio
# ============================================================================

class ErpModel(TenantOwnedModel):
    """Registro espelhado do ERP: chave externa + carimbo da última carga."""

    external_id = models.CharField(max_length=120, db_index=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ============================================================================
# Cadastros
# ============================================================================

class Branch(ErpModel):
    """Filial (PCFILIAL). `code` é a chave usada pelas demais tabelas (CODFILIAL)."""

    code = models.CharField(max_length=20)
    name = models.CharField(max_length=160)
    trade_name = models.CharField(max_length=120, blank=True)
    cnpj = models.CharField(max_length=18, blank=True)
    state_registration = models.CharField(max_length=30, blank=True)
    street = models.CharField(max_length=160, blank=True)
    number = models.CharField(max_length=20, blank=True)
    district = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_branch_ext")]

    def __str__(self):
        return f"{self.code} - {self.name}"


class SalesRep(ErpModel):
    """Vendedor / RCA (PCUSUARI)."""

    code = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=120)
    document = models.CharField(max_length=20, blank=True)
    type = models.CharField(max_length=4, blank=True)
    email = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    city = models.CharField(max_length=80, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    team = models.CharField(max_length=20, blank=True)
    supervisor = models.CharField(max_length=120, blank=True)
    commission_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    sales_target = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_salesrep_ext")]

    def __str__(self):
        return self.name


class Supplier(ErpModel):
    """Fornecedor (PCFORNEC)."""

    name = models.CharField(max_length=160)
    trade_name = models.CharField(max_length=120, blank=True)
    document = models.CharField(max_length=20, blank=True)
    state_registration = models.CharField(max_length=30, blank=True)
    contact = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.CharField(max_length=120, blank=True)
    type = models.CharField(max_length=4, blank=True)
    lead_time_days = models.IntegerField(null=True, blank=True)
    min_order_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    last_purchase_at = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_supplier_ext")]

    def __str__(self):
        return self.name


class Employee(ErpModel):
    """Funcionário (PCEMPR). Alimenta turnover e absenteísmo."""

    registration = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=120)
    document = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=80, blank=True)
    department = models.CharField(max_length=40, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    admission_date = models.DateField(null=True, blank=True)
    dismissal_date = models.DateField(null=True, blank=True)
    salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    email = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_driver = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_employee_ext")]


class Customer(ErpModel):
    """Cliente (PCCLIENT + PCPRACA)."""

    name = models.CharField(max_length=160)
    trade_name = models.CharField(max_length=120, blank=True)
    document = models.CharField(max_length=20, blank=True)
    state_registration = models.CharField(max_length=30, blank=True)
    person_type = models.CharField(max_length=2, blank=True)
    email = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    whatsapp = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=160, blank=True)
    zip_code = models.CharField(max_length=10, blank=True)
    city = models.CharField(max_length=80, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    neighborhood = models.CharField(max_length=80, blank=True)
    region = models.CharField(max_length=20, blank=True)
    activity = models.CharField(max_length=20, blank=True)
    praca = models.CharField(max_length=60, blank=True)
    route = models.CharField(max_length=20, blank=True)
    latitude = models.CharField(max_length=30, blank=True)
    longitude = models.CharField(max_length=30, blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payment_term = models.CharField(max_length=10, blank=True)
    collection_type = models.CharField(max_length=10, blank=True)
    sales_rep = models.ForeignKey(SalesRep, on_delete=models.SET_NULL, null=True, blank=True, related_name="customers")
    blocked = models.BooleanField(default=False)
    first_purchase_at = models.DateField(null=True, blank=True)
    last_purchase_at = models.DateField(null=True, blank=True)
    registered_at = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_customer_ext")]
        indexes = [models.Index(fields=["tenant", "last_purchase_at"])]

    def __str__(self):
        return self.name


class Product(ErpModel):
    """Produto (PCPRODUT + hierarquia). Custo/preço aqui são referência (filial 1 / região 1)."""

    code = models.CharField(max_length=30, blank=True)
    name = models.CharField(max_length=160)
    ean = models.CharField(max_length=30, blank=True)
    ncm = models.CharField(max_length=20, blank=True)
    unit = models.CharField(max_length=6, blank=True)
    packaging = models.CharField(max_length=30, blank=True)
    brand = models.CharField(max_length=80, blank=True)
    department = models.CharField(max_length=80, blank=True)
    section = models.CharField(max_length=80, blank=True)
    category = models.CharField(max_length=80, blank=True)
    subcategory = models.CharField(max_length=80, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    units_per_box = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    net_weight = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    abc_class = models.CharField(max_length=2, blank=True)
    cost_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    replacement_cost = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_product_ext")]

    def __str__(self):
        return f"{self.code} - {self.name}"


class BankAccount(ErpModel):
    """Conta bancária / caixa (PCBANCO); saldo vem da PCESTCR."""

    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="bank_accounts")
    name = models.CharField(max_length=80)
    bank_number = models.CharField(max_length=10, blank=True)
    agency = models.CharField(max_length=20, blank=True)
    account = models.CharField(max_length=30, blank=True)
    account_type = models.CharField(max_length=4, blank=True)
    balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_bank_ext")]


# ============================================================================
# Estoque
# ============================================================================

class StockBalance(ErpModel):
    """Saldo por produto × filial (PCEST). Upsert pela chave natural."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="stock")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="stock")
    quantity = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    reserved = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    blocked = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    min_stock = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    max_stock = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    ideal_stock = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    avg_cost = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    last_entry_cost = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    replacement_cost = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    qty_sold_month = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    daily_turnover = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    qty_lost_sales = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    last_entry_at = models.DateField(null=True, blank=True)
    last_exit_at = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "branch"], name="uniq_stock_product_branch")]
        indexes = [models.Index(fields=["tenant", "branch"])]

    @property
    def available(self):
        return (self.quantity or 0) - (self.reserved or 0) - (self.blocked or 0)




# ============================================================================
# Vendas
# ============================================================================

class Order(ErpModel):
    """Pedido de venda (PCPEDC). Carteira/conversão; o faturamento oficial é a NF."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        SHIPPED = "shipped", "Faturado"
        CANCELED = "canceled", "Cancelado"

    number = models.CharField(max_length=30, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    sales_rep = models.ForeignKey(SalesRep, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    erp_position = models.CharField(max_length=4, blank=True)
    erp_cut_qty = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    sale_type = models.IntegerField(null=True, blank=True)
    payment_term = models.CharField(max_length=10, blank=True)
    discount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    freight = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_weight = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    cost_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    order_date = models.DateField(null=True, blank=True)
    delivery_date = models.DateField(null=True, blank=True)
    invoiced_at = models.DateField(null=True, blank=True)
    invoice_number = models.CharField(max_length=30, blank=True)
    nfe_key = models.CharField(max_length=44, blank=True)
    icms_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-order_date"]
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_order_ext")]
        indexes = [
            models.Index(fields=["tenant", "order_date"]),
            models.Index(fields=["tenant", "branch", "status"]),
        ]




class SalesInvoice(ErpModel):
    """Nota fiscal de saída (PCNFSAID) — o FATO do faturamento.

    O WinThor apura faturamento sobre esta tabela, nunca sobre o pedido: notas
    avulsas/balcão não existem na PCPEDC (diferença medida de ~1,4% no ano).
    """

    number = models.CharField(max_length=30, blank=True)
    series = models.CharField(max_length=6, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices")
    sales_rep = models.ForeignKey(SalesRep, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices")
    sale_type = models.IntegerField(null=True, blank=True)
    operation = models.CharField(max_length=4, blank=True)
    payment_term = models.CharField(max_length=10, blank=True)
    order_number = models.CharField(max_length=30, blank=True)
    load_number = models.CharField(max_length=30, blank=True)
    issued_at = models.DateField(null=True, blank=True)
    canceled_at = models.DateField(null=True, blank=True)
    supervisor = models.CharField(max_length=120, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_general = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    discount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    freight = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    ipi_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    icms_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    icms_st_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    nfe_key = models.CharField(max_length=44, blank=True)
    nfe_status = models.CharField(max_length=10, blank=True)
    kind = models.CharField(max_length=4, blank=True)

    class Meta:
        ordering = ["-issued_at"]
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_invoice_ext")]
        indexes = [
            models.Index(fields=["tenant", "issued_at"]),
            models.Index(fields=["tenant", "sale_type", "issued_at"]),
        ]


class SalesInvoiceItem(ErpModel):
    """Item da nota (PCMOV) — o que efetivamente saiu, com custo. Base da margem."""

    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, null=True, blank=True, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="invoice_items")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoice_items")
    sales_rep = models.ForeignKey(SalesRep, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoice_items")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoice_items")
    invoice_number = models.CharField(max_length=30, blank=True)
    order_number = models.CharField(max_length=30, blank=True)
    operation = models.CharField(max_length=4, blank=True)
    department = models.CharField(max_length=20, blank=True)
    section = models.CharField(max_length=20, blank=True)
    quantity = models.DecimalField(max_digits=16, decimal_places=3, default=0)
    boxes = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    unit_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    table_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    discount = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    commission_pct = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    cost = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    cost_real = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    moved_at = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_invoice_item_ext")]
        indexes = [
            models.Index(fields=["tenant", "moved_at"]),
            models.Index(fields=["tenant", "operation", "moved_at"]),
        ]

    @property
    def total(self):
        return (self.quantity or 0) * (self.unit_price or 0)

    @property
    def total_cost(self):
        return (self.quantity or 0) * (self.cost or self.cost_real or 0)


# ============================================================================
# Financeiro
# ============================================================================

class FinancialTitle(ErpModel):
    """Título a receber (PCPREST) ou a pagar (PCLANC)."""

    class Kind(models.TextChoices):
        RECEIVABLE = "receivable", "A receber"
        PAYABLE = "payable", "A pagar"

    class Status(models.TextChoices):
        OPEN = "open", "Aberto"
        PAID = "paid", "Pago"
        CANCELED = "canceled", "Cancelado"

    kind = models.CharField(max_length=12, choices=Kind.choices)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="titles")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="titles")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="titles")
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="titles")
    number = models.CharField(max_length=30, blank=True)
    installment = models.CharField(max_length=6, blank=True)
    description = models.CharField(max_length=200, blank=True)
    account = models.CharField(max_length=120, blank=True)
    tax_type = models.CharField(max_length=6, blank=True)
    payment_method = models.CharField(max_length=10, blank=True)
    collection_type = models.CharField(max_length=10, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    accrual_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    paid_at = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    fine = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "kind", "external_id"], name="uniq_title_kind_ext")
        ]
        indexes = [
            models.Index(fields=["tenant", "kind", "status", "due_date"]),
            models.Index(fields=["tenant", "kind", "paid_at"]),
        ]

    @property
    def balance(self):
        return (self.amount or 0) - (self.amount_paid or 0)




class CashMovement(ErpModel):
    """Movimento de conta corrente (PCMOVCR) — entradas e saídas reais de caixa."""

    bank_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="movements")
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="cash_movements")
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="cash_movements")
    transaction = models.CharField(max_length=30, blank=True)
    currency = models.CharField(max_length=10, blank=True)
    kind = models.CharField(max_length=2, blank=True)  # D = entrada, C = saída
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    moved_at = models.DateField(null=True, blank=True)
    settled_at = models.DateField(null=True, blank=True)
    reconciled_at = models.DateField(null=True, blank=True)
    history = models.CharField(max_length=200, blank=True)
    routine = models.CharField(max_length=10, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_cash_ext")]
        indexes = [models.Index(fields=["tenant", "moved_at"])]


class FinancialSnapshot(ErpModel):
    """Fotografia diária do financeiro por filial (PCFINANC) — caixa, bancos, CR, CP."""

    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="snapshots")
    date = models.DateField()
    bank_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cash_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    investments = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    receivables = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    payables = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    stock_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    net_position = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    sales_real = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    received_real = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cmv_real = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_snapshot_ext")]
        indexes = [models.Index(fields=["tenant", "date"])]


# ============================================================================
# Compras e logística
# ============================================================================

class PurchaseInvoice(ErpModel):
    """Nota de entrada (PCNFENT), agregada por NUMTRANSENT."""

    number = models.CharField(max_length=30, blank=True)
    series = models.CharField(max_length=6, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchases")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchases")
    issue_date = models.DateField(null=True, blank=True)
    entry_date = models.DateField(null=True, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    icms_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    ipi_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    freight = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    nfe_key = models.CharField(max_length=44, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_purchase_ext")]
        indexes = [models.Index(fields=["tenant", "entry_date"])]


class DeliveryLoad(ErpModel):
    """Carregamento / rota de entrega (PCCARREG)."""

    class Status(models.TextChoices):
        OPEN = "open", "Montando"
        DISPATCHED = "dispatched", "Em rota"
        RETURNED = "returned", "Retornado"
        CANCELED = "canceled", "Cancelado"

    number = models.CharField(max_length=30, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="loads")
    driver = models.CharField(max_length=120, blank=True)
    vehicle_plate = models.CharField(max_length=12, blank=True)
    route = models.CharField(max_length=20, blank=True)
    destination = models.CharField(max_length=60, blank=True)
    departure_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    num_invoices = models.IntegerField(null=True, blank=True)
    num_customers = models.IntegerField(null=True, blank=True)   # PCCARREG.NUMENT (clientes distintos)
    num_cities = models.IntegerField(null=True, blank=True)      # PCCARREG.NUMCID (praças distintas)
    km_start = models.DecimalField(max_digits=12, decimal_places=1, null=True, blank=True)   # KMINICIAL (acerto)
    km_end = models.DecimalField(max_digits=12, decimal_places=1, null=True, blank=True)     # KMFINAL
    total_weight = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    freight = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_load_ext")]




class SalesTarget(ErpModel):
    """Meta cadastrada no ERP (WinThor PCMETA): por filial × RCA × mês.

    O WinThor guarda metas de venda, positivação, mix, margem e pedidos por
    vendedor. A plataforma soma/pondera por filial para alimentar a meta dos
    indicadores marcados com `erp_target`.
    """

    KIND_DAILY = "DIA"  # linha da PCMETARCA: `period` é o DIA, não o mês

    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_targets")
    sales_rep = models.ForeignKey(SalesRep, on_delete=models.SET_NULL, null=True, blank=True, related_name="sales_targets")
    period = models.DateField()                       # dia 1 do mês (PCMETA) ou o dia (PCMETARCA)
    kind = models.CharField(max_length=4, blank=True)  # TIPOMETA da PCMETA, ou "DIA"
    sales_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)   # VLVENDAPREV
    sales_qty = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)     # QTVENDAPREV
    # Contagens em decimal: a meta diária do WinThor rateia clientes/pedidos
    # do mês por dia em frações (1,37 cliente/dia) — inteiro truncaria a soma.
    mix = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)            # MIXPREV
    positivation = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)   # CLIPOSPREV / NUMCLIPOS
    positivation_pct = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)  # PERCLIPOSPREV
    margin_pct = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)     # MARGEMPREV
    orders = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)         # PEDIDOSPREV / QTPEDPREV
    avg_order_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)  # VLMEDIOPEDIDO
    active_customers = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)  # QTDCLIENTESATIVO

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_sales_target_ext")]
        indexes = [models.Index(fields=["tenant", "period"])]


class WmsOrder(ErpModel):
    """Ordem de serviço do WMS (PCMOVENDPEND) agregada por NUMOS.

    Uma OS tem uma linha por produto no WinThor; aqui vira uma linha por OS com
    quantidades somadas e os carimbos de início/fim de separação e conferência.
    É o que dá tempo de separação, produtividade, corte e erro do armazém.
    """

    number = models.CharField(max_length=30)                      # NUMOS
    os_type = models.CharField(max_length=6, blank=True)          # TIPOOS
    operation = models.CharField(max_length=4, blank=True)        # CODOPER (S* saída, E* entrada)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="wms_orders")
    order_number = models.CharField(max_length=30, blank=True)    # NUMPED
    load_number = models.CharField(max_length=30, blank=True)     # NUMCAR
    date = models.DateField(null=True, blank=True)                # DATA
    position = models.CharField(max_length=2, blank=True)         # POSICAO (P pendente, C cancelada)
    lines = models.IntegerField(default=0)                        # linhas (produtos) da OS
    qty = models.DecimalField(max_digits=16, decimal_places=3, default=0)          # Σ QT
    qty_picked = models.DecimalField(max_digits=16, decimal_places=3, default=0)   # Σ QTSEPARADA
    qty_checked = models.DecimalField(max_digits=16, decimal_places=3, default=0)  # Σ QTCONFERIDA
    qty_canceled = models.DecimalField(max_digits=16, decimal_places=3, default=0) # Σ QTCANCEL
    errors = models.IntegerField(default=0)                       # Σ QTERROS
    picking_start = models.DateTimeField(null=True, blank=True)   # MIN DTINICIOOS
    picking_end = models.DateTimeField(null=True, blank=True)     # MAX DTFIMSEPARACAO (só se todas as linhas)
    check_start = models.DateTimeField(null=True, blank=True)     # MIN DTINICIOCONFERENCIA
    check_end = models.DateTimeField(null=True, blank=True)       # MAX DTFIMCONFERENCIA
    picker = models.CharField(max_length=20, blank=True)          # CODFUNCOS
    checker = models.CharField(max_length=20, blank=True)         # CODFUNCCONF

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_wms_order_ext")]
        indexes = [models.Index(fields=["tenant", "date"])]


class RouteLoad(ErpModel):
    """Carga enviada ao roteirizador (FusionTrak FUSIONT.FUSIONTRAK_INT_CARGA)."""

    load_number = models.CharField(max_length=30, blank=True)     # CARGAS_GERADAS_ERP / NUMCAR
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name="route_loads")
    departure_date = models.DateField(null=True, blank=True)      # T10_DATA_SAIDA
    routed_at = models.DateField(null=True, blank=True)           # FUSIONTRAK_CARGAS_ROTEIRIZADAS.DTROTEIRIZACAO
    vehicle_code = models.CharField(max_length=20, blank=True)    # T06_CODIGO_ERP
    driver_code = models.CharField(max_length=20, blank=True)     # T05_CODIGO_ERP
    route = models.CharField(max_length=20, blank=True)           # CODROTAPRINC
    weight = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    volume = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    max_weight = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)   # T06_PESO_MAX_ENTREGAS
    max_volume = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    num_items = models.IntegerField(null=True, blank=True)
    num_customers = models.IntegerField(null=True, blank=True)
    num_cities = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, blank=True)          # STATUS_INT

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_route_load_ext")]
        indexes = [models.Index(fields=["tenant", "departure_date"])]


class DeliveryEvent(ErpModel):
    """Evento de entrega vindo da rua (FusionTrak FUSIONT.FUSIONTRAK_INT_EVENTOS)."""

    event_type = models.CharField(max_length=10, blank=True)      # TIPO (7 = ocorrência que vira PCMENS)
    occurred_at = models.DateField(null=True, blank=True)
    order_number = models.CharField(max_length=30, blank=True)    # SEQ_PEDIDO_ERP
    load_number = models.CharField(max_length=30, blank=True)
    driver_code = models.CharField(max_length=20, blank=True)     # MOTORISTA_CODIGO_ERP
    vehicle_plate = models.CharField(max_length=12, blank=True)
    km = models.DecimalField(max_digits=12, decimal_places=1, null=True, blank=True)   # KMATUAL
    latitude = models.CharField(max_length=30, blank=True)
    longitude = models.CharField(max_length=30, blank=True)
    reason_id = models.IntegerField(null=True, blank=True)        # MOTIVO_DEVOL_REENT_ID
    note = models.CharField(max_length=300, blank=True)           # OBS_MOTORISTA

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_delivery_event_ext")]
        indexes = [models.Index(fields=["tenant", "occurred_at"])]


class KpiTemplate(models.Model):
    """Modelo de KPI por ERP — o catálogo que a empresa "pluga" com um clique.

    Global (não é por tenant): vale para todo cliente cujo conector é daquele
    ERP. Cada modelo aponta para uma métrica do espelho (`erp_metric`) e,
    opcionalmente, para uma fonte de meta (`erp_target`). `status` diz se o
    dado já é calculável hoje ou se depende de uma entidade ainda não
    coletada (`requer`). Semeado por `manage.py seed_kpi_winthor` a partir de
    `erp/catalogo_winthor.py`; editável no admin.
    """

    class Setor(models.TextChoices):
        VENDAS = "vendas", "Vendas"
        CLIENTES = "clientes", "Clientes"
        FINANCEIRO = "financeiro", "Financeiro"
        ESTOQUE = "estoque", "Estoque"
        COMPRAS = "compras", "Compras"
        LOGISTICA = "logistica", "Logística"
        FISCAL = "fiscal", "Fiscal"
        RH = "rh", "Pessoas / RH"
        FORCA_VENDAS = "forca_vendas", "Força de vendas"
        WMS = "wms", "Armazém / WMS"
        ROTEIRIZACAO = "roteirizacao", "Roteirização / entrega"
        DIRETORIA = "diretoria", "Diretoria"

    class Perspectiva(models.TextChoices):
        FINANCEIRA = "financeira", "Financeira"
        CLIENTES = "clientes", "Clientes"
        PROCESSOS = "processos", "Processos internos"
        APRENDIZADO = "aprendizado", "Aprendizado e crescimento"

    class Status(models.TextChoices):
        PRONTO = "pronto", "Pronto (calculado do espelho)"
        PLANEJADO = "planejado", "Planejado (depende de coleta adicional)"

    class Origem(models.TextChoices):
        WINTHOR = "winthor", "Regra do próprio WinThor"
        FORCA_VENDAS = "forca_vendas", "Aprendida da força de vendas (Ion / MaxSoluções)"
        WMS = "wms", "Módulo WMS do WinThor"
        ROTEIRIZADOR = "roteirizador", "Roteirizador (FusionTrak)"
        TECHSYS = "techsys", "Composição TechSys sobre dados do ERP"

    erp = models.CharField(max_length=20, default=Connector.Erp.WINTHOR, db_index=True)
    # De onde veio a inteligência do KPI (root) e o que o cliente precisa ter
    # além do WinThor para o número existir ("" = qualquer banco WinThor).
    origin = models.CharField(max_length=20, choices=Origem.choices, default=Origem.WINTHOR)
    requires_system = models.CharField(max_length=120, blank=True)
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=200)
    sector = models.CharField(max_length=20, choices=Setor.choices)
    perspective = models.CharField(max_length=20, choices=Perspectiva.choices, default=Perspectiva.PROCESSOS)
    unit = models.CharField(max_length=20, blank=True)
    decimals = models.PositiveSmallIntegerField(default=2)
    polarity = models.CharField(max_length=20, default="maior_melhor")
    aggregation = models.CharField(max_length=20, default="soma")
    description = models.TextField(blank=True)        # o que mede, em linguagem de gestão
    explanation = models.TextField(blank=True)        # como é calculado, sem termo técnico (vai para o cliente)
    importance = models.TextField(blank=True)         # por que importa e o que fazer com o número (vai para o cliente)
    rule = models.TextField(blank=True)               # regra no WinThor: tabelas, colunas, PL/SQL (só root)
    erp_metric = models.CharField(max_length=60, blank=True)
    erp_target = models.CharField(max_length=40, blank=True)
    default_filters = models.JSONField(default=dict, blank=True)
    entities = models.JSONField(default=list, blank=True)   # entidades do espelho que a métrica lê
    requer = models.JSONField(default=list, blank=True)     # tabelas do ERP ainda não coletadas
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PRONTO)
    tags = models.JSONField(default=list, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sector", "order", "code"]
        constraints = [models.UniqueConstraint(fields=["erp", "code"], name="uniq_kpi_template_erp_code")]

    def __str__(self):
        return f"[{self.erp}] {self.code} — {self.name}"


class ErpRecord(ErpModel):
    """Qualquer tabela do ERP sem modelo dedicado: a linha crua em JSON."""

    entity = models.CharField(max_length=40)
    data = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "entity", "external_id"], name="uniq_erp_record")
        ]
        indexes = [models.Index(fields=["tenant", "entity"])]
