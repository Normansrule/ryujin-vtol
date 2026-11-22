#!/usr/bin/env python3
"""V21 G8: the data the browser digital twin (site/js/twin_core.js) runs on, written to site/data/v21.json.

Everything comes from files already in the repo, so the twin cannot drift from them:
  analysis/v21_g5.json                         mass, thrust/weight, CG, float, roll stability (G5, ESTIMATE)
  config/ardupilot/ryujin_v21_mini_BENCH_ONLY.param   the protection parameters (G8) and limits
  config/ardupilot/scripts/ryujin_*.lua        the RYW_ / RYV_ script defaults
  tools/v21/water.py                           the water gate thresholds
Fan positions are the G4 layout (front row 256 mm, rear row 436 mm from the datum, fan centroid = CG at 346 mm).

    python3 tools/v21/web.py      # writes site/data/v21.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import water  # noqa: E402

PARAM_FILE = ROOT / "config" / "ardupilot" / "ryujin_v21_mini_BENCH_ONLY.param"
SCRIPTS = ROOT / "config" / "ardupilot" / "scripts"
FAN_ROWS_MM = {"front": (256.0, 143.0), "rear": (436.0, 233.0)}     # (x from datum, |y|), G4 layout (variants v20_mini)


def params() -> dict[str, float]:
    kv = re.findall(r"^([A-Z0-9_]+),([-0-9.]+)\s*$", PARAM_FILE.read_text(), re.M)
    return {k: float(v) for k, v in kv}


def script_defaults(name: str, prefix: str) -> dict[str, float]:
    src = (SCRIPTS / name).read_text()
    return {prefix + k: float(v) for k, v in re.findall(r'add_param\(PARAM_KEY,\s*\d+,\s*"([A-Z_]+)",\s*([-0-9.]+)\)', src)}


def page_data() -> dict | None:
    f = ROOT / "analysis" / "v21_g5.json"
    if not f.exists():
        return None
    g = json.loads(f.read_text())
    s = g["sizing"]
    h = s["hydro"]
    cg_x_mm = s["cg_m"][0] * 1000
    fans = []
    for row, (x, y) in FAN_ROWS_MM.items():
        for side, sy in (("R", 1), ("L", -1)):
            fans.append({"name": f"{row}_{side}", "x_m": round((cg_x_mm - x) / 1000, 4), "y_m": round(sy * y / 1000, 4)})
    p = params()
    p.update(script_defaults("ryujin_water.lua", "RYW_"))
    p.update(script_defaults("ryujin_vanes.lua", "RYV_"))
    return {
        "basis": "ESTIMATE: the G5 model and the G8 bench param file. A teaching model, not ArduPilot; nothing flown.",
        "mass_kg": s["mass_g"] / 1000,
        "tw_lift": s["tw"],
        "hover_w": s["hover_w"],
        "hover_min": s["hover_min"],
        "battery_mah": p.get("BATT_CAPACITY", 9000),
        "battery_wh_usable": s["battery_wh_usable"],
        "fans": fans,
        "cg_x_mm": cg_x_mm,
        "airspeeds": s["airspeeds"],
        "stall_ms": s.get("stall_ms"),            # level 1 g stall from the sizing (ESTIMATE); AIRSPEED_MIN = ceil(1.35 x it)
        "static_margin_pct": s["sm_pct"],
        "float": {
            "waterline_below_cg_m": round(-(h["waterline_z_at_cg_mm"] - s["cg_m"][2] * 1000) / 1000, 4),
            "trim_deg": h["trim_nose_up_deg"],
            "reserve_pct": h["reserve_sealed_pct"],
            "freeboard_mm": h["freeboard_mm"],
            "gz_mm": [[0, 0.0]] + [[r["heel_deg"], r["gz_mm"]] for r in s["roll"]["rows"]],
            "fan_exit_wet_heel_deg": s["roll"]["downflooding_heel_deg"],
        },
        "water_gate": {"wind_max_m_s": water.MAX_WIND_M_S, "wave_max_m": water.MAX_WAVE_HEIGHT_M, "battery_min_pct": water.MIN_BATTERY_PCT},
        "params": p,
    }


def main() -> int:
    d = page_data()
    if d is None:
        print("web.py: run tools/v21/g5.py first (analysis/v21_g5.json missing)")
        return 1
    out = ROOT / "site" / "data" / "v21.json"
    out.write_text(json.dumps(d, separators=(",", ":"), default=float))
    print("wrote", out.relative_to(ROOT), f"({len(d['params'])} params)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
