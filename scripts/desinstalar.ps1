<#
.SYNOPSIS
    Remove os atalhos criados pelo `instalar.ps1`.

.DESCRIPTION
    Só apaga `.lnk` — nada do repositório, do banco ou do Cofre é tocado. Para
    voltar atrás, rode o `instalar.ps1` de novo.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$menuIniciar = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'Microsoft\Windows\Start Menu\Programs\SprintAI'

$alvos = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'SprintAI.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Startup')) 'SprintAI.lnk'),
    (Join-Path $menuIniciar 'SprintAI.lnk'),
    (Join-Path $menuIniciar 'Parar SprintAI.lnk')
)

foreach ($alvo in $alvos) {
    if (Test-Path $alvo) {
        Remove-Item $alvo -Force
        Write-Host "Removido: $alvo" -ForegroundColor Yellow
    }
}

if ((Test-Path $menuIniciar) -and -not (Get-ChildItem $menuIniciar)) {
    Remove-Item $menuIniciar -Force
    Write-Host "Removido: $menuIniciar" -ForegroundColor Yellow
}

Write-Host 'Atalhos removidos. Os serviços que estiverem no ar continuam rodando (use parar-sprintai.ps1).' -ForegroundColor Green
