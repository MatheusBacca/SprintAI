' Roda o launcher sem piscar janela de console.
'
' Um atalho apontando direto para powershell.exe abre um console preto por alguns
' segundos - o suficiente para o dev achar que algo travou no logon. O wscript
' executa o mesmo comando com a janela escondida (o 0 do Run).
'
' Os argumentos recebidos aqui sao repassados para o sprintai.ps1 (e assim que o
' atalho da inicializacao manda o -NoBrowser).
'
' Sem acento de proposito: este arquivo precisa ficar SEM BOM (o Windows Script
' Host recusa com "Caractere invalido" na linha 1), e sem BOM o wscript le o
' arquivo como ANSI - texto acentuado em UTF-8 sairia corrompido.

Dim shell, fso, script, extras, argumento

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

script = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "sprintai.ps1")

extras = ""
For Each argumento In WScript.Arguments
  extras = extras & " " & argumento
Next

shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & script & """" & extras, 0, False
