from .manual import ManualSource

# "api", "sql" e "agent" serão registrados quando o agente conector de ERP
# for integrado — basta adicionar a classe aqui.
SOURCE_REGISTRY = {
    "manual": ManualSource,
}


def get_source(data_source):
    cls = SOURCE_REGISTRY.get(data_source.type)
    if cls is None:
        return None
    return cls(data_source)
