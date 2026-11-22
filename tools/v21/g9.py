#!/usr/bin/env python3
"""V21 G9: the open risks from G5-G8, worked through with numbers. Everything is an ESTIMATE until G7 measures it.

  1. Rear fan exit wets at 5 deg of heel: what heels the aircraft (beam wind at the gate limit, a taxi turn, wave
     slope) against its righting curve, and a float-height sweep (floats lowered so they carry some weight at rest).
  2. Nose stretch and pitch stability: the static margin split into wing+tail, fuselage (with the 50 mm stretch) and
     floats, so the stretch's cost is visible.
  3. Water-taxi thrust: hull drag against EDF thrust at the RYW_TAXI_PWM cap and at full throttle.

    python3 tools/v21/g9.py            # ~1-2 min; writes analysis/v21_g9.json
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import g5  # noqa: E402

H, S, GEO, AM, g4 = g5.H, g5.S, g5.GEO, g5.AM, g5.g4
G = 9.81
RHO_AIR = 1.225
S_MINI = 0.1                              # full-scale model metres -> mini metres

PARAM_FILE = ROOT / "config" / "ardupilot" / "ryujin_v21_mini_BENCH_ONLY.param"
WATER_LUA = ROOT / "config" / "ardupilot" / "scripts" / "ryujin_water.lua"


def lua_default(name: str) -> float:
    m = re.search(rf'add_param\(PARAM_KEY,\s*\d+,\s*"{name}",\s*([-0-9.]+)\)', WATER_LUA.read_text())
    return float(m.group(1))


# ---------------------------------------------------------------------------------------------------------------
# 1. heel

def gz_curve(oml, mass_kg, cg, angles) -> dict:
    return g5.roll_stability(oml, mass_kg, cg, angles=angles)


def flood_heel(rows) -> float | None:
    """Heel (deg) where the lowest low-side fan exit reaches still water, interpolated between rows."""
    prev = None
    for r in rows:
        if "lowest_fan_exit_mm" not in r:
            continue
        if prev and prev["lowest_fan_exit_mm"] > 0 >= r["lowest_fan_exit_mm"]:
            a, b = prev["lowest_fan_exit_mm"], r["lowest_fan_exit_mm"]
            return prev["heel_deg"] + (r["heel_deg"] - prev["heel_deg"]) * a / (a - b)
        prev = r
    return None


def heel_for_moment(rows, mass_kg, m_heel) -> float | None:
    """Equilibrium heel (deg) under a steady heeling moment (N m): where m g GZ(heel) = m_heel."""
    pts = [(0.0, 0.0)] + [(r["heel_deg"], mass_kg * G * r["gz_mm"] / 1000) for r in rows if "gz_mm" in r]
    for (a0, m0), (a1, m1) in zip(pts, pts[1:]):
        if m0 <= m_heel <= m1:
            return a0 + (a1 - a0) * (m_heel - m0) / (m1 - m0) if m1 > m0 else a0
    return None


def heeling_cases(oml, mass_kg) -> dict:
    """Side (x-z) silhouette of the whole aircraft: area (mini m²) and the height of its centroid (full-scale model z).
    ESTIMATE: the wind drag on it uses a bluff-body Cd."""
    import trimesh
    from trimesh.path.polygons import projected
    from shapely.ops import unary_union
    meshes = [m for _n, m, layer in oml if layer in ("skin", "controls")]
    allm = trimesh.util.concatenate(meshes)
    polys = [projected(m, normal=[0, 1, 0], ignore_sign=True) for m in meshes]
    sil = unary_union([p for p in polys if p is not None])
    # projected() returns coordinates in the plane's own 2D frame, with the axes in any order and either sign. Find the
    # 2D axis (and sign) whose range matches the model's z range, then read the centroid's z off it.
    zlo, zhi = float(allm.bounds[0][2]), float(allm.bounds[1][2])
    b = sil.bounds                                                   # (min0, min1, max0, max1)
    cands = []
    for ax in (0, 1):
        lo, hi, cen = b[ax], b[ax + 2], (sil.centroid.x, sil.centroid.y)[ax]
        cands.append((abs(lo - zlo) + abs(hi - zhi), cen))           # same sign
        cands.append((abs(-hi - zlo) + abs(-lo - zhi), -cen))        # flipped
    err, zc = min(cands)
    assert err < 0.05 * (zhi - zlo), f"could not match the side view to z (error {err:.3f})"
    return {"side_area_m2": float(sil.area) * S_MINI ** 2, "centroid_z_full": float(zc)}


def heel_study(oml, c) -> dict:
    mass = c["mass_g"] / 1000
    cg = c["cg_m"]
    angles = (1, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30)
    base = gz_curve(oml, mass, cg, angles)
    hc = heeling_cases(oml, mass)
    h = c["hydro"]
    z_wl = h["waterline_z_at_cg_mm"] / 1000                      # mini m, model frame
    arm_wind = hc["centroid_z_full"] * S_MINI - z_wl               # centre of side area above the waterline
    wind = lua_default("WIND_MAX")
    f_wind = 0.5 * RHO_AIR * wind ** 2 * hc["side_area_m2"] * 1.1   # Cd 1.1 for a bluff side view (ESTIMATE)
    # the water resists the drift at about half the draft below the waterline: the lever is from there
    draft = 0.055
    m_wind = f_wind * (arm_wind + draft / 2)
    # a taxi turn at the cap speed: 1.5 m/s on a 3 m radius (the W6 steering test), CG above the centre of resistance
    v_t, r_t = 1.5, 3.0
    m_turn = mass * v_t ** 2 / r_t * ((cg[2] - z_wl) + draft / 2)
    rows = base["rows"]
    cases = {}
    for name, m in (("beam wind at RYW_WIND_MAX", m_wind), ("taxi turn 1.5 m/s, 3 m radius", m_turn), ("both together", m_wind + m_turn)):
        cases[name] = {"moment_nm": m, "heel_deg": heel_for_moment(rows, mass, m)}
    flood = flood_heel(rows)
    # waves: a hull short against the wave follows the slope; a 30 mm wave of 1.0 m length slopes up to pi H / L
    wave = lua_default("WAVE_MAX") / 1000
    slope_deg = math.degrees(math.atan(math.pi * wave / 1.0))
    exit_fb = min(h["freeboard_mm"].values())
    return {
        "rows": rows, "flood_heel_deg": flood,
        "side_area_m2": hc["side_area_m2"], "wind_lever_m": arm_wind + draft / 2, "wind_force_n": f_wind,
        "cases": cases,
        "wave_max_slope_deg": slope_deg,
        "wave_crest_mm": wave / 2 * 1000, "fan_exit_freeboard_mm": h["freeboard_mm"].get("lift-fan exits (bottom louvres)", exit_fb),
    }


def float_sweep(drops_full=(0.0, 0.05, 0.10, 0.15)) -> list:
    """Lower the floats (full-scale m; 0.05 = 5 mm on the mini) so they carry some of the weight at rest, re-float the
    aircraft and re-run the roll curve. Longer struts, same floats."""
    out = []
    base_gap = g5.FLOAT_GAP
    for d in drops_full:
        g5.FLOAT_GAP = base_gap + d
        S._OML = None
        c = g5.size_and_float()
        oml = S.oml()
        rows = gz_curve(oml, c["mass_g"] / 1000, c["cg_m"], (1, 2, 3, 4, 5, 6, 8, 10))["rows"]
        h = c["hydro"]
        out.append({"float_drop_mm_mini": d * 100, "strut_mm_mini": (base_gap + d) * 100,
                    "flood_heel_deg": flood_heel(rows), "gz_2deg_mm": next(r["gz_mm"] for r in rows if r["heel_deg"] == 2),
                    "freeboard_mm": h["freeboard_mm"], "trim_deg": h["trim_nose_up_deg"],
                    "taxi_1p5_n": next((t["total_n"] for t in h["taxi"] if abs(t["V"] - 1.5) < 1e-6), None),
                    "sm_pct": c["sm_pct"], "mass_g": c["mass_g"]})
    g5.FLOAT_GAP = base_gap
    S._OML = None
    return out


# ---------------------------------------------------------------------------------------------------------------
# 2. pitch stability split

def sm_breakdown(c) -> dict:
    import aero as A
    keep_extra = list(A.EXTRA_BODIES)
    keep_stretch = g5.NOSE_STRETCH
    out = {"with_everything_pct": c["sm_pct"]}
    try:
        A.EXTRA_BODIES[:] = []
        S._AERO.clear()
        out["without_floats_pct"] = AM.size_case(**g4.LOCKED, gear=g4.RECOMMENDED["gear"])["sm_pct"]
    finally:
        A.EXTRA_BODIES[:] = keep_extra
        S._AERO.clear()
    out["floats_cost_pct"] = out["without_floats_pct"] - c["sm_pct"]
    out["nose_stretch_m_full"] = keep_stretch
    return out


# ---------------------------------------------------------------------------------------------------------------
# 3. taxi thrust

def taxi_study(c) -> dict:
    p = dict(re.findall(r"^([A-Z0-9_]+),([-0-9.]+)\s*$", PARAM_FILE.read_text(), re.M))
    cap_pwm = lua_default("TAXI_PWM")
    thr = (cap_pwm - 1000) / 1000
    t_static = g4.EDF_STATIC_N
    # EDF static thrust goes roughly as throttle^2 (thrust ~ rpm^2, rpm ~ throttle on a fixed-pitch fan): ESTIMATE
    t_cap = t_static * thr ** 2
    rows = [{"V": t["V"], "drag_n": t["total_n"], "full_margin": t_static / t["total_n"] if t["total_n"] else None,
             "cap_margin": t_cap / t["total_n"] if t["total_n"] else None} for t in c["hydro"]["taxi"]]
    # speed the cap holds: where drag = capped thrust (linear between the table rows)
    v_cap = None
    for a, b in zip(rows, rows[1:]):
        if a["drag_n"] <= t_cap <= b["drag_n"]:
            v_cap = a["V"] + (b["V"] - a["V"]) * (t_cap - a["drag_n"]) / (b["drag_n"] - a["drag_n"])
    return {"edf_static_n": t_static, "taxi_pwm": cap_pwm, "throttle_at_cap": thr, "thrust_at_cap_n": t_cap,
            "speed_at_cap_m_s": v_cap, "rows": rows, "thr_slewrate": float(p.get("THR_SLEWRATE", 0))}


def main(argv) -> int:
    t0 = time.time()
    GEO.set_variant("mini")
    g5.apply_shape()
    c = g5.size_and_float()
    oml = S.oml()
    print(f"G5 baseline: {c['mass_g']:.0f} g, SM {c['sm_pct']:.1f} %")
    heel = heel_study(oml, c)
    print(f"1. fan exit reaches still water at {heel['flood_heel_deg']:.1f} deg of heel")
    for k, v in heel["cases"].items():
        print(f"   {k}: {v['moment_nm']:.3f} N m -> {v['heel_deg']:.2f} deg" if v["heel_deg"] is not None else f"   {k}: beyond the table")
    print(f"   waves at RYW_WAVE_MAX: crest {heel['wave_crest_mm']:.0f} mm vs fan-exit freeboard {heel['fan_exit_freeboard_mm']:.1f} mm; slope up to {heel['wave_max_slope_deg']:.1f} deg")
    sweep = float_sweep() if "--no-sweep" not in argv else []
    for r in sweep:
        print(f"   floats lowered {r['float_drop_mm_mini']:.0f} mm: flood heel {r['flood_heel_deg']}, GZ@2 {r['gz_2deg_mm']:.1f} mm, "
              f"freeboard {', '.join(f'{v:.1f}' for v in r['freeboard_mm'].values())}, trim {r['trim_deg']:+.2f}, taxi@1.5 {r['taxi_1p5_n']:.2f} N")
    # back to the baseline for the rest
    c = g5.size_and_float()
    sm = sm_breakdown(c)
    print(f"2. static margin {sm['with_everything_pct']:.2f} % (nose stretch in); floats cost {sm['floats_cost_pct']:.2f} points")
    taxi = taxi_study(c)
    print(f"3. EDF at RYW_TAXI_PWM {taxi['taxi_pwm']:.0f}: about {taxi['thrust_at_cap_n']:.2f} N -> holds about {taxi['speed_at_cap_m_s']} m/s")
    for r in taxi["rows"]:
        print(f"   {r['V']:.1f} m/s drag {r['drag_n']:.2f} N: full EDF x{r['full_margin']:.2f}, capped x{r['cap_margin']:.2f}")
    out = {"basis": "ESTIMATE: tools/v21/g9.py on the G5 model; nothing floated or tested", "heel": heel, "float_sweep": sweep,
           "pitch": sm, "taxi": taxi}
    (ROOT / "analysis" / "v21_g9.json").write_text(json.dumps(out, indent=1, default=float))
    print(f"wrote analysis/v21_g9.json ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
