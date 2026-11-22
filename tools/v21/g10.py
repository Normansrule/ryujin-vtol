#!/usr/bin/env python3
"""V21 G10: design study for the G9 wave-margin FLAG, plus the thinnest remaining margin (lift T/W). ESTIMATE.

G9 found a rear lift-fan exit reaches still water at 4.4 deg of heel, so the wave limit had to drop to 15 mm. Two ways
to buy the margin back are modelled here. Neither changes the locked G5 geometry: the study sets the parameters,
re-floats the model and puts them back.

  A. Wider float track: the floats move outboard along the wing (FLOAT_Y), same floats and struts.
  B. Raised rear fan exits: the shoulder bottom around the two rear ducts is raised (a shallower rear duct).

Then the lift T/W margin: the G5 build is 6 g under the 1.9 T/W mass limit, and the mass items that could pay for it.

    python3 tools/v21/g10.py            # ~8 min; writes analysis/v21_g10.json
    python3 tools/v21/g10.py A          # re-run only option A, keep the rest from the last run
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import g5  # noqa: E402
import g9  # noqa: E402
import water  # noqa: E402

H, S, GEO, AM, g4 = g5.H, g5.S, g5.GEO, g5.AM, g5.g4
G = 9.81
S_MINI = 0.1
ANGLES = (0, 1, 2, 3, 4, 5, 6, 8, 10, 15)


def roll_rows(oml, mass_kg: float, cg_m_mini, exit_dz: dict | None = None, angles=ANGLES) -> list:
    """g5.roll_stability with each fan row's exit raised by exit_dz[row] (full-scale m). Returns the rows, plus the
    lowest exit per row so the limiting row is visible."""
    import trimesh
    exit_dz = exit_dz or {}
    s = S_MINI
    body = H.body_meshes(oml)
    meshes = [body["sealed"]] + [m for _n, m in H.hull_parts("vbelly")]
    zcg = cg_m_mini[2] / s
    exits, tags = [], []
    for name, dx, dy in H.P.duct_centres():
        row = name.split("_")[0]
        for a in np.linspace(0, 2 * math.pi, 16, endpoint=False):
            exits.append((dx + H.P.DUCT_ID / 2 * math.cos(a), dy + H.P.DUCT_ID / 2 * math.sin(a),
                          -H.P.BODY_HALF_T + exit_dz.get(row, 0.0)))
            tags.append(row)
    exits, tags = np.array(exits), np.array(tags)
    out = []
    for deg in angles:
        R = trimesh.transformations.rotation_matrix(math.radians(deg), [1, 0, 0], [0, 0, zcg])
        lv = H.float_level([m.copy().apply_transform(R) for m in meshes], mass_kg, s)
        if lv.get("sinks"):
            out.append({"heel_deg": deg, "sinks": True})
            continue
        z = (trimesh.transform_points(exits, R)[:, 2] - lv["z_wl"]) * s * 1000
        out.append({"heel_deg": deg, "gz_mm": -lv["cb"][1] * s * 1000, "lowest_fan_exit_mm": float(z.min()),
                    **{f"lowest_{r}_mm": float(z[tags == r].min()) for r in ("front", "rear")}})
    return out


def margins(rows, c, wind_moment, turn_moment) -> dict:
    """Flood heel, steady heel (wind + turn) and the wave limit water.wave_limit_m() gives for this hull."""
    mass = c["mass_g"] / 1000
    flood = g9.flood_heel(rows)
    steady = g9.heel_for_moment(rows, mass, wind_moment + turn_moment)
    fb = c["hydro"]["freeboard_mm"]
    # the slope rule with this hull's own steady heel in place of the G9 1.0 deg
    keep = water.STEADY_HEEL_DEG
    try:
        water.STEADY_HEEL_DEG = steady if steady is not None else 90.0
        wave = water.wave_limit_m(min(fb.values()) / 1000, flood if flood is not None else 0.0)
    finally:
        water.STEADY_HEEL_DEG = keep
    limiting = None
    for r in rows:
        if r.get("lowest_fan_exit_mm", 1) <= 0:
            limiting = "rear" if r["lowest_rear_mm"] <= r["lowest_front_mm"] else "front"
            break
    return {"flood_heel_deg": flood, "steady_heel_deg": steady, "wave_limit_mm": wave * 1000,
            "gz_2deg_mm": next(r["gz_mm"] for r in rows if r["heel_deg"] == 2),
            "gz_max_mm": max(r.get("gz_mm", 0) for r in rows), "first_exit_to_wet": limiting}


def heel_moments(oml, c) -> tuple:
    """Beam wind at RYW_WIND_MAX and the 1.5 m/s, 3 m radius taxi turn (as G9), N m."""
    mass = c["mass_g"] / 1000
    hc = g9.heeling_cases(oml, mass)
    z_wl = c["hydro"]["waterline_z_at_cg_mm"] / 1000
    draft = 0.055
    f_wind = 0.5 * g9.RHO_AIR * g9.lua_default("WIND_MAX") ** 2 * hc["side_area_m2"] * 1.1
    m_wind = f_wind * (hc["centroid_z_full"] * S_MINI - z_wl + draft / 2)
    m_turn = mass * 1.5 ** 2 / 3.0 * ((c["cg_m"][2] - z_wl) + draft / 2)
    return m_wind, m_turn


def float_stats(c) -> dict:
    """Per float: mass, full-immersion buoyancy and the wing-root bending moment if it is pushed fully under
    (a hard heel or a crooked landing), plus the roll inertia the two floats add. Mini units."""
    s = S_MINI
    f = next(m for n, m in H.hull_parts("vbelly") if n == "float_R")
    vol = float(f.volume) * s ** 3
    shell = float(f.area) * s * s * AM.PETG_SHELL_KG_M2 + AM.STRUT_KG
    y = H.FLOAT["y"] * s
    return {"float_y_mm": y * 1000, "float_kg": shell, "float_buoyancy_n": vol * 1000 * G,
            "root_moment_full_immersion_nm": vol * 1000 * G * y, "floats_ixx_kg_m2": 2 * shell * y ** 2}


def wing_span_y(oml) -> float:
    wing = next(m for n, m, _l in oml if n == "wing_R")
    return float(wing.bounds[1][1])


def case(label: str, exit_dz: dict | None = None) -> dict:
    t = time.time()
    S._OML = None
    c = g5.size_and_float()
    oml = S.oml()
    mw, mt = heel_moments(oml, c)
    rows = roll_rows(oml, c["mass_g"] / 1000, c["cg_m"], exit_dz)
    if exit_dz:   # level fan-exit freeboard rises by however much the lowest exit (front or rear) rose
        flat = roll_rows(oml, c["mass_g"] / 1000, c["cg_m"], None, angles=(0,))[0]
        fb = dict(c["hydro"]["freeboard_mm"])
        k = "lift-fan exits (bottom louvres)"
        if k in fb:
            fb[k] = fb[k] + rows[0]["lowest_fan_exit_mm"] - flat["lowest_fan_exit_mm"]
        c["hydro"] = dict(c["hydro"], freeboard_mm=fb)
    m = margins(rows, c, mw, mt)
    out = {"label": label, "mass_g": c["mass_g"], "tw": c["tw"], "tw_ok": c["tw_ok"], "sm_pct": c["sm_pct"],
           "hover_min": c["hover_min"], "trim_deg": c["hydro"]["trim_nose_up_deg"], "freeboard_mm": c["hydro"]["freeboard_mm"],
           "taxi_1p5_n": next((x["total_n"] for x in c["hydro"]["taxi"] if abs(x["V"] - 1.5) < 1e-6), None),
           "wind_moment_nm": mw, "turn_moment_nm": mt, "strut_extra_mm": c["float_mount"].get("strut_extra_mm", 0.0),
           "cg_offset_mm": c["cg_offset_mm"], **m, **float_stats(c), "rows": rows,
           "secs": time.time() - t}
    print(f"  {label}: flood {m['flood_heel_deg']:.2f} deg (first: {m['first_exit_to_wet']}), steady {m['steady_heel_deg']:.2f} deg, "
          f"wave limit {m['wave_limit_mm']:.0f} mm, GZ@2 {m['gz_2deg_mm']:.1f} mm, mass {c['mass_g']:.0f} g, T/W {c['tw']:.3f}, "
          f"SM {c['sm_pct']:.2f} %, taxi {out['taxi_1p5_n']:.2f} N, root M {out['root_moment_full_immersion_nm']:.2f} N m "
          f"({out['secs']:.0f} s)", flush=True)
    return out


TRACK_CASES = ((3.00, None, 0.0), (3.25, None, 0.0), (3.75, (4.00, 6.00), 0.0), (4.25, (4.80, 6.40), 0.0),
               (3.25, None, 0.05), (3.25, None, 0.10), (3.25, None, 0.15),
               (3.25, {"r": 0.35}, 0.05), (3.25, {"r": 0.40}, 0.05))


def track_sweep(cases=TRACK_CASES) -> list:
    """Floats outboard, their bottom held at the G5 height (the wing has dihedral, so the struts get longer outboard).
    The wing is swept: past y ~3.3 its leading edge is aft of the G5 floats (x 1.55-3.55), so the outer cases also move
    the floats aft under the wing. (y, (x0, x1) or None to keep the G5 x, drop below the G5 float height).
    Dropped floats touch the water at rest, so the hull pivots about the low-side float, outboard of the rear exits."""
    keep_y, keep_x, keep_place = g5.FLOAT_Y, dict(g5.FLOAT_V21), g5.place_floats
    S._OML = None
    c0 = g5.size_and_float()
    z0, keep_r = H.FLOAT["z"], H.FLOAT["r"]       # after size_and_float: g4.set_layout sets the G5 float radius (0.30)
    zb0 = c0["float_mount"]["wing_bottom_z"]
    out = []
    drop = [0.0]

    def place_fixed_z(oml):
        x0, x1 = H.FLOAT["x0"], H.FLOAT["x1"]
        xs = (x0 + x1) / 2 + 0.55 if (x0, x1) == (keep_x["x0"], keep_x["x1"]) else (x0 + x1) / 2
        zb = g5.wing_bottom_z(oml, xs - 0.4, xs + 0.4, g5.FLOAT_Y)
        H.FLOAT.update({"y": g5.FLOAT_Y, "z": z0 - drop[0] + (H.FLOAT["r"] - keep_r)})
        return {"wing_bottom_z": zb, "float_z": z0 - drop[0], "strut_extra_mm": (zb - zb0 + drop[0]) * 100}

    try:
        g5.place_floats = place_fixed_z
        for y, xr, dz in cases:
            g5.FLOAT_Y, drop[0] = y, dz
            g5.FLOAT_V21.clear()
            g5.FLOAT_V21.update(keep_x)
            H.FLOAT["r"] = keep_r
            if isinstance(xr, dict):      # bigger floats: same length and x, a larger radius
                g5.FLOAT_V21.update(xr)
            elif xr is not None:
                g5.FLOAT_V21.update({"x0": xr[0], "x1": xr[1]})
            label = (f"A floats y {y * 100:.0f} mm" + ("" if xr is None else f", r {xr['r'] * 100:.0f} mm" if isinstance(xr, dict)
                                                      else f", x {xr[0] * 100:.0f}-{xr[1] * 100:.0f} mm")
                     + (f", lowered {dz * 100:.0f} mm" if dz else ""))
            try:
                out.append(dict(case(label), float_y_full=y, float_x_full=xr, float_drop_mm=dz * 100))
            except Exception as e:  # the wing may not reach
                print(f"  {label}: {type(e).__name__}: {e}", flush=True)
                out.append({"label": label, "error": str(e), "float_y_full": y})
    finally:
        g5.FLOAT_Y, g5.place_floats = keep_y, keep_place
        g5.FLOAT_V21.clear()
        g5.FLOAT_V21.update(keep_x)
        H.FLOAT["r"] = keep_r
        S._OML = None
    return out


def exit_sweep(dzs=(0.05, 0.10)) -> list:
    return [dict(case(f"B rear exits raised {dz * 100:.0f} mm", {"rear": dz}), rear_exit_raise_mm=dz * 100,
                 rear_duct_depth_mm=(H.P.DUCT_DEPTH - dz) * 100) for dz in dzs]


def mass_budget() -> dict:
    """The lift T/W gate as a mass limit, and the biggest items in the G5 build."""
    S._OML = None
    c = g5.size_and_float()
    limit_g = 4 * g4.LOCKED.get("rotor_tmax_kg", 0.95) * 1000 / AM.TW_GATE
    return {"mass_g": c["mass_g"], "limit_g": limit_g, "headroom_g": limit_g - c["mass_g"], "groups_g": c["groups_g"],
            "tw": c["tw"], "hover_min": c["hover_min"], "payload_max_g": c["payload_max_g"]}


def main(argv) -> int:
    t0 = time.time()
    GEO.set_variant("mini")
    g5.apply_shape()
    only = argv[0] if argv else "all"
    prev = json.loads((ROOT / "analysis" / "v21_g10.json").read_text()) if only != "all" else {}
    print("baseline (G5):", flush=True)
    base = case("G5 baseline") if only == "all" else prev["baseline"]
    print("A. wider float track:", flush=True)
    a = track_sweep() if only in ("all", "A") else prev["A_track"]
    print("B. raised rear fan exits:", flush=True)
    b = exit_sweep() if only in ("all", "B") else prev["B_exits"]
    print("lift T/W budget:", flush=True)
    mb = mass_budget() if only == "all" else prev["mass_budget"]
    print(f"  mass {mb['mass_g']:.0f} g, T/W-gate limit {mb['limit_g']:.0f} g -> headroom {mb['headroom_g']:.1f} g", flush=True)
    for k, v in sorted(mb["groups_g"].items(), key=lambda kv: -kv[1]):
        print(f"   {k}: {v:.0f} g", flush=True)
    out = {"basis": "ESTIMATE: tools/v21/g10.py on the G5 model; nothing built or floated",
           "baseline": base, "A_track": a, "B_exits": b, "mass_budget": mb}
    (ROOT / "analysis" / "v21_g10.json").write_text(json.dumps(out, indent=1, default=float))
    print(f"wrote analysis/v21_g10.json ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
