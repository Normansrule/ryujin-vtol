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
TIP_GAP = 0.022             # blade tip to duct wall (full-scale m): mini 2.2 mm, a 4-inch prop in a 106 mm duct


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
SPAR_MAIN_X = 4.80          # spanwise main spar (mini: 6 mm carbon tube), behind the rear ducts (set by refresh)
SPAR_CENTRE_X = 3.36        # spanwise centre spar through the strip between the front and rear ducts (set by refresh)


def refresh() -> None:
    """Recompute everything derived from the shape parameters (after v20params.use)."""
    global R_ID, R_OUT, LE_X, TE_X, Y_TIP, SPAR_MAIN_X, SPAR_CENTRE_X
    R_ID = P.DUCT_ID / 2
    R_OUT = R_ID + P.DUCT_LIP
    LE_X, TE_X, Y_TIP = _outline_fn()
    SPAR_CENTRE_X = P.duct_centre_x()
    SPAR_MAIN_X = max(P.DUCT_X.values()) + R_OUT + 0.20


def set_variant(variant: str) -> None:
    P.use(variant)
    refresh()


def wing_half_thickness(x, y, chord, u):
    """Thin symmetric section outboard; inboard of BODY_Y the 'wing' is the blended body's shoulder, a thick flat-topped
    section that holds the ducts and louvres and fairs into the fuselage sides (the F-35 look)."""
    h = naca_t(u, P.T_C) * chord
    le, te = x - u * chord, x + (1 - u) * chord
    body = P.BODY_HALF_T * smoothstep(0.0, 0.5, x - le) * smoothstep(0.0, 0.9, te - x)
    blend = 1 - smoothstep(P.BODY_Y - 0.35, P.BODY_Y + 0.15, y)
    h = np.maximum(h, body * blend)
    fair = np.zeros_like(h)
    for _n, dx, dy in P.duct_centres():
        if dy < 0:
            continue
        r = np.hypot(x - dx, y - dy)
        fair = np.maximum(fair, 1 - smoothstep(R_OUT + 0.02, R_OUT + 0.40, r))
    h_duct = P.DUCT_DEPTH / 2 + 0.012
    # blended wing-body fillet: ahead of and behind the duct band the wing root thickens smoothly up to the body's
    # height, so the fuselage, aft body and wing read as one lifting body (beside the fans the body stands up from the
    # shoulders, as on the F-35)
    fx = np.array([f[0] for f in P.FUS])
    w_b = np.interp(x, fx, [f[1] for f in P.FUS])
    h_b = np.minimum(np.interp(x, fx, [f[3] for f in P.FUS]), -np.interp(x, fx, [f[2] for f in P.FUS])) - 0.03
    xf_, xr_ = min(P.DUCT_X.values()), max(P.DUCT_X.values())
    band = smoothstep(xf_ - R_OUT - 0.6, xf_ - R_OUT - 0.1, x) * (1 - smoothstep(xr_ + R_OUT + 0.1, xr_ + R_OUT + 0.9, x))
    reach = 0.9 - 0.75 * band
    fil = h_b * (1 - smoothstep(w_b - 0.05, w_b + reach, y)) ** 1.6
    h = np.maximum(h, fil * smoothstep(0.0, 0.5, x - le) * smoothstep(0.0, 0.5, te - x))
    # stay a closed section at the leading and trailing edges
    edge = smoothstep(0.0, 0.06, u) * smoothstep(0.0, 0.06, 1 - u)
    return np.maximum(h, h_duct * fair * edge)


WING_ENVELOPE = None


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
    global WING_ENVELOPE
    WING_ENVELOPE = wing.copy()           # before the holes: the duct walls and louvres are trimmed to it (flush)
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


def louvres(z0: float, z1: float, n: int = 8, angle_deg: float = 0.0):
    """A louvre cascade across one duct opening (centred at the origin): n flat slats, shown closed as in cruise,
    turned by angle_deg about z (0: slats spanwise, hinged about y). Underneath they are the exit vanes - spanwise, so
    they turn the efflux aft in transition, driven by one servo per side; on top they open by the fan's own suction and
    run parallel to the outer leading edge, so each grille follows the planform's sweep."""
    out = []
    pitch = 2 * R_ID / n
    for k in range(n):
        x = -R_ID + pitch * (k + 0.5)
        half = math.sqrt(max(R_ID ** 2 - x ** 2, 0.0)) - 0.012
        if half > 0.05:
            out.append(box(x - pitch / 2 + 0.003, x + pitch / 2 - 0.003, -R_ID, R_ID, z0, z1))
    m = inter(union(*out), cyl([0, 0, z0 - 0.01], [0, 0, z1 + 0.01], R_ID - 0.012, 128))   # round ends, no steps
    if angle_deg:
        m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(angle_deg), [0, 0, 1]))
    return m


def le_sweep_deg() -> float:
    """Sweep of the outer leading edge (shoulder corner to tip), from the y axis."""
    a, b = P.OUTLINE[2], P.OUTLINE[3]
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))


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
def fus_ring(x, k=64):
    """Chined section at station x: z = z_chine + h (1 - |y/w|^q)^r above and below the chine line. r = 1 gives the
    sharp chine of the nose (its edge runs into the wing leading edge); r < 1 rounds it off aft."""
    w, zb, zt = P.fus_at(x)
    zc = min(max(P.CHINE_Z, zb + 0.3 * (zt - zb)), zt - 0.2 * (zt - zb)) if w > 0 else 0.0
    r = P.chine_r(x)
    pts = []
    for t in np.linspace(0, 2 * math.pi, k, endpoint=False):
        c, s_ = math.cos(t), math.sin(t)
        y = w * c
        u = min(abs(c), 1.0)
        if s_ >= 0:
            z = zc + (zt - zc) * (1 - u ** P.CHINE["q_up"]) ** r
        else:
            z = zc - (zc - zb) * (1 - u ** P.CHINE["q_lo"]) ** r
        pts.append((x, y, z))
    return np.array(pts)


def build_fuselage():
    xs = np.concatenate([np.linspace(0.04, 0.6, 10), np.linspace(0.7, P.FUS_LEN, 46)])
    rings = [fus_ring(x) for x in xs]
    return loft_rings(rings, cap_start=True, cap_end=True, start_point=(0.0, 0.0, 0.0))


def build_canopy():
    """Low frameless canopy: a long teardrop whose tail runs down into the dorsal spine."""
    c = P.CANOPY
    xs = np.linspace(c["x0"], c["x1"], 48)
    rings = []
    for x in xs:
        u = (x - c["x0"]) / (c["x1"] - c["x0"])
        up = (c["x_peak"] - c["x0"]) / (c["x1"] - c["x0"])
        prof = math.sin(0.5 * math.pi * u / up) ** 0.6 if u < up else math.cos(0.5 * math.pi * (u - up) / (1 - up)) ** 1.4
        prof = max(prof, 0.02)
        _w, _zb, zt = P.fus_at(x)
        h = (c["z_top"] - zt) * prof
        hw = c["half_width"] * max(math.sin(math.pi * min(u / (2 * up), 0.5)) ** 0.5, 0.05) * (1 - 0.35 * max(0.0, u - up) / (1 - up))
        ring = []
        for t in np.linspace(0, math.pi, 28):
            ring.append((x, hw * math.cos(t), zt - 0.05 + (h + 0.05) * math.sin(t) ** 0.7))
        ring.append((x, -hw * 0.98, zt - 0.09))
        ring.append((x, hw * 0.98, zt - 0.09))
        rings.append(np.array(ring))
    return loft_rings(rings)


def build_spine():
    """Dorsal spine from behind the canopy to the V-tail roots: it carries the canopy line aft (and the mini's
    ruddervator servos and wiring)."""
    sp = P.SPINE
    xs = np.linspace(sp["x0"], sp["x1"], 36)
    rings = []
    for x in xs:
        u = (x - sp["x0"]) / (sp["x1"] - sp["x0"])
        _w, _zb, zt = P.fus_at(x)
        rise = (sp["z_top"] - zt) * (math.sin(math.pi * min(u / 0.25, 1.0) / 2) ** 0.8) * (1 - smoothstep(0.55, 1.0, u))
        hw = sp["half_width"] * (1 - 0.45 * u)
        ring = [(x, hw * math.cos(t), zt - 0.06 + (rise + 0.06) * math.sin(t) ** 0.8) for t in np.linspace(0, math.pi, 22)]
        ring += [(x, -hw * 0.98, zt - 0.10), (x, hw * 0.98, zt - 0.10)]
        rings.append(np.array(ring))
    return loft_rings(rings)


def bay_box():
    pb = P.PAYLOAD_BAY
    return box(pb["x0"], pb["x1"], -pb["half_width"], pb["half_width"], -1.0, pb["z_top"])


def translated(m, v):
    t = m.copy()
    t.apply_translation(v)
    return t


def build_vtail(side: int = 1):
    """One all-moving ruddervator, built in its own tilted plane (dihedral VTAIL['dihedral_deg']); its root runs a
    little into the aft body."""
    v = P.VTAIL
    root, sdir, nrm = P.vtail_frame(side)
    sv = np.linspace(-0.08, v["span"], 26)
    g = np.clip(sv / v["span"], 0, 1)
    le = v["x_le_root"] + sv.clip(0) * math.tan(math.radians(v["le_sweep_deg"]))
    ch = v["c_root"] + g * (v["c_tip"] - v["c_root"])
    us = (1 - np.cos(np.linspace(0, math.pi, 36))) / 2
    X = le[:, None] + us[None, :] * ch[:, None]
    S = np.repeat(sv[:, None], len(us), 1)
    Pm = np.stack([X, root[1] + S * sdir[1], root[2] + S * sdir[2]], -1)
    N = np.zeros_like(Pm)
    N[..., 1], N[..., 2] = nrm[1], nrm[2]
    return surface_solid(Pm, N, naca_t(us, 0.05)[None, :] * ch[:, None], hmin=0.003)


def intake_mouth_area_m2() -> float:
    """Both intake mouths (full-scale m2): what the cruise fan can breathe."""
    it = P.INTAKE
    w = P.fus_at(it["x0"] + 0.1)[0]
    return 2 * (it["y_out"] - w - 0.035) * (it["z1"] - it["z0"] - 0.09)


def build_intake():
    """Starboard side intake (F-35 style): a raked scoop beside the cockpit just ahead of the front lift fan, then a
    cheek under the body shoulder - inboard of the fans' lips and below their exit louvres - back to the cruise fan."""
    it = P.INTAKE
    xs = np.linspace(it["x0"], it["x1"], 40)
    rings = []
    for x in xs:
        w = P.fus_at(x)[0]
        g = smoothstep(it["x_cheek"] - 0.25, it["x_cheek"], x)
        yo = it["y_out"] + (it["y_cheek"] - it["y_out"]) * g
        zt = it["z1"] + (it["z_cheek"] - it["z1"]) * g
        fade = 1 - smoothstep(it["x1"] - 0.6, it["x1"], x)
        yo = w + (yo - w) * fade + 0.004
        zc, hz = (it["z0"] + zt) / 2, (zt - it["z0"]) / 2
        ring = []
        for t in np.linspace(-math.pi / 2, math.pi / 2, 18):
            ring.append((x, w - 0.15 + (yo - w + 0.15) * math.cos(t) ** 0.3, zc + hz * math.sin(t)))
        rings.append(np.array(ring))
    body = loft_rings(rings)
    rake = box(it["x0"] - 0.6, it["x0"] + 0.20, -2, 2, -2, 2)
    rake.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-30), [0, 0, 1], [it["x0"], it["y_out"], 0]))
    body = diff(body, rake)
    w0 = P.fus_at(it["x0"] + 0.1)[0]
    mouth = box(it["x0"] - 0.3, it["x0"] + 0.45, w0 + 0.0, it["y_out"] - 0.035, it["z0"] + 0.045, it["z1"] - 0.045)
    return diff(body, mouth)


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
    x_hip, z_seat = 3.55, -0.25
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
    fus = build_fuselage()
    # internal payload bay in the belly at the CG: the bay is cut out of the body and closed by two conformal doors
    # (the bottom door_t of skin over the bay, split on the centreline; they open sideways like bomb-bay doors)
    pb = P.PAYLOAD_BAY
    bay = bay_box()
    skin = diff(inter(fus, bay), translated(fus, [0, 0, pb["door_t"]]))
    fus = diff(fus, bay)
    for side, (y0, y1) in (("R", (0.004, pb["half_width"])), ("L", (-pb["half_width"], -0.004))):
        parts.append((f"bay_door_{side}", inter(skin, box(pb["x0"] - 0.1, pb["x1"] + 0.1, y0, y1, -2, 0)), "controls"))
    parts.append(("fuselage", fus, "skin"))
    parts.append(("canopy", build_canopy(), "glass"))
    wing, elevon = build_wing()
    parts += [("wing_R", wing, "skin"), ("wing_L", mirror_y(wing), "skin"),
              ("elevon_R", elevon, "controls"), ("elevon_L", mirror_y(elevon), "controls")]
    vr = build_vtail(1)
    parts += [("ruddervator_R", vr, "controls"), ("ruddervator_L", build_vtail(-1), "controls"), ("spine", build_spine(), "skin")]
    it = build_intake()
    parts += [("intake_R", it, "skin"), ("intake_L", mirror_y(it), "skin")]
    nz, cone = build_nozzle()
    parts += [("nozzle", nz, "propulsion"), ("nozzle_cone", cone, "propulsion")]
    ring = duct_ring()
    d2 = P.DUCT_DEPTH / 2
    sw = le_sweep_deg()
    top = {1: louvres(d2 + 0.0, d2 + 0.012, 9, -sw), -1: louvres(d2 + 0.0, d2 + 0.012, 9, sw)}
    bot = louvres(-d2 - 0.012, -d2)
    env_R = WING_ENVELOPE
    env_L = mirror_y(env_R)
    for n, dx, dy in P.duct_centres():
        env = env_R if dy > 0 else env_L
        r = ring.copy()
        r.apply_translation([dx, dy, 0])
        parts.append((f"duct_{n}", inter(r, env), "propulsion"))      # never proud of the skin near the edges
        for nm, m in ((f"louvres_{n}", top[1 if dy > 0 else -1]), (f"vanes_{n}", bot)):
            v = m.copy()
            v.apply_translation([dx, dy, -0.004 if nm.startswith("louvres") else 0.004])
            parts.append((nm, inter(v, env), "controls"))
    for name, m in build_gear(main_x):
        parts.append((name, m, "gear"))
    return parts


# ---------------------------------------------------------------------------------------------------
# scale-specific insides
# the main spar is two halves that plug into a printed carry-through ring around the thrust tube
def spars_mini():
    return [("spar_main_6mm_R", [SPAR_MAIN_X, 0.52, 0], [SPAR_MAIN_X, SPAR_MAIN_Y, 0], 0.03),
            ("spar_main_6mm_L", [SPAR_MAIN_X, -0.52, 0], [SPAR_MAIN_X, -SPAR_MAIN_Y, 0], 0.03),
            ("spar_centre_4mm", [SPAR_CENTRE_X, -2.30, 0], [SPAR_CENTRE_X, 2.30, 0], 0.02)]
SPAR_MAIN_Y = 4.40          # the main spar halves reach to here (the tip section is too thin beyond)
PACK_CHECK: dict = {}       # filled by inside_parts (full scale): where the battery really ended up
PACK_KG_PER_M3 = 2000.0     # battery pack density (cylindrical-cell modules with structure and cooling, about 2 kg/L)
WING_MOUNTED = ("servo_", "fuel_tank_", "inverter_")     # checked against fuselage + wings, not the fuselage alone
SERVOS_MINI = [("servo_elevon_R", 6.10, 3.90), ("servo_elevon_L", 6.10, -3.90), ("servo_vanes_R", 4.36, 1.02),
               ("servo_vanes_L", 4.36, -1.02)]   # vane servos inboard of the rear fans, a short linkage to each pair
# ruddervator servos: on the centreline in the dorsal spine, fore and aft of each other, above the thrust tube
SERVOS_SPINE = [("servo_ruddervator_R", 7.60, 7.83), ("servo_ruddervator_L", 7.90, 8.13)]


def intake_duct(sg: int):
    """One intake duct inside the fuselage (both scales): from the mouth, inside the cheek, to the cruise fan's face."""
    x0 = P.INTAKE["x0"]
    xf = P.CRUISE_FAN_X
    pts = [(x0 + 0.25, 0.52, -0.20), (x0 + 1.0, 0.46, -0.25), (xf - 0.65, 0.40, -0.22), (xf - 0.43, 0.13, P.CRUISE_FAN_Z)]
    return union(*[cyl([a[0], sg * a[1], a[2]], [b[0], sg * b[1], b[2]], 0.10, 20) for a, b in zip(pts[:-1], pts[1:])])


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
        pb = P.PAYLOAD_BAY
        out += [
            ("battery_4S3P_21700", union(*[cyl([bx + xo - 0.35, yy, zz], [bx + xo + 0.35, yy, zz], 0.105, 32)
                                           for xo in (-0.355, 0.355) for yy in (-0.215, 0.0, 0.215) for zz in (-0.115, 0.097)]), "systems",
             "4S3P Li-ion pack: 12 x 21700 cells lying fore-aft, two 3 x 2 bundles end to end, 141 x 65 x 43 mm; in and out "
             "through the canopy hatch (magnets)"),
            ("fc_speedybee_f405_wing", box(2.80, 3.16, -0.18, 0.18, -0.06, 0.06), "systems",
             "SpeedyBee F405 WING on soft mounts, right behind the battery"),
            ("esc_4in1", box(2.80, 3.16, -0.18, 0.18, -0.24, -0.14), "systems", "4-in-1 ESC (XRotor Micro 60A) under the flight controller, above the payload bay"),
            ("edf_e7206", cyl([P.CRUISE_FAN_X - 0.35, 0, P.CRUISE_FAN_Z], [P.CRUISE_FAN_X + 0.35, 0, P.CRUISE_FAN_Z], 0.35, 48), "propulsion",
             "Freewing E7206 64 mm EDF (70 mm housing), fed by both side intakes"),
            ("thrust_tube", cyl([P.CRUISE_FAN_X + 0.37, 0, P.CRUISE_FAN_Z], [P.NOZZLE["x0"], 0, -0.02], 0.30, 48), "propulsion",
             "0.2 mm PET film thrust tube to the nozzle"),
            ("intake_duct_R", intake_duct(1), "propulsion", "0.2 mm PET film intake duct"),
            ("intake_duct_L", intake_duct(-1), "propulsion", "0.2 mm PET film intake duct"),
            ("fpv_camera_19mm", box(3.12, 3.32, -0.095, 0.095, 0.36, 0.55), "systems", "19 mm FPV camera at the pilot's eye point"),
            ("gps_m10", box(2.50, 2.76, -0.125, 0.125, 0.26, 0.32), "systems", "M10 GPS + compass under the front of the canopy (sky view)"),
            ("edf_esc_60a", box(3.20, 3.80, -0.13, 0.13, -0.27, -0.17), "systems", "EDF ESC (Skywalker 60A V2) on the payload bay roof, in the intake ducts' airflow"),
            ("payload_camera_module", box(pb["x0"] + 0.20, pb["x0"] + 0.62, -0.17, 0.17, -0.46, -0.31), "payload",
             "payload module (default): 4K action camera on a tilt cradle, looking down through the bay-door window; "
             "swap for the mapping, drop-release or sensor module (all at the CG)"),
        ]
        for nm, x, y in SERVOS_MINI:
            out.append((nm, box(x - 0.115, x + 0.115, y - 0.11, y + 0.11, -0.05, 0.05), "systems", "5 g digital servo, laid flat in a pocket"))
        for nm, x0, x1 in SERVOS_SPINE:
            out.append((nm, box(x0, x1, -0.11, 0.11, 0.27, 0.37), "systems", "5 g digital servo in the dorsal spine, short pushrod to the ruddervator's horn"))
        for nm, p0, p1, r in spars_mini():
            out.append((nm, cyl(p0, p1, r, 24), "structure", "carbon tube"))
    else:
        out += [(n, m, "payload", "seated pilot envelope") for n, m in build_pilot()]
        pb = P.PAYLOAD_BAY
        out.append(("cargo_container", box(pb["x0"] + 0.04, pb["x1"] - 0.04, -pb["half_width"] + 0.03, pb["half_width"] - 0.03, -0.45, pb["z_top"] - 0.02),
                    "payload", "belly cargo bay at the CG: medical kit, survival or rescue gear, baggage (doors open sideways)"))
        bx = sizing["battery_x_m"]
        kwh = sizing["battery_kwh"]
        vol = sizing["battery_kg"] / PACK_KG_PER_M3
        hy = sizing.get("hybrid") or {}
        tx0, tx1 = 0.95, 1.70                         # turbogenerator in the nose
        # the battery fills the nose bay between the turbogenerator and the pilot's feet, narrow enough to clear the
        # intake ducts and the exhaust pipes (it is the trim weight: the sizing puts its centroid where the CG needs it)
        nose, info = conformal_pack(vol, float(np.clip(bx, 1.85, 2.30)), x_min=tx1 + 0.08, x_max=2.47, z_lo=-0.40, z_hi=0.05,
                                    w_max=0.44)
        PACK_CHECK.update({"battery_centroid_m": round(float(info["centroid_x"]), 3), "battery_x_sizing_m": round(float(bx), 3),
                           "battery_volume_fill": round(float(info["fill"]), 3)})
        out.append(("battery_pack_nose", nose, "systems",
                    f"{kwh:.0f} kWh pack: conformal modules ahead of the pilot's feet (x {info['x0']:.2f}-{info['x1']:.2f} m, "
                    f"{100 * info['fill']:.0f} % of the volume asked for at {PACK_KG_PER_M3 / 1000:.1f} kg/L)"))
        out += [("intake_duct_R", intake_duct(1), "propulsion", "intake duct inside the cheek"),
                ("intake_duct_L", intake_duct(-1), "propulsion", "intake duct inside the cheek")]
        if hy:
            out.append(("turbogenerator", cyl([tx0, 0, -0.05], [tx1, 0, -0.05], 0.20, 48), "propulsion",
                        f"{hy['generator_kw']:.0f} kW turboshaft + generator in the nose (where a fighter has its radar), fed "
                        "from the intake ducts; it is the heaviest thing that can go forward of the tail-heavy airframe"))
            for sg, nm in ((1, "R"), (-1, "L")):
                pipe = union(cyl([tx1 - 0.02, sg * 0.14, 0.0], [tx1 + 0.12, sg * 0.31, 0.12], 0.05, 20),
                             cyl([tx1 + 0.12, sg * 0.31, 0.12], [P.CRUISE_FAN_X + 0.32, sg * 0.38, 0.12], 0.05, 20),
                             cyl([P.CRUISE_FAN_X + 0.32, sg * 0.38, 0.12], [P.CRUISE_FAN_X + 1.0, sg * 0.20, 0.04], 0.05, 20))
                out.append((f"turbine_exhaust_{nm}", pipe, "propulsion",
                            "insulated exhaust pipe beside the cockpit into the thrust tube (the exhaust leaves by the jet nozzle)"))
            # wing tanks in the outer wing ahead of the main spar
            y0, y1 = P.BODY_Y + 0.10, P.BODY_Y + 0.60
            ys = np.linspace(y0, y1, 6)
            plan = [(float(LE_X(y)) + 0.30, float(y)) for y in ys] + [(SPAR_MAIN_X - 0.10, y1), (SPAR_MAIN_X - 0.10, y0)]
            tank_R = trimesh.creation.extrude_polygon(Polygon(plan), 0.12)
            tank_R.apply_translation([0, 0, -0.06])
            tank_L = mirror_y(tank_R)
            cap = 2 * tank_R.volume * 1000 * 0.92
            out += [("fuel_tank_R", tank_R, "systems", f"wing tank ahead of the main spar ({cap / 2:.0f} L; needs {hy['fuel_l'] / 2:.0f} L)"),
                    ("fuel_tank_L", tank_L, "systems", f"wing tank ahead of the main spar ({cap / 2:.0f} L; needs {hy['fuel_l'] / 2:.0f} L)")]
            PACK_CHECK["fuel_capacity_l"] = round(cap, 1)
            PACK_CHECK["fuel_needed_l"] = round(hy["fuel_l"] * 1.10, 1)
            PACK_CHECK["fuel_centroid_x_m"] = round(float(tank_R.center_mass[0]), 3)
        out += [
            ("flight_computers", box(2.50, 2.80, -0.20, 0.20, 0.0, 0.15), "systems",
             "triplex flight-control computers, air data, radios: behind the instrument panel"),
            ("parachute", cyl([P.CRUISE_FAN_X - 0.45, 0, 0.10], [P.CRUISE_FAN_X - 0.45, 0, 0.40], 0.12, 32), "systems",
             "ballistic recovery parachute behind the seat, under the aft canopy, fires upward"),
            ("cruise_fan", cyl([P.CRUISE_FAN_X - 0.25, 0, P.CRUISE_FAN_Z], [P.CRUISE_FAN_X + 0.25, 0, P.CRUISE_FAN_Z], P.CRUISE_FAN_D / 2, 64),
             "propulsion", "electric ducted cruise fan behind the seat, fed by both side intakes"),
            ("thrust_tube", cyl([P.CRUISE_FAN_X + 0.26, 0, P.CRUISE_FAN_Z], [P.NOZZLE["x0"], 0, -0.02], 0.30, 48), "propulsion",
             "thrust tube from the cruise fan to the nozzle"),
        ]
        for n, dx, dy in P.duct_centres():
            sg = np.sign(dy)
            yy = 0.85 if n.startswith("front") else 2.10
            out.append((f"inverter_{n}", box(SPAR_MAIN_X + 0.15, SPAR_MAIN_X + 0.45, sg * yy - 0.15, sg * yy + 0.15, -0.06, 0.06),
                        "systems", "two inverters (one per rotor) in the aft body behind the main spar"))
        for nm, p0, p1, r in (("spar_main_R", [SPAR_MAIN_X, 0.52, 0], [SPAR_MAIN_X, P.BODY_Y + 1.4, 0], 0.045),
                              ("spar_main_L", [SPAR_MAIN_X, -0.52, 0], [SPAR_MAIN_X, -P.BODY_Y - 1.4, 0], 0.045),
                              ("spar_centre_R", [SPAR_CENTRE_X, 0.52, 0], [SPAR_CENTRE_X, P.BODY_Y - 0.05, 0], 0.05),
                              ("spar_centre_L", [SPAR_CENTRE_X, -0.52, 0], [SPAR_CENTRE_X, -P.BODY_Y + 0.05, 0], 0.05)):
            out.append((nm, cyl(p0, p1, r, 24), "structure", "carbon box-spar line (schematic); a frame carries it round the cockpit"))
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


def best_rect(x, z_lo, z_hi, clear, w_max=9.0):
    """Largest box section (width, z0, z1) that fits the fuselage section at x between z_lo and z_hi."""
    _w, zb, zt = P.fus_at(x)
    lo, hi = max(z_lo, zb + clear), min(z_hi, zt - clear)
    best = (0.0, lo, lo)
    zz = np.linspace(lo, hi, 13)
    for i in range(len(zz)):
        for j in range(i + 2, len(zz)):
            w = min(min(section_width(x, z) for z in np.linspace(zz[i], zz[j], 5)) - 2 * clear, w_max)
            if w > 0 and w * (zz[j] - zz[i]) > best[0] * (best[2] - best[1]):
                best = (w, zz[i], zz[j])
    return best


def conformal_pack(volume, x_centre, x_min, x_max, z_lo, z_hi, dx=0.05, fill=0.85, clear=0.03, w_max=9.0):
    """Battery modules filling fuselage slices around x_centre (alternately aft and fore, so the pack's centroid
    stays near x_centre) until the volume is reached. Each slice is the largest box that fits the section between
    z_lo and z_hi (less a clearance), times a packing fill."""
    slices = []

    def add(x0):
        w, z0, z1 = best_rect(x0 + dx / 2, z_lo, z_hi, clear, w_max)
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
COLORS = {"skin": "#8A939B", "controls": "#7A848D", "glass": "#2A2F33", "propulsion": "#30353A", "gear": "#202428",
          "props": "#15191E", "hardware": "#4B535C", "systems": "#3F7CAC", "payload": "#B07A2A", "structure": "#2A2E33"}
STL_DIR = {"mini": "stl", "full": "stl"}


def inside_test(mesh, pts):
    """Points inside a closed mesh. trimesh's ray-parity test can misfire on a point whose ray grazes an edge, so a
    point it calls outside is re-checked by signed distance (positive inside)."""
    ins = mesh.contains(pts)
    if (~ins).any():
        ins[~ins] = trimesh.proximity.signed_distance(mesh, pts[~ins]) > 0
    return ins


def build(scale_key: str, sizing: dict, out_root: Path | None = None, export: bool = True):
    from mesh import split_to_fit
    from v18_extract import P1S, bed_fit
    set_variant(scale_key)
    s = {"mini": 0.1, "full": 1.0}[scale_key]
    mm_per_m = 1000.0 * s
    cg_x = sizing["cg_m"][0] / s
    main_x = cg_x + P.GEAR["main_dx_behind_cg"]
    oml_parts = build_oml(main_x)
    inner = inside_parts(scale_key, sizing)
    parts = [(n, m, layer, "") for n, m, layer in oml_parts] + inner
    if scale_key == "full":
        parts = [p for p in parts if not p[0].startswith("gear_")] + [p for p in parts if p[0].startswith("gear_")]
    # spar holes through the mini airframe (6 mm main, 4 mm centre) + 0.3 mm clearance
    if scale_key == "mini":
        cutters = [cyl([SPAR_MAIN_X, 0.40, 0], [SPAR_MAIN_X, SPAR_MAIN_Y + 0.02, 0], 0.033, 24),
                   cyl([SPAR_MAIN_X, -0.40, 0], [SPAR_MAIN_X, -SPAR_MAIN_Y - 0.02, 0], 0.033, 24),
                   cyl([SPAR_CENTRE_X, -2.35, 0], [SPAR_CENTRE_X, 2.35, 0], 0.023, 24)]
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
    # the containment envelope is built from the outer mould line before the spar holes are cut (a thin hole through
    # the body would confuse the inside test's ray parity), plus the payload-bay cavity
    env = [bay_box()] + [m for n, m, _l in oml_parts if n in ("fuselage", "canopy", "intake_R", "intake_L", "spine")]
    env = [m.copy() for m in env]
    for m in env:
        m.apply_scale(mm_per_m)
    fus = union(*env)
    airframe = trimesh.util.concatenate([m for n, m, layer, _ in scaled if n in ("fuselage", "wing_R", "wing_L")])
    contain = {}
    for n, m, layer, _ in scaled:
        if (layer in ("systems", "payload") or n.startswith(("turbogenerator", "turbine_exhaust"))) and not n.startswith(WING_MOUNTED):
            v = m.vertices[:: max(1, len(m.vertices) // 300)]
            c0 = v.mean(0)
            v = c0 + (v - c0) * 0.99              # 1 % inset: points on the skin itself count as inside
            inside = inside_test(fus, v) if fus.is_watertight else np.ones(len(v), bool)
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
    # servos sit in wing and spine pockets: check them against the airframe (fuselage + wings + spine) instead
    air = union(*[m for n, m, layer, _ in scaled if n in ("fuselage", "wing_R", "wing_L", "spine")])
    for n, m, layer, _ in scaled:
        if n.startswith(WING_MOUNTED):
            v = m.vertices
            c0 = v.mean(0)
            contain[n] = round(float(inside_test(air, c0 + (v - c0) * 0.99).mean()), 3)
    # internal collisions: every pair of inside parts whose bounding boxes touch, by boolean intersection volume
    inside_names = {n for n, _m, _l, _ in inner if not n.startswith(("fan_",))}
    ins = [(n, m) for n, m, _l, _ in scaled if n in inside_names]
    def ok_pair(a, b):             # intended contacts: the pilot in the seat, the exhaust pipes joining the thrust tube
        pil = lambda n: n.startswith("pilot_") or n == "seat"  # noqa: E731
        joins = ([{"cruise_fan", "thrust_tube"}] + [{f"turbine_exhaust_{sd}", o} for sd in "RL" for o in ("thrust_tube", "turbogenerator")]
                 + [{f"intake_duct_{sd}", o} for sd in "RL" for o in ("edf_e7206", "cruise_fan")])     # the ducts feed the fan face
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
                   and PACK_CHECK["battery_volume_fill"] >= 0.98
                   and PACK_CHECK.get("fuel_capacity_l", 1.0) >= PACK_CHECK.get("fuel_needed_l", 0.0))
    res["checks"]["prop_tip_gap_mm"] = round(tip_gap, 2)
    res["checks"]["watertight"] = {n: bool(m.is_watertight) for n, m, layer, _ in scaled if layer not in ("props", "hardware")}
    # mini print set: every printed part split until it fits the P1S bed
    pieces = []
    if scale_key == "mini":
        printed_names = [n for n, m, layer, _ in scaled if (layer in ("skin", "controls", "glass") or n.startswith(("duct_", "nozzle")))
                         and not n.startswith(FOAM_PARTS)]
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
        for n, m in stand_parts():
            mm = m.copy()
            mm.apply_scale(mm_per_m)
            bf = bed_fit(mm)
            pieces.append({"name": n, "of": "stand", "mesh": mm, "fits": bool(bf and bf[0]), "footprint_mm": bf[1] if bf else None,
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
            foam_templates(out / "foam" / "v20_mini_foam_templates.svg")
        else:
            for n, m, layer, _ in scaled:
                if layer in ("skin", "controls", "glass") or n.startswith(("duct_", "nozzle")):
                    m.export(out / "stl" / f"{n}.stl")
        # the web shows both in one frame: the mini at real size, the full-scale aircraft at 1:10
        glb(scaled, ROOT / "site" / "models" / "raw" / f"v20_{scale_key}.glb", 0.1 if scale_key == "full" else 1.0)
        (out / "parts.json").write_text(json.dumps(res["parts"], indent=1))
        (out / "checks.json").write_text(json.dumps(res["checks"], indent=1))
    return res


FOAM_PARTS = ("ruddervator",)    # mini: cut from 3 mm Depron sheet, not printed


def foam_templates(path: Path, mm_per_m: float = 100.0) -> None:
    """1:1 cutting template (SVG, millimetres) for the mini's foam ruddervators (cut two, one flipped), with the line of
    the 2 mm carbon pivot rod (30 % of the chord: the surface is close to balanced about it, so a 5 g servo holds it)."""
    v = P.VTAIL
    pts = P.vtail_outline()
    tl = math.tan(math.radians(v["le_sweep_deg"]))
    piv = [(v["x_le_root"] + 0.30 * v["c_root"], -0.10), (v["x_le_root"] + v["span"] * tl + 0.30 * v["c_tip"], v["span"])]
    pad, top = 10.0, 18.0
    x0 = min(x for x, _ in pts)
    f = lambda x, y: f"{(x - x0) * mm_per_m + pad:.1f},{top + (v['span'] - y) * mm_per_m:.1f}"   # noqa: E731  root at the bottom
    w = (max(x for x, _ in pts) - x0) * mm_per_m + 2 * pad
    h = top + (v["span"] + 0.15) * mm_per_m + 10
    body = (f'<text x="{pad}" y="10" font-size="5">V20 mini ruddervator - 3 mm Depron, cut 2 (flip one). Print at 100 %; '
            f'the root edge is at the bottom. Dashed: 2 mm carbon pivot rod, 10 mm into the spine.</text>'
            f'<polygon points="{" ".join(f(x, y) for x, y in pts)}" fill="none" stroke="black" stroke-width="0.3"/>'
            f'<polyline points="{f(*piv[0])} {f(*piv[1])}" fill="none" stroke="black" stroke-width="0.3" stroke-dasharray="2,1.5"/>'
            f'<line x1="{pad}" y1="{h - 4:.1f}" x2="{pad + 50}" y2="{h - 4:.1f}" stroke="black" stroke-width="0.5"/>'
            f'<text x="{pad + 52}" y="{h - 3:.1f}" font-size="4">50 mm (check the print scale)</text>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}mm" height="{h:.0f}mm" viewBox="0 0 {w:.0f} {h:.0f}">'
                    + body + "</svg>\n")


def stand_parts():
    """Printed display / balance / charging stand for the mini (full-scale metres, scaled like the aircraft). Two posts
    with rounded saddles hold the body shoulders on the fan-centre line: if the aircraft sits level on them, its CG is
    on the hover balance point. A cable slot lets the charger reach the pack through the canopy hatch."""
    xc = P.duct_centre_x()
    out = [("stand_base", box(xc - 0.95, xc + 0.95, -1.15, 1.15, -1.18, -1.12))]
    for side, y in (("R", 0.78), ("L", -0.78)):
        post = cyl([xc, y, -1.13], [xc, y, -0.20], 0.10, 32)
        saddle = cyl([xc - 0.25, y, -0.215], [xc + 0.25, y, -0.215], 0.06, 32)    # rounded edge along x: a knife edge in pitch
        out.append((f"stand_post_{side}", union(post, saddle)))
    slot = box(xc + 0.55, xc + 0.95, -0.12, 0.12, -1.20, -1.10)
    out[0] = ("stand_base", diff(out[0][1], slot))
    return out


def glb(scaled, path: Path, display_scale: float = 1.0):
    from trimesh.visual.material import PBRMaterial

    def col(h):
        h = h.lstrip("#")
        return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    scene = trimesh.Scene()
    # display only: the blended body (fuselage, wings with their root fillets, spine) is one union, so the overlapping
    # skins do not flicker where they nearly coincide; it is shown under the fuselage's name
    blend = ("fuselage", "wing_R", "wing_L", "spine")
    by = {n: m for n, m, _l, _ in scaled}
    body = union(*[by[n] for n in blend if n in by]) if all(n in by for n in blend) else None
    for n, m, layer, _ in scaled:
        if body is not None and n in blend[1:]:
            continue
        mm = (body if (body is not None and n == "fuselage") else m).copy()
        mm.apply_scale(display_scale)
        # smooth shading with the vertices split at creases (chines, trailing edges, duct lips stay sharp); without
        # normals the viewer falls back to flat, faceted shading
        mm = trimesh.graph.smooth_shade(mm, angle=math.radians(32))
        key = "glass" if n == "canopy" else ("props" if layer == "props" else layer)
        alpha = {"glass": 0.82, "props": 0.85}.get(key, 1.0)
        metal = {"propulsion": 0.45, "hardware": 0.5, "glass": 0.6, "structure": 0.3}.get(key, 0.08)
        mm.visual = trimesh.visual.TextureVisuals(material=PBRMaterial(
            name=n, baseColorFactor=[*col(COLORS.get(key, "#B9C3CD")), alpha], roughnessFactor=0.08 if key == "glass" else 0.62,
            metallicFactor=metal, alphaMode="BLEND" if alpha < 1 else "OPAQUE", doubleSided=False))
        scene.add_geometry(mm, node_name=n, geom_name=n)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(trimesh.exchange.gltf.export_glb(scene, include_normals=True))


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
