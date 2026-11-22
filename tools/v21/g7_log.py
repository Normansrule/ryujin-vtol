#!/usr/bin/env python3
"""Read an ArduPilot Plane log from a G7 water test and pull out the numbers the G7 gates need.

    python3 tools/v21/g7_log.py LOG.bin               # DataFlash binary from the SD card
    python3 tools/v21/g7_log.py LOG.log               # or the text export (Mission Planner "convert .bin to .log")
    python3 tools/v21/g7_log.py LOG.bin --write       # also fill the empty fields in config/v21_measurements.json
    python3 tools/v21/g7_log.py LOG.bin --replay out.json   # sticks, modes, attitude and current for the twin tab
    python3 tools/v21/g7_log.py --selftest

What it reads (message and field names from each log's own FMT records, so firmware versions can differ):
  MODE.Mode   flight mode number (ArduPlane numbering: 0 MANUAL, 17 QSTABILIZE, 18 QHOVER, 19 QLOITER, ...)
  BAT.Curr    battery current, A (instance 0 when the log has several)
  GPS.Spd     ground speed, m/s (instance 0)

What it gives:
  W6 taxi_max_speed_m_s     the highest 2 s running median of GPS ground speed while in MANUAL (water-taxi is MANUAL with the
                            water switch high). Do one straight run per log; a fast wing-borne MANUAL pass in the same
                            log would count too.
  W7 water_takeoff_peak_a   the highest BAT current in each stretch of QSTABILIZE / QHOVER / QLOITER (one per take-off
                            attempt), and the worst of them.
It does not judge whether a take-off succeeded: that stays the pilot's call (water_takeoffs_ok).

--replay writes what the "V21 twin" tab needs to fly the same stick inputs through the model and draw the measured
attitude beside it: RCIN C1-C4 (through RCMAP_* and RCn_MIN/TRIM/MAX from the PARM records), MODE, ATT Roll/Pitch/
DesRoll/DesPitch and BAT Curr, resampled to 50 Hz. Stick signs are checked against the log itself: the roll stick must
agree with ATT.DesRoll and pulling back (twin pitch -1) with a nose-up ATT.DesPitch; a channel the log contradicts is
flipped and reported (RCn_REVERSED differs between radios).

The reader is checked against logs it writes itself (--selftest). Reading a real Plane log is UNCONFIRMED until the
first G7 log goes through it: check its MODE / BAT / GPS counts against Mission Planner's log browser once.
"""
from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MEAS = ROOT / "config" / "v21_measurements.json"

HEAD = b"\xa3\x95"
FMT_ID = 128
# DataFlash format characters -> (struct code, scale). Strings are decoded and stripped of NULs.
TYPES = {
    "a": ("32h", None), "b": ("b", 1), "B": ("B", 1), "h": ("h", 1), "H": ("H", 1), "i": ("i", 1), "I": ("I", 1),
    "f": ("f", 1), "d": ("d", 1), "n": ("4s", None), "N": ("16s", None), "Z": ("64s", None),
    "c": ("h", 0.01), "C": ("H", 0.01), "e": ("i", 0.01), "E": ("I", 0.01), "L": ("i", 1e-7), "M": ("B", 1),
    "q": ("q", 1), "Q": ("Q", 1),
}
PLANE_MODES = {0: "MANUAL", 1: "CIRCLE", 2: "STABILIZE", 3: "TRAINING", 4: "ACRO", 5: "FBWA", 6: "FBWB", 7: "CRUISE",
               8: "AUTOTUNE", 10: "AUTO", 11: "RTL", 12: "LOITER", 13: "TAKEOFF", 15: "GUIDED", 17: "QSTABILIZE",
               18: "QHOVER", 19: "QLOITER", 20: "QLAND", 21: "QRTL", 22: "QAUTOTUNE", 23: "QACRO", 24: "THERMAL"}
TAKEOFF_MODES = {17, 18, 19}
WANTED = ("MODE", "BAT", "GPS", "RCIN", "ATT", "PARM")


# --- reading ---------------------------------------------------------------------------------------------------------
def read_bin(data: bytes) -> dict:
    """{name: [ {field: value} ]} for the WANTED messages of a DataFlash binary log."""
    fmts = {FMT_ID: ("FMT", "<BB4s16s64s", "BBnNZ", ["Type", "Length", "Name", "Format", "Columns"], 89)}
    out = {n: [] for n in WANTED}
    i, n = 0, len(data)
    while i + 3 <= n:
        if data[i:i + 2] != HEAD:
            j = data.find(HEAD, i + 1)
            if j < 0:
                break
            i = j
            continue
        mid = data[i + 2]
        f = fmts.get(mid)
        if f is None or i + f[4] > n:
            i += 1                                    # unknown or cut-off record: resync on the next header
            continue
        name, st, fmt, cols, length = f
        try:
            vals = struct.unpack(st, data[i + 3:i + length])
        except struct.error:
            i += 1
            continue
        if mid == FMT_ID:
            t, ln, nm, fm, cl = vals
            nm, fm = _s(nm), _s(fm)
            codes = "".join(TYPES[c][0] for c in fm if c in TYPES)
            if len(codes) and all(c in TYPES for c in fm) and struct.calcsize("<" + codes) == ln - 3:
                fmts[t] = (nm, "<" + codes, fm, _s(cl).split(","), ln)
        elif name in out:
            out[name].append(_row(vals, fmt, cols))
        i += length
    return out


def _s(b) -> str:
    return b.split(b"\0", 1)[0].decode("ascii", "replace") if isinstance(b, bytes) else str(b)


def _row(vals, fmt, cols) -> dict:
    row, k = {}, 0
    for c, col in zip(fmt, cols):
        if c == "a":
            row[col] = list(vals[k:k + 32])
            k += 32
            continue
        v = vals[k]
        k += 1
        sc = TYPES[c][1]
        row[col] = _s(v) if sc is None else (v * sc if sc != 1 else v)
    return row


def read_text(text: str) -> dict:
    """The same from a text log: 'FMT, type, len, NAME, fmt, cols...' lines, then 'NAME, v1, v2, ...' lines."""
    fmts, out = {}, {n: [] for n in WANTED}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        if parts[0] == "FMT" and len(parts) >= 6:
            fmts[parts[3]] = (parts[4], parts[5:])
        elif parts[0] in out and parts[0] in fmts:
            fmt, cols = fmts[parts[0]]
            row = {}
            for c, col, v in zip(fmt, cols, parts[1:]):
                try:
                    row[col] = float(v) if c not in "nNZ" else v
                except ValueError:
                    row[col] = v
            out[parts[0]].append(row)
    return out


def read_log(path: Path) -> dict:
    data = path.read_bytes()
    return read_bin(data) if data[:2] == HEAD else read_text(data.decode("utf-8", "replace"))


# --- the numbers -----------------------------------------------------------------------------------------------------
def _instance0(rows: list) -> list:
    key = next((k for k in ("Inst", "Instance", "I") if rows and k in rows[0]), None)
    return [r for r in rows if key is None or int(r[key]) == 0]


def _t(r) -> float:
    return float(r.get("TimeUS", 0)) / 1e6


def mode_spans(log: dict) -> list:
    """[(t0, t1, mode_number)] from the MODE messages; the last span runs to the end of the log."""
    ms = [(_t(r), int(r.get("Mode", r.get("ModeNum", -1)))) for r in log["MODE"]]
    t_end = max([_t(r) for k in WANTED for r in log[k]] or [0.0])
    return [(t0, ms[i + 1][0] if i + 1 < len(ms) else t_end, m) for i, (t0, m) in enumerate(ms)]


def taxi_max_speed(log: dict, window_s: float = 2.0) -> float | None:
    gps = [(_t(r), float(r["Spd"])) for r in _instance0(log["GPS"]) if "Spd" in r]
    manual = [(a, b) for a, b, m in mode_spans(log) if m == 0]
    best = None
    for a, b in manual:
        pts = [(t, v) for t, v in gps if a <= t <= b]
        for i, (t, _v) in enumerate(pts):
            win = [v for tt, v in pts[i:] if tt <= t + window_s]
            if pts[-1][0] - t >= window_s * 0.9 and win:
                med = sorted(win)[len(win) // 2]          # a median: a GPS glitch shorter than 1 s does not count
                best = med if best is None else max(best, med)
    return best


def takeoff_peaks(log: dict) -> list:
    bat = [(_t(r), float(r["Curr"])) for r in _instance0(log["BAT"]) if "Curr" in r]
    out = []
    for a, b, m in mode_spans(log):
        if m in TAKEOFF_MODES:
            cur = [c for t, c in bat if a <= t <= b]
            if cur:
                out.append({"t0_s": round(a, 1), "mode": PLANE_MODES.get(m, str(m)), "peak_a": round(max(cur), 1)})
    return out


def params(log: dict) -> dict:
    return {str(r.get("Name", "")).strip(): float(r.get("Value", 0)) for r in log["PARM"] if r.get("Name")}


def _interp(ts: list, vs: list, t: float) -> float:
    """Linear interpolation in a sorted series (held flat outside it)."""
    if not ts:
        return 0.0
    if t <= ts[0]:
        return vs[0]
    if t >= ts[-1]:
        return vs[-1]
    lo, hi = 0, len(ts) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ts[mid] <= t:
            lo = mid
        else:
            hi = mid
    f = (t - ts[lo]) / (ts[hi] - ts[lo]) if ts[hi] > ts[lo] else 0.0
    return vs[lo] + f * (vs[hi] - vs[lo])


def _corr(a: list, b: list) -> float:
    n = len(a)
    if n < 10:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return 0.0 if sa < 1e-9 or sb < 1e-9 else sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def replay(log: dict, hz: float = 50.0) -> dict:
    """Sticks (twin convention: roll/yaw -1..1 right positive, pitch -1 = back stick, thr 0..1), mode, measured
    attitude and current at hz, for the twin's log replay."""
    p = params(log)
    rc = log["RCIN"]
    if not rc:
        raise ValueError("no RCIN records: turn on RC logging (LOG_BITMASK) before G7")
    chan = {k: int(p.get(f"RCMAP_{k.upper()}", d)) for k, d in (("roll", 1), ("pitch", 2), ("throttle", 3), ("yaw", 4))}

    def norm(k, pwm, centred):
        n = chan[k]
        lo, tr, hi = p.get(f"RC{n}_MIN", 1100.0), p.get(f"RC{n}_TRIM", 1500.0), p.get(f"RC{n}_MAX", 1900.0)
        if not centred:
            return min(1.0, max(0.0, (pwm - lo) / max(hi - lo, 1.0)))
        v = (pwm - tr) / max(hi - tr, 1.0) if pwm >= tr else (pwm - tr) / max(tr - lo, 1.0)
        return min(1.0, max(-1.0, v))

    t_rc = [_t(r) for r in rc]
    raw = {k: [float(r.get(f"C{chan[k]}", 1500)) for r in rc] for k in chan}
    att = log["ATT"]
    t_att = [_t(r) for r in att]
    a = {k: [float(r.get(k, 0)) for r in att] for k in ("Roll", "Pitch", "DesRoll", "DesPitch")}
    bat = _instance0(log["BAT"])
    t_bat, cur = [_t(r) for r in bat], [float(r.get("Curr", 0)) for r in bat]
    spans = mode_spans(log)
    t0, t1 = t_rc[0], t_rc[-1]
    n = int((t1 - t0) * hz) + 1
    ts = [t0 + i / hz for i in range(n)]
    st = {k: [norm(k, _interp(t_rc, raw[k], t), k != "throttle") for t in ts] for k in chan}
    signs, notes = {}, []
    for k, des, want in (("roll", "DesRoll", 1), ("pitch", "DesPitch", -1)):
        c = _corr(st[k], [_interp(t_att, a[des], t) for t in ts]) if att else 0.0
        if abs(c) < 0.3:
            signs[k] = 1
            notes.append(f"{k}: stick and ATT.{des} barely correlate ({c:+.2f}); sign left as logged (UNCONFIRMED)")
        else:
            signs[k] = 1 if c * want > 0 else -1
            if signs[k] < 0:
                notes.append(f"{k}: stick flipped to match ATT.{des} (correlation {c:+.2f})")

    def mode_at(t):
        m = next((m for a_, b_, m in spans if a_ <= t < b_), spans[-1][2] if spans else 0)
        return PLANE_MODES.get(m, str(m))

    rows = [{"t": round(t - t0, 3), "roll_cmd": round(signs["roll"] * st["roll"][i], 4),
             "pitch_cmd": round(signs["pitch"] * st["pitch"][i], 4), "yaw_cmd": round(st["yaw"][i], 4),
             "thr": round(st["throttle"][i], 4), "mode": mode_at(t),
             "roll": round(_interp(t_att, a["Roll"], t), 2) if att else None,
             "pitch": round(_interp(t_att, a["Pitch"], t), 2) if att else None,
             "curr": round(_interp(t_bat, cur, t), 2) if bat else None} for i, t in enumerate(ts)]
    return {"kind": "ryujin-v21-replay", "version": 1, "hz": hz, "channels": chan, "signs": signs, "notes": notes,
            "start_mode": rows[0]["mode"] if rows else "MANUAL", "rows": rows}


def summarise(log: dict) -> dict:
    peaks = takeoff_peaks(log)
    v = taxi_max_speed(log)
    return {"counts": {k: len(v_) for k, v_ in log.items()},
            "modes": [(round(a, 1), PLANE_MODES.get(m, str(m))) for a, _b, m in mode_spans(log)],
            "taxi_max_speed_m_s": None if v is None else round(v, 2), "takeoff_attempts": peaks,
            "water_takeoff_peak_a": max((p["peak_a"] for p in peaks), default=None)}


def write_measurements(s: dict, force: bool = False) -> list:
    m = json.loads(MEAS.read_text())
    done = []
    for stage, key in (("W6", "taxi_max_speed_m_s"), ("W7", "water_takeoff_peak_a")):
        if s[key] is not None and (m[stage].get(key) is None or force):
            m[stage][key] = s[key]
            done.append(f"{stage}.{key} = {s[key]}")
    MEAS.write_text(json.dumps(m, indent=1) + "\n")
    return done


# --- self-test: logs written here in both formats ------------------------------------------------------------------
def _fmt_record(t: int, name: str, fmt: str, cols: str) -> bytes:
    ln = 3 + struct.calcsize("<" + "".join(TYPES[c][0] for c in fmt))
    return HEAD + bytes([FMT_ID]) + struct.pack("<BB4s16s64s", t, ln, name.encode(), fmt.encode(), cols.encode())


def _synthetic():
    """A 60 s log: MANUAL taxi to 1.4 m/s (one 0.3 s GPS spike to 9 m/s), then two QHOVER attempts peaking 58 A and
    71 A, a second battery instance at 99 A that must be ignored, and some junk bytes to resync over."""
    defs = {"MODE": (200, "QMBB", "TimeUS,Mode,ModeNum,Rsn"), "BAT": (201, "QBfffcf", "TimeUS,Inst,Volt,VoltR,Curr,CurrTot,EnrgTot"),
            "GPS": (202, "QBBIHBcLLeffff", "TimeUS,I,Status,GMS,GWk,NSats,HDop,Lat,Lng,Alt,Spd,GCrs,VZ,Yaw"),
            "RCIN": (203, "QHHHH", "TimeUS,C1,C2,C3,C4"), "ATT": (204, "QccccCC", "TimeUS,DesRoll,Roll,DesPitch,Pitch,DesYaw,Yaw"),
            "PARM": (205, "QNf", "TimeUS,Name,Value")}
    recs = [(0.0, "MODE", (0, 0, 0))]
    for k in range(0, 600):
        t = k * 0.1
        v = 1.4 * min(1.0, t / 10) if t < 30 else 0.2
        if 12.0 <= t < 12.3:
            v = 9.0
        recs.append((t, "GPS", (0, 3, 0, 0, 12, 0.8, -33.7, 151.0, 1.0, v, 0.0, 0.0, 0.0)))
        amps = 4.0 + (54.0 * math.exp(-((t - 33) ** 2)) if 32 < t < 40 else 0) + (67.0 * math.exp(-((t - 47) ** 2)) if 45 < t < 55 else 0)
        recs.append((t, "BAT", (0, 15.6, 15.8, amps, 100.0, 0.0)))
        recs.append((t, "BAT", (1, 15.6, 15.8, 99.0, 100.0, 0.0)))
        # sticks: roll a 0.2 Hz sine; this radio's pitch channel is reversed (RC2 high = back stick = nose up)
        rs, ps = math.sin(2 * math.pi * 0.2 * t), 0.5 * math.sin(2 * math.pi * 0.13 * t)
        recs.append((t, "RCIN", (int(1500 + 400 * rs), int(1500 + 400 * ps), int(1100 + 800 * (0.6 if 32 < t < 40 else 0.2)), 1500)))
        recs.append((t, "ATT", (30 * rs, 28 * rs, 15 * ps, 14 * ps, 0.0, 0.0)))
    recs += [(0.0, "PARM", ("RC1_MIN", 1100.0)), (0.0, "PARM", ("RC1_MAX", 1900.0)), (0.0, "PARM", ("RC2_MIN", 1100.0)),
             (0.0, "PARM", ("RC2_MAX", 1900.0)), (0.0, "PARM", ("RC3_MIN", 1100.0)), (0.0, "PARM", ("RC3_MAX", 1900.0))]
    recs += [(32.0, "MODE", (18, 18, 0)), (40.0, "MODE", (0, 0, 0)), (45.0, "MODE", (18, 18, 0)), (55.0, "MODE", (0, 0, 0))]
    recs.sort(key=lambda r: r[0])
    out = b"".join(_fmt_record(i, n, f, c) for n, (i, f, c) in defs.items()) + b"\x00\x13junk"
    text = ["FMT, 128, 89, FMT, BBnNZ, Type,Length,Name,Format,Columns"] + [f"FMT, {i}, 0, {n}, {f}, {c}" for n, (i, f, c) in defs.items()]
    for t, n, vals in recs:
        i, f, _c = defs[n]
        packed = []
        for c, v in zip(f, (int(t * 1e6),) + vals):
            code, sc = TYPES[c]
            if isinstance(v, str):
                packed.append(v.encode())
                continue
            packed.append(int(round(v / sc)) if sc not in (1, None) and code not in ("f", "d") else (int(v) if code not in ("f", "d") else v))
        out += HEAD + bytes([i]) + struct.pack("<" + "".join(TYPES[c][0] for c in f), *packed)
        text.append(", ".join([n] + [str(int(t * 1e6))] + [str(v) for v in vals]))
    return out, "\n".join(text)


def _selftest() -> int:
    b, t = _synthetic()
    fails = []
    for kind, log in (("binary", read_bin(b)), ("text", read_text(t))):
        s = summarise(log)
        if not (1.3 <= (s["taxi_max_speed_m_s"] or 0) <= 1.45):
            fails.append(f"{kind}: taxi speed {s['taxi_max_speed_m_s']} (spike must be averaged out)")
        if [p["peak_a"] for p in s["takeoff_attempts"]] != [58.0, 71.0]:
            fails.append(f"{kind}: take-off peaks {s['takeoff_attempts']}")
        if s["water_takeoff_peak_a"] != 71.0:
            fails.append(f"{kind}: peak {s['water_takeoff_peak_a']}")
        if s["counts"]["MODE"] != 5:
            fails.append(f"{kind}: MODE count {s['counts']['MODE']}")
        rp = replay(log)
        r0 = next(r for r in rp["rows"] if abs(r["t"] - 1.25) < 0.011)       # sin peak of the 0.2 Hz roll stick
        if not (0.95 <= r0["roll_cmd"] <= 1.0 and abs(r0["roll"] - 28.0) < 1.0):
            fails.append(f"{kind}: replay roll {r0}")
        if rp["signs"]["pitch"] != -1 or rp["signs"]["roll"] != 1:
            fails.append(f"{kind}: stick signs {rp['signs']} (pitch is reversed in this log)")
        if {r["mode"] for r in rp["rows"]} != {"MANUAL", "QHOVER"} or abs(len(rp["rows"]) / 50 - 59.9) > 0.1:
            fails.append(f"{kind}: replay modes/length")
    if summarise({k: [] for k in WANTED})["taxi_max_speed_m_s"] is not None:
        fails.append("empty log must give no numbers")
    for f in fails:
        print("FAIL", f)
    print(f"g7_log self-test: {'PASS' if not fails else 'FAIL'}")
    return 1 if fails else 0


def main(argv) -> int:
    if "--selftest" in argv:
        return _selftest()
    files = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--replay")]
    if len(files) != 1:
        print(__doc__)
        return 2
    s = summarise(read_log(Path(files[0])))
    print(f"messages read: {s['counts']}")
    print("modes:", ", ".join(f"{t} s {m}" for t, m in s["modes"]) or "none")
    print(f"W6 taxi_max_speed_m_s: {s['taxi_max_speed_m_s']}")
    for p in s["takeoff_attempts"]:
        print(f"W7 attempt at {p['t0_s']} s ({p['mode']}): peak {p['peak_a']} A")
    print(f"W7 water_takeoff_peak_a: {s['water_takeoff_peak_a']}")
    if "--replay" in argv:
        out = Path(argv[argv.index("--replay") + 1])
        rp = replay(read_log(Path(files[0])))
        out.write_text(json.dumps(rp, separators=(",", ":")))
        print(f"wrote {out} ({len(rp['rows'])} rows at {rp['hz']:.0f} Hz); load it in the V21 twin tab, 'Replay a flight log'")
        for n_ in rp["notes"]:
            print("  note:", n_)
    if "--write" in argv:
        done = write_measurements(s, force="--force" in argv)
        print("wrote " + ("; ".join(done) if done else "nothing (fields already filled; --force to overwrite)") + f" to {MEAS.relative_to(ROOT)}")
        print("then: python3 tools/v21/g7.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
