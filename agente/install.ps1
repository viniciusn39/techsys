# Instalador do agente TechSys (coletor WinThor) — Windows / Task Scheduler.
# Rode como Administrador:
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Server https://SEU-SERVIDOR -Key CHAVE `
#     -User TECHSYS -Password 'SENHA' [-Dsn host:1521/SERVICO] [-Schema DONO]
param(
  [Parameter(Mandatory=$true)][string]$Server,
  [Parameter(Mandatory=$true)][string]$Key,
  [string]$Dsn = "",
  [string]$User = "",
  [string]$Password = "",
  [string]$Schema = "",
  [string]$Name = $env:COMPUTERNAME,
  [int]$Interval = 0,
  [switch]$AllowInsecure
)
$ErrorActionPreference = "Stop"
$Dir = "C:\ProgramData\techsys-agente"
New-Item -ItemType Directory -Force -Path $Dir | Out-Null

# --- código ---
$Local = Join-Path $PSScriptRoot "agente.py"
if (Test-Path $Local) {
  Copy-Item -Force $Local "$Dir\agente.py"
} else {
  Invoke-WebRequest -Uri "$($Server.TrimEnd('/'))/api/coletor/agente.py" -Headers @{"X-Coletor-Token"=$Key} -OutFile "$Dir\agente.py"
}

# --- Python ---
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { Write-Host "!! Python 3 não encontrado. Instale em https://www.python.org/downloads/ (marque 'Add to PATH') e rode de novo."; exit 1 }

& $py -m pip install --quiet oracledb psutil 2>$null
& $py -c "import oracledb" 2>$null
if ($LASTEXITCODE -ne 0) { & $py -m pip install --quiet cx_Oracle 2>$null }

# --- config.json ---
$apply = @("--apply", "--server", $Server.TrimEnd('/'), "--key", $Key, "--name", $Name)
if ($Dsn)      { $apply += @("--dsn", $Dsn) }
if ($User)     { $apply += @("--user", $User) }
if ($Password) { $apply += @("--password", $Password) }
if ($Schema)   { $apply += @("--schema", $Schema) }
if ($Interval) { $apply += @("--interval", "$Interval") }
if ($AllowInsecure) { $apply += @("--allow-insecure") }
Push-Location $Dir
& $py agente.py @apply
Pop-Location
icacls "$Dir\config.json" /inheritance:r /grant:r "SYSTEM:F" /grant:r "Administrators:F" | Out-Null

# --- tarefa agendada (SYSTEM, inicia com o Windows) + vigia a cada 5 min ---
$pyw = $py -replace "python\.exe$", "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }
schtasks /Delete /TN "techsys-agente" /F 2>$null | Out-Null
schtasks /Create /TN "techsys-agente" /SC ONSTART /RU SYSTEM /RL HIGHEST `
  /TR "`"$pyw`" `"$Dir\agente.py`" --service" /F | Out-Null
schtasks /Delete /TN "techsys-agente-vigia" /F 2>$null | Out-Null
schtasks /Create /TN "techsys-agente-vigia" /SC MINUTE /MO 5 /RU SYSTEM /RL HIGHEST `
  /TR "schtasks /Run /TN techsys-agente" /F | Out-Null
schtasks /Run /TN "techsys-agente" | Out-Null

Write-Host "✓ techsys-agente instalado em $Dir (log: $Dir\agent.log)"
Write-Host "  status: python `"$Dir\agente.py`" --status"
