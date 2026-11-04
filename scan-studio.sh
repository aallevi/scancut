#!/bin/zsh
# apre Scan Studio: avvia il server se non gira gia', poi una finestra di Chrome senza schede.
# Lo usa l'app nel Dock (~/Applications/Scan Studio.app).
PY=/opt/miniconda3/bin/python3
DIR=${0:A:h}
DATA=$HOME/Scans/.scancut/studio-data
URL=http://127.0.0.1:8765/
mkdir -p $DATA
if ! curl -s -o /dev/null --max-time 1 ${URL}api/settings; then
  nohup $PY -I $DIR/studio.py serve >> $DATA/server.log 2>&1 &!
  for i in {1..60}; do curl -s -o /dev/null --max-time 1 ${URL}api/settings && break; sleep 0.25; done
fi
open -na "Google Chrome" --args --app=$URL --user-data-dir=$DATA/window --no-first-run --no-default-browser-check --window-size=1400,900
