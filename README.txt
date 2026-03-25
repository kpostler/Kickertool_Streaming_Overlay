README – Kickertool / Tournament.io OBS Overlay

Enthaltene Dateien
- proxy.py
- Overlay.html
- control.html
- standings_full.html
- standings_mini.html
- bracket_mini.html
- start_overlay.bat
- check_overlay_pages.bat

Benötigte Python-Pakete
pip install flask flask-cors requests

Start
1. Alle Dateien in einen gemeinsamen Ordner legen
2. Doppelklick auf start_overlay.bat
3. control.html wird automatisch geöffnet

Wichtige URLs
- Steuerseite:
  http://127.0.0.1:8000/control.html

- Match-Overlay:
  http://127.0.0.1:8000/Overlay.html

- Vollbild-Standings:
  http://127.0.0.1:8000/standings_full.html

- Mini-Standings:
  http://127.0.0.1:8000/standings_mini.html

- Mini-Bracket:
  http://127.0.0.1:8000/bracket_mini.html

OBS Browser Source
- Breite: 1920
- Höhe: 1080
- Lokale Datei: aus
- Browser bei Szenenaktivierung aktualisieren: an

Turnier auswählen
- In control.html einfach Tournament-ID, API-URL oder Live-URL einfügen
- Dann auf "Turnier übernehmen" klicken

Funktionslogik
- Für das Match-Overlay wird nicht mehr nur nach match.courts gefiltert
- Laufende bzw. angekündigte Matches werden aus der aktuellen Runde nach roundOrder / order sortiert
- Für Tisch 1 wird das erste laufende Match verwendet
- Für Result-Fallbacks wird weiterhin court-Zuordnung genutzt, falls vorhanden
- Für die YouTube-History werden Matches mitgeschrieben, sobald sie auf dem Streaming-Tisch als Live erkannt werden

Hinweis
Die zwei schwarzen Fenster für Proxy und Webserver müssen während des Betriebs offen bleiben.

Update:
- Live-Matches behalten jetzt ihre feste Tisch-Zuordnung, auch wenn ein anderer Tisch schon fertig ist.
- Der Zeitstempel in der YouTube-History wird nur noch beim ersten Erkennen des Live-Matches gesetzt.

Update 2:
- Wenn auf Tisch 1 das Match einer Runde bereits beendet ist, bleibt dieses Result sichtbar, auch wenn auf anderen Tischen derselben Runde noch Live-Matches laufen.
- Wenn eine neue Runde angelegt wurde, aber noch keine Spiele aufgerufen wurden, bleibt das vorherige Match stehen.

Bracket Mini:
- wird nur in der KO-Runde angezeigt
- wird bei Live-Matches ausgeblendet
- zeigt sonst die relevante KO-Runde an
- im Finale werden zusätzlich die Halbfinals eingeblendet

Patch 3:
- Im Match-Overlay wird jetzt automatisch zwischen standings_mini.html (Vorrunde) und bracket_mini.html (KO Runde) umgeschaltet.
- Wenn auf Tisch 1 bereits das Resultat einer Runde steht und auf einem anderen Tisch noch die ältere Runde läuft, wird bei einem neu gestarteten Match auf Tisch 1 die neuere Runde bevorzugt.
