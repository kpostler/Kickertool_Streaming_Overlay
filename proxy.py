
from flask import Flask, jsonify, request, Response, send_file
from flask_cors import CORS
import requests
import time
import json
import re
from pathlib import Path
from copy import deepcopy

STREAM_TABLE_NUMBER = 1
API_TEMPLATE = "https://api.tournament.io/v1/table_soccer/result/tournaments/{tournament_id}"

SAVE_DIR = Path("overlay_state")
SAVE_DIR.mkdir(exist_ok=True)
CONFIG_PATH = SAVE_DIR / "config.json"

DEFAULT_TOURNAMENT_ID = "tio:Lo0yC6ACT2k9a"

app = Flask(__name__)
CORS(app)

overlay_state = {"swapped": False}
stream_state = {
    "stream_offset_seconds": 0.0,
    "timer_running": False,
    "timer_started_at_unix": None,
}

table1_history = []
history_index_by_match_id = {}
table_slot_assignments = {}
current_tournament_id = None
stream_override = {"match_id": None}


def now_ts():
    return time.time()


def current_elapsed_seconds():
    offset = float(stream_state.get("stream_offset_seconds", 0.0) or 0.0)
    if stream_state.get("timer_running") and stream_state.get("timer_started_at_unix"):
        return int(offset + (now_ts() - float(stream_state["timer_started_at_unix"])))
    return int(offset)


def build_api_url(tournament_id: str) -> str:
    return API_TEMPLATE.format(tournament_id=tournament_id)


def extract_tournament_id(value: str):
    if not value:
        return None
    value = value.strip()
    if value.startswith("tio:"):
        return value
    match = re.search(r"(tio:[A-Za-z0-9]+)", value)
    return match.group(1) if match else None


def format_elapsed(seconds_total):
    seconds_total = max(0, int(seconds_total))
    h = seconds_total // 3600
    m = (seconds_total % 3600) // 60
    s = seconds_total % 60
    return f"{h}:{m:02d}:{s:02d}"


def build_map(items):
    return {item["_id"]: item for item in (items or []) if "_id" in item}


def get_match_id(match):
    if not isinstance(match, dict):
        return None
    return match.get("_id") or match.get("id")


def player_label(entry):
    if not entry:
        return "—"
    etype = entry.get("type")
    if etype == "player":
        return " ".join(
            p for p in [str(entry.get("firstName", "")).strip(), str(entry.get("lastName", "")).strip()] if p
        ) or entry.get("_id", "—")
    if etype == "player_name":
        return entry.get("name", entry.get("_id", "—"))
    return entry.get("name", entry.get("_id", "—"))


def team_label(side, entry_map):
    if side is None:
        return "—"
    if isinstance(side, str):
        entry = entry_map.get(side)
        if not entry:
            return side
        if entry.get("type") == "team" and isinstance(entry.get("players"), list):
            return " / ".join(player_label(entry_map.get(pid)) for pid in entry["players"])
        return player_label(entry)
    if isinstance(side, list):
        return " / ".join(player_label(entry_map.get(pid)) for pid in side)
    return "—"


def round_label(round_obj):
    if not round_obj:
        return "Aktuelle Runde"
    name = round_obj.get("name")
    params = round_obj.get("nameParams", {})
    if name == "FINALS":
        d = params.get("denominator")
        if d == 1:
            return "Finale"
        if d == 2:
            return "1/2 Finale"
        if d == 4:
            return "1/4 Finale"
        return f"Finalrunde ({d})"
    if name == "THIRD_PLACE":
        return "Spiel um Platz 3"
    idx = round_obj.get("index")
    if idx is not None and not name:
        return f"Vorrunde {int(idx) + 1}"
    return name or "Aktuelle Runde"


def stage_group_name(stage_obj):
    if not stage_obj:
        return "Sonstiges"
    stage_name = str(stage_obj.get("name", "")).strip().lower()
    tournament_mode = str(stage_obj.get("tournamentMode", "")).lower()

    if "ko" in stage_name or tournament_mode == "elimination":
        return "KO Runde"
    if "preliminary" in stage_name or "vorrunde" in stage_name or tournament_mode == "monster_dyp":
        return "Vorrunde"
    return "Sonstiges"


def get_effective_state(match):
    raw_state = str(match.get("state", "")).lower()
    has_result = bool(isinstance(match.get("result"), list) and len(match.get("result")) > 0)
    has_points = bool(isinstance(match.get("points"), list) and len(match.get("points")) > 0)
    has_winner = isinstance(match.get("winner"), int) or isinstance(match.get("winnerIndex"), int)
    has_end_time = bool(match.get("endTime"))

    if raw_state in {"running", "live", "active", "started"}:
        return "live"
    if raw_state in {"open", "pending", "announced", "called"}:
        return "upcoming"
    if raw_state == "played":
        if not has_result and not has_points and not has_winner:
            return "live"
        if not has_end_time and not has_winner and not has_points:
            return "live"
        return "result"
    if raw_state == "bye":
        return "bye"
    return "unknown"


def get_running_stage(data):
    stages = data.get("stages", [])
    running = [s for s in stages if str(s.get("state", "")).lower() == "running"]
    if running:
        return sorted(running, key=lambda s: int(s.get("order", 9999)))[0]
    if stages:
        return sorted(stages, key=lambda s: int(s.get("order", 9999)))[-1]
    return None


def get_court(data, court_number):
    for court in data.get("courts", []):
        try:
            if int(court.get("number", -1)) == int(court_number):
                return court
        except Exception:
            pass
    return None


def normalize_match(match, payload, table_number=None, source_reason=None):
    entry_map = build_map(payload.get("entries"))
    round_map = build_map(payload.get("rounds"))
    stage_map = build_map(payload.get("stages"))

    round_obj = round_map.get(match.get("roundId"))
    stage_obj = stage_map.get(match.get("stageId"))
    entries = match.get("entries", [])

    team_a = team_label(entries[0] if len(entries) > 0 else None, entry_map)
    team_b = team_label(entries[1] if len(entries) > 1 else None, entry_map)

    winner = match.get("winner")
    if not isinstance(winner, int):
        winner = match.get("winnerIndex")

    draw = False
    if get_effective_state(match) == "result" and winner not in (0, 1):
        draw = True

    return {
        "found": True,
        "table_number": table_number,
        "tournament_name": (payload.get("tournaments") or [{}])[0].get("name", "Turnier"),
        "tournament_id": current_tournament_id,
        "match_id": get_match_id(match),
        "display_state": get_effective_state(match),
        "round_label": round_label(round_obj),
        "section_label": stage_group_name(stage_obj),
        "team_a": team_a,
        "team_b": team_b,
        "winner": winner if winner in (0, 1) else None,
        "draw": draw,
        "source_reason": source_reason,
        "raw_state": match.get("state"),
        "group_id": match.get("groupId"),
        "stage_id": match.get("stageId"),
        "round_id": match.get("roundId"),
        "round_order": match.get("roundOrder"),
        "order": match.get("order"),
        "start_time": match.get("startTime"),
        "end_time": match.get("endTime"),
    }


def sort_live_candidates(matches):
    priority = {"live": 1, "upcoming": 2, "result": 4, "bye": 6, "unknown": 9}

    def key(m):
        eff = get_effective_state(m)
        return (
            priority.get(eff, 9),
            int(m.get("roundOrder", 9999) if m.get("roundOrder") is not None else 9999),
            int(m.get("order", 9999) if m.get("order") is not None else 9999),
            str(m.get("startTime") or ""),
        )

    return sorted(matches, key=key)


def assign_live_slots(live_like):
    """
    Persist a stable mapping from live/upcoming match_id -> streaming table slot.
    This prevents remaining live matches from shifting to lower table numbers
    when a lower-numbered table has already finished.
    """
    global table_slot_assignments

    live_like = sort_live_candidates(live_like)
    used_slots = set()

    # Keep existing assignments where possible.
    for match in live_like:
        slot = table_slot_assignments.get(get_match_id(match))
        if isinstance(slot, int) and slot > 0 and slot not in used_slots:
            used_slots.add(slot)

    # Assign free slots to newly seen matches in sorted order.
    next_slot = 1
    for match in live_like:
        match_id = get_match_id(match)
        if not match_id:
            continue
        slot = table_slot_assignments.get(match_id)
        if isinstance(slot, int) and slot > 0:
            continue
        while next_slot in used_slots:
            next_slot += 1
        table_slot_assignments[match_id] = next_slot
        used_slots.add(next_slot)
        next_slot += 1


def select_display_match(payload, table_number=1):
    all_matches = payload.get("matches", [])
    running_stage = get_running_stage(payload)
    running_stage_id = running_stage.get("_id") if running_stage else None

    stage_matches = [m for m in all_matches if (not running_stage_id or m.get("stageId") == running_stage_id)]

    # 0) Manueller Stream-Override hat Vorrang fuer Tisch 1
    override_match_id = stream_override.get("match_id")
    if int(table_number) == 1 and override_match_id:
        override_match = next((m for m in all_matches if get_match_id(m) == override_match_id), None)
        if override_match is not None:
            return normalize_match(override_match, payload, table_number, "manual_override")

    def match_sort_key(m):
        return (
            int(m.get("roundOrder", -1) if m.get("roundOrder") is not None else -1),
            str(m.get("startTime") or ""),
            int(m.get("order", -1) if m.get("order") is not None else -1),
        )

    # 1) Letztes explizites Result dieses Tisches suchen
    latest_court_result = None
    court = get_court(payload, table_number)
    if court:
        court_id = court["_id"]
        court_results = [
            m for m in stage_matches
            if get_effective_state(m) == "result"
            and isinstance(m.get("courts"), list)
            and court_id in m["courts"]
        ]
        court_results = sorted(court_results, key=match_sort_key, reverse=False)
        if court_results:
            latest_court_result = court_results[0]

    latest_result_round_order = None
    if latest_court_result and latest_court_result.get("roundOrder") is not None:
        latest_result_round_order = int(latest_court_result.get("roundOrder"))

    # 2) Laufende / kommende Matches der aktuellen Stage
    live_like = [m for m in stage_matches if get_effective_state(m) in {"live", "upcoming"}]
    if not live_like:
        live_like = [m for m in all_matches if get_effective_state(m) in {"live", "upcoming"}]

    live_like = sort_live_candidates(live_like)
    # KO-Schutz:
    # Wenn es bereits ein echtes Result für Tisch 1 gibt, dürfen nur Matches
    # aus demselben Feld (groupId) als Fortsetzung von Tisch 1 gelten.
    if latest_court_result is not None and latest_court_result.get("groupId") is not None:
        live_like = [
            m for m in live_like
            if m.get("groupId") == latest_court_result.get("groupId")
        ]

    # 3) WENN es schon ein echtes Tisch-Result gibt:
    #    -> KEINE stabile Slot-Zuordnung priorisieren
    #    -> nur auf höhere Runde springen
    if latest_court_result is not None:
        if live_like:
            newer_round_matches = [
                m for m in live_like
                if m.get("roundOrder") is not None
                and latest_result_round_order is not None
                and int(m.get("roundOrder")) > latest_result_round_order
                and latest_court_result is not None
                and m.get("groupId") == latest_court_result.get("groupId")
            ]

            if newer_round_matches:
                newer_round_matches = sorted(newer_round_matches, key=match_sort_key, reverse=False)
                chosen = newer_round_matches[0]
                match_id = get_match_id(chosen)
                if match_id:
                    table_slot_assignments[match_id] = int(table_number)
                    if current_tournament_id:
                        save_state(current_tournament_id)
                return normalize_match(chosen, payload, table_number, "newer_round_live_priority")

            same_round_matches = [
                m for m in live_like
                if m.get("roundOrder") is not None
                and latest_result_round_order is not None
                and int(m.get("roundOrder")) == latest_result_round_order
                and latest_court_result is not None
                and m.get("groupId") == latest_court_result.get("groupId")
            ]

            if same_round_matches:
                return normalize_match(latest_court_result, payload, table_number, "same_round_result_hold")

        return normalize_match(latest_court_result, payload, table_number, "court_result")

    # 4) Nur wenn es noch KEIN echtes Tisch-Result gibt:
    #    stabile Slot-Zuordnung verwenden
    if live_like:
        assign_live_slots(live_like)

        for match in live_like:
            if table_slot_assignments.get(get_match_id(match)) == int(table_number):
                return normalize_match(match, payload, table_number, "stable_live_slot")

        idx = max(0, int(table_number) - 1)
        if len(live_like) > idx:
            chosen = live_like[idx]
            match_id = get_match_id(chosen)
            if match_id:
                table_slot_assignments[match_id] = int(table_number)
                if current_tournament_id:
                    save_state(current_tournament_id)
            return normalize_match(chosen, payload, table_number, "auto_live_slot")

    # 5) Letzter Fallback: History
    if table_number == 1 and table1_history:
        last = deepcopy(table1_history[-1])
        last["found"] = True
        last["table_number"] = table_number
        last["tournament_name"] = (payload.get("tournaments") or [{}])[0].get("name", "Turnier")
        last["tournament_id"] = current_tournament_id
        last["display_state"] = "result"
        last["source_reason"] = "history_fallback"
        return last

    return {
        "found": False,
        "table_number": table_number,
        "tournament_name": (payload.get("tournaments") or [{}])[0].get("name", "Turnier"),
        "tournament_id": current_tournament_id,
        "display_state": "none",
        "source_reason": "no_match",
    }


def serialize_state():
    return {
        "overlay_state": overlay_state,
        "stream_state": stream_state,
        "table1_history": table1_history,
        "table_slot_assignments": table_slot_assignments,
        "stream_override": stream_override,
    }


def rebuild_history_index():
    global history_index_by_match_id
    history_index_by_match_id = {}
    for idx, item in enumerate(table1_history):
        mid = item.get("match_id")
        if mid:
            history_index_by_match_id[mid] = idx


def tournament_save_path(tournament_id):
    safe = tournament_id.replace(":", "_").replace("/", "_")
    return SAVE_DIR / f"{safe}.json"


def save_state(tournament_id):
    if not tournament_id:
        return
    tournament_save_path(tournament_id).write_text(
        json.dumps(serialize_state(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def reset_runtime_state():
    global table1_history, table_slot_assignments
    overlay_state["swapped"] = False
    stream_override["match_id"] = None
    stream_state["stream_offset_seconds"] = 0.0
    stream_state["timer_running"] = False
    stream_state["timer_started_at_unix"] = None
    table1_history = []
    table_slot_assignments = {}
    rebuild_history_index()


def load_state(tournament_id):
    global table1_history, table_slot_assignments
    path = tournament_save_path(tournament_id)
    reset_runtime_state()

    if not path.exists():
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        overlay_state["swapped"] = bool(data.get("overlay_state", {}).get("swapped", False))

        saved_stream = data.get("stream_state", {})
        stream_state["stream_offset_seconds"] = float(saved_stream.get("stream_offset_seconds", 0.0) or 0.0)
        stream_state["timer_running"] = bool(saved_stream.get("timer_running", False))
        stream_state["timer_started_at_unix"] = saved_stream.get("timer_started_at_unix", None)

        table1_history = list(data.get("table1_history", []) or [])
        table_slot_assignments = dict(data.get("table_slot_assignments", {}) or {})
        stream_override["match_id"] = (data.get("stream_override", {}) or {}).get("match_id")
        rebuild_history_index()
    except Exception:
        reset_runtime_state()


def load_global_config():
    global current_tournament_id
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            tid = data.get("current_tournament_id")
            if tid:
                current_tournament_id = tid
                return
        except Exception:
            pass
    current_tournament_id = DEFAULT_TOURNAMENT_ID


def save_global_config():
    CONFIG_PATH.write_text(
        json.dumps({"current_tournament_id": current_tournament_id}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def switch_tournament(tournament_id):
    global current_tournament_id
    current_tournament_id = tournament_id
    save_global_config()
    load_state(tournament_id)


def get_current_api_url():
    return build_api_url(current_tournament_id)


def fetch_payload():
    r = requests.get(get_current_api_url(), timeout=15)
    r.raise_for_status()
    return r.json()


def register_stream_history(display_match):
    if display_match.get("table_number") != 1:
        return
    if display_match.get("display_state") != "live":
        return

    match_id = display_match.get("match_id")
    if not match_id:
        return

    # Important: keep the original timestamp stable once the match was first seen.
    if match_id in history_index_by_match_id:
        return

    item = {
        "match_id": match_id,
        "section_label": display_match.get("section_label", "Sonstiges"),
        "round_label": display_match.get("round_label", "Aktuelle Runde"),
        "team_a": display_match.get("team_a", "—"),
        "team_b": display_match.get("team_b", "—"),
        "winner": None,
        "draw": False,
        "timestamp_seconds": current_elapsed_seconds(),
    }

    table1_history.append(item)
    history_index_by_match_id[match_id] = len(table1_history) - 1

    if current_tournament_id:
        save_state(current_tournament_id)


def build_history_text():
    groups = {"Vorrunde": [], "KO Runde": [], "Sonstiges": []}

    for item in table1_history:
        section = item.get("section_label", "Sonstiges")
        if section not in groups:
            groups[section] = []

        groups[section].append(
            f'{format_elapsed(item["timestamp_seconds"])} {item["round_label"]} ( {item["team_a"]} vs. {item["team_b"]} )'
        )

    parts = []
    for section in ["Vorrunde", "KO Runde", "Sonstiges"]:
        lines = groups.get(section, [])
        if not lines:
            continue
        parts.append(f"{section}:")
        parts.append("")
        parts.extend(lines)
        parts.append("")

    return "\n".join(parts).strip()


@app.route("/config", methods=["GET"])
def get_config():
    return jsonify({
        "tournament_id": current_tournament_id,
        "api_url": get_current_api_url(),
    })


@app.route("/config/tournament", methods=["POST"])
def set_tournament():
    payload = request.get_json(silent=True) or {}
    value = str(payload.get("value", "")).strip()

    tournament_id = extract_tournament_id(value)
    if not tournament_id:
        return jsonify({"ok": False, "error": "Keine gültige Tournament-ID gefunden"}), 400

    switch_tournament(tournament_id)

    return jsonify({
        "ok": True,
        "tournament_id": current_tournament_id,
        "api_url": get_current_api_url(),
    })


@app.route("/data")
def data():
    payload = fetch_payload()
    return jsonify(payload)


@app.route("/display_match/<int:table_number>")
def display_match(table_number):
    payload = fetch_payload()
    match = select_display_match(payload, table_number=table_number)

    if table_number == 1 and match.get("found"):
        register_stream_history(match)

    return jsonify(match)


@app.route("/state")
def state():
    return jsonify({
        **overlay_state,
        "elapsed_seconds": current_elapsed_seconds(),
        "elapsed_formatted": format_elapsed(current_elapsed_seconds()),
        "timer_running": stream_state.get("timer_running", False),
        "tournament_id": current_tournament_id,
    })


@app.route("/toggle_swap", methods=["GET", "POST"])
def toggle_swap():
    overlay_state["swapped"] = not overlay_state["swapped"]
    if current_tournament_id:
        save_state(current_tournament_id)
    return jsonify(overlay_state)


@app.route("/set_swap/<value>", methods=["GET", "POST"])
def set_swap(value):
    overlay_state["swapped"] = value.lower() in ["1", "true", "yes", "on"]
    if current_tournament_id:
        save_state(current_tournament_id)
    return jsonify(overlay_state)


@app.route("/timer/start", methods=["GET", "POST"])
def timer_start():
    if not stream_state["timer_running"]:
        stream_state["timer_running"] = True
        stream_state["timer_started_at_unix"] = now_ts()
        if current_tournament_id:
            save_state(current_tournament_id)
    return jsonify({"ok": True, "elapsed_seconds": current_elapsed_seconds()})


@app.route("/timer/stop", methods=["GET", "POST"])
def timer_stop():
    if stream_state["timer_running"] and stream_state["timer_started_at_unix"]:
        stream_state["stream_offset_seconds"] = current_elapsed_seconds()
        stream_state["timer_running"] = False
        stream_state["timer_started_at_unix"] = None
        if current_tournament_id:
            save_state(current_tournament_id)
    return jsonify({"ok": True, "elapsed_seconds": current_elapsed_seconds()})


@app.route("/timer/reset", methods=["GET", "POST"])
def timer_reset():
    stream_state["stream_offset_seconds"] = 0.0
    stream_state["timer_running"] = False
    stream_state["timer_started_at_unix"] = None
    if current_tournament_id:
        save_state(current_tournament_id)
    return jsonify({"ok": True, "elapsed_seconds": 0})



def winner_draw_info(match):
    winner = match.get("winner")
    if not isinstance(winner, int):
        winner = match.get("winnerIndex")
    draw = False
    if get_effective_state(match) == "result" and winner not in (0, 1):
        draw = True
    return winner if winner in (0, 1) else None, draw


def build_bracket_match(match, payload, highlight_match_id=None):
    entry_map = build_map(payload.get("entries"))
    round_map = build_map(payload.get("rounds"))
    entries = match.get("entries") or []

    team_a = team_label(entries[0] if len(entries) > 0 else None, entry_map)
    team_b = team_label(entries[1] if len(entries) > 1 else None, entry_map)
    winner, draw = winner_draw_info(match)
    round_obj = round_map.get(match.get("roundId"))

    return {
        "match_id": get_match_id(match),
        "team_a": team_a,
        "team_b": team_b,
        "display_state": get_effective_state(match),
        "winner": winner,
        "draw": draw,
        "round_label": round_label(round_obj),
        "round_order": match.get("roundOrder"),
        "order": match.get("order"),
        "highlight": get_match_id(match) == highlight_match_id,
    }


def build_bracket_mini_payload(payload):
    display = select_display_match(payload, table_number=1)

    result = {
        "visible": False,
        "tournament_name": (payload.get("tournaments") or [{}])[0].get("name", "Turnier"),
        "field_label": "",
        "title": "KO Runde",
        "reason": "",
        "sections": [],
        "highlight_match_id": None,
    }

    if not display.get("found"):
        result["reason"] = "no_display_match"
        return result

    if display.get("section_label") != "KO Runde":
        result["reason"] = "not_ko_round"
        return result

    if display.get("display_state") == "live":
        result["reason"] = "hidden_during_live"
        return result

    current_group_id = display.get("group_id")
    current_round_order = display.get("round_order")
    current_match_id = display.get("match_id")

    if current_group_id is None or current_round_order is None:
        result["reason"] = "missing_group_or_round"
        return result

    groups_map = build_map(payload.get("groups"))
    field_group = groups_map.get(current_group_id) or {}
    field_label = field_group.get("name", "KO Feld")

    group_matches = [m for m in payload.get("matches", []) if m.get("groupId") == current_group_id]
    if not group_matches:
        result["reason"] = "no_group_matches"
        return result

    group_round_orders = sorted({
        int(m.get("roundOrder")) for m in group_matches if m.get("roundOrder") is not None
    })
    max_round_order = max(group_round_orders) if group_round_orders else int(current_round_order)

    if int(current_round_order) == max_round_order and max_round_order > 0:
        round_orders_to_show = [max_round_order - 1, max_round_order]
    else:
        round_orders_to_show = [int(current_round_order)]

    round_orders_to_show = [ro for ro in round_orders_to_show if ro in group_round_orders]
    round_map = build_map(payload.get("rounds"))
    sections = []

    for ro in round_orders_to_show:
        round_matches = sorted(
            [m for m in group_matches if int(m.get("roundOrder", -999)) == ro],
            key=lambda m: int(m.get("order", 9999) if m.get("order") is not None else 9999),
        )
        if not round_matches:
            continue

        round_label_text = round_label(round_map.get(round_matches[0].get("roundId")))
        sections.append({
            "round_label": round_label_text,
            "matches": [build_bracket_match(m, payload, highlight_match_id=current_match_id) for m in round_matches],
        })

    result["visible"] = len(sections) > 0
    result["field_label"] = field_label
    result["title"] = "KO Runde"
    result["reason"] = "ok" if result["visible"] else "no_sections"
    result["sections"] = sections
    result["highlight_match_id"] = current_match_id
    return result


@app.route("/bracket_mini")
def bracket_mini():
    payload = fetch_payload()
    return jsonify(build_bracket_mini_payload(payload))




def build_live_candidates_payload(payload):
    all_matches = payload.get("matches", [])
    running_stage = get_running_stage(payload)
    running_stage_id = running_stage.get("_id") if running_stage else None
    stage_matches = [m for m in all_matches if (not running_stage_id or m.get("stageId") == running_stage_id)]
    entry_map = build_map(payload.get("entries"))
    round_map = build_map(payload.get("rounds"))
    court_map = build_map(payload.get("courts"))

    candidates = [m for m in stage_matches if get_effective_state(m) in {"live", "upcoming"}]
    candidates = sort_live_candidates(candidates)

    items = []
    for m in candidates:
        entries = m.get("entries", [])
        courts = m.get("courts") if isinstance(m.get("courts"), list) else []
        court_labels = []
        for cid in courts:
            court = court_map.get(cid)
            if court:
                court_labels.append(f'Tisch {court.get("number", "?")}')
        items.append({
            "match_id": get_match_id(m),
            "display_state": get_effective_state(m),
            "round_label": round_label(round_map.get(m.get("roundId"))),
            "team_a": team_label(entries[0] if len(entries) > 0 else None, entry_map),
            "team_b": team_label(entries[1] if len(entries) > 1 else None, entry_map),
            "court_labels": court_labels,
            "group_id": m.get("groupId"),
            "round_order": m.get("roundOrder"),
            "order": m.get("order"),
            "start_time": m.get("startTime"),
            "is_override": get_match_id(m) == stream_override.get("match_id"),
        })

    return {
        "override_match_id": stream_override.get("match_id"),
        "items": items,
    }


@app.route("/stream_override", methods=["GET"])
def get_stream_override():
    return jsonify({"match_id": stream_override.get("match_id")})


@app.route("/stream_override", methods=["POST"])
def set_stream_override():
    payload = request.get_json(silent=True) or {}
    match_id = payload.get("match_id")
    stream_override["match_id"] = str(match_id).strip() if match_id else None
    if current_tournament_id:
        save_state(current_tournament_id)
    return jsonify({"ok": True, "match_id": stream_override.get("match_id")})


@app.route("/stream_override/clear", methods=["POST"])
def clear_stream_override():
    stream_override["match_id"] = None
    if current_tournament_id:
        save_state(current_tournament_id)
    return jsonify({"ok": True, "match_id": None})


@app.route("/live_candidates")
def live_candidates():
    payload = fetch_payload()
    return jsonify(build_live_candidates_payload(payload))


@app.route("/history_text")
def history_text():
    return Response(build_history_text(), mimetype="text/plain; charset=utf-8")


@app.route("/history/reset", methods=["GET", "POST"])
def history_reset():
    global table1_history, table_slot_assignments
    table1_history = []
    table_slot_assignments = {}
    rebuild_history_index()
    if current_tournament_id:
        save_state(current_tournament_id)
    return jsonify({"ok": True})


@app.route("/history/export")
def history_export():
    if not current_tournament_id:
        return Response(build_history_text(), mimetype="text/plain; charset=utf-8")

    path = tournament_save_path(current_tournament_id)
    if not path.exists():
        path.write_text(
            json.dumps(serialize_state(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return send_file(path, as_attachment=True, download_name=path.name, mimetype="application/json")

@app.route("/debug/display_match_logic/<int:table_number>")
def debug_display_match_logic(table_number):
    payload = fetch_payload()

    all_matches = payload.get("matches", [])
    running_stage = get_running_stage(payload)
    running_stage_id = running_stage.get("_id") if running_stage else None
    stage_matches = [m for m in all_matches if (not running_stage_id or m.get("stageId") == running_stage_id)]

    court = get_court(payload, table_number)
    court_id = court["_id"] if court else None

    def short(m):
        return {
            "id": get_match_id(m),
            "state": m.get("state"),
            "effective_state": get_effective_state(m),
            "roundOrder": m.get("roundOrder"),
            "order": m.get("order"),
            "startTime": m.get("startTime"),
            "courts": m.get("courts"),
            "groupId": m.get("groupId"),
            "roundId": m.get("roundId"),
            "entries": m.get("entries"),
        }

    court_results = [
        m for m in stage_matches
        if get_effective_state(m) == "result"
        and isinstance(m.get("courts"), list)
        and court_id in m["courts"]
    ] if court_id else []

    live_like = [m for m in stage_matches if get_effective_state(m) in {"live", "upcoming"}]

    return jsonify({
        "running_stage": running_stage,
        "court": court,
        "court_results": [short(m) for m in court_results],
        "live_like": [short(m) for m in live_like],
        "table_slot_assignments": table_slot_assignments,
        "stream_override": stream_override,
        "selected": select_display_match(payload, table_number),
    })


if __name__ == "__main__":
    load_global_config()
    load_state(current_tournament_id)
    app.run(host="127.0.0.1", port=5000)
