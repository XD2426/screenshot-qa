' start_capture.vbs - 静默后台启动 capture.py (无控制台窗口)
' 双击本文件即可；要停止请用任务管理器结束 pythonw.exe
Option Explicit
Dim fso, sh, base, py, script, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
py = base & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(py) Then
    py = base & "\.venv\Scripts\python.exe"
End If
If Not fso.FileExists(py) Then
    MsgBox "Python not found. Run install.ps1 first.", 16, "capture"
    WScript.Quit 1
End If
script = base & "\capture.py"
cmd = """" & py & """ """ & script & """"
sh.CurrentDirectory = base
sh.Run cmd, 0, False
