# Agente TechSys — coletor WinThor

Arquivo único (`agente.py`), só biblioteca padrão do Python + driver Oracle
(`oracledb` ou `cx_Oracle`). Roda **na rede do cliente**, junto ao Oracle do
WinThor, e fala com a plataforma apenas por conexões de **saída** (HTTPS).

É **somente leitura**: não existe caminho de escrita no ERP neste agente.

## Instalação

A tela **Integrações → Conector ERP** gera o comando pronto com a chave da empresa.

Linux (systemd):

```bash
curl -fsSL https://SEU-SERVIDOR/api/coletor/install.sh | sudo bash -s -- \
  --server https://SEU-SERVIDOR --key CHAVE --user TECHSYS --password 'SENHA'
```

Windows (PowerShell como administrador):

```powershell
iwr https://SEU-SERVIDOR/api/coletor/install.ps1 -OutFile install.ps1
.\install.ps1 -Server https://SEU-SERVIDOR -Key CHAVE -User TECHSYS -Password 'SENHA'
```

`--dsn host:1521/SERVICO` é opcional: sem ele o agente descobre o Oracle na
máquina (oratab, tnsnames.ora, listener.ora, IPs locais) e valida conectando.
`--schema DONO` força o schema dono das tabelas (normalmente descoberto pela PCPEDC).

## Antes: usuário Oracle somente leitura

A mesma tela mostra o script para o DBA — cria o usuário `TECHSYS` com `GRANT
SELECT` **tabela a tabela** (nada de `SELECT ANY TABLE`) só nas tabelas que o
plano de coleta usa.

## Como funciona

1. `GET /api/coletor/plan/` — a plataforma envia o plano: consultas SQL, cadência
   por entidade, versão publicada do agente.
2. Cada consulta roda isolada; `:since` recebe a marca d'água local (`state.json`)
   e `:janela` o backfill gradual (meses que crescem a cada ciclo).
3. Os dados sobem em lotes (`POST /api/coletor/ingest/`); a marca avança **por
   lote confirmado** — queda de rede não perde progresso.
4. Coluna que não existe neste WinThor (ORA-00904) é retirada do SELECT e a
   consulta refeita — perder uma coluna é melhor que perder a entidade.
5. Heartbeat a cada 60 s (Oracle ok? versão? host) e long-poll de comandos de
   diagnóstico (`ping`, `validar_schema`, `coletar`, `reset_state`).
6. Auto-update quando a plataforma anuncia versão maior — só por HTTPS e com
   sha256 conferido.

## Operação

```bash
techsys-agente status      # serviço + marca d'água por entidade
techsys-agente once        # um ciclo de coleta agora
techsys-agente logs        # journalctl -f
techsys-agente descobrir   # redescobre o DSN
```

Arquivos em `/opt/techsys-agente` (Linux) ou `C:\ProgramData\techsys-agente` (Windows):
`config.json` (chmod 600 — tem a senha), `state.json` (marcas d'água), `crash.log`.
