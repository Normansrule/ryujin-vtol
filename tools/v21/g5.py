#!/usr/bin/env python3
"""V21 "Ryujin" G5: the V21 shape and the mini print set, on top of the G4 layout (tools/v21/g4.py RECOMMENDED).

    python3 tools/v21/g5.py            # analysis/v21_g5.json, cad/v21/mini/, site/models/raw/v21_mini.glb (about 10 minutes)
    python3 tools/v21/g5.py --no-build # sizing + float only (about 2 minutes)

What G5 changes against the V20 outer mould line (full-scale metres; mini = /10). Every number is ESTIMATE:
  * EDF intakes: lower lip raised from z -0.46 to -0.15 (the G4 float put it 11 mm mini under water). The mouth keeps
    the V20 area by growing upwards (top z +0.24) and sinks deeper into the body; the cheek fades into the body by
    x 2.25, ahead of the front lift duct, and the PET intake ducts run inside the fuselage to the fan.
  * Nozzle: axis raised from z -0.01 to +0.15 (lower lip at -0.15), lip radius 0.33 -> 0.30. The thrust tube keeps the
    V20 line past the ruddervator servos and kinks up 5 deg behind them; a tail fairing covers the raised section.
    The thrust line now sits about 25 mm (mini) above the CG: a nose-down moment in cruise, trimmed in G6.
  * Hull: V-belly (x 0.90-6.00, 40 mm deep mini) + two floats moved inboard to y 2.75, between the front and rear
    lift fans, so a short strut reaches the wing (at y 3.55 the G4 float sat wholly ahead of the leading edge).
  * Wheels off; a replaceable skid shoe under the belly keel.
  * Payload bay: free-flooding by design. It was never in the sealed volume (G4 counted it as flooded), so its doors
    get drain holes instead of a gasket: nothing to seal, nothing to fail. Payload modules must be waterproof.
  * 4S2P pack: a fit search for 8 x 21700 cells around the G4 battery x, inside the fuselage + belly.
  * Lift fans: each duct bore opens 1.5 mm (mini) and takes an identical printed drop-in pod liner (motor spider and
    stators ride on it), so the four fan pods are interchangeable. The tip gap is unchanged.
  * Wings: two nylon M4 shear bolts per side at the root (breakaway in a cartwheel; the carbon spars slide out).
  * Nose stretched 50 mm (mini) ahead of the V20 1.05 m station: the 4S2P (two 2 x 2 bundles) fits where the balance
    needs it (Alek's pick, 2026-11-17). The static margin now counts the longer nose and both floats as destabilising
    bodies (tools/v21/aero.py), and the V-tail span grows 230 -> 290 mm (mini) to win the margin back.
  * Roll on the water is computed (righting arm vs heel, wings flooded) and where a low-side fan exit floods.
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
sys.path.insert(0, str(ROOT / "tools"))
import amphib as AM  # noqa: E402
import g4  # noqa: E402
import geometry as GEO  # noqa: E402
import hydro as H  # noqa: E402
import sizing as S  # noqa: E402
import v20params as P  # noqa: E402
from mesh import box, cyl, diff, inter, loft_rings, mirror_y, revolve, union  # noqa: E402

# --- V21 shape (full-scale m) --------------------------------------------------------------------------------------
INTAKE_V21 = {"x0": 1.40, "x_cheek": 1.75, "x1": 2.25, "y_out": 0.90, "y_cheek": 0.56, "z0": -0.15, "z1": 0.27,
              "z_cheek": 0.18, "bury": 0.30,
              # PET duct inside the body: mouth -> above the payload bay, inboard of the front duct lip -> fan face
              "duct_pts": [(1.65, 0.42, 0.045), (2.40, 0.38, -0.04), (3.36, 0.37, -0.14), (3.75, 0.34, -0.14),
                           (3.97, 0.13, P.CRUISE_FAN_Z)]}          # passes under the 4 mm centre spar at x 3.36
HATCH_Z = 0.24                         # nose hatch split height: the opening there (about 55 mm mini) passes the 43 mm bundles
ESC_X = 2.50                           # EDF ESC centre: G4 had 2.60, 100 mm ahead keeps it clear of the 4-in-1 ESC
# flattened (2D-style) nozzle: the V20 round nozzle squashed to an oval of the same areas (inlet 0.40 x 0.225 semi-axes,
# exit 0.36 x 0.20), its axis raised to z +0.03 so the top stays inside the V20 tail (no fairing, no extra mass aft)
NOZZLE_SY, NOZZLE_SZ = 4 / 3, 0.75
NOZZLE_V21 = {"r0": 0.30, "z": 0.03, "b0": 0.30 * NOZZLE_SZ}
TUBE_KINK = (8.30, -0.04)              # thrust tube: V20 line to here (clear of the spine servos), then into the oval
FLOAT_Y = 2.75                         # between the front duct (outer lip y 2.28) and the rear duct (x >= 3.52)
FLOAT_GAP = 0.06                       # float top below the wing's lower surface (the strut length)
POD_T = 0.015                          # drop-in pod liner wall (mini 1.5 mm)
# G10 option B (Alek, 2026-11-18): the outboard half of every lift-fan exit is cut up by 5 mm (mini), a scarf, so the
# rim that meets the water first in a heel sits higher. Same scarf on all four pods (one pod design; the left ones are
# the right ones turned 180 deg). The exit vanes move up by the same amount. ESTIMATE: its thrust cost is measured on
# the G7 W1 stand (scarfed pod vs plain pod); until it passes, the water-mode wave limit stays at the plain-exit value.
EXIT_SCARF = 0.05


def exit_points(n_rim: int = 16) -> list:
    """[(row, x, y, z)] sample points round every lift-fan exit rim, full scale, with the outboard half scarfed."""
    out = []
    for name, dx, dy in P.duct_centres():
        for a in np.linspace(0, 2 * math.pi, n_rim, endpoint=False):
            y_off = P.DUCT_ID / 2 * math.sin(a)
            outboard = y_off * dy > 1e-9
            out.append((name.split("_")[0], dx + P.DUCT_ID / 2 * math.cos(a), dy + y_off,
                        -P.BODY_HALF_T + (EXIT_SCARF if outboard else 0.0)))
    return out


def scarf_cutter(dx: float, dy: float):
    """The block the scarf removes below one exit: the outboard half of the duct footprint, up to 5 mm above the exit."""
    z_exit = -P.DUCT_DEPTH / 2 - 0.01
    r = GEO.R_OUT + 0.005
    y0, y1 = (dy, dy + r + 0.01) if dy > 0 else (dy - r - 0.01, dy)
    return inter(box(dx - r - 0.01, dx + r + 0.01, y0, y1, -1.0, z_exit + EXIT_SCARF),
                 cyl([dx, dy, -1.0], [dx, dy, 0.0], r, 128))
CELL_D, CELL_L = 0.217, 0.705          # 21700 cell with wrap (mini 21.7 x 70.5 mm)
PACK_CLEAR = 0.025                     # cell to outer skin (mini 2.5 mm: 1.2 mm wall + 1.3 mm foam pad)
WING_BOLTS = [(3.10, 0.66), (4.90, 0.66)]   # (x, |y|): clear of the front duct (x 2.32-2.80 at this y) and the intake
PETG_KG_M2 = AM.PETG_SHELL_KG_M2


NOSE_STRETCH = 0.50                    # full-scale m inserted ahead of the 1.05 m station (mini 50 mm): room for the pack (40 mm was enough before the V-tail grew)
_FUS_V20 = list(P.FUS)


def stretch_nose(d: float) -> None:
    """Insert d of constant section ahead of the V20 1.05 m station: the nose tip moves to x = -d."""
    f = _FUS_V20
    P.FUS[:] = [(f[0][0] - d,) + f[0][1:], (f[1][0] - d,) + f[1][1:], (f[2][0] - d,) + f[2][1:]] + f[2:]
    P.FUS_LEN = P.FUS[-1][0]


def build_fuselage_v21():
    x0 = P.FUS[0][0]
    xs = np.concatenate([np.linspace(x0 + 0.04, x0 + 0.6, 10), np.linspace(x0 + 0.7, P.FUS_LEN, 50)])
    return loft_rings([GEO.fus_ring(x) for x in xs], cap_start=True, cap_end=True, start_point=(x0, 0.0, 0.0))


VTAIL_V21: dict = {"span": 2.9}                   # overrides of the V-tail (v20params.VTAIL keys)


def apply_shape() -> None:
    """Put the V21 outer mould line into the (copied) V20 modules. The hull itself stays in hydro/amphib."""
    if NOSE_STRETCH:
        stretch_nose(NOSE_STRETCH)
        GEO.build_fuselage = build_fuselage_v21
    P.INTAKE.update(INTAKE_V21)
    P.NOZZLE.update(NOZZLE_V21)
    P.VTAIL.update(VTAIL_V21)
    H.WET_BAY = True
    S._OML = None                       # the sizing caches the outer mould line: rebuild it with the new shape


def thrust_tube_tail():
    """The thrust tube's last section: round (r 0.30) at the kink, morphing into the oval nozzle inlet."""
    x0, z0 = TUBE_KINK
    x1, z1 = P.NOZZLE["x0"], P.NOZZLE["z"]
    rings = []
    for u in np.linspace(0, 1, 16):
        x, zc = x0 + u * (x1 - x0), z0 + u * (z1 - z0)
        a, b = 0.30 * (1 + u * (NOZZLE_SY - 1)), 0.30 * (1 + u * (NOZZLE_SZ - 1))
        rings.append(np.array([(x, a * math.cos(t), zc + b * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 40, endpoint=False)]))
    return loft_rings(rings)


_BUILD_OML = GEO.build_oml
_BUILD_NOZZLE = GEO.build_nozzle


def nozzle_v21():
    """The V20 nozzle and cone built on the axis, squashed into the oval, then raised."""
    z = P.NOZZLE["z"]
    P.NOZZLE["z"] = 0.0
    try:
        ms = _BUILD_NOZZLE()
    finally:
        P.NOZZLE["z"] = z
    out = []
    for m in ms:
        m = m.copy()
        m.apply_scale([1.0, NOZZLE_SY, NOZZLE_SZ])
        m.apply_translation([0, 0, z])
        out.append(m)
    return tuple(out)


def oml_v21(main_x: float):
    """V21 outer mould line for the sizing (no hull: amphib adds its mass): no wheels, the oval nozzle."""
    GEO.build_nozzle = nozzle_v21
    try:
        return [p for p in _BUILD_OML(main_x) if p[2] != "gear"]
    finally:
        GEO.build_nozzle = _BUILD_NOZZLE


def wing_bottom_z(oml, x0: float, x1: float, y: float) -> float:
    wing = next(m for n, m, _l in oml if n == "wing_R")
    v = wing.vertices
    sel = (np.abs(v[:, 1] - y) < 0.12) & (v[:, 0] >= x0) & (v[:, 0] <= x1)
    return float(v[sel, 2].min())


def place_floats(oml) -> dict:
    zb = wing_bottom_z(oml, 2.5, 3.3, FLOAT_Y)
    H.FLOAT.update({"y": FLOAT_Y, "z": zb - FLOAT_GAP - H.FLOAT["r"]})
    return {"wing_bottom_z": zb, "float_z": H.FLOAT["z"]}


def g5_mass_items(oml) -> list:
    """Extra V21 hardware (mini kg) for the sizing: pod liners, drain holes are free, wing bolts."""
    s = 0.1
    liner = pod_liner()
    liner_kg = float(liner.area) * s * s * PETG_KG_M2 / 2      # a 1.5 mm wall: half the 2-skin shell estimate
    xc = float(np.mean([x for _n, x, _y in P.duct_centres()]))
    return [("G5 drop-in fan pod liners x4 (PETG, ESTIMATE)", xc, 0.0, 0.0, 4 * liner_kg, "propulsion"),
            ("G5 nylon M4 wing shear bolts x4 + heat-set inserts (ESTIMATE)", 4.0, 0.0, 0.0, 0.006, "airframe")]


def pod_liner():
    d2 = P.DUCT_DEPTH / 2
    r0 = GEO.R_ID
    prof = [(r0, -d2), (r0 + POD_T, -d2), (r0 + POD_T, d2 - 0.02), (r0, d2 - 0.02)]
    return revolve(prof, 128)


# --- sizing + float ------------------------------------------------------------------------------------------------
BAY_FWD = 1.00                         # forward limit of the pack centre (full-scale m); the fit search decides if it is real
BELLY_V21: dict = {"x1": 7.0}                   # overrides of the G4 belly (hydro.BELLY keys)
FLOAT_V21: dict = {"x0": 1.55, "x1": 3.55}                   # overrides of the G4 float x0 / x1 (full-scale m)


def size_and_float() -> dict:
    R = g4.RECOMMENDED
    GEO.build_oml = oml_v21
    S._OML = None
    oml = S.oml()
    g4.set_layout(BAY_FWD, R["float_x_m"], R["float_r_m"], R["belly_x_m"], ESC_X)
    H.BELLY.update(BELLY_V21)
    H.FLOAT.update(FLOAT_V21)
    import aero as A
    A.EXTRA_BODIES[:] = [(2 * H.FLOAT["r"], H.FLOAT["x1"] - H.FLOAT["x0"], H.FLOAT["x0"])] * 2   # the two floats
    S._AERO.clear()                         # the belly sits inside the fuselage planform: not counted again
    fl = place_floats(oml)
    if not any(i[0].startswith("G5 ") for i in AM.WET_KIT):
        AM.WET_KIT.extend(g5_mass_items(oml))
    H.BELLY["depth"] = BELLY_V21.get("depth", R["belly_depth_m"])
    c = AM.size_case(**g4.LOCKED, gear=R["gear"])
    h = H.analyse(oml, "vbelly", c["mass_g"] / 1000, c["cg_m"])
    c["hydro"] = h
    c["float_mount"] = fl
    c["raise_needed_mm"] = {k: max(0.0, g4.SPRAY_MARGIN_MM - v) for k, v in h.get("freeboard_mm", {}).items()}
    c["taxi"] = [dict(t, edf_thrust_frac=t["total_n"] / g4.EDF_STATIC_N) for t in h.get("taxi", [])]
    c["gates"] = {
        "lift T/W >= 1.9": (c["tw"], c["tw_ok"]),
        "static margin >= 5 %": (c["sm_pct"], c["sm_ok"]),
        "CG within 3 mm of fan centroid": (c["cg_offset_mm"], abs(c["cg_offset_mm"]) <= g4.CG_TOL_MM),
        "reserve buoyancy >= 100 % (sealed)": (h["reserve_sealed_pct"], h["reserve_sealed_pct"] >= 100),
        **{f"freeboard >= {g4.SPRAY_MARGIN_MM:.0f} mm: {k}": (v, v >= g4.SPRAY_MARGIN_MM) for k, v in h.get("freeboard_mm", {}).items()},
    }
    c["intake_mouth_m2_full"] = GEO.intake_mouth_area_m2()
    return c


# --- 4S2P fit ------------------------------------------------------------------------------------------------------
def _cells(axis: str, grid: tuple, xc: float, zc: float):
    """Cell axes [(p0, p1)] for an n_a x n_z x n_axis block centred on (xc, 0, zc)."""
    na, nz, nl = grid
    out = []
    for i in range(na):
        for k in range(nz):
            for j in range(nl):
                a = (i - (na - 1) / 2) * CELL_D
                z = zc + (k - (nz - 1) / 2) * CELL_D
                l = (j - (nl - 1) / 2) * CELL_L
                if axis == "x":
                    out.append(((xc + l - CELL_L / 2, a, z), (xc + l + CELL_L / 2, a, z)))
                else:
                    out.append(((xc + a, l - CELL_L / 2, z), (xc + a, l + CELL_L / 2, z)))
    return out


def _probe(cells):
    """Points on every cell's outside, pushed out by the clearance."""
    r = CELL_D / 2 + PACK_CLEAR
    pts = []
    for p0, p1 in cells:
        p0, p1 = np.array(p0), np.array(p1)
        ax = (p1 - p0) / np.linalg.norm(p1 - p0)
        u = np.cross(ax, [0, 0, 1.0]) if abs(ax[2]) < 0.9 else np.cross(ax, [0, 1.0, 0])
        u /= np.linalg.norm(u)
        w = np.cross(ax, u)
        for t in np.linspace(-PACK_CLEAR, 1 + PACK_CLEAR, 6):
            c = p0 + (p1 - p0) * t
            for a in np.linspace(0, 2 * math.pi, 12, endpoint=False):
                pts.append(c + r * (math.cos(a) * u + math.sin(a) * w))
    return np.array(pts)


def fit_pack(oml, battery_x: float) -> dict:
    """The 4S2P as two 4-cell bundles (2 x 2 cells lying fore-aft, wired in series), each free to sit at its own
    height, their mean x on the sizing's battery x. Tries the closest spacing first and, for each bundle, the highest
    position that clears the skin (fuselage + belly), the payload bay and the intake ducts by PACK_CLEAR."""
    parts = {n: m for n, m, _l in oml}
    env = union(parts["fuselage"], H.belly())
    keep_out = [GEO.bay_box(), GEO.intake_duct(1), GEO.intake_duct(-1)]

    def frac(cells):
        pts = _probe(cells)
        good = GEO.inside_test(env, pts)
        for m in keep_out:
            good &= ~m.contains(pts)
        return float(good.mean())

    def highest(x):
        best = (0.0, None)
        for zc in np.arange(0.10, -0.80, -0.02):
            f = frac(_cells("x", (2, 2, 1), x, float(zc)))
            if f >= 0.999:
                return float(zc), f
            best = max(best, (f, float(zc)))
        return None, best[0]

    tried = []
    for half in np.arange(0.36, 0.84, 0.04):
        xf, xr = battery_x - half, battery_x + half
        zf, ff = highest(xf)
        zr, fr = highest(xr)
        tried.append({"half_spacing": round(float(half), 2), "front": [round(xf, 2), zf, round(ff, 3)], "rear": [round(xr, 2), zr, round(fr, 3)]})
        if zf is not None and zr is not None:
            cells = _cells("x", (2, 2, 1), xf, zf) + _cells("x", (2, 2, 1), xr, zr)
            zs = [p[2] for c in cells for p in c]
            return {"battery_x_m": battery_x, "fits": True, "axis": "x", "grid": [2, 2, 2], "bundles": tried[-1],
                    "tried": tried, "mesh": union(*[cyl(p0, p1, CELL_D / 2 - 0.002, 24) for p0, p1 in cells]),
                    "z_range": [min(zs) - CELL_D / 2, max(zs) + CELL_D / 2],
                    "below_fuselage_bottom_m": max(0.0, max(P.fus_at(x)[1] - (z - CELL_D) for x, z in ((xf, zf), (xr, zr))))}
    return {"battery_x_m": battery_x, "fits": False, "tried": tried}


# --- roll stability on the water -----------------------------------------------------------------------------------
def roll_stability(oml, mass_kg: float, cg_m_mini: list, s: float = 0.1, angles=(2, 4, 5, 6, 8, 10, 15, 20, 30)) -> dict:
    """Righting arm GZ (mini mm, positive = rights itself) at each heel angle, heeling about the CG with the wings
    flooded (only the sealed body and the hull float), and the heel at which the lowest lift-fan exit on the low side
    reaches the water (downflooding). Pitch trim is left at zero (it is under 1 deg). ESTIMATE."""
    import trimesh
    body = H.body_meshes(oml)
    meshes = [body["sealed"]] + [m for _n, m in H.hull_parts("vbelly")]
    zcg = cg_m_mini[2] / s
    exits = [(x, y, z) for _row, x, y, z in exit_points()]
    rows = []
    for deg in angles:
        R = trimesh.transformations.rotation_matrix(math.radians(deg), [1, 0, 0], [0, 0, zcg])   # starboard up, port down
        lv = H.float_level([m.copy().apply_transform(R) for m in meshes], mass_kg, s)
        if lv.get("sinks"):
            rows.append({"heel_deg": deg, "sinks": True})
            continue
        pts = trimesh.transform_points(np.array(exits), R)
        rows.append({"heel_deg": deg, "gz_mm": -lv["cb"][1] * s * 1000,
                     "lowest_fan_exit_mm": float((pts[:, 2] - lv["z_wl"]).min()) * s * 1000})
    flood, prev = None, None
    for r in rows:                      # interpolated between the rows where the lowest exit crosses the water
        if "lowest_fan_exit_mm" not in r:
            continue
        if prev and prev["lowest_fan_exit_mm"] > 0 >= r["lowest_fan_exit_mm"]:
            a, b = prev["lowest_fan_exit_mm"], r["lowest_fan_exit_mm"]
            flood = round(prev["heel_deg"] + (r["heel_deg"] - prev["heel_deg"]) * a / (a - b), 2)
            break
        prev = r
    return {"rows": rows, "downflooding_heel_deg": flood, "righting_all": all(r.get("gz_mm", -1) > 0 for r in rows)}


# --- the build -----------------------------------------------------------------------------------------------------
def hull_oml(oml_base, pack: dict) -> list:
    """Hull, skid, pods, drain holes, nose hatch and bolts added to the outer mould line for the print set and model."""
    parts = list(oml_base)
    names = {n: i for i, (n, _m, _l) in enumerate(parts)}
    for n, m in H.hull_parts("vbelly"):
        parts.append((n, m, "skin"))
    # float struts: one per float, from its top to the wing's lower surface
    for sd, sg in (("R", 1), ("L", -1)):
        xs = (H.FLOAT["x0"] + H.FLOAT["x1"]) / 2 + 0.55
        ztop = H.FLOAT["z"] + H.FLOAT["r"] * 0.7
        parts.append((f"float_strut_{sd}", cyl([xs, sg * FLOAT_Y, ztop], [xs, sg * FLOAT_Y, ztop + FLOAT_GAP + 0.10], 0.045, 20), "skin"))
    # skid shoe under the belly keel: a replaceable TPU wedge from x 1.6 to 5.4
    b = H.BELLY
    rings = []
    for x in np.linspace(1.6, 5.4, 24):
        f = min(1.0, (x - b["x0"]) / b["bow_taper"])
        f = 0.15 + 0.85 * (3 * f * f - 2 * f ** 3)
        keel = P.fus_at(x)[1] - b["depth"] * f
        rings.append(np.array([[x, -0.07, keel + 0.05], [x, 0.07, keel + 0.05], [x, 0.0, keel - 0.04]]))
    parts.append(("skid_shoe", loft_rings(rings), "skin"))
    # payload bay doors: four 4 mm (mini) drain holes each (the bay floods and drains by design)
    for sd in "RL":
        i = names[f"bay_door_{sd}"]
        n, m, layer = parts[i]
        sg = 1 if sd == "R" else -1
        holes = [cyl([x, sg * 0.14, -1.0], [x, sg * 0.14, 0.0], 0.02, 12) for x in np.linspace(P.PAYLOAD_BAY["x0"] + 0.12, P.PAYLOAD_BAY["x1"] - 0.12, 4)]
        parts[i] = (n, diff(m, *holes), layer)
    # lift ducts: bore opened by the liner wall; one identical drop-in pod liner per fan
    bore = cyl([0, 0, -1], [0, 0, 1], GEO.R_ID + POD_T, 128)
    liner = pod_liner()
    for dn, dx, dy in P.duct_centres():
        i = names[f"duct_{dn}"]
        n, m, layer = parts[i]
        c = bore.copy()
        c.apply_translation([dx, dy, 0])
        parts[i] = (n, diff(m, c), layer)
        lp = liner.copy()
        lp.apply_translation([dx, dy, 0])
        if EXIT_SCARF > 0:          # G10 B: scarf the outboard half of the exit (duct ring and pod), vanes up to match
            cut = scarf_cutter(dx, dy)
            parts[i] = (n, diff(parts[i][1], cut), layer)
            lp = diff(lp, cut)
            j = names[f"vanes_{dn}"]
            vn, vm, vl = parts[j]
            parts[j] = (vn, vm.copy().apply_translation([0, 0, EXIT_SCARF]), vl)
        parts.append((f"duct_pod_{dn}", lp, "propulsion"))
    # nose hatch over the pack (gasketed lid, well above the waterline): the pack lifts out upwards
    if pack.get("fits"):
        x0, x1 = pack["mesh"].bounds[0][0] - 0.06, pack["mesh"].bounds[1][0] + 0.06
        zcut = HATCH_Z
        i = names["fuselage"]
        n, m, layer = parts[i]
        lid = box(x0, x1, -1, 1, zcut, 2)
        parts[i] = (n, diff(m, lid), layer)
        parts.append(("nose_hatch", inter(m, lid), "skin"))
    # nylon shear bolts (hardware, not printed)
    for x, y in WING_BOLTS:
        for sd, sg in (("R", 1), ("L", -1)):
            parts.append((f"wing_bolt_M4_nylon_{sd}_{x:.1f}", cyl([x, sg * y, -0.12], [x, sg * y, 0.12], 0.02, 12), "hardware"))
    return parts


_INSIDE = GEO.inside_parts


def inside_v21(pack: dict, esc_x: float):
    def f(scale_key, sizing):
        out = []
        for n, m, layer, note in _INSIDE(scale_key, sizing):
            if n.startswith("battery_"):
                if pack.get("fits"):
                    g = "x".join(str(v) for v in pack["grid"])
                    out.append(("battery_4S2P_21700", pack["mesh"], "systems",
                                f"4S2P Li-ion pack: 8 x 21700 cells, {g} block lying {'fore-aft' if pack['axis'] == 'x' else 'across'}, "
                                "in the nose under a gasketed hatch (fit from tools/v21/g5.py; ESTIMATE until printed)"))
                continue
            if n == "edf_esc_60a":
                m = box(esc_x - 0.30, esc_x + 0.29, -0.13, 0.13, -0.27, -0.17)
                note = "EDF ESC moved 100 mm (mini) forward of V20, between the intake ducts"
            if n == "thrust_tube":
                a = [P.CRUISE_FAN_X + 0.37, 0, P.CRUISE_FAN_Z]
                k = [TUBE_KINK[0], 0, TUBE_KINK[1]]
                e = [P.NOZZLE["x0"], 0, P.NOZZLE["z"]]
                m = union(cyl(a, k, 0.30, 48), thrust_tube_tail(), GEO.trimesh.creation.icosphere(2, 0.30).apply_translation(k))
                note = "0.2 mm PET film thrust tube, V20 line to x 830 mm (mini), then morphing into the raised oval nozzle"
            out.append((n, m, layer, note))
        return out
    return f


def build(c: dict, pack: dict) -> dict:
    GEO.TAG = "v21"
    GEO.ENVELOPE_PARTS = GEO.ENVELOPE_PARTS + ("belly", "nose_hatch")
    base = oml_v21
    GEO.build_oml = lambda main_x: hull_oml(base(main_x), pack)
    GEO.inside_parts = inside_v21(pack, ESC_X)
    try:
        sizing = {"cg_m": c["cg_m"], "battery_x_m": c["battery_x_mm"] / 1000}
        return GEO.build("mini", sizing)
    finally:
        GEO.build_oml, GEO.inside_parts = base, _INSIDE


def main(argv) -> int:
    t0 = time.time()
    GEO.set_variant("mini")
    apply_shape()
    c = size_and_float()
    print(AM.row(c))
    for k, (v, ok) in c["gates"].items():
        print(f"  {'PASS' if ok else 'FAIL'}  {k}: {v:.1f}")
    h = c["hydro"]
    print(f"  float trim {h.get('trim_nose_up_deg', 0):+.1f} deg, sealed {h['volume_sealed_l']:.2f} L, displacement {h['displacement_l']:.2f} L; "
          f"floats y {FLOAT_Y} z {H.FLOAT['z']:.2f} (wing bottom {c['float_mount']['wing_bottom_z']:.2f})")
    for t in c["taxi"]:
        print(f"  taxi {t['V']:.1f} m/s: {t['total_n']:.2f} N = {100 * t['edf_thrust_frac']:.0f} % EDF static")
    print(f"  intake mouths {c['intake_mouth_m2_full']:.3f} m2 full scale (V20 0.222)")
    oml = S.oml()
    roll = roll_stability(oml, c["mass_g"] / 1000, c["cg_m"])
    c["roll"] = roll
    print("  roll (wings flooded): " + ", ".join(f"{r['heel_deg']} deg GZ {r.get('gz_mm', float('nan')):+.1f} mm" for r in roll["rows"])
          + f"; a low-side fan exit reaches the water at {roll['downflooding_heel_deg']} deg (exit scarf {EXIT_SCARF * 100:.0f} mm)")
    pack = fit_pack(oml, c["battery_x_mm"] / 100)
    print("  pack fit:", {k: v for k, v in pack.items() if k not in ("mesh", "tried")})
    if not pack["fits"]:
        print("  tries:", pack["tried"])
    out = {"basis": "ESTIMATE: V21 G5 shape (tools/v21/g5.py) on the G4 layout; nothing printed, floated or flown",
           "sizing": {k: v for k, v in c.items() if k not in ("groups_g",)},
           "pack": {k: v for k, v in pack.items() if k != "mesh"}}
    if "--no-build" not in argv:
        r = build(c, pack)
        ch = r["checks"]
        out["checks"] = ch
        out["parts"] = r["parts"]
        print(f"  build: {len(r['parts'])} parts, checks {ch['status']}")
        bad = {n: v for n, v in ch["inside_fuselage_fraction"].items() if v < 0.98}
        print("  outside the shell:", bad or "none")
        print("  internal collisions (cm3):", ch["internal_collisions"] or "none")
        print("  tip gap", ch["prop_tip_gap_mm"], "mm; watertight", all(ch["watertight"].values()),
              [n for n, v in ch["watertight"].items() if not v], "; print pieces watertight", ch.get("watertight_print_pieces"))
        nf = [n for n, v in ch.get("P1S", {}).items() if not v["fits"]]
        print(f"  P1S pieces: {len(ch.get('P1S', {}))}, not fitting: {nf or 'none'}")
        # G7 W1 compares a scarfed pod with a plain one: one plain (unscarfed) pod liner, mini mm, centred on its axis.
        # It is also the fallback pod if the scarf costs thrust. Not part of the assembly.
        plain = pod_liner().copy()
        plain.apply_scale(100.0)
        out_dir = ROOT / "cad" / "v21" / "mini" / "test"
        out_dir.mkdir(parents=True, exist_ok=True)
        plain.export(out_dir / "duct_pod_PLAIN_W1_test_and_fallback.stl")
        print(f"  wrote cad/v21/mini/test/duct_pod_PLAIN_W1_test_and_fallback.stl (watertight {plain.is_watertight})")
    (ROOT / "analysis" / "v21_g5.json").write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o)))
    print(f"wrote analysis/v21_g5.json ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
