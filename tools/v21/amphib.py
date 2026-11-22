#!/usr/bin/env python3
"""V21 "Ryujin" G4 groundwork: the amphibious trade on top of the V20 mini (V20 itself stays frozen).

    python3 tools/v21/amphib.py            # analysis/v21_trade.json + a printed table (about 5 minutes)
    python3 tools/v21/amphib.py --quick    # sizing only, no hydrostatics

For every G3 option set (water propulsion A/B/C, hull, material, pack) it re-runs the V20 mini sizing
(tools/v21/sizing.py, an unchanged copy) with the extra hardware and the new skin density, then floats the result
(tools/v21/hydro.py). Nothing here is a G3 decision: the options are inputs, the recommendation is Alek's call.

Basis of every new number (all ESTIMATE until measured):
  * hull shells, floats and sponsons: their mesh area x a solid-PETG areal density (0.45 mm wall, +25 % for ribs),
  * skins: the V20 areal densities scaled by filament density over the 0.60 g/cm3 foamed LW-PLA V20 assumed,
  * the water-jet module: a component estimate (no part chosen; no part number is claimed),
  * thrust per lift fan stays the V20 0.95 kg assumption (open item 1: thrust stand).
"""
from __future__ import annotations

import copy
import itertools
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
import geometry as GEO  # noqa: E402
import hydro as H  # noqa: E402
import sizing as S  # noqa: E402

G0 = 9.80665
TW_GATE = 1.9                  # lift thrust / weight kept from V20 (project rule)
SM_GATE = 5.0                  # static margin, louvres shut (% MAC)
RESERVE_GATE = 100.0           # reserve buoyancy (%), sealed volume only

# ---------------------------------------------------------------------------------------------------------------
# G3 options. Positions are full-scale metres (the V20 frame); masses are mini kg.
PETG_SHELL_KG_M2 = 1.27e3 * 0.45e-3 * 1.25          # solid PETG, 0.45 mm wall, +25 % ribs: 0.71 kg/m2 (mini)
BASE_FILAMENT = 0.60                                # g/cm3 the V20 skin densities assume (foamed LW-PLA)
MATERIALS = {
    "lw_asa": {"label": "LW-ASA skins (foamed, 0.65 g/cm3 ESTIMATE; availability UNCONFIRMED)", "rho": 0.65},
    "asa": {"label": "solid ASA skins (1.07 g/cm3)", "rho": 1.07},
    "petg": {"label": "solid PETG skins (1.27 g/cm3)", "rho": 1.27},
    "lw_pla": {"label": "LW-PLA as V20 (0.60 g/cm3; unfit for wet use, reference only)", "rho": 0.60},
}
PACKS = {
    "4S3P": {"parallel": 3, "kg": 0.87},
    "4S2P": {"parallel": 2, "kg": 0.58},
}
WET_KIT = [  # every amphibious option: sealing the avionics bay and the electrics
    ("sealed bay: gasket, vent membrane, hatch O-ring", 3.0, 0.0, 0.05, 0.020, "systems"),
    ("conformal coat + potted connectors + bilge leak sensor", 3.4, 0.0, -0.1, 0.012, "systems"),
]
SPRAY_RAILS = ("spray rails along the belly chines (PETG)", 3.5, 0.0, -0.55, 0.010, "airframe")
STEP_BLOCK = ("planing step insert + local stiffening", H.STEP_X, 0.0, -0.70, 0.010, "airframe")
SKID_SHOE = ("replaceable skid shoe under the belly keel (PETG/TPU, ESTIMATE)", 3.6, 0.0, -0.80, 0.015, "gear")
STRUT_KG = 0.008               # each float / sponson strut and mount
WATERJET = [  # option B: payload module P05 on S9 (no part chosen; component-class estimate)
    ("P05 water-jet: brushless pump motor (ESTIMATE)", 6.0, 0.0, -0.40, 0.045, "propulsion"),
    ("P05 water-jet: printed impeller, housing, nozzle, intake grate (ESTIMATE)", 6.3, 0.0, -0.45, 0.035, "propulsion"),
    ("P05 water-jet: ESC (ESTIMATE)", 5.6, 0.0, -0.30, 0.012, "propulsion"),
    ("P05 water-jet: hull seal + wiring (ESTIMATE)", 6.0, 0.0, -0.35, 0.008, "propulsion"),
]
PROPULSION = {
    "A": {"label": "A airboat: cruise EDF (S11) + ruddervators", "items": [], "outputs": 0, "s9_free": True},
    "B": {"label": "B water-jet P05 on S9", "items": WATERJET, "outputs": 0, "s9_free": False},
    "C": {"label": "C both (A default, B backup)", "items": WATERJET, "outputs": 0, "s9_free": False},
}
HULLS = ("none", "vbelly", "stepped", "sponsons")


def hull_items(hull: str) -> list:
    """Hull hardware from the add-on meshes (area x PETG shell density) plus rails, step and struts."""
    s = 0.1
    items = []
    for name, m in H.hull_parts(hull):
        c = m.center_mass
        kg = float(m.area) * s * s * PETG_SHELL_KG_M2
        items.append((f"hull: {name} shell (PETG, from mesh area)", float(c[0]), float(c[1]), float(c[2]), kg, "airframe"))
        if name.startswith(("float", "sponson")):
            items.append((f"hull: {name} strut + mount", float(c[0]), float(c[1]), float(c[2]) + 0.15, STRUT_KG, "airframe"))
    if hull in ("vbelly", "stepped"):
        items.append(SPRAY_RAILS)
    if hull == "stepped":
        items.append(STEP_BLOCK)
    return items


def size_case(prop: str, hull: str, material: str, pack: str, rotor_tmax_kg: float = 0.95, gear: str = "wheels") -> dict:
    """Re-run the V20 mini sizing with the V21 option set."""
    base = copy.deepcopy(S.SCALES["mini"])
    cfg = copy.deepcopy(base)
    f = MATERIALS[material]["rho"] / BASE_FILAMENT
    for layer in ("skin", "controls", "propulsion"):
        cfg["areal_kg_m2"][layer] = base["areal_kg_m2"][layer] * f
    cfg["battery"]["parallel"] = PACKS[pack]["parallel"]
    cfg["battery"]["kg"] = PACKS[pack]["kg"]
    cfg["rotor_tmax_kg"] = rotor_tmax_kg
    extra = (WET_KIT if hull != "none" else []) + hull_items(hull) + PROPULSION[prop]["items"]
    orig_comp, orig_cfg = S.mini_components, S.SCALES["mini"]
    S.SCALES["mini"] = cfg
    if gear == "skid":         # G5: the belly and floats take the landings; wheels off, a replaceable skid shoe on
        extra = extra + [SKID_SHOE]

    def comps(payload_kg=None):
        base_items = orig_comp(payload_kg)
        if gear == "skid":
            base_items = [i for i in base_items if i[5] != "gear"]
        return base_items + list(extra)
    S.mini_components = comps
    try:
        r = S.size_mini()
    finally:
        S.mini_components, S.SCALES["mini"] = orig_comp, orig_cfg
    M = r["mass_kg"]
    tw = r["thrust_to_weight_lift"]
    return {
        "prop": prop, "hull": hull, "material": material, "pack": pack, "rotor_tmax_kg": rotor_tmax_kg, "gear": gear,
        "battery_x_mm": r["battery_x_m"] * 1000,
        "mass_g": M * 1000, "groups_g": {k: v * 1000 for k, v in r["groups_kg"].items()},
        "added_g": sum(i[4] for i in extra) * 1000, "hull_g": sum(i[4] for i in hull_items(hull)) * 1000,
        "tw": tw, "tw_ok": tw >= TW_GATE,
        "fan_kg_for_gate": TW_GATE * M / 4,
        "rotor_limit": r["rotor_tmax_limit"],
        "hover_min": r["hover_min"], "hover_w": r["hover_w"], "cruise_min": r["cruise"]["min"],
        "range_km": r["cruise"]["range_km"],
        "cg_m": r["cg_m"], "cg_offset_mm": r["cg_offset_mm"], "battery_x_clipped": abs(r["battery_x_m"] - r["battery_x_unclipped_m"]) > 1e-6,
        "sm_pct": float(r["aero"]["sm_gate_pct"]), "sm_ok": float(r["aero"]["sm_gate_pct"]) >= SM_GATE,
        "payload_max_g": r["payload"]["max_kg"] * 1000,
        "s9_free_for_payload": PROPULSION[prop]["s9_free"],
        "corridor_ok": all(c["hover_ok"] and c["forward_ok"] for c in r["corridor"]),
        "airspeeds": r["airspeeds"], "stall_ms": r["stall_ms"], "battery_wh_usable": r["battery_wh_usable"],
    }


def row(c: dict) -> str:
    return (f"{c['prop']} {c['hull']:9s} {c['material']:6s} {c['pack']} | {c['mass_g']:6.0f} g (+{c['added_g']:3.0f}) | "
            f"T/W {c['tw']:4.2f}{' ' if c['tw_ok'] else '!'} | hover {c['hover_min']:4.1f} min | cruise {c['cruise_min']:4.1f} min "
            f"| SM {c['sm_pct']:4.1f}%{' ' if c['sm_ok'] else '!'} | CG {c['cg_offset_mm']:+5.1f} mm | payload {c['payload_max_g']:4.0f} g "
            f"| fan for 1.9: {c['fan_kg_for_gate']:.3f} kg")


def main(argv) -> int:
    quick = "--quick" in argv
    GEO.set_variant("mini")
    cases = [size_case("A", "none", "lw_pla", "4S3P")]          # V20 reproduction (the reference)
    print("V20 reference:", row(cases[0]))
    for prop, hull, mat, pack in itertools.product(("A", "B"), HULLS[1:], ("lw_asa", "asa", "petg"), PACKS):
        c = size_case(prop, hull, mat, pack)
        cases.append(c)
        print(row(c))
    hydro = []
    if not quick:
        oml = S.oml()
        for hull in HULLS:
            for pack in PACKS:
                c = next(x for x in cases if x["prop"] == "A" and x["hull"] == hull and x["material"] == ("lw_pla" if hull == "none" else "lw_asa")
                         and x["pack"] == pack) if hull != "none" or pack == "4S3P" else None
                if c is None:
                    continue
                hres = H.analyse(oml, hull, c["mass_g"] / 1000, c["cg_m"])
                hres["case"] = {k: c[k] for k in ("prop", "hull", "material", "pack", "mass_g")}
                hydro.append(hres)
                fb = ", ".join(f"{k.split(' (')[0]} {v:+.0f}" for k, v in hres.get("freeboard_mm", {}).items())
                print(f"float {hull:9s} {pack}: reserve {hres['reserve_sealed_pct']:4.0f} %, trim {hres.get('trim_nose_up_deg', 0):+.1f} deg, "
                      f"freeboard mm: {fb}")
    out = {"basis": "ESTIMATE: V20 mini sizing + V21 option masses + level/trimmed float (tools/v21/hydro.py)",
           "gates": {"lift_tw": TW_GATE, "static_margin_pct": SM_GATE, "reserve_buoyancy_pct": RESERVE_GATE},
           "options": {"propulsion": {k: v["label"] for k, v in PROPULSION.items()},
                       "materials": {k: v["label"] for k, v in MATERIALS.items()}, "packs": PACKS, "hulls": HULLS},
           "cases": cases, "hydro": hydro}
    (ROOT / "analysis" / "v21_trade.json").write_text(json.dumps(out, indent=1, default=float))
    print("wrote analysis/v21_trade.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
