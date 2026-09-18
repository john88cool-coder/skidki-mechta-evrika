' Runs a deploy\*.cmd script without a console window (default: run_crawl.cmd).
' A crawl takes minutes and the bot listener runs for hours - a visible cmd
' window would sit on the desktop the whole time.
' Second argument (optional) is passed to the script as-is: shops list for
' run_crawl.cmd, e.g. "mechta".
Set shell = CreateObject("WScript.Shell")
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
script = "run_crawl.cmd"
extra = ""
If WScript.Arguments.Count > 0 Then script = WScript.Arguments(0)
If WScript.Arguments.Count > 1 Then extra = " " & WScript.Arguments(1)
WScript.Quit shell.Run("""" & here & "\" & script & """" & extra, 0, True)
