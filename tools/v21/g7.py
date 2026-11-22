#!/usr/bin/env python3
"""V21 G7: turn test results into gate results (docs/V21_G7_TEST_PROCEDURES.md).

    python3 tools/v21/g7.py                 # reads config/v21_measurements.json, prints every gate
    python3 tools/v21/g7.py --template      # writes the empty template (every field null); never overwrites data
    python3 tools/v21/g7.py --selftest

A field left null is NOT MEASURED, never a pass. Predictions come from analysis/v21_g5.json (ESTIMATE).
Also prints the water-mode wave limit the measured freeboard and heel support, for tools/v21/water.py and RYW_WAVE_MAX.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MEAS = ROOT / "config" / "v21_measurements.json"
sys.path.insert(0, str(HERE))
import water  # noqa: E402

FIELDS = {
    "W0": ["pack_fits", "pods_interchangeable", "tip_gap_mm_min", "bay_drains_s"],
    "W1": ["lift_fan_thrust_g_min", "edf_static_thrust_g", "pack_v_at_hover", "scarfed_pod_thrust_g", "plain_pod_thrust_g"],
    "W2": ["all_up_mass_g", "cg_x_mm"],
    "W3": ["leak_ingress_g_30min", "leak_sensor_trips", "leak_sensor_dry_v", "leak_sensor_open_trips", "float_trim_deg", "freeboard_fan_mm", "freeboard_intake_mm",
           "freeboard_nozzle_mm", "heel_fan_wet_deg", "rights_from_20deg"],
    "W4": ["bench_scripts_load", "bench_arming_refused", "bench_taxi_cap", "bench_vtol_refused", "bench_vanes",
           "bench_likely_flying_false"],
    "W5": ["spray_hull_water_g", "spray_motor_events", "spray_plume_height_m"],
    "W6": ["bollard_pull_g", "taxi_max_speed_m_s", "taxi_turn_ok", "taxi_hull_water_g"],
    "W7": ["water_takeoffs_ok", "water_takeoff_peak_a"],
}
SPLASH_KEEP_MM = 5.0
HEEL_PREDICTED_DEG = water.HEEL_FAN_WET_DEG    # G9 roll model, plain exits
HEEL_PREDICTED_SCARFED_DEG = water.HEEL_FAN_WET_SCARFED_DEG    # G10 option B
_LUA = (ROOT / "config" / "ardupilot" / "scripts" / "ryujin_water.lua").read_text()
LEAK_VLO, LEAK_VHI = (float(re.search(rf'"{n}", ([-0-9.]+)\)', _LUA).group(1)) for n in ("LEAK_VLO", "LEAK_VHI"))


def predictions() -> dict:
    s = json.loads((ROOT / "analysis" / "v21_g5.json").read_text())["sizing"]
    taxi = {round(t["V"], 1): t["total_n"] for t in s["taxi"]}
    return {"mass_g": s["mass_g"], "cg_x_mm": s["cg_m"][0] * 1000 - s["cg_offset_mm"], "taxi_1p5_n": taxi[1.5]}


def band(v, pass_if, fix_if=None):
    if v is None:
        return "NOT MEASURED"
    if pass_if(v):
        return "PASS"
    return "FIX" if fix_if and fix_if(v) else "STOP"


def scarf_status(m: dict, need_fan: float) -> str:
    """G10 option B: the 5 mm outboard exit scarf. PASS: it costs no thrust that matters, the wave limit may use the
    scarfed heel. FIX: fit plain (unscarfed) pods and keep the plain-exit wave limit. Never a STOP on its own."""
    sc, pl = m.get("scarfed_pod_thrust_g"), m.get("plain_pod_thrust_g")
    if sc is None or pl is None:
        return "NOT MEASURED"
    return "PASS" if sc >= need_fan and sc >= 0.99 * pl else "FIX"


def gates(m: dict, pred: dict) -> list:
    """[(stage, gate, value, status)]"""
    g = lambda k: m.get(k)  # noqa: E731
    mass = g("all_up_mass_g") or pred["mass_g"]
    need_fan = 1.9 * mass / 4
    taxi_g = 1.25 * pred["taxi_1p5_n"] / 9.80665 * 1000
    is_true = lambda v: v is True  # noqa: E731
    heel_want = HEEL_PREDICTED_SCARFED_DEG if scarf_status(m, need_fan) == "PASS" else HEEL_PREDICTED_DEG
    out = [
        ("W0", "pack fits through the hatch", g("pack_fits"), band(g("pack_fits"), is_true)),
        ("W0", "4 fan pods interchangeable", g("pods_interchangeable"), band(g("pods_interchangeable"), is_true)),
        ("W0", "tip gap 1.5-3.0 mm", g("tip_gap_mm_min"), band(g("tip_gap_mm_min"), lambda v: 1.5 <= v <= 3.0, lambda v: v >= 1.0)),
        ("W0", "bay drains < 10 s", g("bay_drains_s"), band(g("bay_drains_s"), lambda v: v < 10, lambda v: True)),
        ("W1", f"lift fan >= {need_fan:.0f} g (1.9 x mass / 4)", g("lift_fan_thrust_g_min"),
         band(g("lift_fan_thrust_g_min"), lambda v: v >= need_fan, lambda v: v >= 0.95 * need_fan)),
        ("W1", f"EDF >= {taxi_g:.0f} g (1.25 x drag at 1.5 m/s)", g("edf_static_thrust_g"),
         band(g("edf_static_thrust_g"), lambda v: v >= taxi_g, lambda v: v >= 0.8 * taxi_g)),
        ("W1", "pack >= 14.0 V at hover current", g("pack_v_at_hover"), band(g("pack_v_at_hover"), lambda v: v >= 14.0, lambda v: v >= 13.2)),
        ("W1", f"scarfed pod >= {need_fan:.0f} g and >= 99 % of a plain pod", g("scarfed_pod_thrust_g"), scarf_status(m, need_fan)),
        ("W2", f"mass <= {1.03 * pred['mass_g']:.0f} g", g("all_up_mass_g"),
         band(g("all_up_mass_g"), lambda v: v <= 1.03 * pred["mass_g"], lambda v: v <= 1.08 * pred["mass_g"])),
        ("W2", f"CG x {pred['cg_x_mm']:.0f} +/- 3 mm", g("cg_x_mm"),
         band(g("cg_x_mm"), lambda v: abs(v - pred["cg_x_mm"]) <= 3, lambda v: abs(v - pred["cg_x_mm"]) <= 6)),
        ("W3", "leak <= 1 g in 30 min", g("leak_ingress_g_30min"), band(g("leak_ingress_g_30min"), lambda v: v <= 1, lambda v: v <= 5)),
        ("W3", "leak sensor trips", g("leak_sensor_trips"), band(g("leak_sensor_trips"), is_true)),
        ("W3", f"leak sensor dry {LEAK_VLO}-{LEAK_VHI} V", g("leak_sensor_dry_v"),
         band(g("leak_sensor_dry_v"), lambda v: LEAK_VLO + 0.1 <= v <= LEAK_VHI - 0.05, lambda v: LEAK_VLO <= v <= LEAK_VHI)),
        ("W3", "leak sensor unplugged -> NO-GO", g("leak_sensor_open_trips"), band(g("leak_sensor_open_trips"), is_true)),
        ("W3", "float trim -2.0..+1.0 deg", g("float_trim_deg"),
         band(g("float_trim_deg"), lambda v: -2.0 <= v <= 1.0, lambda v: -3.0 <= v <= 2.0)),
        *[("W3", f"freeboard {k} >= 20 mm", g(f"freeboard_{k}_mm"),
           band(g(f"freeboard_{k}_mm"), lambda v: v >= 20, lambda v: v >= 15)) for k in ("fan", "intake", "nozzle")],
        ("W3", f"heel to wet a fan exit >= {heel_want} deg", g("heel_fan_wet_deg"),
         band(g("heel_fan_wet_deg"), lambda v: v >= heel_want, lambda v: v >= 3)),
        ("W3", "rights itself from 20 deg", g("rights_from_20deg"), band(g("rights_from_20deg"), is_true)),
        *[("W4", k.replace("bench_", "bench: ").replace("_", " "), g(k), band(g(k), is_true)) for k in FIELDS["W4"]],
        ("W5", "no water in the hull after spray hover", g("spray_hull_water_g"), band(g("spray_hull_water_g"), lambda v: v == 0, lambda v: v <= 1)),
        ("W5", "no motor desyncs / spikes", g("spray_motor_events"), band(g("spray_motor_events"), lambda v: v == 0)),
        ("W6", f"bollard pull >= {taxi_g:.0f} g", g("bollard_pull_g"), band(g("bollard_pull_g"), lambda v: v >= taxi_g, lambda v: v >= 0.8 * taxi_g)),
        ("W6", "taxi >= 1.0 m/s", g("taxi_max_speed_m_s"), band(g("taxi_max_speed_m_s"), lambda v: v >= 1.0, lambda v: v >= 0.6)),
        ("W6", "turns both ways", g("taxi_turn_ok"), band(g("taxi_turn_ok"), is_true)),
        ("W6", "no water in the hull after taxi", g("taxi_hull_water_g"), band(g("taxi_hull_water_g"), lambda v: v == 0, lambda v: v <= 1)),
        ("W7", "3 of 3 tethered water take-offs", g("water_takeoffs_ok"), band(g("water_takeoffs_ok"), lambda v: v >= 3, lambda v: v == 2)),
        ("W7", "lift-off peak <= 76 A", g("water_takeoff_peak_a"), band(g("water_takeoff_peak_a"), lambda v: v <= 76)),
    ]
    return out


def wave_limit_mm(m: dict) -> float | None:
    """Wave height (mm) the measured margins support: water.wave_limit_m() with the lowest measured freeboard and the
    measured heel to wet a fan exit (the G9 prediction until W3 measures it). None until the freeboards are measured."""
    fbs = [m.get(f"freeboard_{k}_mm") for k in ("fan", "intake", "nozzle")]
    if any(v is None for v in fbs):
        return None
    heel = m.get("heel_fan_wet_deg")
    return 1000 * water.wave_limit_m(min(fbs) / 1000, HEEL_PREDICTED_DEG if heel is None else heel)


def report(m: dict, pred: dict) -> int:
    rows = gates(m, pred)
    stop = False
    for stage, name, v, st in rows:
        print(f"  {stage}  {st:12s} {name}: {'-' if v is None else v}")
        stop |= st in ("FIX", "STOP")
    first_open = next((s for s, _n, _v, st in rows if st != "PASS"), None)
    print(f"next stage to run or fix: {first_open or 'none - every G7 gate passed'}")
    w = wave_limit_mm(m)
    now = water.MAX_WAVE_HEIGHT_M * 1000
    scarf_ok = scarf_status(m, 1.9 * (m.get("all_up_mass_g") or pred["mass_g"]) / 4) == "PASS"
    if w is None:
        print(f"wave limit: keep the ESTIMATE {now:.0f} mm until W3 freeboards are measured")
    elif w < now:
        print(f"wave limit the measured margins support: {w:.0f} mm (now {now:.0f} mm; LOWER water.py MAX_WAVE_HEIGHT_M and RYW_WAVE_MAX to it)")
    elif w > now and scarf_ok:
        print(f"wave limit the measured margins support: {w:.0f} mm (now {now:.0f} mm; the W1 scarf check passed, so it may go up)")
    elif w > now:
        print(f"wave limit: keep {now:.0f} mm (W3 supports {w:.0f} mm, but it may go up only after the W1 scarfed-pod check passes)")
    else:
        print(f"wave limit the measured margins support: {w:.0f} mm (now {now:.0f} mm; no change needed)")
    return 1 if stop else 0


def _selftest() -> int:
    pred = {"mass_g": 2000.0, "cg_x_mm": 346.0, "taxi_1p5_n": 2.53}
    good = {"pack_fits": True, "pods_interchangeable": True, "tip_gap_mm_min": 2.1, "bay_drains_s": 4,
            "lift_fan_thrust_g_min": 980, "edf_static_thrust_g": 1100, "pack_v_at_hover": 14.6,
            "scarfed_pod_thrust_g": 985, "plain_pod_thrust_g": 990, "all_up_mass_g": 2010,
            "cg_x_mm": 347, "leak_ingress_g_30min": 0.2, "leak_sensor_trips": True, "leak_sensor_dry_v": 3.0,
            "leak_sensor_open_trips": True, "float_trim_deg": -0.5,
            "freeboard_fan_mm": 22, "freeboard_intake_mm": 23, "freeboard_nozzle_mm": 27, "heel_fan_wet_deg": 5.5,
            "rights_from_20deg": True, **{k: True for k in FIELDS["W4"]}, "spray_hull_water_g": 0, "spray_motor_events": 0,
            "spray_plume_height_m": 0.4, "bollard_pull_g": 400, "taxi_max_speed_m_s": 1.2, "taxi_turn_ok": True,
            "taxi_hull_water_g": 0, "water_takeoffs_ok": 3, "water_takeoff_peak_a": 60}
    fails = []
    st = {n: s for _g, n, _v, s in gates(good, pred)}
    if any(s != "PASS" for s in st.values()):
        fails.append(f"all-good set: {[n for n, s in st.items() if s != 'PASS']}")
    st = {n: s for _g, n, _v, s in gates({}, pred)}
    if any(s != "NOT MEASURED" for s in st.values()):
        fails.append("empty set must be NOT MEASURED everywhere")
    bad = dict(good, lift_fan_thrust_g_min=940, freeboard_fan_mm=12, leak_sensor_trips=False, cg_x_mm=351)
    st = {n.split(" >=")[0].split(" +/-")[0]: s for _g, n, _v, s in gates(bad, pred)}
    want = {"lift fan": "FIX", "freeboard fan": "STOP", "leak sensor trips": "STOP", f"CG x {346}": "FIX"}
    # scarf: 2 % thrust loss -> FIX (fit plain pods), never STOP
    st2 = {n: s for _g, n, _v, s in gates(dict(good, scarfed_pod_thrust_g=965), pred)}
    if next(v for k, v in st2.items() if k.startswith("scarfed pod")) != "FIX":
        fails.append("scarfed pod 2 % down must be FIX")
    for k, v in want.items():
        if st.get(k) != v:
            fails.append(f"{k}: {st.get(k)} != {v}")
    # good: freeboard 22 mm (crest 34 mm), heel 5.5 deg -> slope 22.2 mm -> 20 mm; heel 4.0 deg -> 13.9 mm -> 10 mm
    if (abs(wave_limit_mm(good) - 20.0) > 1e-6 or abs(wave_limit_mm(dict(good, heel_fan_wet_deg=4.0)) - 10.0) > 1e-6
            or abs(wave_limit_mm(dict(good, heel_fan_wet_deg=None)) - 15.0) > 1e-6 or wave_limit_mm({}) is not None):
        fails.append(f"wave limit {wave_limit_mm(good)}")
    for f in fails:
        print("FAIL", f)
    print(f"g7 self-test: {'PASS' if not fails else 'FAIL'}")
    return 1 if fails else 0


def main(argv) -> int:
    if "--selftest" in argv:
        return _selftest()
    if "--template" in argv:
        if MEAS.exists():
            print(f"{MEAS.relative_to(ROOT)} exists: not overwritten")
            return 0
        tpl = {"_note": "V21 G7 measurements (docs/V21_G7_TEST_PROCEDURES.md). null = not measured. Then: python3 tools/v21/g7.py"}
        tpl.update({st: {k: None for k in ks} for st, ks in FIELDS.items()})
        MEAS.write_text(json.dumps(tpl, indent=1) + "\n")
        print(f"wrote {MEAS.relative_to(ROOT)}")
        return 0
    raw = json.loads(MEAS.read_text()) if MEAS.exists() else {}
    m = {k: v for st in FIELDS for k, v in (raw.get(st) or {}).items()}
    return report(m, predictions())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
