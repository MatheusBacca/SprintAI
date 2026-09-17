<#
.SYNOPSIS
    Cria os atalhos do SprintAI: Área de Trabalho, Menu Iniciar e inicialização
    do Windows.

.DESCRIPTION
    Não instala nada no sistema — só cria `.lnk` apontando para os scripts deste
    repositório. Desinstalar é apagar os atalhos (`desinstalar.ps1`); o repo
    continua onde está.

    Os três atalhos chamam o mesmo `sprintai.ps1`, que é idempotente:
      - Área de Trabalho / Menu Iniciar: sobe o que faltar e abre o navegador;
      - Inicialização: sobe tudo com `-NoBrowser`, para não roubar o foco no logon.

.PARAMETER SemInicializacao
    Não cria o atalho na pasta de inicialização do Windows.
#>
[CmdletBinding()]
param(
    [switch]$SemInicializacao
)

$ErrorActionPreference = 'Stop'

$Raiz     = Split-Path -Parent $PSScriptRoot
$Vbs      = Join-Path $PSScriptRoot 'sprintai-oculto.vbs'
$Parar    = Join-Path $PSScriptRoot 'parar-sprintai.ps1'
$Icone    = Join-Path $PSScriptRoot 'sprintai.ico'
$Wscript  = Join-Path $env:WINDIR 'System32\wscript.exe'

function New-DesenhoSprintAI {
    param([int]$Lado)

    $bmp = New-Object System.Drawing.Bitmap($Lado, $Lado, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    # Violeta da marca: --color-primary -> --color-primary-deep dos tokens.
    $retangulo = New-Object System.Drawing.Rectangle(0, 0, $Lado, $Lado)
    $pincel = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
        $retangulo,
        [System.Drawing.Color]::FromArgb(255, 138, 79, 255),
        [System.Drawing.Color]::FromArgb(255, 91, 63, 214),
        45.0)

    $raio = [int]($Lado * 0.22)
    $forma = New-Object System.Drawing.Drawing2D.GraphicsPath
    $forma.AddArc(0, 0, $raio, $raio, 180, 90)
    $forma.AddArc($Lado - $raio, 0, $raio, $raio, 270, 90)
    $forma.AddArc($Lado - $raio, $Lado - $raio, $raio, $raio, 0, 90)
    $forma.AddArc(0, $Lado - $raio, $raio, $raio, 90, 90)
    $forma.CloseFigure()
    $g.FillPath($pincel, $forma)

    $fonte = New-Object System.Drawing.Font('Segoe UI', [float]($Lado * 0.6), [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $formato = New-Object System.Drawing.StringFormat
    $formato.Alignment = [System.Drawing.StringAlignment]::Center
    $formato.LineAlignment = [System.Drawing.StringAlignment]::Center
    $g.DrawString('S', $fonte, [System.Drawing.Brushes]::White, (New-Object System.Drawing.RectangleF(0, 0, $Lado, $Lado)), $formato)

    $fonte.Dispose(); $formato.Dispose(); $forma.Dispose(); $pincel.Dispose(); $g.Dispose()
    return $bmp
}

function ConvertTo-Dib {
    param([System.Drawing.Bitmap]$Bitmap)

    $largura = $Bitmap.Width
    $altura = $Bitmap.Height
    $bytesMascara = ([math]::Floor(($largura + 31) / 32) * 4) * $altura

    $memoria = New-Object System.IO.MemoryStream
    $escritor = New-Object System.IO.BinaryWriter($memoria)

    # BITMAPINFOHEADER: a altura é dobrada porque o formato prevê a máscara AND
    # logo abaixo dos pixels (aqui ela vai zerada — o alfa já resolve o recorte).
    $escritor.Write([uint32]40)
    $escritor.Write([int32]$largura)
    $escritor.Write([int32]($altura * 2))
    $escritor.Write([uint16]1)
    $escritor.Write([uint16]32)
    $escritor.Write([uint32]0)
    $escritor.Write([uint32](($largura * $altura * 4) + $bytesMascara))
    $escritor.Write([int32]0); $escritor.Write([int32]0)
    $escritor.Write([uint32]0); $escritor.Write([uint32]0)

    $area = New-Object System.Drawing.Rectangle(0, 0, $largura, $altura)
    $dados = $Bitmap.LockBits($area,
        [System.Drawing.Imaging.ImageLockMode]::ReadOnly,
        [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $buffer = New-Object byte[] ($dados.Stride * $altura)
    [System.Runtime.InteropServices.Marshal]::Copy($dados.Scan0, $buffer, 0, $buffer.Length)
    $Bitmap.UnlockBits($dados)

    # DIB é de baixo para cima.
    for ($y = $altura - 1; $y -ge 0; $y--) {
        $escritor.Write($buffer, $y * $dados.Stride, $largura * 4)
    }
    $escritor.Write((New-Object byte[] $bytesMascara))
    $escritor.Flush()

    # A vírgula impede o PowerShell de desenrolar o byte[] no pipeline — sem ela
    # quem chama recebe um Object[] de bytes soltos e o BinaryWriter escreve um
    # byte só.
    return ,$memoria.ToArray()
}

function New-IconeSprintAI {
    param([string]$Destino)
    Add-Type -AssemblyName System.Drawing

    # DIB cru em vez de PNG embutido: ICO com payload PNG é válido e o Explorer
    # abre, mas o System.Drawing (e outros consumidores antigos) engasga nele —
    # não vale economizar KB em um arquivo gerado uma vez.
    $lados = @(256, 64, 48, 32, 16)
    $imagens = @()
    foreach ($lado in $lados) {
        $bmp = New-DesenhoSprintAI -Lado $lado
        $imagens += ,@($lado, (ConvertTo-Dib -Bitmap $bmp))
        $bmp.Dispose()
    }

    $arquivo = [System.IO.File]::Create($Destino)
    $escritor = New-Object System.IO.BinaryWriter($arquivo)
    $escritor.Write([uint16]0); $escritor.Write([uint16]1); $escritor.Write([uint16]$imagens.Count)

    $deslocamento = 6 + (16 * $imagens.Count)
    foreach ($imagem in $imagens) {
        $lado = $imagem[0]
        $conteudo = $imagem[1]
        # 0 no byte de largura/altura significa 256.
        $escritor.Write([byte]($lado % 256)); $escritor.Write([byte]($lado % 256))
        $escritor.Write([byte]0); $escritor.Write([byte]0)
        $escritor.Write([uint16]1); $escritor.Write([uint16]32)
        $escritor.Write([uint32]$conteudo.Length)
        $escritor.Write([uint32]$deslocamento)
        $deslocamento += $conteudo.Length
    }
    foreach ($imagem in $imagens) { $escritor.Write($imagem[1]) }
    $escritor.Close()
}

function New-Atalho {
    param(
        [string]$Destino,
        [string]$Alvo,
        [string]$Argumentos,
        [string]$Descricao
    )
    $shell = New-Object -ComObject WScript.Shell
    $atalho = $shell.CreateShortcut($Destino)
    $atalho.TargetPath = $Alvo
    $atalho.Arguments = $Argumentos
    $atalho.WorkingDirectory = $Raiz
    $atalho.Description = $Descricao
    if (Test-Path $Icone) { $atalho.IconLocation = "$Icone,0" }
    $atalho.Save()
    Write-Host "Atalho criado: $Destino" -ForegroundColor Green
}

if (-not (Test-Path $Icone)) {
    New-IconeSprintAI -Destino $Icone
    Write-Host "Ícone gerado: $Icone" -ForegroundColor Green
}

$areaTrabalho = [Environment]::GetFolderPath('Desktop')
$menuIniciar  = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'Microsoft\Windows\Start Menu\Programs\SprintAI'
$inicializar  = [Environment]::GetFolderPath('Startup')

if (-not (Test-Path $menuIniciar)) { New-Item -ItemType Directory -Path $menuIniciar | Out-Null }

New-Atalho -Destino (Join-Path $areaTrabalho 'SprintAI.lnk') `
    -Alvo $Wscript -Argumentos "`"$Vbs`"" `
    -Descricao 'Sobe Docker, banco, API e front do SprintAI e abre a tela'

New-Atalho -Destino (Join-Path $menuIniciar 'SprintAI.lnk') `
    -Alvo $Wscript -Argumentos "`"$Vbs`"" `
    -Descricao 'Sobe Docker, banco, API e front do SprintAI e abre a tela'

New-Atalho -Destino (Join-Path $menuIniciar 'Parar SprintAI.lnk') `
    -Alvo 'powershell.exe' `
    -Argumentos "-NoProfile -ExecutionPolicy Bypass -File `"$Parar`"" `
    -Descricao 'Derruba a API e o front do SprintAI'

if ($SemInicializacao) {
    Write-Host 'Atalho da inicialização não criado (-SemInicializacao).' -ForegroundColor Yellow
} else {
    New-Atalho -Destino (Join-Path $inicializar 'SprintAI.lnk') `
        -Alvo $Wscript -Argumentos "`"$Vbs`" -NoBrowser" `
        -Descricao 'Deixa o SprintAI pronto no logon, sem abrir o navegador'
}

Write-Host ''
Write-Host 'Pronto. No próximo logon o SprintAI sobe sozinho;' -ForegroundColor Cyan
Write-Host 'abra o atalho da Área de Trabalho para ir direto para a tela.' -ForegroundColor Cyan
