# Remove o agente TechSys (coletor WinThor) desta máquina. Rode como Administrador.
$Dir = "C:\ProgramData\techsys-agente"
schtasks /End /TN "techsys-agente" 2>$null | Out-Null
schtasks /Delete /TN "techsys-agente" /F 2>$null | Out-Null
schtasks /Delete /TN "techsys-agente-vigia" /F 2>$null | Out-Null
Get-Process pythonw,python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*techsys-agente*" } | Stop-Process -Force -ErrorAction SilentlyContinue
if (Test-Path $Dir) { Remove-Item -Recurse -Force $Dir }
Write-Host "✓ techsys-agente removido (o usuário TECHSYS no Oracle continua — revogue no banco se quiser)."
