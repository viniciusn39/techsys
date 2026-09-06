from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class Tenant(models.Model):
    name = models.CharField("nome", max_length=200)
    slug = models.SlugField(unique=True)
    cnpj = models.CharField(max_length=18, blank=True)
    logo = models.FileField(upload_to="logos/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TenantOwnedModel(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("E-mail é obrigatório")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ROOT)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ROOT = "root", "Root"
        ADMIN = "admin", "Administrador"
        GESTOR = "gestor", "Gestor"
        COLABORADOR = "colaborador", "Colaborador"

    username = None
    email = models.EmailField("e-mail", unique=True)
    first_name = models.CharField("nome", max_length=150)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, null=True, blank=True, related_name="users"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.COLABORADOR)
    org_unit = models.ForeignKey(
        "OrgUnit", on_delete=models.SET_NULL, null=True, blank=True, related_name="members"
    )
    cargo = models.CharField(max_length=100, blank=True)
    # Perfil de acesso por setor (RBAC): o que este usuário enxerga. Nulo = tudo do papel.
    access_profile = models.ForeignKey(
        "AccessProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="users",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["first_name", "email"]

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def is_root(self):
        return self.role == self.Role.ROOT


class OrgUnit(TenantOwnedModel):
    class Kind(models.TextChoices):
        EMPRESA = "empresa", "Empresa"
        AREA = "area", "Área"
        TIME = "time", "Time"

    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    name = models.CharField("nome", max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.AREA)
    manager = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="managed_units"
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


# Módulos do produto que um perfil pode liberar (chaves usadas pelo menu do frontend).
MODULOS = [
    ("dashboard", "Dashboard"), ("mapa", "Mapa estratégico"), ("metas", "Metas"), ("indicadores", "Indicadores"),
    ("painel_erp", "Painel do ERP"), ("cultura", "Cultura e identidade"), ("swot", "Análise SWOT"), ("canvas", "Canvas"),
    ("stakeholders", "Stakeholders"), ("relatorio", "Relatório"), ("planos", "Planos de ação"), ("agenda", "Agenda de gestão"),
    ("desvios", "Desvios"), ("ia", "Assistente IA"), ("usuarios", "Usuários"), ("organograma", "Organograma"), ("conector", "Conector ERP"),
]

# Setores dos indicadores (os mesmos do catálogo de KPIs do ERP).
SETORES = [
    ("vendas", "Vendas"), ("clientes", "Clientes"), ("financeiro", "Financeiro"), ("estoque", "Estoque"), ("compras", "Compras"),
    ("logistica", "Logística"), ("fiscal", "Fiscal"), ("rh", "Pessoas / RH"), ("forca_vendas", "Força de vendas"),
    ("wms", "Armazém / WMS"), ("roteirizacao", "Roteirização / entrega"), ("diretoria", "Diretoria"),
]


class AccessProfile(TenantOwnedModel):
    """Perfil de acesso por setor: quais indicadores (por setor) e quais módulos o usuário vê.

    Listas vazias significam "tudo". Os perfis padrão (Diretoria, Comercial,
    Financeiro, Logística, Suprimentos, Pessoas) nascem com a empresa e podem ser
    ajustados; o admin pode criar outros.
    """

    name = models.CharField("nome", max_length=80)
    key = models.SlugField(max_length=40)
    description = models.CharField(max_length=200, blank=True)
    sectors = models.JSONField("setores", default=list, blank=True)
    modules = models.JSONField("módulos", default=list, blank=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="uniq_access_profile_key")]

    def __str__(self):
        return self.name


PERFIS_PADRAO = [
    ("diretoria", "Diretoria", "Vê tudo: todos os setores e módulos.", [], []),
    ("comercial", "Comercial", "Vendas, clientes e força de vendas.", ["vendas", "clientes", "forca_vendas"],
     ["dashboard", "mapa", "metas", "indicadores", "cultura", "swot", "relatorio", "planos", "agenda", "desvios", "ia"]),
    ("financeiro", "Financeiro", "Financeiro e fiscal.", ["financeiro", "fiscal", "clientes"],
     ["dashboard", "mapa", "metas", "indicadores", "painel_erp", "relatorio", "planos", "agenda", "desvios", "ia"]),
    ("logistica", "Logística", "Logística, armazém e entrega.", ["logistica", "wms", "roteirizacao"],
     ["dashboard", "mapa", "metas", "indicadores", "planos", "agenda", "desvios", "ia"]),
    ("suprimentos", "Suprimentos", "Compras e estoque.", ["compras", "estoque"],
     ["dashboard", "mapa", "metas", "indicadores", "painel_erp", "planos", "agenda", "desvios", "ia"]),
    ("pessoas", "Pessoas", "RH e cultura.", ["rh"],
     ["dashboard", "mapa", "metas", "indicadores", "cultura", "stakeholders", "planos", "agenda", "desvios", "ia"]),
]


def seed_access_profiles(tenant):
    """Cria (sem duplicar) os perfis padrão da empresa."""
    criados = 0
    for key, name, desc, setores, modulos in PERFIS_PADRAO:
        _, novo = AccessProfile.objects.get_or_create(
            tenant=tenant, key=key,
            defaults={"name": name, "description": desc, "sectors": setores, "modules": modulos, "is_system": True},
        )
        criados += int(novo)
    return criados
