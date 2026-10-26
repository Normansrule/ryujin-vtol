#!/usr/bin/env python3
"""V20 "Falcon Jet" geometry: the shared outer mould line plus each scale's insides.

    python3 tools/v20/geometry.py                 # both scales -> cad/v20/<scale>/ + site/models/raw/v20_<scale>.glb
    python3 tools/v20/geometry.py mini            # one scale

Everything is generated in full-scale metres from tools/v20/v20params.py and scaled at the end
(mini: 1 full-scale metre = 100 mm; full: 1 m = 1000 mm), so the two aircraft are the same shape by
construction. Parts carry a layer (skin, controls, structure, propulsion, systems, keepouts, payload),
a material per scale and a mass basis; tools/v20/sizing.py turns them into masses and the CG.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import Polygon

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
import v20params as P  # noqa: E402
from mesh import (box, cyl, diff, inter, loft_rings, mirror_y, naca_t, revolve, smoothstep,  # noqa: E402
                  surface_solid, union)

R_ID = P.DUCT_ID / 2
R_OUT = R_ID + P.DUCT_LIP
TIP_GAP = 0.018             # blade tip to duct wall (full-scale m): mini 1.8 mm, a 6-inch prop in a 156 mm duct


# ---------------------------------------------------------------------------------------------------
# planform helpers (full scale, metres)
def _outline_fn():
    pts = P.OUTLINE
    le_pts = [(pts[0][0], 0.0)] + pts[:4]               # chine ... tip LE
    tip_le, tip_te = pts[3], pts[4]
    te_pts = [tip_te] + pts[5:] + [(pts[-1][0], 0.0)]   # tip TE ... root TE
    le_y = np.array([p[1] for p in le_pts]); le_x = np.array([p[0] for p in le_pts])
    te = sorted(te_pts, key=lambda p: p[1])
    te_y = np.array([p[1] for p in te]); te_x = np.array([p[0] for p in te])
    return (lambda y: np.interp(y, le_y, le_x)), (lambda y: np.interp(y, te_y, te_x)), tip_le[1]


LE_X, TE_X, Y_TIP = _outline_fn()


def wing_half_thickness(x, y, chord, u):
    """Thin symmetric section, thickened smoothly around each duct into a fan fairing."""
    h = naca_t(u, P.T_C) * chord
    fair = np.zeros_like(h)
    for _n, dx, dy in P.duct_centres():
        if dy < 0:
            continue
        r = np.hypot(x - dx, y - dy)
        fair = np.maximum(fair, 1 - smoothstep(R_OUT + 0.02, R_OUT + 0.40, r))
    h_duct = P.DUCT_DEPTH / 2 + 0.012
    # stay a closed section at the leading and trailing edges
    edge = smoothstep(0.0, 0.06, u) * smoothstep(0.0, 0.06, 1 - u)
    return np.maximum(h, h_duct * fair * edge)


def build_wing():
    """Starboard strake + wing (one solid through the fuselage centreline), duct holes and elevon cut out."""
    ys = np.concatenate([np.linspace(0.0, 0.27, 4), np.linspace(0.30, Y_TIP, 70)])
    us = (1 - np.cos(np.linspace(0, math.pi, 64))) / 2
    le, te = LE_X(ys), TE_X(ys)
    ch = te - le
    X = le[:, None] + us[None, :] * ch[:, None]
    Y = np.repeat(ys[:, None], len(us), 1)
    H = wing_half_thickness(X, Y, ch[:, None], us[None, :])
    Pm = np.stack([X, Y, np.zeros_like(X)], -1)
    N = np.zeros_like(Pm)
    N[..., 2] = 1
    wing = surface_solid(Pm, N, H, hmin=0.002)
    holes = [cyl([dx, dy, -1], [dx, dy, 1], R_OUT, 96) for _n, dx, dy in P.duct_centres() if dy > 0]
    wing = diff(wing, *holes)
    # elevon: the aft chord_frac of the outer wing between y0 and y1
    e = P.ELEVON
    yv = np.linspace(e["y0"], e["y1"], 12)
    hinge = LE_X(yv) + (1 - e["chord_frac"]) * (TE_X(yv) - LE_X(yv))
    poly = Polygon(list(zip(hinge, yv)) + [(TE_X(yv[-1]) + 0.5, yv[-1]), (TE_X(yv[0]) + 0.5, yv[0])])
    prism = trimesh.creation.extrude_polygon(poly, 1.0)
    prism.apply_translation([0, 0, -0.5])
    elevon = inter(wing, prism)
    gap = trimesh.creation.extrude_polygon(poly.buffer(0.012), 1.0)
    gap.apply_translation([0, 0, -0.5])
    wing = diff(wing, gap)
    return wing, elevon


def duct_ring():
    """Bell-mouth duct wall around one lift fan (centred at the origin, axis z)."""
    d2 = P.DUCT_DEPTH / 2
    lip = P.DUCT_LIP
    prof = [(R_ID, -d2 - 0.01), (R_OUT, -d2 - 0.01), (R_OUT, d2 + 0.012)]
    for t in np.linspace(0, math.pi / 2, 10)[1:]:
        prof.append((R_ID + lip - lip * math.sin(t), d2 + 0.012 - lip * (1 - math.cos(t)) * 0.9))
    prof.append((R_ID, d2 - lip * 0.6))
    # profile must run counter-clockwise in (r, z)
    poly = Polygon(prof)
    if not poly.exterior.is_ccw:
        prof = prof[::-1]
    return revolve(prof, 128)


def exit_vanes():
    """Exit-vane cascade under one duct (as on the XV-5): four flat vanes spanning the exit, hinged spanwise (about y);
    deflected together they turn the efflux aft for transition thrust, differentially for yaw."""
    out = []
    for f in (-0.57, -0.19, 0.19, 0.57):
        x = f * R_ID
        half = math.sqrt(max(R_ID ** 2 - x ** 2, 0.0)) - 0.02
        out.append(box(x - 0.07, x + 0.07, -half, half, -P.DUCT_DEPTH / 2 - 0.05, -P.DUCT_DEPTH / 2 - 0.038))
    return union(*out)


def fan(coax: bool, blades: int, r_tip: float):
    """Hub, stators and rotor blade(s) for one lift duct (visual)."""
    parts = []
    hub_r = 0.14 * r_tip / 0.53 if r_tip > 0.2 else 0.14 * r_tip / 0.53
    hub = cyl([0, 0, -0.10], [0, 0, 0.08], hub_r, 48)
    parts.append(("hub", hub))
    for k in range(4):           # stators below the rotor(s)
        a = k * math.pi / 2 + math.pi / 4
        st = box(hub_r * 0.9, r_tip + 0.004, -0.006, 0.006, -0.10, -0.05)
        st.apply_transform(trimesh.transformations.rotation_matrix(a, [0, 0, 1]))
        parts.append(("stator", st))
    levels = [0.035, -0.02] if coax else [0.02]
    for li, zc in enumerate(levels):
        for k in range(blades):
            a = 2 * math.pi * k / blades + (math.pi / blades if li else 0.0)
            us = np.linspace(0, 1, 12)
            r = hub_r * 0.95 + us * (r_tip - TIP_GAP - hub_r * 0.95)
            c = 0.16 * r_tip * (1.15 - 0.55 * us)
            twist = np.radians(32 - 20 * us) * (1 if li == 0 else -1)
            pts_top, pts_bot = [], []
            for ri, ci, tw in zip(r, c, twist):
                for sgn, lst in ((1, pts_top), (-1, pts_bot)):
                    pass
            # blade as a thin twisted plate (surface_solid over r x chord)
            ug = np.linspace(-0.5, 0.5, 6)
            Xb = r[:, None] * np.ones_like(ug)[None, :]
            Yb = (c[:, None] * ug[None, :]) * np.cos(twist)[:, None]
            Zb = zc + (c[:, None] * ug[None, :]) * np.sin(twist)[:, None]
            Pm = np.stack([Xb, Yb, Zb], -1)
            N = np.zeros_like(Pm)
            N[..., 2] = np.cos(twist)[:, None]
            N[..., 1] = -np.sin(twist)[:, None]
            bl = surface_solid(Pm, N, np.full(Xb.shape, 0.006 * r_tip / 0.53), hmin=1e-4)
            bl.apply_transform(trimesh.transformations.rotation_matrix(a, [0, 0, 1]))
            parts.append(("blade", bl))
    return parts


# ---------------------------------------------------------------------------------------------------
def fus_ring(x, k=56, n_up=2.2, n_lo=1.75):
    w, zb, zt = P.fus_at(x)
    zc = min(max(P.CHINE_Z, zb + 0.3 * (zt - zb)), zt - 0.2 * (zt - zb)) if w > 0 else 0.0
    pts = []
    for t in np.linspace(0, 2 * math.pi, k, endpoint=False):
        c, s = math.cos(t), math.sin(t)
        if s >= 0:
            y = w * math.copysign(abs(c) ** (2 / n_up), c)
            z = zc + (zt - zc) * abs(s) ** (2 / n_up)
        else:
            y = w * math.copysign(abs(c) ** (2 / n_lo), c)
            z = zc - (zc - zb) * abs(s) ** (2 / n_lo)
        pts.append((x, y, z))
    return np.array(pts)


def build_fuselage():
    xs = np.concatenate([np.linspace(0.04, 0.6, 10), np.linspace(0.7, P.FUS_LEN, 46)])
    rings = [fus_ring(x) for x in xs]
    return loft_rings(rings, cap_start=True, cap_end=True, start_point=(0.0, 0.0, 0.0))


def build_canopy():
    c = P.CANOPY
    xs = np.linspace(c["x0"], c["x1"], 40)
    rings = []
    for x in xs:
        u = (x - c["x0"]) / (c["x1"] - c["x0"])
        up = (c["x_peak"] - c["x0"]) / (c["x1"] - c["x0"])
        prof = math.sin(math.pi * u) ** 0.5 if u < up else math.sin(math.pi * (0.5 + 0.5 * (u - up) / (1 - up))) ** 0.75
        prof = max(prof, 0.02)
        _w, _zb, zt = P.fus_at(x)
        h = (c["z_top"] - zt) * prof
        hw = c["half_width"] * max(math.sin(math.pi * u) ** 0.35, 0.05)
        ring = []
        for t in np.linspace(0, math.pi, 24):
            ring.append((x, hw * math.cos(t), zt - 0.04 + (h + 0.04) * math.sin(t) ** 0.8))
        ring.append((x, -hw * 0.98, zt - 0.08))
        ring.append((x, hw * 0.98, zt - 0.08))
        rings.append(np.array(ring))
    return loft_rings(rings)


def build_stab():
    s = P.STAB
    xs_out = P.stab_outline(1)
    yv = np.linspace(s["y_root"] - 0.12, s["y_tip"], 28)
    f = np.clip((yv - s["y_root"]) / (s["y_tip"] - s["y_root"]), 0, 1)
    le = s["x_le_root"] + f * (xs_out[1][0] - s["x_le_root"])
    ch = s["c_root"] + f * (s["c_tip"] - s["c_root"])
    us = (1 - np.cos(np.linspace(0, math.pi, 40))) / 2
    X = le[:, None] + us[None, :] * ch[:, None]
    Y = np.repeat(yv[:, None], len(us), 1)
    Pm = np.stack([X, Y, np.full(X.shape, s["z"])], -1)
    N = np.zeros_like(Pm)
    N[..., 2] = 1
    return surface_solid(Pm, N, naca_t(us, 0.045)[None, :] * ch[:, None], hmin=0.002)


def build_fin():
    """Starboard fin (canted outboard) and its rudder."""
    f = P.FIN
    sv = np.linspace(-0.06, f["height"], 24)
    g = np.clip(sv / f["height"], 0, 1)
    le = f["x_root_le"] + sv.clip(0) * math.tan(math.radians(f["le_sweep_deg"]))
    ch = f["root_chord"] + g * (f["tip_chord"] - f["root_chord"])
    out = []
    for name, (u0, u1) in (("fin", (0.0, 1 - f["rudder_frac"] - 0.01)), ("rudder", (1 - f["rudder_frac"] + 0.005, 1.0))):
        us = u0 + (u1 - u0) * (1 - np.cos(np.linspace(0, math.pi, 30))) / 2
        X = le[:, None] + us[None, :] * ch[:, None]
        S = np.repeat(sv[:, None], len(us), 1)
        Pm = np.stack([X, np.zeros_like(X), S], -1)
        N = np.zeros_like(Pm)
        N[..., 1] = 1
        H = np.maximum(naca_t(us, 0.05)[None, :] * ch[:, None], 0.004 if name == "rudder" else 0.002)
        m = surface_solid(Pm, N, H, hmin=0.002)
        m.apply_transform(trimesh.transformations.rotation_matrix(-math.radians(f["cant_deg"]), [1, 0, 0]))
        m.apply_translation([0, f["y_root"], f["z_root"]])
        out.append((name, m))
    return out


def build_intake():
    """Starboard side intake: a raked box on the fuselage side under the strake, open at the front."""
    it = P.INTAKE
    x0, x1 = it["x0"], it["x1"]
    w = P.fus_at(x0)[0]
    outer = Polygon([(w - 0.10, it["z0"]), (it["y_out"], it["z0"] + 0.05), (it["y_out"], it["z1"]), (w - 0.10, it["z1"])])
    body = trimesh.creation.extrude_polygon(outer, x1 - x0)
    # extrude_polygon builds along +z from (x, y) = (y, z) here; rotate into the aircraft frame
    T = np.array([[0, 0, 1, x0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
    body.apply_transform(T)
    rake = box(x0 - 0.5, x0 + 0.25, -2, 2, -2, 2)
    rake.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-25), [0, 0, 1], [x0, it["y_out"], 0]))
    body = diff(body, rake)
    inner = box(x0 - 0.2, x1 - 0.25, w + 0.02, it["y_out"] - 0.04, it["z0"] + 0.07, it["z1"] - 0.04)
    return diff(body, inner)


def build_nozzle():
    nz = P.NOZZLE
    prof = [(nz["r0"] - 0.035, nz["x0"]), (nz["r0"], nz["x0"]), (nz["r1"], nz["x1"]), (nz["r1"] - 0.03, nz["x1"])]
    poly = Polygon(prof)
    if not poly.exterior.is_ccw:
        prof = prof[::-1]
    m = revolve(prof, 96)
    # revolve is about z: map (r, z) -> aircraft frame with the axis along x at z = 0
    m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    m.apply_translation([0, 0, -0.01])
    cone = cyl([nz["x0"] + 0.05, 0, -0.01], [nz["x1"] - 0.12, 0, -0.01], nz["r1"] * 0.45, 32)
    return m, cone


def build_gear(main_x: float):
    g = P.GEAR
    parts = []
    zb_n = P.fus_at(g["nose_x"])[1]
    zw = zb_n - g["height"] + g["nose_wheel_d"] / 2
    parts.append(("gear_nose_leg", cyl([g["nose_x"], 0, zb_n + 0.05], [g["nose_x"], 0, zw], 0.035, 16)))
    parts.append(("gear_nose_wheel", cyl([g["nose_x"], -0.06, zw], [g["nose_x"], 0.06, zw], g["nose_wheel_d"] / 2, 32)))
    zb_m = P.fus_at(main_x)[1]
    zm = zb_n - g["height"] + g["wheel_d"] / 2
    for s, side in ((1, "R"), (-1, "L")):
        parts.append((f"gear_main_leg_{side}", cyl([main_x, s * 0.42, zb_m + 0.08], [main_x, s * g["main_y"], zm], 0.04, 16)))
        parts.append((f"gear_main_wheel_{side}", cyl([main_x, s * (g["main_y"] - 0.07), zm], [main_x, s * (g["main_y"] + 0.07), zm],
                                                    g["wheel_d"] / 2, 32)))
    return parts


def build_pilot():
    """Seated pilot (95th-percentile-ish envelope) and seat, full scale only."""
    x_hip, z_seat = 3.55, -0.30
    parts = [("pilot_torso", box(x_hip - 0.18, x_hip + 0.12, -0.21, 0.21, z_seat, z_seat + 0.62)),
             ("pilot_head", trimesh.creation.icosphere(subdivisions=2, radius=0.12)),
             ("pilot_legs", box(x_hip - 1.05, x_hip - 0.05, -0.17, 0.17, z_seat - 0.02, z_seat + 0.20)),
             ("seat", box(x_hip - 0.10, x_hip + 0.22, -0.26, 0.26, z_seat - 0.06, z_seat + 0.72))]
    parts[1][1].apply_translation([x_hip - 0.05, 0, z_seat + 0.78])
    return parts


# ---------------------------------------------------------------------------------------------------
def build_oml(main_x: float):
    """Outer-mould-line parts shared by both scales: [(name, mesh, layer)] in full-scale metres."""
    parts = []
    parts.append(("fuselage", build_fuselage(), "skin"))
    parts.append(("canopy", build_canopy(), "glass"))
    wing, elevon = build_wing()
    parts += [("wing_R", wing, "skin"), ("wing_L", mirror_y(wing), "skin"),
              ("elevon_R", elevon, "controls"), ("elevon_L", mirror_y(elevon), "controls")]
    st = build_stab()
    parts += [("stabilator_R", st, "controls"), ("stabilator_L", mirror_y(st), "controls")]
    for name, m in build_fin():
        layer = "controls" if name == "rudder" else "skin"
        parts += [(f"{name}_R", m, layer), (f"{name}_L", mirror_y(m), layer)]
    it = build_intake()
    parts += [("intake_R", it, "skin"), ("intake_L", mirror_y(it), "skin")]
    nz, cone = build_nozzle()
    parts += [("nozzle", nz, "propulsion"), ("nozzle_cone", cone, "propulsion")]
    ring = duct_ring()
    vanes = exit_vanes()
    for n, dx, dy in P.duct_centres():
        r = ring.copy()
        r.apply_translation([dx, dy, 0])
        parts.append((f"duct_{n}", r, "propulsion"))
        v = vanes.copy()
        v.apply_translation([dx, dy, 0])
        parts.append((f"vanes_{n}", v, "controls"))
    for name, m in build_gear(main_x):
        parts.append((name, m, "gear"))
    return parts


# ---------------------------------------------------------------------------------------------------
# scale-specific insides
SPAR_MAIN_X = 6.45          # spanwise main spar (mini: 6 mm carbon tube), behind the rear ducts
SPAR_CENTRE_X = 4.56        # spanwise centre spar through the strip between the front and rear ducts (mini: 4 mm tube)
KEEL_Z = -0.12              # fore-aft keel tube (mini: 6 mm) from behind the battery bay to the EDF
# the main spar is two halves that plug into a printed carry-through ring around the thrust tube
SPARS_MINI = [("spar_main_6mm_R", [SPAR_MAIN_X, 0.38, 0], [SPAR_MAIN_X, 2.85, 0], 0.03),
              ("spar_main_6mm_L", [SPAR_MAIN_X, -0.38, 0], [SPAR_MAIN_X, -2.85, 0], 0.03),
              ("spar_centre_4mm", [SPAR_CENTRE_X, -2.20, 0], [SPAR_CENTRE_X, 2.20, 0], 0.02),
              ("keel_6mm", [4.10, 0, KEEL_Z], [5.30, 0, KEEL_Z], 0.03)]
PACK_CHECK: dict = {}       # filled by inside_parts (full scale): where the battery really ended up
WING_MOUNTED = ("servo_", "fuel_tank_", "inverter_rear")     # checked against fuselage + wings, not the fuselage alone
SERVOS_MINI = [("servo_elevon_R", 5.60, 2.75), ("servo_elevon_L", 5.60, -2.75), ("servo_stab_R", 7.20, 0.85),
               ("servo_stab_L", 7.20, -0.85), ("servo_rudders", 6.80, -0.85), ("servo_vanes_R", 5.00, 0.30),
               ("servo_vanes_L", 5.00, -0.30)]


def inside_parts(scale_key: str, sizing: dict):
    """[(name, mesh, layer, note)] in full-scale metres for one scale."""
    out = []
    xc = P.duct_centre_x()
    blades, coax = (3, False) if scale_key == "mini" else (5, True)
    for n, dx, dy in P.duct_centres():
        grouped = {}
        for part, m in fan(coax, blades, R_ID):
            grouped.setdefault(part, []).append(m)
        for part, ms in grouped.items():        # one mesh per kind per duct (names must be unique in the GLB)
            mm = trimesh.util.concatenate(ms)
            mm.apply_translation([dx, dy, 0])
            label = {"blade": f"{'2 x ' if coax else ''}{blades}-blade rotor{'s (contra-rotating)' if coax else ''}",
                     "stator": "4 stator vanes", "hub": "hub and motor"}[part]
            out.append((f"fan_{part}s_{n}" if part != "hub" else f"fan_hub_{n}", mm, "props" if part == "blade" else "hardware", label))
    if scale_key == "mini":
        s = 0.1
        bx = sizing["battery_x_m"] / s
        out += [
            ("battery_4S2P_21700", union(*[cyl([bx + xo - 0.35, yy, zz], [bx + xo + 0.35, yy, zz], 0.105, 32)
                                           for xo in (-0.355, 0.355) for yy in (-0.106, 0.106) for zz in (-0.115, 0.097)]), "systems",
             "4S2P Li-ion pack: 8 x 21700 cells lying fore-aft, two 2 x 2 bundles end to end, 141 x 43 x 43 mm"),
            ("fc_speedybee_f405_wing", box(4.10, 4.46, -0.18, 0.18, 0.04, 0.16), "systems",
             "SpeedyBee F405 WING on soft mounts, on the battery-bay deck behind the pack"),
            ("esc_4in1", box(xc - 0.18, xc + 0.18, -0.18, 0.18, -0.30, -0.20), "systems", "4-in-1 ESC (XRotor Micro 60A) under the strake floor"),
            ("edf_e7206", cyl([P.CRUISE_FAN_X_MINI - 0.35, 0, -0.10], [P.CRUISE_FAN_X_MINI + 0.35, 0, -0.10], 0.35, 48), "propulsion",
             "Freewing E7206 64 mm EDF (70 mm housing)"),
            ("thrust_tube", cyl([P.CRUISE_FAN_X_MINI + 0.37, 0, -0.08], [P.NOZZLE["x0"], 0, -0.02], 0.30, 48), "propulsion",
             "0.2 mm PET film thrust tube to the nozzle"),
            ("fpv_camera_19mm", box(3.12, 3.32, -0.095, 0.095, 0.36, 0.55), "systems", "19 mm FPV camera at the pilot's eye point"),
            ("gps_m10", box(3.10, 3.36, -0.125, 0.125, 0.29, 0.35), "systems", "M10 GPS + compass under the camera seat (sky view through the canopy)"),
            ("edf_esc_60a", box(4.82, 5.30, -0.13, 0.13, -0.30, -0.17), "systems", "EDF ESC (Skywalker 60A V2), just ahead of the EDF"),
        ]
        for nm, x, y in SERVOS_MINI:
            out.append((nm, box(x - 0.115, x + 0.115, y - 0.11, y + 0.11, -0.05, 0.05), "systems", "5 g digital servo, laid flat in a pocket"))
        for nm, p0, p1, r in SPARS_MINI:
            out.append((nm, cyl(p0, p1, r, 24), "structure", "carbon tube"))
    else:
        out += [(n, m, "payload", "seated pilot envelope") for n, m in build_pilot()]
        bx = sizing["battery_x_m"]
        kwh = sizing["battery_kwh"]
        vol = sizing["battery_kg"] / 1500.0          # about 1.5 kg/L at pack level
        hy = sizing.get("hybrid") or {}
        # two battery bays: conformal modules in the nose bay ahead of the pilot's feet and a box behind the CG; the
        # split puts the pack's centroid where the sizing put the battery (CG on the fan centre)
        rear_x, rear_box = 5.24, (5.05, 5.43, -0.22, -0.01)
        f_nose = 1.0
        xn = float(np.clip(bx, 1.10, 2.35))          # grow the nose pack around the station the sizing asked for
        for _ in range(8):
            nose, info = conformal_pack(max(vol * f_nose, 1e-4), xn, x_min=1.0, x_max=2.45, z_lo=-0.40, z_hi=0.30)
            f_new = (rear_x - bx) / max(rear_x - info["centroid_x"], 1e-6)
            f_nose = float(np.clip(0.5 * f_nose + 0.5 * f_new, 0.05, 1.0))
        nose, info = conformal_pack(vol * f_nose, xn, x_min=1.0, x_max=2.45, z_lo=-0.40, z_hi=0.30)
        v_rear = vol * (1 - f_nose)
        x0, x1, z0, z1 = rear_box
        w = min(0.60, v_rear / 0.85 / ((x1 - x0) * (z1 - z0)))
        rear = box(x0, x1, -w / 2, w / 2, z0, z1) if v_rear > 2e-3 else None
        self_check = info["centroid_x"] * f_nose + rear_x * (1 - f_nose) if rear is not None else info["centroid_x"]
        PACK_CHECK.update({"battery_centroid_m": round(float(self_check), 3), "battery_x_sizing_m": round(float(bx), 3),
                           "battery_volume_fill": round(float(info["fill"]), 3)})
        out.append(("battery_pack_nose", nose, "systems",
                    f"{kwh * (f_nose if rear is not None else 1.0):.0f} kWh of the {kwh:.0f} kWh pack: conformal modules in the "
                    f"nose bay ahead of the pilot's feet (x {info['x0']:.2f}-{info['x1']:.2f} m, {100 * info['fill']:.0f} % of the "
                    "volume asked for)"))
        if rear is not None:
            out.append(("battery_pack_rear", rear, "systems",
                        f"{kwh * (1 - f_nose):.0f} kWh behind the CG; pack centroid x {self_check:.2f} m (sizing: {bx:.2f} m)"))
        if hy:
            # wing tanks outboard of the ducts: plan from 0.30 m behind the leading edge to x 5.50, y 2.30-2.80
            ys = np.linspace(2.30, 2.80, 6)
            plan = [(float(LE_X(y)) + 0.30, float(y)) for y in ys] + [(5.50, 2.80), (5.50, 2.30)]
            tank_R = trimesh.creation.extrude_polygon(Polygon(plan), 0.13)
            tank_R.apply_translation([0, 0, -0.065])
            tank_L = mirror_y(tank_R)
            fuel_l_cap = 2 * tank_R.volume * 1000 * 0.92
            out += [("fuel_tank_R", tank_R, "systems", f"wing tank, {fuel_l_cap / 2:.0f} L (needs {hy['fuel_l'] / 2:.0f} L)"),
                    ("fuel_tank_L", tank_L, "systems", f"wing tank, {fuel_l_cap / 2:.0f} L (needs {hy['fuel_l'] / 2:.0f} L)"),
                    ("turbogenerator", cyl([3.80, 0, 0.05], [4.48, 0, 0.05], 0.21, 48), "propulsion",
                     f"{hy['generator_kw']:.0f} kW turboshaft generator (series hybrid) behind the pilot: flush inlet on the spine, "
                     "exhaust in two pipes either side of the cruise fan into its thrust tube and out of the jet nozzle")]
            for sg, nm in ((1, "R"), (-1, "L")):
                pipe = union(cyl([4.46, sg * 0.15, 0.12], [5.30, sg * 0.38, 0.12], 0.05, 20),
                             cyl([5.30, sg * 0.38, 0.12], [6.30, sg * 0.38, 0.12], 0.05, 20),
                             cyl([6.30, sg * 0.38, 0.12], [7.20, sg * 0.20, 0.05], 0.05, 20))
                out.append((f"turbine_exhaust_{nm}", pipe, "propulsion", "insulated exhaust pipe, joins the thrust tube"))
        out += [
            ("flight_computers", box(2.50, 2.80, -0.20, 0.20, 0.0, 0.15), "systems",
             "triplex flight-control computers, air data, radios: behind the instrument panel"),
            ("parachute", cyl([4.80, 0, 0.20], [5.35, 0, 0.20], 0.14, 32), "systems", "ballistic recovery parachute, fires upward"),
            ("cruise_fan", cyl([P.CRUISE_FAN_X - 0.25, 0, -0.03], [P.CRUISE_FAN_X + 0.25, 0, -0.03], P.CRUISE_FAN_D / 2, 64), "propulsion",
             "ducted cruise fan, electric, at the intake throat"),
            ("thrust_tube", cyl([P.CRUISE_FAN_X + 0.26, 0, -0.03], [P.NOZZLE["x0"], 0, -0.02], 0.27, 48), "propulsion",
             "thrust tube from the cruise fan to the nozzle" + ("; the turbine exhaust joins it" if hy else "")),
        ]
        for n, dx, dy in P.duct_centres():
            sg = np.sign(dy)
            if n.startswith("front"):
                inv = box(dx - 0.15, dx + 0.15, sg * 0.38 - 0.05, sg * 0.38 + 0.05, -0.10, 0.05)
            else:                       # rear pair: in the wing root behind the rear ducts and the main spar
                inv = box(6.55, 6.85, sg * 0.80 - 0.15, sg * 0.80 + 0.15, -0.06, 0.06)
            out.append((f"inverter_{n}", inv, "systems", "two inverters (one per rotor)"))
        for nm, p0, p1, r in (("spar_main_R", [SPAR_MAIN_X, 0.50, 0], [SPAR_MAIN_X, 2.75, 0], 0.045),
                              ("spar_main_L", [SPAR_MAIN_X, -0.50, 0], [SPAR_MAIN_X, -2.75, 0], 0.045),
                              ("spar_centre", [SPAR_CENTRE_X, -2.20, 0], [SPAR_CENTRE_X, 2.20, 0], 0.05)):
            out.append((nm, cyl(p0, p1, r, 24), "structure", "carbon box-spar line (schematic)"))
    return out


def section_width(x, z):
    """Fuselage width at station x and height z (from the section ring)."""
    pts = fus_ring(x)[:, 1:]
    ys = []
    for a, b in zip(pts, np.roll(pts, -1, 0)):
        if (a[1] - z) * (b[1] - z) <= 0 and a[1] != b[1]:
            t = (z - a[1]) / (b[1] - a[1])
            ys.append(abs(a[0] + t * (b[0] - a[0])))
    return 2 * max(ys) if ys else 0.0


def best_rect(x, z_lo, z_hi, clear):
    """Largest box section (width, z0, z1) that fits the fuselage section at x between z_lo and z_hi."""
    _w, zb, zt = P.fus_at(x)
    lo, hi = max(z_lo, zb + clear), min(z_hi, zt - clear)
    best = (0.0, lo, lo)
    zz = np.linspace(lo, hi, 13)
    for i in range(len(zz)):
        for j in range(i + 2, len(zz)):
            w = min(section_width(x, z) for z in np.linspace(zz[i], zz[j], 5)) - 2 * clear
            if w > 0 and w * (zz[j] - zz[i]) > best[0] * (best[2] - best[1]):
                best = (w, zz[i], zz[j])
    return best


def conformal_pack(volume, x_centre, x_min, x_max, z_lo, z_hi, dx=0.05, fill=0.85, clear=0.03):
    """Battery modules filling fuselage slices around x_centre (alternately aft and fore, so the pack's centroid
    stays near x_centre) until the volume is reached. Each slice is the largest box that fits the section between
    z_lo and z_hi (less a clearance), times a packing fill."""
    slices = []

    def add(x0):
        w, z0, z1 = best_rect(x0 + dx / 2, z_lo, z_hi, clear)
        if w <= 0.05 or z1 - z0 < 0.08:
            return 0.0
        slices.append((x0, w, z0, z1))
        return w * (z1 - z0) * dx * fill
    v = 0.0
    fwd, aft = x_centre - dx, x_centre
    while v < volume and (fwd >= x_min or aft + dx <= x_max):
        if aft + dx <= x_max:
            v += add(aft)
            aft += dx
        if v < volume and fwd >= x_min:
            v += add(fwd)
            fwd -= dx
    boxes = [box(x0, x0 + dx, -w / 2, w / 2, z0, z1) for x0, w, z0, z1 in slices]
    m = union(*boxes) if boxes else box(x_centre - 0.1, x_centre + 0.1, -0.1, 0.1, z_lo, z_hi)
    xs = [sl[0] for sl in slices]
    return m, {"x0": min(xs), "x1": max(xs) + dx, "volume_m3": v, "needed_m3": volume, "fill": min(1.0, v / volume) if volume else 1.0,
               "centroid_x": float(m.center_mass[0])}


# ---------------------------------------------------------------------------------------------------
COLORS = {"skin": "#B9C3CD", "controls": "#98A7B6", "glass": "#C9A35B", "propulsion": "#3A4149", "gear": "#23272C",
          "props": "#15191E", "hardware": "#4B535C", "systems": "#3F7CAC", "payload": "#5C6B4E", "structure": "#2A2E33"}
STL_DIR = {"mini": "stl", "full": "stl"}


def build(scale_key: str, sizing: dict, out_root: Path | None = None, export: bool = True):
    from mesh import split_to_fit
    from v18_extract import P1S, bed_fit
    s = {"mini": 0.1, "full": 1.0}[scale_key]
    mm_per_m = 1000.0 * s
    cg_x = sizing["cg_m"][0] / s
    main_x = cg_x + P.GEAR["main_dx_behind_cg"]
    oml_parts = build_oml(main_x)
    inner = inside_parts(scale_key, sizing)
    parts = [(n, m, layer, "") for n, m, layer in oml_parts] + inner
    if scale_key == "full":
        parts = [p for p in parts if not p[0].startswith("gear_")] + [p for p in parts if p[0].startswith("gear_")]
    # spar holes through the mini airframe (6 mm main, 4 mm centre, 6 mm keel) + 0.3 mm clearance
    if scale_key == "mini":
        cutters = [cyl([SPAR_MAIN_X, 0.36, 0], [SPAR_MAIN_X, 2.87, 0], 0.033, 24),
                   cyl([SPAR_MAIN_X, -0.36, 0], [SPAR_MAIN_X, -2.87, 0], 0.033, 24),
                   cyl([SPAR_CENTRE_X, -2.3, 0], [SPAR_CENTRE_X, 2.3, 0], 0.023, 24),
                   cyl([4.05, 0, KEEL_Z], [5.35, 0, KEEL_Z], 0.033, 24)]
        new = []
        for n, m, layer, note in parts:
            if n.startswith(("wing_", "fuselage")):
                m = diff(m, *[c for c in cutters if c.bounds[0][0] <= m.bounds[1][0] and c.bounds[1][0] >= m.bounds[0][0]])
            new.append((n, m, layer, note))
        parts = new
    scaled = []
    for n, m, layer, note in parts:
        mm = m.copy()
        mm.apply_scale(mm_per_m)
        scaled.append((n, mm, layer, note))
    res = {"scale": scale_key, "parts": [], "checks": {}}
    # checks: insides within the fuselage / airframe outer mould line, prop tips vs duct wall, everything watertight
    fus = union(*[m for n, m, layer, _ in scaled if n in ("fuselage", "canopy")])
    airframe = trimesh.util.concatenate([m for n, m, layer, _ in scaled if n in ("fuselage", "wing_R", "wing_L")])
    contain = {}
    for n, m, layer, _ in scaled:
        if (layer in ("systems", "payload") or n.startswith(("turbogenerator", "turbine_exhaust"))) and not n.startswith(WING_MOUNTED):
            v = m.vertices[:: max(1, len(m.vertices) // 300)]
            c0 = v.mean(0)
            v = c0 + (v - c0) * 0.99              # 1 % inset: points on the skin itself count as inside
            inside = fus.contains(v) if fus.is_watertight else np.ones(len(v), bool)
            contain[n] = round(float(inside.mean()), 3)
    # prop tip gap, measured: the duct's smallest inner radius over the rotor's height band minus the largest radius
    # any blade vertex reaches (both about the duct axis)
    gaps = []
    by = {n: m for n, m, _l, _ in scaled}
    for dn, dx, dy in P.duct_centres():
        blades = by.get(f"fan_blades_{dn}")
        duct = by.get(f"duct_{dn}")
        if blades is None or duct is None:
            continue
        c = np.array([dx, dy]) * mm_per_m
        rb = np.hypot(*(blades.vertices[:, :2] - c).T)
        zlo, zhi = blades.vertices[:, 2].min(), blades.vertices[:, 2].max()
        dv = duct.vertices[(duct.vertices[:, 2] >= zlo - 1e-6) & (duct.vertices[:, 2] <= zhi + 1e-6)]
        if len(dv) == 0:
            dv = duct.vertices
        rd = np.hypot(*(dv[:, :2] - c).T)
        gaps.append(float(rd.min() - rb.max()))
    tip_gap = min(gaps) if gaps else float("nan")
    # servos sit in wing and tail pockets: check them against the airframe (fuselage + wings) instead
    air = union(*[m for n, m, layer, _ in scaled if n in ("fuselage", "wing_R", "wing_L")])
    for n, m, layer, _ in scaled:
        if n.startswith(WING_MOUNTED):
            v = m.vertices
            c0 = v.mean(0)
            contain[n] = round(float(air.contains(c0 + (v - c0) * 0.99).mean()), 3)
    # internal collisions: every pair of inside parts whose bounding boxes touch, by boolean intersection volume
    inside_names = {n for n, _m, _l, _ in inner if not n.startswith(("fan_",))}
    ins = [(n, m) for n, m, _l, _ in scaled if n in inside_names]
    def ok_pair(a, b):             # intended contacts: the pilot in the seat, the exhaust pipes joining the thrust tube
        pil = lambda n: n.startswith("pilot_") or n == "seat"  # noqa: E731
        joins = [{f"turbine_exhaust_{sd}", o} for sd in "RL" for o in ("thrust_tube", "turbogenerator")]
        return (pil(a) and pil(b)) or {a, b} in joins
    collisions = []
    for i in range(len(ins)):
        for j in range(i + 1, len(ins)):
            (na, ma), (nb, mb) = ins[i], ins[j]
            if ok_pair(na, nb):
                continue
            lo = np.maximum(ma.bounds[0], mb.bounds[0])
            hi = np.minimum(ma.bounds[1], mb.bounds[1])
            if np.any(hi <= lo):
                continue
            try:
                vol = float(inter(ma, mb).volume)
            except Exception:  # noqa: BLE001
                vol = float(np.prod(hi - lo))
            if vol > 1e-4 * min(ma.volume, mb.volume):
                collisions.append([na, nb, round(vol / 1000.0, 3)])          # cm3 at this scale
    res["checks"]["internal_collisions"] = collisions
    res["checks"]["inside_fuselage_fraction"] = contain
    pack_ok = True
    if scale_key == "full" and PACK_CHECK:
        res["checks"]["battery_pack"] = dict(PACK_CHECK)
        pack_ok = (abs(PACK_CHECK["battery_centroid_m"] - PACK_CHECK["battery_x_sizing_m"]) <= 0.05
                   and PACK_CHECK["battery_volume_fill"] >= 0.98)
    res["checks"]["prop_tip_gap_mm"] = round(tip_gap, 2)
    res["checks"]["watertight"] = {n: bool(m.is_watertight) for n, m, layer, _ in scaled if layer not in ("props", "hardware")}
    # mini print set: every printed part split until it fits the P1S bed
    pieces = []
    if scale_key == "mini":
        printed_names = [n for n, m, layer, _ in scaled if layer in ("skin", "controls", "glass") or n.startswith(("duct_", "nozzle"))]
        fits = lambda mm: (bed_fit(mm) or (False,))[0]     # noqa: E731
        for n, m, layer, _ in scaled:
            if n not in printed_names:
                continue
            ps = split_to_fit(m, fits, 4)
            for i, pm in enumerate(ps):
                bf = bed_fit(pm)
                pieces.append({"name": f"{n}" + (f"_p{i + 1}" if len(ps) > 1 else ""), "of": n, "mesh": pm,
                               "fits": bool(bf and bf[0]), "footprint_mm": bf[1] if bf else None,
                               "height_mm": bf[3] if bf else None})
        res["checks"]["P1S"] = {p["name"]: {"fits": p["fits"], "footprint_mm": p["footprint_mm"], "height_mm": p["height_mm"]} for p in pieces}
    res["checks"]["watertight_print_pieces"] = all(bool(p["mesh"].is_watertight) for p in pieces)
    res["checks"]["status"] = "PASS" if (all(v >= 0.98 for v in contain.values()) and all(res["checks"]["watertight"].values())
                                         and all(p["fits"] for p in pieces) and res["checks"]["watertight_print_pieces"]
                                         and tip_gap > 0 and not collisions and pack_ok) else "FLAG"
    for n, m, layer, note in scaled:
        res["parts"].append({"name": n, "layer": layer, "note": note, "bbox_mm": [round(float(v), 1) for v in m.extents],
                             "centroid_mm": [round(float(v), 1) for v in (m.center_mass if m.is_volume else m.centroid)]})
    if export:
        out = out_root or (ROOT / "cad" / "v20" / scale_key)
        (out / "stl").mkdir(parents=True, exist_ok=True)
        for f in (out / "stl").glob("*.stl"):
            f.unlink()
        if scale_key == "mini":
            for p in pieces:
                p["mesh"].export(out / "stl" / f"{p['name']}.stl")
            ps = trimesh.Scene()
            for p in pieces:
                ps.add_geometry(p["mesh"], node_name=p["name"], geom_name=p["name"])
            ps.export(out / f"v20_{scale_key}_print_set.3mf")
        else:
            for n, m, layer, _ in scaled:
                if layer in ("skin", "controls", "glass") or n.startswith(("duct_", "nozzle")):
                    m.export(out / "stl" / f"{n}.stl")
        # the web shows both in one frame: the mini at real size, the full-scale aircraft at 1:10
        glb(scaled, ROOT / "site" / "models" / "raw" / f"v20_{scale_key}.glb", 0.1 if scale_key == "full" else 1.0)
        (out / "parts.json").write_text(json.dumps(res["parts"], indent=1))
        (out / "checks.json").write_text(json.dumps(res["checks"], indent=1))
    return res


def glb(scaled, path: Path, display_scale: float = 1.0):
    from trimesh.visual.material import PBRMaterial

    def col(h):
        h = h.lstrip("#")
        return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    scene = trimesh.Scene()
    for n, m, layer, _ in scaled:
        mm = m.copy()
        mm.apply_scale(display_scale)
        key = "glass" if n == "canopy" else ("props" if layer == "props" else layer)
        alpha = {"glass": 0.5, "props": 0.85}.get(key, 1.0)
        metal = {"propulsion": 0.45, "hardware": 0.5, "glass": 0.6, "structure": 0.3}.get(key, 0.08)
        mm.visual = trimesh.visual.TextureVisuals(material=PBRMaterial(
            name=n, baseColorFactor=[*col(COLORS.get(key, "#B9C3CD")), alpha], roughnessFactor=0.18 if key == "glass" else 0.55,
            metallicFactor=metal, alphaMode="BLEND" if alpha < 1 else "OPAQUE", doubleSided=False))
        scene.add_geometry(mm, node_name=n, geom_name=n)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.export(path)


def main(argv) -> int:
    import time
    sz = json.loads((ROOT / "analysis" / "v20_sizing.json").read_text())
    keys = argv[1:] or ["mini", "full"]
    allres = {}
    for k in keys:
        t0 = time.time()
        r = build(k, sz[k])
        allres[k] = {"checks": r["checks"], "parts": r["parts"]}
        print(f"[{k}] {len(r['parts'])} parts, checks {r['checks']['status']}, {time.time() - t0:.0f}s")
        bad = {n: v for n, v in r["checks"]["inside_fuselage_fraction"].items() if v < 0.98}
        if bad:
            print("   outside the fuselage:", bad)
        if r["checks"]["internal_collisions"]:
            print("   internal collisions (cm3):", r["checks"]["internal_collisions"])
        print("   tip gap", r["checks"]["prop_tip_gap_mm"], "mm; watertight pieces", r["checks"].get("watertight_print_pieces"))
        if "P1S" in r["checks"]:
            nf = [n for n, v in r["checks"]["P1S"].items() if not v["fits"]]
            print(f"   print pieces: {len(r['checks']['P1S'])}, not fitting: {nf}")
    out = ROOT / "analysis" / "v20_geometry.json"
    prev = json.loads(out.read_text()) if out.exists() else {}
    prev.update(allres)
    out.write_text(json.dumps(prev, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
