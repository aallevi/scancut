-- Scan Studio nel Dock: un clic apre lo studio, o lo riporta davanti se e' nascosto o chiuso.
-- Compilare: osacompile -s -o "$HOME/Applications/Scan Studio.app" scan-studio.applescript
-- (-s: resta aperta, cosi' riceve il clic nel Dock; poi l'icona: vedi STUDIO.md)
on run
	showStudio()
end run

on reopen
	showStudio()
end reopen

property seen : false
property misses : 0

on idle
	-- lo studio si chiude da solo a finestra chiusa; allora si chiude anche l'app.
	-- Solo dopo averlo visto acceso: all'avvio ci mette qualche secondo a rispondere
	try
		do shell script "curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/api/ping"
		set seen to true
		set misses to 0
	on error
		set misses to misses + 1
		if seen or misses > 6 then quit
	end try
	return 15
end idle

on showStudio()
	do shell script "zsh " & quoted form of (POSIX path of (path to home folder) & "Scans/.scancut/scan-studio.sh") & " > /dev/null 2>&1 &"
end showStudio
