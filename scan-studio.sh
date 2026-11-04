#!/bin/zsh
# apre Scan Studio (lo chiama l'app del Dock, scan-studio.applescript):
# - lo studio gira gia': riporta davanti la finestra nascosta, o ne apre una se non ce n'e'
# - non gira: lo avvia (studio.py fa da server e apre la finestra di Chrome)
URL=http://127.0.0.1:8765/
DATA=$HOME/Scans/.scancut/studio-data
mkdir -p $DATA
idle=$(curl -s --max-time 1 ${URL}api/ping | sed -n 's/.*"idle": *\([0-9.]*\).*/\1/p')
if [[ -n $idle ]]; then
  pid=$(pgrep -o -f 'user-data-dir=.*studio-data/window')
  [[ -n $pid ]] && ${0:A:h}/studio/appctl show $pid
  # nessuna finestra ha chiesto niente da un minuto: non ce n'e' una aperta
  if (( idle > 60 )); then
    open -na "Google Chrome" --args --app=$URL --user-data-dir=$DATA/window --no-first-run --no-default-browser-check
  fi
  exit 0
fi
nohup /opt/miniconda3/bin/python3 -I ${0:A:h}/studio.py >> $DATA/server.log 2>&1 &
