<#
.SYNOPSIS
    Derruba a API e o front do SprintAI (e, se pedido, o container do banco).

.DESCRIPTION
    Mata por duas vias, nessa ordem: os PIDs que o launcher anotou em
    `.logs/processos.json` e, como rede de segurança, o dono da porta da API e da
    porta do front. A segunda via é a que importa quando o processo foi iniciado
    à mão em um terminal, fora do atalho.

    A árvore inteira é derrubada (`taskkill /T`) porque tanto o uvicorn com
    reload quanto o `npm run dev` rodam o servidor de verdade em um processo
    filho — matar só o pai deixaria a porta ocupada.

.PARAMETER PararBanco
    Também para o container `sprintai-db`. Por padrão ele fica de pé: subir o
    Postgres de novo custa mais que deixá-lo ligado.
#>
[CmdletBinding()]
param(
    [switch]$PararBanco
)

$ErrorActionPreference = 'Stop'

$Raiz    = Split-Path -Parent $PSScriptRoot
$DirLogs = Join-Path $Raiz '.logs'
$ArqPids = Join-Path $DirLogs 'processos.json'

function Write-Saida {
    param([string]$Mensagem, [string]$Cor = 'Gray')
    Write-Host $Mensagem -ForegroundColor $Cor
}

function Read-DotEnv {
    param([string]$Caminho)
    $valores = @{}
    if (-not (Test-Path $Caminho)) { return $valores }
    foreach ($linha in Get-Content $Caminho -Encoding UTF8) {
        $texto = $linha.Trim()
        if ($texto -eq '' -or $texto.StartsWith('#')) { continue }
        $corte = $texto.IndexOf('=')
        if ($corte -lt 1) { continue }
        $valores[$texto.Substring(0, $corte).Trim()] = $texto.Substring($corte + 1).Trim().Trim('"').Trim("'")
    }
    return $valores
}

function Invoke-Nativo {
    param([string]$Arquivo, [string[]]$Argumentos)
    $anterior = $ErrorActionPreference
    # O PowerShell 5.1 vira ErrorRecord cada linha de stderr de um .exe; com
    # ErrorActionPreference='Stop' um "processo não encontrado" do taskkill
    # derrubaria o script no meio da limpeza.
    $ErrorActionPreference = 'Continue'
    try {
        $saida = & $Arquivo @Argumentos 2>&1
        return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Saida = $saida }
    } finally {
        $ErrorActionPreference = $anterior
    }
}

function Stop-Arvore {
    param([int]$ProcessId, [string]$Rotulo)
    if (-not $ProcessId) { return }
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { return }
    Invoke-Nativo 'taskkill.exe' @('/PID', "$ProcessId", '/T', '/F') | Out-Null
    Write-Saida "Derrubado: $Rotulo (PID $ProcessId)" 'Yellow'
}

function Stop-DonoDaPorta {
    param([int]$Porta, [string]$Rotulo)
    $conexoes = Get-NetTCPConnection -LocalPort $Porta -State Listen -ErrorAction SilentlyContinue
    foreach ($conexao in $conexoes) {
        Stop-Arvore -ProcessId $conexao.OwningProcess -Rotulo "$Rotulo na porta $Porta"
    }
}

$valoresEnv = Read-DotEnv (Join-Path $Raiz '.env')
$apiPorta   = 8765
if ($valoresEnv.ContainsKey('API_PORT') -and $valoresEnv['API_PORT']) { $apiPorta = [int]$valoresEnv['API_PORT'] }
$frontUrl   = 'http://localhost:5273'
if ($valoresEnv.ContainsKey('FRONT_ORIGIN') -and $valoresEnv['FRONT_ORIGIN']) { $frontUrl = $valoresEnv['FRONT_ORIGIN'] }
$frontPorta = [int]([uri]$frontUrl).Port

if (Test-Path $ArqPids) {
    try {
        $anotados = Get-Content $ArqPids -Raw | ConvertFrom-Json
        foreach ($prop in $anotados.PSObject.Properties) {
            Stop-Arvore -ProcessId ([int]$prop.Value) -Rotulo $prop.Name
        }
    } catch {
        Write-Saida 'processos.json ilegível; usando só as portas.' 'Yellow'
    }
    Remove-Item $ArqPids -ErrorAction SilentlyContinue
}

Stop-DonoDaPorta -Porta $apiPorta -Rotulo 'API'
Stop-DonoDaPorta -Porta $frontPorta -Rotulo 'front'

if ($PararBanco) {
    Push-Location $Raiz
    try {
        Invoke-Nativo 'docker.exe' @('compose', 'stop', 'db') | Out-Null
        Write-Saida 'Container sprintai-db parado.' 'Yellow'
    } finally {
        Pop-Location
    }
}

Write-Saida 'SprintAI parado.' 'Green'
