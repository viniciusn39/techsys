# TechSys Gestão

SaaS de **planejamento estratégico focado em IA**, inspirado no Actio Software: mapa estratégico (BSC), desdobramento de metas em cascata, indicadores/KPIs com farol, planos de ação 5W2H/PDCA com Kanban, tratamento de desvios, dashboards e camada de IA (insights, análise de desvios e chat sobre resultados).

## Stack

- **Backend**: Django 5.1 + DRF 3.15 + SimpleJWT · PostgreSQL 16 · Celery 5.4 + Redis 7
- **Frontend**: Vite + React 18 + TypeScript + Bootstrap 5 + **Apache ECharts 6**
- **IA**: provider configurável pelo root em *Integrações* (DeepSeek por padrão; qualquer API OpenAI-compatible)
- **Multi-tenant**: isolamento por `tenant_id` (FK compartilhada + escopo explícito em queryset)

## Design system e visualização de dados

Tokens de tema (claro/escuro) ficam em `frontend/src/styles/main.scss`; a troca é feita
no seletor da barra superior e respeita a preferência do sistema (`ThemeProvider` em
`src/hooks/useTheme.tsx`).

A camada de gráficos vive em `frontend/src/charts/theme.ts` e segue regras fixas:

- **Paleta categórica** de 4 slots em ordem fixa, validada para daltonismo nos dois modos
  (ΔE CVD ≥ 8, ΔE visão normal ≥ 19 — claro e escuro).
- **Paleta de status** reservada para o farol; cor **nunca comunica sozinha** — todo farol
  sai com ícone + rótulo (`<StatusPill>` / `<StatusDot>` em `src/components/ui.tsx`).
- **Um único eixo Y** por gráfico (sem dual-axis), marcas finas (≤ 24px), ponta arredondada
  em 4px, gap de 2px na cor da superfície entre segmentos, grid hairline sólido.
- Gráficos usados: barra horizontal com linha de referência na meta, donut com número-herói,
  colunas empilhadas de faróis por mês, heatmap indicador × mês, combo coluna+linha
  (meta × realizado), área de acumulado, medidor (gauge) de atingimento, radar de
  perspectivas BSC e sparklines em SVG nas tabelas.
- Onde a cor da marca fica abaixo de 3:1 no fundo claro, existe alternativa em texto —
  o ranking do dashboard tem botão **Tabela**, e toda tabela traz o valor numérico.

## Subir o ambiente

```bash
docker compose up -d --build
docker compose exec backend python manage.py seed_demo
```

| Serviço  | URL                          |
|----------|------------------------------|
| Frontend | http://localhost:3091        |
| API      | http://localhost:8091/api/   |
| Postgres | localhost:5436               |

### Logins demo (senha: `demo1234`)

| Papel  | E-mail              |
|--------|---------------------|
| Root   | root@techsys.local  |
| Admin  | admin@acme.com      |
| Gestor | gestor@acme.com     |
| Colab. | carla@acme.com      |

O root não pertence a nenhuma empresa: use o seletor de empresa na sidebar (header `X-Tenant-Id`) para atuar dentro de um tenant. Configure a API key do DeepSeek em **Integrações** para habilitar insights e chat de IA.

## Testes

```bash
docker compose exec backend python manage.py test
```

Inclui a suíte de **isolamento multi-tenant** (accounts) e as regras de **farol/atingimento/YTD** (indicators).

## Arquitetura (backend)

- `accounts` — Tenant, User (papéis root/admin/gestor/colaborador), OrgUnit, `TenantScopedViewSet`
- `strategy` — StrategicMap/Perspective/StrategicObjective (BSC) e Goal (desdobramento empresa→área→time→pessoa)
- `indicators` — Indicator/Target/Value, `services.py` (farol, polaridade, YTD), `sources/` (**ponto de extensão do agente conector de ERP**: implemente `BaseSource` e registre em `sources/registry.py`)
- `plans` — Deviation (criada automaticamente quando um valor fica vermelho), ActionPlan 5W2H/PDCA, ActionItem (Kanban)
- `ai` — AIIntegration (key criptografada com Fernet), providers OpenAI-compatible, prompts pt-BR, insights via Celery, chat síncrono

### Tarefas Celery (beat)

- `recalcular_farois` (diária) · `detectar_desvios` (horária) · `coletar_fontes_dados` (diária, gancho do agente ERP) · `marcar_planos_atrasados` (diária) · `gerar_insight` (sob demanda)
