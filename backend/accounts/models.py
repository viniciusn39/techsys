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
