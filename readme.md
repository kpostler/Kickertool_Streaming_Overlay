# Kicker Stream Overlay

## Overview

This project provides a browser-based overlay for live streaming foosball (table soccer) tournaments. It integrates with the Kickertool API to display real-time match information in OBS or similar streaming software.

The overlay is optimized for tournaments with:

- Randomized preliminary rounds (DYP / Monster DYP)
- Subsequent knockout stages (A/B brackets)
- Multiple tables (focus on Table 1 as stream table)

Key features:

- Automatic detection of the current match on Table 1
- Live / Upcoming / Result state handling
- Manual override via control interface
- Persistent match history with timer
- OBS-friendly layout with minimal table obstruction

---

## Project Structure

```
project-root/
├── overlay.html              # Main stream overlay (used in OBS browser source)
├── control.html              # Manual control interface (override matches)
├── standings_mini.html       # Mini standings panel
├── standings_full.html       # fullscreen standings panel
├── bracket_mini.html         # Mini bracket panel (KO phase)
├── proxy.py                  # Backend proxy (API aggregation + logic)
├── requirements.txt          # Python dependencies
├── .gitignore                # Ignored files and folders
└── overlay_state/            # Last state of the overlay per tournament (ignored)
```

---

## Requirements

- Python 3.9+
- Modern web browser

### Install Python

Download Python from:

[https://www.python.org/downloads/](https://www.python.org/downloads/)

During installation, make sure to enable:

- ✔ "Add Python to PATH"

---

### Install dependencies (Webserver)

Open a terminal in the project folder and run:

```
pip install -r requirements.txt
```

This installs the required packages (including Flask), which runs the local webserver.

If `requirements.txt` is missing, create it with the following content:

```
flask
requests
python-dotenv
```


---

## Setup

### 1. Clone repository

```
git clone https://github.com/kpostler/Kickertool_Streaming_Overlay.git
cd Kickertool_Streaming_Overlay
```

---

### 2. Start the overlay

Use the provided batch file:

```
start_overlay.bat
```

This will:

- Start the backend (`proxy.py`)
- Automatically open the control interface in your browser

---

### 3. Configure Tournament

Open your tournament in Kickertool and copy the full URL, e.g.:

```
https://live.kickertool3.de/tournament/abcdef123456
```

Paste this link into the control interface (`control.html`).

👉 The overlay will automatically extract the tournament ID.

---


### 4. Configure OBS

Add a **Browser Source**:

- URL:

```
http://127.0.0.1:8000/overlay.html
```

- Recommended resolution:

```
1920x1080
```

---

## Control Interface

The control interface opens automatically when starting via `start_overlay.bat`.

Alternatively:

```
http://127.0.0.1:8000/control.html
```

Features:

- View all currently running matches
- Manually select match for stream
- Override automatic table detection

Use case:

- When Kickertool assigns incorrect table priority
- When production wants to focus on a specific match

---

## Core Logic

### Automatic match selection

Priority order:

1. Manual override (if active)
2. Match assigned to Table 1
3. Fallback: latest running match in newest round

---

### Match states

- `live` → currently running match
- `upcoming` → next scheduled match
- `result` → finished match
- `bye` → no opponent

---

### History tracking

- Tracks played matches with timestamps
- Persists across restarts
- Used for stream timeline and debugging

---

## Webserver

The backend runs a local webserver (Flask).

Default configuration in this project:

```
http://127.0.0.1:8000
```

If you change the port in `proxy.py`, you must also update the URLs in OBS and your browser.

---

## Known Issues

- Table 1 is not always correctly detected
- After a match ends, the overlay may temporarily display a result from the wrong round or table


## License

This project is licensed under the MIT License.

You are free to use, modify and distribute this software.