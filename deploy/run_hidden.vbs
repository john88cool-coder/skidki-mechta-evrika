' Runs run_crawl.cmd without a console window: a crawl takes ~30 minutes
' and a visible cmd window would sit on the desktop the whole time.
Set shell = CreateObject("WScript.Shell")
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WScript.Quit shell.Run("""" & here & "\run_crawl.cmd""", 0, True)
