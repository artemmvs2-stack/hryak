' Запуск Jarvis без окна консоли
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = base
shell.Run """" & base & "\venv\Scripts\pythonw.exe"" """ & base & "\jarvis.py""", 0, False
