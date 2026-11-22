"""V21 "Ryujin" hydrostatics: hull add-ons, floating waterline, reserve buoyancy and freeboard at the openings.

Screening model, every result an ESTIMATE until the G7 float and leak test:
  * level float (no pitch or heel trim solved); the centre of buoyancy is reported against the CG so the trim
    error can be seen,
  * the four lift ducts and the two EDF intakes are open to the water (they flood), so they give no buoyancy,
  * "sealed" volume = fuselage + canopy + spine + hull add-ons. The printed wings are counted separately: single-wall
    LW prints are not watertight unless coated, so the conservative reserve leaves them out,
  * freshwater (1000 kg/m3); saltwater (1025) floats about 2.5 % higher but needs its own corrosion gate.

Geometry is in full-scale metres (the V20 frame: x aft from the nose, y starboard, z up); the mini is s = 0.1, so a
mini mass of M kg displaces M / 1000 m3 of water = M m3 of full-scale shape.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mesh as MESH  # noqa: E402
import v20params as P  # noqa: E402

RHO_FRESH, RHO_SALT = 1000.0, 1025.0
NU_WATER = 1.0e-6               # kinematic viscosity of fresh water at about 20 C (m2/s)
G0 = 9.80665

# ---------------------------------------------------------------------------------------------------------------
# hull add-ons (full-scale metres). The lift-fan exits sit on the shoulders between y = 0.58 and 3.17 (front pair
# 0.58-2.28, rear 1.49-3.17): anything below the shoulders in that band would block a fan, so a belly must stay
# inside the fuselage (|y| < 0.54) and floats or sponsons must sit outboard of the rear fans (|y| > 3.2).
BELLY = {"x0": 1.40, "x1": 8.20, "half_width": 0.50, "depth": 0.25, "bow_taper": 1.2, "z_top": -0.30}
STEP_X = 4.00                   # planing step just behind the CG (stepped option)
STEP_H = 0.05
FLOAT = {"y": 3.55, "x0": 4.00, "x1": 6.40, "r": 0.17, "z": -0.32}          # outrigger float under each outer wing
WET_BAY = False                 # V21 G5: the payload bay is a free-flooding tub outside the sealed volume (doors drain)
SPONSON = {"y": 3.70, "x0": 2.40, "x1": 6.80, "r": 0.30, "z": -0.40}        # big pontoon outboard of each rear fan


def _fus_bottom(x: float) -> float:
    return P.fus_at(x)[1]


def belly(stepped: bool = False, depth: float | None = None) -> trimesh.Trimesh:
    """A V-bottom displacement belly under the fuselage keel (deadrise from half-width and depth); the bow tapers in."""
    b = BELLY
    h = b["depth"] if depth is None else depth
    rings = []
    for x in np.linspace(b["x0"], b["x1"], 36):
        f = min(1.0, (x - b["x0"]) / b["bow_taper"])
        f = 0.15 + 0.85 * (3 * f * f - 2 * f ** 3)
        keel = _fus_bottom(x) - h * f
        if stepped and x > STEP_X:
            keel += STEP_H
        hw = b["half_width"] * f
        rings.append(np.array([[x, -hw, b["z_top"]], [x, hw, b["z_top"]], [x, 0.0, keel]]))
    return MESH.loft_rings(rings)


def pontoon(spec: dict, side: int) -> trimesh.Trimesh:
    p0 = (spec["x0"], side * spec["y"], spec["z"])
    p1 = (spec["x1"], side * spec["y"], spec["z"])
    return MESH.cyl(p0, p1, spec["r"])


def hull_parts(hull: str) -> list:
    """[(name, mesh)] of the add-on hull for an option key."""
    if hull == "vbelly":
        return [("belly", belly()), ("float_R", pontoon(FLOAT, 1)), ("float_L", pontoon(FLOAT, -1))]
    if hull == "stepped":
        return [("belly", belly(stepped=True)), ("float_R", pontoon(FLOAT, 1)), ("float_L", pontoon(FLOAT, -1))]
    if hull == "sponsons":
        return [("sponson_R", pontoon(SPONSON, 1)), ("sponson_L", pontoon(SPONSON, -1))]
    if hull == "none":
        return []
    raise ValueError(hull)


# ---------------------------------------------------------------------------------------------------------------
def body_meshes(oml) -> dict:
    """The airframe's buoyant solids from the V20 outer mould line, ducts cut out (they flood)."""
    parts = {n: m for n, m, _l in oml}
    cut = [MESH.cyl((x, y, -0.6), (x, y, 0.6), P.DUCT_ID / 2 + P.DUCT_LIP) for _n, x, y in P.duct_centres()]
    sealed = MESH.union(parts["fuselage"], parts["canopy"], parts["spine"])
    wings = MESH.diff(MESH.union(parts["wing_R"], parts["wing_L"]), *cut)
    wings = MESH.diff(wings, sealed)            # the wing roots overlap the fuselage: count that volume once
    return {"sealed": sealed, "wings": wings}


def submerged(mesh: trimesh.Trimesh, z: float) -> tuple[float, np.ndarray, float]:
    """(volume, centroid, wetted area) of the part of a closed mesh below the plane z."""
    if mesh.bounds[0][2] >= z:
        return 0.0, np.zeros(3), 0.0
    if mesh.bounds[1][2] <= z:
        return float(mesh.volume), np.array(mesh.center_mass), float(mesh.area)
    (x0, y0, z0), (x1, y1, _z1) = mesh.bounds
    cut = MESH.inter(mesh, MESH.box(x0 - 1, x1 + 1, y0 - 1, y1 + 1, z0 - 1, z))   # manifold boolean, no extra deps
    if cut is None or len(cut.faces) == 0:
        return 0.0, np.zeros(3), 0.0
    vol = abs(float(cut.volume))
    on_cap = (np.abs(cut.face_normals[:, 2] - 1.0) < 1e-6) & (np.abs(cut.triangles_center[:, 2] - z) < 1e-6)
    cap = float(np.sum(cut.area_faces[on_cap]))
    return vol, np.array(cut.center_mass), float(cut.area) - cap


def float_level(meshes: list, mass_kg: float, s: float, rho: float = RHO_FRESH) -> dict:
    """Waterline z (full-scale m) where the submerged volume carries mass_kg (mini kg at scale s)."""
    need = mass_kg / rho / s ** 3                    # full-scale-shape m3
    z_lo = min(m.bounds[0][2] for m in meshes)
    z_hi = max(m.bounds[1][2] for m in meshes)

    def total(z):
        v, c, a = 0.0, np.zeros(3), 0.0
        for m in meshes:
            vi, ci, ai = submerged(m, z)
            v += vi
            c += vi * ci
            a += ai
        return v, (c / v if v > 0 else c), a

    if total(z_hi)[0] < need:
        return {"sinks": True, "need_m3": need}
    lo, hi = z_lo, z_hi
    for _ in range(40):
        mid = (lo + hi) / 2
        if total(mid)[0] < need:
            lo = mid
        else:
            hi = mid
    v, cb, wet = total(hi)
    return {"sinks": False, "z_wl": hi, "need_m3": need, "cb": cb.tolist(), "wetted_m2": wet}


def openings() -> dict:
    """Openings that must stay dry while floating: name -> [(x, z)] sample points along the lowest edge (full scale)."""
    xs = lambda a, b: np.linspace(a, b, 7)
    fan = [(x, -P.BODY_HALF_T) for r in P.rows() for x in xs(P.DUCT_X[r] - P.DUCT_ID / 2, P.DUCT_X[r] + P.DUCT_ID / 2)]
    bay = (P.PAYLOAD_BAY["x0"], P.PAYLOAD_BAY["x1"])
    return {
        "lift-fan exits (bottom louvres)": fan,
        "EDF side intakes (lower lip)": [(x, P.INTAKE["z0"]) for x in xs(P.INTAKE["x0"], P.INTAKE["x_cheek"])],
        **({} if WET_BAY else {"payload bay doors (belly skin)": [(x, _fus_bottom(x)) for x in xs(*bay)]}),
        "EDF nozzle (lower lip)": [(P.NOZZLE["x0"], P.NOZZLE.get("z", -0.01) - P.NOZZLE.get("b0", P.NOZZLE["r0"]))],
    }


def _pitch(m: trimesh.Trimesh, theta: float, x_pivot: float) -> trimesh.Trimesh:
    """Rotate a mesh nose-up by theta (rad) about the lateral axis through (x_pivot, 0, 0)."""
    if theta == 0.0:
        return m
    R = trimesh.transformations.rotation_matrix(theta, [0, 1, 0], [x_pivot, 0, 0])   # +theta about +y: aft goes down
    return m.copy().apply_transform(R)


def _pt(x, z, theta, xp):
    """Point (x, z) after the same nose-up pitch."""
    dx = x - xp
    return xp + dx * math.cos(theta) + z * math.sin(theta), -dx * math.sin(theta) + z * math.cos(theta)


def float_trimmed(meshes: list, mass_kg: float, s: float, x_cg: float, rho: float = RHO_FRESH) -> dict:
    """Free float in pitch: the nose-up angle where the centre of buoyancy sits under the CG (x_cg full-scale m)."""
    def at(theta):
        ms = [_pitch(m, theta, x_cg) for m in meshes]
        lv = float_level(ms, mass_kg, s, rho)
        return lv, (lv["cb"][0] - x_cg) if not lv["sinks"] else None

    lo, hi = math.radians(-12), math.radians(12)
    lv_lo, e_lo = at(lo)
    lv_hi, e_hi = at(hi)
    if e_lo is None or e_hi is None or e_lo * e_hi > 0:     # no balance inside +/-12 deg: report the level float
        lv, e = at(0.0)
        lv.update({"theta_deg": 0.0, "trim_found": False, "cb_minus_cg_m": e})
        return lv
    for _ in range(18):
        mid = (lo + hi) / 2
        lv, e = at(mid)
        if e is None:
            break
        if (e > 0) == (e_lo > 0):
            lo, e_lo = mid, e
        else:
            hi = mid
    lv.update({"theta_deg": math.degrees(mid), "trim_found": True, "cb_minus_cg_m": e})
    return lv


def taxi_drag_n(V: float, wet_m2_full: float, length_m_full: float, s: float, rho: float = RHO_FRESH) -> dict:
    """Displacement-mode water resistance of the mini at V (m/s): ITTC-57 friction x (1 + k) plus a crude wave term
    that climbs steeply past hull speed (Froude number 0.4). ESTIMATE until a towed or bollard-pull test."""
    L = length_m_full * s
    S = wet_m2_full * s * s
    Re = max(V * L / NU_WATER, 1e4)
    cf = 0.075 / (math.log10(Re) - 2) ** 2
    rf = 0.5 * rho * V * V * S * cf * 1.25           # form factor 1.25 for a short, full hull
    fn = V / math.sqrt(G0 * L)
    rw = rf * (fn / 0.40) ** 4                        # wave making: small below Fn 0.3, dominant above 0.45
    return {"V": V, "Fn": fn, "friction_n": rf, "wave_n": rw, "total_n": rf + rw}


def analyse(oml, hull: str, mass_kg: float, cg_m_mini: list, s: float = 0.1, rho: float = RHO_FRESH,
            wings_buoyant: bool = False) -> dict:
    """Waterline (trimmed in pitch), reserve buoyancy, freeboard at each opening and water-taxi drag for one hull.
    wings_buoyant=False (the gate case): the printed wings flood, only the sealed body and the hull float it."""
    body = body_meshes(oml)
    add = hull_parts(hull)
    sealed_parts = [body["sealed"]] + [m for _n, m in add]
    floating = sealed_parts + ([body["wings"]] if wings_buoyant else [])
    x_cg = cg_m_mini[0] / s
    need = mass_kg / rho / s ** 3
    v_sealed = sum(float(m.volume) for m in sealed_parts)
    v_wings = float(body["wings"].volume)
    out = {
        "hull": hull, "mass_kg": mass_kg, "rho": rho, "wings_buoyant": wings_buoyant,
        "displacement_l": mass_kg / rho * 1000,
        "volume_sealed_l": v_sealed * s ** 3 * 1000, "volume_wings_l": v_wings * s ** 3 * 1000,
        "reserve_sealed_pct": (v_sealed / need - 1) * 100,
        "reserve_with_wings_pct": ((v_sealed + v_wings) / need - 1) * 100,
        "addon_volume_l": sum(float(m.volume) for _n, m in add) * s ** 3 * 1000,
    }
    lv = float_trimmed(floating, mass_kg, s, x_cg, rho)
    if lv.get("sinks"):
        out["sinks"] = True
        return out
    th, z = math.radians(lv["theta_deg"]), lv["z_wl"]
    fb = {}
    for k, pts in openings().items():
        fb[k] = min((_pt(x, zz, th, x_cg)[1] - z) for x, zz in pts) * s * 1000
    out.update({
        "sinks": False, "trim_nose_up_deg": lv["theta_deg"], "trim_found": lv["trim_found"],
        "cb_minus_cg_mm": lv["cb_minus_cg_m"] * s * 1000,
        "waterline_z_at_cg_mm": z * s * 1000,
        "freeboard_mm": fb,
        "openings_dry": all(v > 0 for v in fb.values()),
        "wetted_m2_mini": lv["wetted_m2"] * s * s,
    })
    out["taxi"] = [taxi_drag_n(v, lv["wetted_m2"], P.FUS_LEN, s, rho) for v in (0.5, 1.0, 1.5, 2.0)]
    return out
