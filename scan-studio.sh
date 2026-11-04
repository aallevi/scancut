#!/bin/zsh
# apre Scan Studio dal Dock (~/Applications/Scan Studio.app): l'app stessa fa da server e apre
# una finestra di Chrome senza schede. Chiusa la finestra, si chiude da sola dopo un minuto.
# (Il server non puo' essere un figlio lasciato indietro: macOS lo chiude quando l'app esce.)
exec /opt/miniconda3/bin/python3 -I ${0:A:h}/studio.py >> $HOME/Scans/.scancut/studio-data/server.log 2>&1
