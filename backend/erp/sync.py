"""Motor de importação: lotes crus do agente -> tabelas normalizadas.

Cada item chega como {ALIAS_ORACLE: valor}. O mapa `fields` (winthor.DEFAULT_SYNC)
traduz para o nosso schema e o registro é gravado por upsert — reprocessar o
mesmo lote é inofensivo.

Campos-FK (ENTITY_FKS) chegam com o CÓDIGO do ERP (CODCLI, CODFILIAL...) e são
resolvidos para a instância local por external_id no mesmo tenant. Por isso a
ordem de coleta importa: cadastros antes de movimentos. Código órfão em FK
opcional vira NULL; em FK obrigatória (REQUIRED_FKS) a linha é pulada.
"""
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import MultipleObjectsReturned
from django.db import models as dj_models, transaction

from .models import (
    BankAccount,
    Branch,
    CardSettlement,
    CashMovement,
    CreditAuthorization,
    Customer,
    CustomerCredit,
    DeliveryEvent,
    DeliveryLoad,
    Employee,
    ErpRecord,
    FinancialSnapshot,
    FinancialTitle,
    FvOrder,
    Mdfe,
    Order,
    OrderBlock,
    PosDaily,
    Product,
    PurchaseInvoice,
    PurchaseOrder,
    RouteLoad,
    SalesInvoice,
    SalesInvoiceItem,
    SalesRep,
    SalesTarget,
    StockBalance,
    Supplier,
    SupplierCredit,
    WmsOrder,
)

logger = logging.getLogger(__name__)

ENTITY_MODELS = {
    "branch": Branch,
    "salesrep": SalesRep,
    "supplier": Supplier,
    "employee": Employee,
    "customer": Customer,
    "product": Product,
    "bank_account": BankAccount,
    "stock": StockBalance,
    "order": Order,
    "sales_invoice": SalesInvoice,
    "sales_invoice_item": SalesInvoiceItem,
    "title_receivable": FinancialTitle,
    "title_payable": FinancialTitle,
    "cash_movement": CashMovement,
    "financial_snapshot": FinancialSnapshot,
    "purchase": PurchaseInvoice,
    "load": DeliveryLoad,
    "target": SalesTarget,
    "target_daily": SalesTarget,
    "wms_os": WmsOrder,
    "route_load": RouteLoad,
    "delivery_event": DeliveryEvent,
    "order_block": OrderBlock,
    "fv_order": FvOrder,
    "customer_credit": CustomerCredit,
    "credit_auth": CreditAuthorization,
    "card_settlement": CardSettlement,
    "pos_daily": PosDaily,
    "purchase_order": PurchaseOrder,
    "supplier_credit": SupplierCredit,
    "mdfe": Mdfe,
}

ENTITY_DEFAULTS = {
    "target_daily": {"kind": SalesTarget.KIND_DAILY},
    "title_receivable": {"kind": FinancialTitle.Kind.RECEIVABLE},
    "title_payable": {"kind": FinancialTitle.Kind.PAYABLE},
}

ENTITY_FKS = {
    "employee": {"branch": Branch},
    "customer": {"sales_rep": SalesRep},
    "product": {"supplier": Supplier},
    "bank_account": {"branch": Branch},
    "stock": {"product": Product, "branch": Branch},
    "order": {"customer": Customer, "sales_rep": SalesRep, "branch": Branch},
    "sales_invoice": {"customer": Customer, "sales_rep": SalesRep, "branch": Branch},
    "sales_invoice_item": {
        "invoice": SalesInvoice, "product": Product, "customer": Customer,
        "sales_rep": SalesRep, "branch": Branch,
    },
    "title_receivable": {"customer": Customer, "branch": Branch, "order": Order},
    "title_payable": {"supplier": Supplier, "branch": Branch},
    "cash_movement": {"bank_account": BankAccount, "branch": Branch, "customer": Customer},
    "financial_snapshot": {"branch": Branch},
    "purchase": {"supplier": Supplier, "branch": Branch},
    "load": {"branch": Branch},
    "target": {"branch": Branch, "sales_rep": SalesRep},
    "target_daily": {"branch": Branch, "sales_rep": SalesRep},
    "wms_os": {"branch": Branch},
    "route_load": {"branch": Branch},
    "fv_order": {"sales_rep": SalesRep, "customer": Customer, "branch": Branch},
    "customer_credit": {"customer": Customer, "branch": Branch},
    "credit_auth": {"customer": Customer, "sales_rep": SalesRep},
    "card_settlement": {"branch": Branch, "customer": Customer},
    "pos_daily": {"branch": Branch},
    "purchase_order": {"supplier": Supplier, "branch": Branch},
    "supplier_credit": {"supplier": Supplier, "branch": Branch},
    "mdfe": {"branch": Branch},
}

REQUIRED_FKS = {
    "stock": ("product", "branch"),
    "sales_invoice_item": ("product",),
}

# Upsert pela chave natural (constraint única) em vez de external_id.
NATURAL_KEYS = {
    "stock": ("product", "branch"),
}

# Campos que entram na chave do upsert junto com external_id.
LOOKUP_EXTRA = {
    "title_receivable": ("kind",),
    "title_payable": ("kind",),
}

# Filial é referenciada pelo CÓDIGO (CODFILIAL '1'), que é o external_id dela.
_TRUE = {"1", "S", "Y", "T", "TRUE", "SIM"}


def _coerce(field, value):
    """Converte o valor cru do Oracle (sempre texto/número) para o tipo do campo."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None

    if isinstance(field, dj_models.BooleanField):
        if isinstance(value, bool):
            return value
        return str(value).strip().upper() in _TRUE

    if isinstance(field, dj_models.DateField) and not isinstance(field, dj_models.DateTimeField):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value)[:10]
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    if isinstance(field, dj_models.DateTimeField):
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    if isinstance(field, dj_models.DecimalField):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    if isinstance(field, (dj_models.IntegerField, dj_models.BigIntegerField)):
        try:
            return int(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            return None

    if isinstance(field, dj_models.CharField):
        text = str(value)
        return text[: field.max_length] if field.max_length else text

    return value


def _resolve_fk(cache, tenant, model, value):
    ext = str(value).strip() if value is not None else ""
    if not ext:
        return None
    # Códigos numéricos chegam como "1.0"/"12.0" quando o driver devolve float.
    if ext.endswith(".0"):
        ext = ext[:-2]
    key = (model, ext)
    if key not in cache:
        cache[key] = model.objects.filter(tenant=tenant, external_id=ext).first()
    return cache[key]


def _normalize_ext(value):
    ext = str(value).strip() if value is not None else ""
    return ext[:-2] if ext.endswith(".0") else ext


def _linhas_preparadas(connector, entity, raw_items, fields):
    """Traduz o lote cru em (lookup, data) por linha, já com FKs resolvidas."""
    model = ENTITY_MODELS[entity]
    tenant = connector.tenant
    fks = ENTITY_FKS.get(entity, {})
    required = REQUIRED_FKS.get(entity, ())
    natural = NATURAL_KEYS.get(entity)
    lookup_extra = LOOKUP_EXTRA.get(entity, ())
    defaults_fixed = ENTITY_DEFAULTS.get(entity, {})
    model_fields = {f.name: f for f in model._meta.get_fields() if hasattr(f, "attname")}

    cache = {}
    linhas, errors = [], []
    for raw in raw_items or []:
        try:
            data = dict(defaults_fixed)
            for local, alias in fields.items():
                if alias not in raw:
                    continue
                value = raw.get(alias)
                if local in fks:
                    data[local] = _resolve_fk(cache, tenant, fks[local], value)
                elif local in model_fields:
                    coerced = _coerce(model_fields[local], value)
                    if coerced is not None:
                        data[local] = coerced
            if any(data.get(f) is None for f in required):
                continue
            ext = _normalize_ext(data.pop("external_id", ""))
            if natural:
                lookup = {"tenant": tenant, **{k: data.pop(k) for k in natural if k in data}}
                if any(v is None for v in lookup.values()):
                    continue
                data["external_id"] = ext
            else:
                if not ext:
                    continue
                lookup = {"tenant": tenant, "external_id": ext}
                for extra in lookup_extra:
                    lookup[extra] = data.get(extra)
            linhas.append((lookup, data))
        except Exception as exc:  # noqa: BLE001 — uma linha ruim não derruba o lote
            if len(errors) < 3:
                errors.append(f"{type(exc).__name__}: {str(exc)[:160]}")
            logger.warning("ingest %s: linha rejeitada: %s", entity, exc)
    return model, linhas, errors


def _upsert_em_lote(model, entity, linhas):
    """Um INSERT ... ON CONFLICT DO UPDATE para o lote inteiro (Postgres).

    Um lote de 500 títulos custava ~1.000 consultas (SELECT + UPDATE por linha);
    aqui custa uma. A chave do conflito é a constraint única da entidade.
    """
    if not linhas:
        return 0
    natural = NATURAL_KEYS.get(entity)
    # Tem de ser exatamente a constraint única do modelo (ON CONFLICT exige índice igual).
    unique_fields = list(natural) if natural else ["tenant", *LOOKUP_EXTRA.get(entity, ()), "external_id"]
    # Última ocorrência de cada chave vence (ON CONFLICT não aceita a mesma chave duas vezes).
    por_chave = {}
    for lookup, data in linhas:
        chave = tuple(str(lookup.get(k).pk if hasattr(lookup.get(k), "pk") else lookup.get(k)) for k in unique_fields)
        por_chave[chave] = (lookup, data)
    objs, campos = [], set()
    for lookup, data in por_chave.values():
        campos.update(data.keys())
        objs.append(model(**{**data, **lookup}))
    update_fields = sorted((campos | {"synced_at"}) - set(unique_fields) - {"id"})
    model.objects.bulk_create(objs, update_conflicts=True, unique_fields=unique_fields, update_fields=update_fields, batch_size=1000)
    return len(objs)


def _upsert_linha_a_linha(model, linhas):
    imported, errors = 0, []
    for lookup, data in linhas:
        try:
            try:
                model.objects.update_or_create(defaults=data, **lookup)
            except MultipleObjectsReturned:
                obj = model.objects.filter(**lookup).order_by("id").first()
                for k, v in data.items():
                    setattr(obj, k, v)
                obj.save()
            imported += 1
        except Exception as exc:  # noqa: BLE001
            if len(errors) < 3:
                errors.append(f"{type(exc).__name__}: {str(exc)[:160]}")
            logger.warning("ingest: linha rejeitada: %s", exc)
    return imported, errors


def map_and_upsert(connector, entity, raw_items, fields):
    """Grava um lote. Retorna (importados, erro-amostra)."""
    if ENTITY_MODELS.get(entity) is None:
        return _upsert_erp_records(connector, entity, raw_items, fields)

    model, linhas, errors = _linhas_preparadas(connector, entity, raw_items, fields)
    try:
        with transaction.atomic():
            imported = _upsert_em_lote(model, entity, linhas)
    except Exception as exc:  # noqa: BLE001 — cai para linha a linha (diagnóstico e resiliência)
        logger.warning("ingest %s: upsert em lote falhou (%s); gravando linha a linha", entity, exc)
        imported, mais = _upsert_linha_a_linha(model, linhas)
        errors.extend(mais)
    return imported, "; ".join(errors[:3])


def _upsert_erp_records(connector, entity, raw_items, fields):
    """Entidade sem modelo dedicado: guarda a linha crua em JSON."""
    ext_alias = (fields or {}).get("external_id", "EXTERNAL_ID")
    imported = 0
    for raw in raw_items or []:
        ext = _normalize_ext(raw.get(ext_alias))
        if not ext:
            continue
        ErpRecord.objects.update_or_create(
            tenant=connector.tenant, entity=entity, external_id=ext,
            defaults={"data": raw},
        )
        imported += 1
    return imported, ""
