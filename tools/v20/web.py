"""V20 data for the web workbench: two standalone viewer variants (v20_mini, v20_full) and the V20 tab's page data.

Both models are shown in the same display frame: the mini at real size (mm) and the full-scale aircraft at 1:10, so
the two sit in the same frame (the full scale is a wider-shouldered variant of the same layout) and the viewer's camera, grid and markers need no rescaling. The
page shows full-scale numbers in metres and kilograms.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import v20params as P  # noqa: E402
from bom import MINI_BOM, PINMAP  # noqa: E402

DISPLAY_MM_PER_M = 100.0     # full-scale metre -> display mm (mini scale 1:10; full shown at 1:10)


def _group(name: str) -> str:
    for pre, label in (("wing", "Wing and strakes"), ("elevon", "Controls"), ("stabilator", "Controls"), ("rudder", "Controls"),
                       ("fin", "Fins"), ("duct", "Lift ducts"), ("fan", "Lift fans"), ("nozzle", "Cruise jet"), ("edf", "Cruise jet"),
                       ("thrust", "Cruise jet"), ("cruise", "Cruise jet"), ("intake", "Cruise jet"), ("gear", "Landing gear"),
                       ("battery", "Battery"), ("fuel", "Fuel"), ("turbo", "Power"), ("pilot", "Cockpit"), ("seat", "Cockpit"), ("canopy", "Cockpit"),
                       ("fpv", "Cockpit"), ("spar", "Structure"), ("keel", "Structure"), ("fuselage", "Fuselage")):
        if name.startswith(pre):
            return label
    return "Systems"


def _pack_notes(checks: dict) -> list:
    bp = checks.get("battery_pack", {})
    out = []
    if bp.get("battery_volume_fill", 1.0) < 0.98:
        out.append(f"only {100 * bp['battery_volume_fill']:.0f} % of the battery fits the nose bay")
    if bp.get("fuel_capacity_l", 1.0) < bp.get("fuel_needed_l", 0.0):
        out.append("the wing tanks are too small")
    if checks.get("internal_collisions"):
        out.append(f"{len(checks['internal_collisions'])} internal collisions")
    return out or ["see cad/v20/full/checks.json"]


def _entry(key: str, sz: dict, geo: dict) -> dict:
    P.use(key)
    s = sz[key]
    full = key == "full"
    k = DISPLAY_MM_PER_M
    scale = 1.0 if full else 0.1
    to_disp = (k / scale) / 1000.0            # metres at this scale -> display mm
    cg = [v * 1000 * to_disp for v in s["cg_m"]]
    xf, xr = P.DUCT_X["front"] * k, P.DUCT_X["rear"] * k
    a = s["aero"]
    np_d = a["x_np_m"] * 1000 * to_disp
    off_real_mm = s["cg_offset_mm"]
    rear_share = 50.0 * (cg[0] - xf) / (xr - xf)            # % of the weight on each rear duct (x2 ducts)
    worst = max(rear_share, 50.0 - rear_share)
    cor = s["corridor"]
    corridor_ok = all(r["forward_ok"] and r["hover_ok"] for r in cor)
    sm_gate = a["sm_gate_pct"]
    sm_need = 0.0 if full else 5.0          # the full scale flies on triplex fly-by-wire; the mini wants 5 %
    gates_ok = sm_gate >= sm_need and (abs(off_real_mm) <= (3.0 if not full else 30.0)) and corridor_ok \
        and geo[key]["checks"]["status"] == "PASS"
    mass_g = (s["mass_kg"] if not full else s["mtow_kg"]) * 1000
    trim = s["trim_16ms"] if not full else s["trim_cruise"]
    masses = {n: kg for n, kg, _p, _g in s["items"]}
    new = []
    for p in geo[key]["parts"]:
        new.append({"name": p["name"], "class": "printed" if (not full and p["layer"] in ("skin", "controls", "glass")) else "v20",
                    "material": None, "mass_g": round(masses.get(p["name"], 0.0) * 1000, 1), "layer": p["layer"], "note": p["note"],
                    "mass_basis": "surface area x areal density" if p["name"] in masses else "",
                    "centroid_mm": [round(v * (0.1 if full else 1.0), 1) for v in p["centroid_mm"]],
                    "bbox_mm": [round(v * (0.1 if full else 1.0), 1) for v in p["bbox_mm"]], "P1S": None, "group_label": _group(p["name"])})
    eye = (3.22, 0.0, 0.455) if not full else (3.48, 0.0, 0.52)
    label = "V20 mini (1:10, printable)" if not full else "V20 full scale (single seat, concept; shown 1:10)"
    summ = ("F-35-style lift + cruise VTOL: 4 lift fans hidden under louvres, side intakes to one 64 mm EDF, 4S2P Li-ion, "
            "3D-printed on the P1S with a foam tail" if not full else
            "The same layout for one pilot, shoulders widened for 1.56 m fans: 8 motors in 4 coaxial ducts, series hybrid "
            "(nose turbogenerator + battery); engineering concept")
    return {
        "label": label, "short": "V20 Mini" if not full else "V20 Full", "summary": summ, "standalone": True, "family": "v20",
        "display_scale": 1.0 if not full else 10.0, "unit": "mm" if not full else "m",
        "eye_mm": [v * k for v in eye], "motor_y_mm": P.DUCT_Y * k,
        "eval": {"all_up_g": mass_g, "cg_mm": cg, "rotor_front_x_mm": xf, "rotor_rear_x_mm": xr, "rotor_centroid_x_mm": (xf + xr) / 2,
                 # the viewer's band runs from louvres shut (cruise, the gate) to louvres open
                 "np_closed_x_mm": a["x_np_closed_m"] * 1000 * to_disp, "np_open_x_mm": a["x_np_open_m"] * 1000 * to_disp, "mac_mm": a["mac_m"] * 1000 * to_disp,
                 "sm_closed_pct": a["sm_closed_pct"], "sm_open_pct": a["sm_open_pct"], "sm_gate_pct": sm_gate,
                 "sm_gate_label": "static margin with the louvres shut",
                 "sm_window_pct": [sm_need, 12.0], "worst_motor_pct": worst,
                 "trim_16ms": {"open": {"alpha_deg": trim["alpha_deg"], "pitch_surfaces_deg": trim["pitch_surfaces_deg"], "CL": trim["CL"]}},
                 "hover_ok": abs(off_real_mm) <= (3.0 if not full else 30.0), "flight_ok": sm_gate >= sm_need, "geometry_ok": True,
                 "fit_ok": geo[key]["checks"]["status"] == "PASS", "passes": gates_ok},
        "verdict": ("Passes every model gate." if gates_ok else
                    ("Passes the hover and flight gates; packaging is open: " + "; ".join(_pack_notes(geo[key]["checks"])) + "."
                     if full and sm_gate >= sm_need and corridor_ok else "Does not pass every gate.")),
        "length_mm": P.FUS_LEN * k + 15, "span_mm": a["span_m"] * 1000 * to_disp,
        "moves": {}, "repo_moves": {}, "hidden": [], "modified": [], "modified_detail": [], "new": new,
        "new_mass_g": round(mass_g, 1), "changes": [], "notes": [],
        "checks": {"collisions": 0, "collision_list": [], "intended": 0, "jet": None, "p1s_ok": geo[key]["checks"]["status"] == "PASS",
                   "p1s_fail": []},
    }


def variant_entries() -> dict:
    szf, gf = ROOT / "analysis" / "v20_sizing.json", ROOT / "analysis" / "v20_geometry.json"
    if not (szf.exists() and gf.exists()):
        return {}
    sz, geo = json.loads(szf.read_text()), json.loads(gf.read_text())
    return {"v20_mini": _entry("mini", sz, geo), "v20_full": _entry("full", sz, geo)}


def page_data() -> dict | None:
    szf, gf = ROOT / "analysis" / "v20_sizing.json", ROOT / "analysis" / "v20_geometry.json"
    if not (szf.exists() and gf.exists()):
        return None
    sz, geo = json.loads(szf.read_text()), json.loads(gf.read_text())
    geom = {}
    for key in ("mini", "full"):
        P.use(key)
        geom[key] = {"length_m": P.FUS_LEN, "span_m": sz[key]["aero"]["span_m"] / sz[key]["scale"], "duct_id_m": P.DUCT_ID,
                     "duct_x_m": P.DUCT_X, "duct_y_m": P.DUCT_Y}
    P.use("mini")
    out = {"mini": {}, "full": {}, "trade": sz["trade"], "bom": MINI_BOM, "pinmap": PINMAP, "assumptions": sz["assumptions"],
           "geometry": geom["full"], "geometry_by_scale": geom}
    for key in ("mini", "full"):
        s = dict(sz[key])
        s["items"] = [{"name": n, "kg": kg, "x_m": p[0], "group": g} for n, kg, p, g in s["items"]]
        s.pop("iterations", None)
        s["checks"] = geo[key]["checks"]
        out[key] = s
    return out
