#!/usr/bin/env python3
"""V21 "Ryujin" G4 sizing for the locked G3 set (A airboat, V-belly + spray rails + floats, LW-ASA skins, 4S2P).

    python3 tools/v21/g4.py          # analysis/v21_g4_sizing.json + a printed gate table (about 10 minutes)

Searches the layout levers that cost little or no mass, for a design that meets every G4 gate at once:
  * where the 4S2P pack sits (it is now light enough to move into the nose: fit is UNCONFIRMED until G5 CAD),
  * the belly's length and where the outrigger floats sit fore and aft (forward = nose-up float AND forward CG),
  * the wheeled tricycle gear swapped for a skid shoe (the belly and floats take the landings, as planned for G5).
Then floats the best layouts with pitch trim and reports how far each opening must rise to stay dry.

Gates: lift T/W >= 1.9, static margin >= 5 % (louvres shut), CG on the fan centroid within 3 mm, reserve buoyancy
>= 100 % (sealed volume only), every opening >= SPRAY_MARGIN_MM above the still waterline. All ESTIMATE.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
import amphib as AM  # noqa: E402
import geometry as GEO  # noqa: E402
import hydro as H  # noqa: E402
import sizing as S  # noqa: E402
import v20params as P  # noqa: E402

LOCKED = {"prop": "A", "hull": "vbelly", "material": "lw_asa", "pack": "4S2P"}
SPRAY_MARGIN_MM = 20.0         # still-water freeboard wanted at every opening (mini mm): ESTIMATE, the G7 spray test
                               # at 1 m hover over water decides the real number
CG_TOL_MM = 3.0
PACK_LEN = 0.70                # 4S2P of 21700 cells laid fore-aft: about 70 mm long (mini), 0.70 m full scale
BAY_LIMITS = (1.30, 1.45)                     # forward limit of the pack centre (full-scale m); a first search over
                                              # 1.30-1.90 found nothing balanced aft of 1.45 (analysis kept in git history)
FLOAT_X = (2.6, 3.0, 3.4)                     # float centre (full-scale m); V21 groundwork had 5.2 (CG +36 mm, nose-down)
FLOAT_R = (0.17, 0.21)
BELLY_X = ((0.90, 7.00), (0.90, 6.00))
ESC_X = (3.50, 2.60)                          # EDF ESC: V20 position, or 90 mm (mini) forward beside the intake ducts
FLOAT_LEN = 2.40


_ORIG_COMP = S.mini_components


def set_layout(bay0: float, fx: float, fr: float, bx: tuple, esc_x: float = 3.50):
    def comps(payload_kg=None):
        return [((n, esc_x) + tuple(it[2:]) if n.startswith("EDF ESC") else it) for it in _ORIG_COMP(payload_kg)
                for n in (it[0],)]
    S.mini_components = comps
    S.MINI_BAY = (bay0, 2.08)
    H.FLOAT.update({"x0": fx - FLOAT_LEN / 2, "x1": fx + FLOAT_LEN / 2, "r": fr})
    H.BELLY.update({"x0": bx[0], "x1": bx[1]})


RECOMMENDED = {"bay_fwd_m": 1.30, "float_x_m": 2.2, "float_r_m": 0.30, "belly_x_m": (0.90, 6.00), "belly_depth_m": 0.40,
               "esc_x_m": 2.60, "gear": "skid"}
EDF_STATIC_N = 1.20 * 9.80665  # Freewing E7206 64 mm on 4S (vendor figure, as V20)


def recommended() -> dict:
    """The G4 layout: balanced, trimmed level, fan exits 20 mm clear. Every number ESTIMATE."""
    R = RECOMMENDED
    set_layout(R["bay_fwd_m"], R["float_x_m"], R["float_r_m"], R["belly_x_m"], R["esc_x_m"])
    H.BELLY["depth"] = R["belly_depth_m"]
    c = AM.size_case(**LOCKED, gear=R["gear"])
    h = H.analyse(S.oml(), "vbelly", c["mass_g"] / 1000, c["cg_m"])
    c["hydro"] = h
    c["raise_needed_mm"] = {k: max(0.0, SPRAY_MARGIN_MM - v) for k, v in h["freeboard_mm"].items()}
    c["taxi"] = [dict(t, edf_thrust_frac=t["total_n"] / EDF_STATIC_N) for t in h["taxi"]]
    c["layout"] = {k: (list(v) if isinstance(v, tuple) else v) for k, v in R.items()}
    c["gates"] = {
        "lift T/W >= 1.9": (c["tw"], c["tw_ok"]),
        "static margin >= 5 %": (c["sm_pct"], c["sm_ok"]),
        "CG within 3 mm of fan centroid": (c["cg_offset_mm"], abs(c["cg_offset_mm"]) <= CG_TOL_MM),
        "reserve buoyancy >= 100 % (sealed)": (h["reserve_sealed_pct"], h["reserve_sealed_pct"] >= 100),
        **{f"freeboard >= {SPRAY_MARGIN_MM:.0f} mm: {k}": (v, v >= SPRAY_MARGIN_MM) for k, v in h["freeboard_mm"].items()},
    }
    return c


def main(argv) -> int:
    if "--rec" in argv:
        GEO.set_variant("mini")
        c = recommended()
        print(AM.row(c))
        for k, (v, ok) in c["gates"].items():
            print(f"  {'PASS' if ok else 'FAIL'}  {k}: {v:.1f}")
        print(f"  float trim {c['hydro']['trim_nose_up_deg']:+.1f} deg, displacement {c['hydro']['displacement_l']:.2f} L, "
              f"sealed volume {c['hydro']['volume_sealed_l']:.2f} L")
        for t in c["taxi"]:
            print(f"  taxi {t['V']:.1f} m/s (Froude {t['Fn']:.2f}): water drag {t['total_n']:.2f} N = {100 * t['edf_thrust_frac']:.0f} % of EDF static thrust")
        print("  raise needed (mm):", {k: round(v) for k, v in c["raise_needed_mm"].items()})
        prev = json.loads((ROOT / "analysis" / "v21_g4_sizing.json").read_text())
        prev["recommended"] = c
        (ROOT / "analysis" / "v21_g4_sizing.json").write_text(json.dumps(prev, indent=1, default=float))
        return 0
    GEO.set_variant("mini")
    base_bay, base_float, base_belly = S.MINI_BAY, dict(H.FLOAT), dict(H.BELLY)
    rows = []
    for bay0, fx, fr, bx, gear, esc in itertools.product(BAY_LIMITS, FLOAT_X, FLOAT_R, BELLY_X, ("wheels", "skid"), ESC_X):
        set_layout(bay0, fx, fr, bx, esc)
        c = AM.size_case(**LOCKED, gear=gear)
        c.update({"bay_fwd_m": bay0, "float_x_m": fx, "float_r_m": fr, "belly_x_m": list(bx), "esc_x_m": esc})
        c["balanced"] = abs(c["cg_offset_mm"]) <= CG_TOL_MM
        rows.append(c)
    ok = [c for c in rows if c["balanced"] and c["tw_ok"] and c["sm_ok"]]
    print(f"{len(rows)} layouts sized; {len(ok)} meet T/W, static margin and CG together")
    # prefer: the pack least far forward (least packaging risk), then the lightest
    ok.sort(key=lambda c: (-c["bay_fwd_m"], c["mass_g"]))
    oml = S.oml()
    floated = []
    seen = set()
    for c in ok:
        key = (c["bay_fwd_m"], c["gear"], tuple(c["belly_x_m"]))
        if key in seen:
            continue
        seen.add(key)
        set_layout(c["bay_fwd_m"], c["float_x_m"], c["float_r_m"], tuple(c["belly_x_m"]), c["esc_x_m"])
        h = H.analyse(oml, "vbelly", c["mass_g"] / 1000, c["cg_m"])
        c["hydro"] = h
        fb = h.get("freeboard_mm", {})
        c["raise_needed_mm"] = {k: max(0.0, SPRAY_MARGIN_MM - v) for k, v in fb.items()}
        floated.append(c)
        print(AM.row(c), f"| bay {c['bay_fwd_m']:.2f} float x {c['float_x_m']:.1f} r {c['float_r_m']:.2f} belly {c['belly_x_m']} {c['gear']} ESC x {c['esc_x_m']}")
        print(f"   float: trim {h.get('trim_nose_up_deg', 0):+.1f} deg, reserve {h['reserve_sealed_pct']:.0f} %, freeboard mm "
              + ", ".join(f"{k.split(' (')[0]} {v:+.0f}" for k, v in fb.items()))
        if len(floated) >= 6:
            break
    # the same layouts with the float x swept, to show what the float position does to the trim (first ok layout)
    sweep = []
    if floated:
        best = floated[0]
        for fx in FLOAT_X:
            set_layout(best["bay_fwd_m"], fx, best["float_r_m"], tuple(best["belly_x_m"]), best["esc_x_m"])
            c = AM.size_case(**LOCKED, gear=best["gear"])
            h = H.analyse(oml, "vbelly", c["mass_g"] / 1000, c["cg_m"])
            sweep.append({"float_x_m": fx, "cg_offset_mm": c["cg_offset_mm"], "sm_pct": c["sm_pct"], "mass_g": c["mass_g"],
                          "trim_deg": h.get("trim_nose_up_deg"), "freeboard_mm": h.get("freeboard_mm")})
            print(f"   sweep float x {fx:.1f}: CG {c['cg_offset_mm']:+.1f} mm, SM {c['sm_pct']:.1f} %, trim {h.get('trim_nose_up_deg', 0):+.1f} deg, "
                  + ", ".join(f"{k.split(' (')[0]} {v:+.0f}" for k, v in h.get("freeboard_mm", {}).items()))
    S.MINI_BAY = base_bay
    S.mini_components = _ORIG_COMP
    H.FLOAT.update(base_float)
    H.BELLY.update(base_belly)
    out = {"basis": "ESTIMATE: V20 mini sizing + V21 hull/skin/pack + trimmed float (tools/v21/g4.py)",
           "locked_g3": LOCKED, "spray_margin_mm": SPRAY_MARGIN_MM, "pack_len_m_full": PACK_LEN,
           "n_layouts": len(rows), "n_pass_sizing": len(ok), "floated": floated, "float_sweep": sweep,
           "all": [{k: v for k, v in c.items() if k not in ("groups_g",)} for c in rows]}
    (ROOT / "analysis" / "v21_g4_sizing.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote analysis/v21_g4_sizing.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
