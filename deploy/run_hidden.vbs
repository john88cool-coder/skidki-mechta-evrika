' Runs a deploy\*.cmd script without a console window (default: run_crawl.cmd).
' A crawl takes minutes and the bot listener runs for hours - a visible cmd
' window would sit on the desktop the whole time.
Set shell = CreateObject("WScript.Shell")
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
script = "run_crawl.cmd"
If WScript.Arguments.Count > 0 Then script = WScript.Arguments(0)
WScript.Quit shell.Run("""" & here & "\" & script & """", 0, True)
