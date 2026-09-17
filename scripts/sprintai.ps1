<#
.SYNOPSIS
    Sobe o SprintAI inteiro: Docker Desktop -> Postgres -> migrations -> API -> front.

.DESCRIPTION
    Orquestrador do uso diário. Cada etapa é idempotente: se o Docker já está de pé,
    se o banco já responde ou se a porta da API/front já está ocupada, a etapa é
    pulada. Dá para rodar duas vezes seguidas sem subir nada duplicado.

    O back NÃO roda em container de propósito (precisa do Cofre do Windows via
    keyring), então API e front sobem como processos ocultos do host e escrevem
    em `.logs/`.

.PARAMETER NoBrowser
    Não abre o navegador no fim. É o modo do atalho da inicialização do Windows:
    o app fica pronto, mas sem roubar o foco assim que a máquina liga.

.PARAMETER NoMigrate
    Pula `alembic upgrade head`.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\sprintai.ps1
#>
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$NoMigrate,
    [int]$DockerTimeoutSeconds = 300,
    [int]$ReadyTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'

$Raiz     = Split-Path -Parent $PSScriptRoot
$DirBack  = Join-Path $Raiz 'back'
$DirFront = Join-Path $Raiz 'front'
$DirLogs  = Join-Path $Raiz '.logs'
$ArqPids  = Join-Path $DirLogs 'processos.json'

if (-not (Test-Path $DirLogs)) { New-Item -ItemType Directory -Path $DirLogs | Out-Null }

function Write-Log {
    param([string]$Mensagem, [string]$Nivel = 'info')
    $linha = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Nivel, $Mensagem
    Add-Content -Path (Join-Path $DirLogs 'launcher.log') -Value $linha -Encoding UTF8
    switch ($Nivel) {
        'erro'  { Write-Host $linha -ForegroundColor Red }
        'aviso' { Write-Host $linha -ForegroundColor Yellow }
        'ok'    { Write-Host $linha -ForegroundColor Green }
        default { Write-Host $linha }
    }
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
        $chave = $texto.Substring(0, $corte).Trim()
        $valor = $texto.Substring($corte + 1).Trim().Trim('"').Trim("'")
        $valores[$chave] = $valor
    }
    return $valores
}

function Get-ValorEnv {
    param([hashtable]$Valores, [string]$Chave, [string]$Padrao)
    if ($Valores.ContainsKey($Chave) -and $Valores[$Chave]) { return $Valores[$Chave] }
    return $Padrao
}

# TcpClient em vez de Test-NetConnection: o cmdlet gasta ~1s por tentativa, e aqui
# a porta é consultada dentro de um laço de espera.
function Test-PortaEmUso {
    param([string]$Endereco, [int]$Porta)
    $cliente = New-Object System.Net.Sockets.TcpClient
    try {
        $tarefa = $cliente.BeginConnect($Endereco, $Porta, $null, $null)
        if (-not $tarefa.AsyncWaitHandle.WaitOne(400)) { return $false }
        $cliente.EndConnect($tarefa)
        return $true
    } catch {
        return $false
    } finally {
        $cliente.Close()
    }
}

function Wait-Condicao {
    param([scriptblock]$Condicao, [int]$TimeoutSeconds, [string]$Descricao)
    $limite = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $limite) {
        if (& $Condicao) { return $true }
        Start-Sleep -Milliseconds 1500
    }
    Write-Log "Tempo esgotado esperando: $Descricao" 'aviso'
    return $false
}

function Invoke-Nativo {
    param([string]$Arquivo, [string[]]$Argumentos)
    $anterior = $ErrorActionPreference
    # O PowerShell 5.1 transforma cada linha de stderr de um .exe em ErrorRecord;
    # com ErrorActionPreference='Stop' isso derruba o script mesmo quando o
    # comando terminou bem. O `docker info` com o engine parado e o próprio
    # `docker compose up` (que narra o progresso no stderr) caíam aqui.
    $ErrorActionPreference = 'Continue'
    try {
        $saida = & $Arquivo @Argumentos 2>&1
        return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Saida = $saida }
    } finally {
        $ErrorActionPreference = $anterior
    }
}

function Invoke-Etapa {
    param([string]$Arquivo, [string[]]$Argumentos, [string]$DiretorioTrabalho, [string]$Log)
    $saida = Join-Path $DirLogs "$Log.log"
    $erro  = Join-Path $DirLogs "$Log.err.log"
    $proc = Start-Process -FilePath $Arquivo -ArgumentList $Argumentos -WorkingDirectory $DiretorioTrabalho -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput $saida -RedirectStandardError $erro
    return $proc.ExitCode
}

function Start-Servico {
    param([string]$Nome, [string]$Arquivo, [string[]]$Argumentos, [string]$DiretorioTrabalho)
    $saida = Join-Path $DirLogs "$Nome.log"
    $erro  = Join-Path $DirLogs "$Nome.err.log"
    # Zera a cada boot: o log que interessa é o da execução atual, e sem isso o
    # arquivo cresceria para sempre numa máquina que liga todo dia.
    Set-Content -Path $saida -Value '' -Encoding UTF8
    Set-Content -Path $erro  -Value '' -Encoding UTF8
    return Start-Process -FilePath $Arquivo -ArgumentList $Argumentos -WorkingDirectory $DiretorioTrabalho -WindowStyle Hidden -PassThru -RedirectStandardOutput $saida -RedirectStandardError $erro
}

function Resolve-Uv {
    $noPath = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($noPath) { return $noPath.Source }
    # O uv deste projeto vive dentro da venv do back, não no PATH da máquina.
    $naVenv = Join-Path $DirBack '.venv\Scripts\uv.exe'
    if (Test-Path $naVenv) { return $naVenv }
    throw 'uv não encontrado (nem no PATH, nem em back\.venv\Scripts).'
}

function Resolve-Npm {
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npm) { return $npm.Source }
    $padrao = Join-Path $env:ProgramFiles 'nodejs\npm.cmd'
    if (Test-Path $padrao) { return $padrao }
    throw 'npm não encontrado. Instale o Node 20+.'
}

function Test-ApiSaudavel {
    param([string]$Url)
    try {
        # A guarda local exige o header X-SprintAI; sem ele a resposta é 403 e o
        # laço de espera nunca fecharia mesmo com a API no ar.
        $resp = Invoke-WebRequest -Uri $Url -Headers @{ 'X-SprintAI' = 'launcher' } -UseBasicParsing -TimeoutSec 4
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-DockerNoAr {
    return (Invoke-Nativo 'docker.exe' @('info', '--format', '{{.ServerVersion}}')).ExitCode -eq 0
}

Write-Log '=== Subindo o SprintAI ==='

# --- .env -------------------------------------------------------------------
$arqEnv = Join-Path $Raiz '.env'
if (-not (Test-Path $arqEnv)) {
    Copy-Item (Join-Path $Raiz '.env.example') $arqEnv
    Write-Log '.env criado a partir do .env.example' 'aviso'
}
$valoresEnv = Read-DotEnv $arqEnv
$apiHost    = Get-ValorEnv $valoresEnv 'API_HOST' '127.0.0.1'
$apiPorta   = [int](Get-ValorEnv $valoresEnv 'API_PORT' '8765')
$frontUrl   = (Get-ValorEnv $valoresEnv 'FRONT_ORIGIN' 'http://localhost:5273').TrimEnd('/')
$frontPorta = [int]([uri]$frontUrl).Port
$urlSaude   = 'http://{0}:{1}/api/health' -f $apiHost, $apiPorta

# --- Docker Desktop ---------------------------------------------------------
if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
    Write-Log 'docker.exe não encontrado no PATH.' 'erro'
    exit 1
}

if (Test-DockerNoAr) {
    Write-Log 'Docker já está no ar.'
} else {
    $exeDocker = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Docker\Docker Desktop.exe')
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $exeDocker) {
        Write-Log 'Docker Desktop não encontrado para iniciar.' 'erro'
        exit 1
    }

    Write-Log 'Iniciando o Docker Desktop...'
    # Pelo explorer.exe, e não com Start-Process direto: aberto como filho do
    # PowerShell, o Docker Desktop herda o diretório de trabalho e o ambiente de
    # quem chamou e morre em "initializing Inference manager: ... The file cannot
    # be accessed by the system". Abrir pelo shell é o mesmo caminho do atalho da
    # barra do Windows, que funciona.
    Start-Process -FilePath (Join-Path $env:WINDIR 'explorer.exe') -ArgumentList "`"$exeDocker`"" | Out-Null
    if (-not (Wait-Condicao { Test-DockerNoAr } $DockerTimeoutSeconds 'engine do Docker responder')) {
        Write-Log 'O Docker não subiu a tempo. Abra o Docker Desktop e rode o atalho de novo.' 'erro'
        exit 1
    }
    Write-Log 'Docker pronto.' 'ok'
}

# --- Banco ------------------------------------------------------------------
Write-Log 'Subindo o container do Postgres...'
Push-Location $Raiz
try {
    $compose = Invoke-Nativo 'docker.exe' @('compose', 'up', '-d', 'db')
    $compose.Saida | ForEach-Object { Write-Log "docker: $_" }
    if ($compose.ExitCode -ne 0) {
        Write-Log 'docker compose up falhou.' 'erro'
        exit 1
    }
} finally {
    Pop-Location
}

$bancoPronto = Wait-Condicao {
    $inspecao = Invoke-Nativo 'docker.exe' @('inspect', '-f', '{{.State.Health.Status}}', 'sprintai-db')
    return $inspecao.ExitCode -eq 0 -and (($inspecao.Saida -join '').Trim() -eq 'healthy')
} 90 'healthcheck do sprintai-db'

if ($bancoPronto) {
    Write-Log 'Postgres saudável.' 'ok'
} else {
    Write-Log 'Banco não ficou saudável; seguindo assim mesmo (a API avisa se não conectar).' 'aviso'
}

# --- Dependências (primeira execução) ---------------------------------------
$uv  = Resolve-Uv
$npm = Resolve-Npm

if (-not (Test-Path (Join-Path $DirBack '.venv'))) {
    Write-Log 'Instalando dependências do back (uv sync)...'
    if ((Invoke-Etapa $uv @('sync') $DirBack 'uv-sync') -ne 0) {
        Write-Log 'uv sync falhou — veja .logs\uv-sync.err.log' 'erro'
        exit 1
    }
}

if (-not (Test-Path (Join-Path $DirFront 'node_modules'))) {
    Write-Log 'Instalando dependências do front (npm install)...'
    if ((Invoke-Etapa $npm @('install') $DirFront 'npm-install') -ne 0) {
        Write-Log 'npm install falhou — veja .logs\npm-install.err.log' 'erro'
        exit 1
    }
}

# --- Migrations -------------------------------------------------------------
if (-not $NoMigrate -and $bancoPronto) {
    Write-Log 'Aplicando migrations...'
    if ((Invoke-Etapa $uv @('run', 'alembic', 'upgrade', 'head') $DirBack 'alembic') -ne 0) {
        Write-Log 'alembic upgrade head falhou — veja .logs\alembic.err.log' 'erro'
        exit 1
    }
    Write-Log 'Migrations em dia.' 'ok'
}

# --- API e front ------------------------------------------------------------
$pids = @{}

if (Test-PortaEmUso $apiHost $apiPorta) {
    Write-Log "API já respondia na porta $apiPorta; não subi outra."
} else {
    Write-Log 'Subindo a API...'
    $pids['back'] = (Start-Servico 'back' $uv @('run', 'python', 'main.py') $DirBack).Id
}

if (Test-PortaEmUso '127.0.0.1' $frontPorta) {
    Write-Log "Front já respondia na porta $frontPorta; não subi outro."
} else {
    Write-Log 'Subindo o front...'
    $pids['front'] = (Start-Servico 'front' $npm @('run', 'dev') $DirFront).Id
}

if ($pids.Count -gt 0) {
    # Guardado só para o stop matar a árvore certa; quem já estava no ar antes do
    # atalho não entra aqui e continua sendo derrubado pelo dono da porta.
    $pids | ConvertTo-Json | Set-Content -Path $ArqPids -Encoding UTF8
}

# --- Espera ficar servível --------------------------------------------------
$apiOk = Wait-Condicao { Test-ApiSaudavel $urlSaude } $ReadyTimeoutSeconds 'API responder /api/health'
if ($apiOk) {
    Write-Log 'API no ar.' 'ok'
} else {
    Write-Log 'API não respondeu — veja .logs\back.err.log' 'erro'
}

$frontOk = Wait-Condicao { Test-PortaEmUso '127.0.0.1' $frontPorta } 60 'front abrir a porta'
if ($frontOk) {
    Write-Log 'Front no ar.' 'ok'
} else {
    Write-Log 'Front não subiu — veja .logs\front.err.log' 'erro'
}

if ($frontOk -and -not $NoBrowser) {
    Write-Log "Abrindo $frontUrl"
    Start-Process $frontUrl | Out-Null
}

Write-Log '=== SprintAI pronto ==='
if ($apiOk -and $frontOk) { exit 0 } else { exit 1 }
