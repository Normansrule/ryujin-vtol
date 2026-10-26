"""V20 vortex-lattice model: the blended-body planform with the four lift-duct openings and the V-tail, at any scale.

The wing lattice is built strip by strip from the planform polygon (tools/v20/v20params.py). Each strip covers the
chordwise intervals inside the outline; the duct openings are holes ("open": louvres open, fans windmilling or
stopped) or are covered ("closed": louvres shut in cruise) - the two bound the real case. Elevons are the aft
ELEVON["chord_frac"] of the outer strips.

The V-tail is not flat, so the lattice is non-planar: every panel carries its own normal and the boundary condition
is no flow through the panel along that normal (same horseshoe vortices and Biot-Savart kernel as tools/aero_vlm.py,
which agrees with AeroSandbox within 0.3 % on its self-test wings). A ruddervator tilted by its dihedral G then works
in pitch with the familiar cos^2 G and in yaw with sin^2 G without any correction factor. Linear and inviscid:
fuselage cross-flow (added by Raymer's method), duct lips, fan and jet flow are not modelled.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Polygon, Point

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import aero_vlm as av  # noqa: E402
import v20params as P  # noqa: E402

RHO, G0 = av.RHO, av.G0
KEYS = ("xa", "ya", "za", "xb", "yb", "zb", "xc", "yc", "zc", "nx", "ny", "nz", "tag", "x_le", "x_te")


def planform_polygon():
    half = P.half_planform()
    full = [(x, y) for x, y in half] + [(x, -y) for x, y in reversed(half)]
    return Polygon(full)


def _add(pan, a, b, c, n, tag, le, te):
    for k, v in zip(("xa", "ya", "za"), a):
        pan[k].append(v)
    for k, v in zip(("xb", "yb", "zb"), b):
        pan[k].append(v)
    for k, v in zip(("xc", "yc", "zc"), c):
        pan[k].append(v)
    for k, v in zip(("nx", "ny", "nz"), n):
        pan[k].append(v)
    pan["tag"].append(tag); pan["x_le"].append(le); pan["x_te"].append(te)


def add_vtail(pan, strip: float, panel: float, vt: dict | None = None):
    """Both ruddervators as panels in their own (tilted) planes. Bound vortices run in +y on both sides, so a positive
    circulation pushes along the panel normal (up and inboard)."""
    vt = vt or P.VTAIL
    g = math.radians(vt["dihedral_deg"])
    n_span = max(3, int(round(vt["span"] / strip)))
    ss = np.linspace(0.0, vt["span"], n_span + 1)
    tl = math.tan(math.radians(vt["le_sweep_deg"]))
    for j in range(n_span):
        sa, sb = ss[j], ss[j + 1]
        sc = (sa + sb) / 2
        f = sc / vt["span"]
        xl = vt["x_le_root"] + sc * tl
        c = vt["c_root"] + f * (vt["c_tip"] - vt["c_root"])
        n = max(2, int(round(c / panel)))
        dx = c / n
        for i in range(n):
            x0 = xl + i * dx
            for side in (1, -1):
                p = lambda s, x: (x, side * (vt["y_root"] + s * math.cos(g)), vt["z_root"] + s * math.sin(g))  # noqa: E731
                A_, B_ = p(sa, x0 + dx / 4), p(sb, x0 + dx / 4)
                if side == -1:
                    A_, B_ = B_, A_
                _add(pan, A_, B_, p(sc, x0 + 0.75 * dx), (0.0, -side * math.sin(g), math.cos(g)), "vtail", xl, xl + c)


def lattice(scale: float = 1.0, ducts: str = "open", strip: float = 0.10, panel: float = 0.12, vtail: bool = True):
    """Panels in metres at the given scale. ducts: 'open' (holes) or 'closed' (covered)."""
    poly = planform_polygon()
    if ducts == "open":
        r = P.DUCT_ID / 2 + P.DUCT_LIP * 0.5      # the lip is rounded: count half of it as lifting surface
        for _n, x, y in P.duct_centres():
            poly = poly.difference(Point(x, y).buffer(r, 64))
    ymax = max(abs(y) for _x, y in poly.exterior.coords)
    n_span = int(round(ymax / strip))
    ys = np.linspace(0.0, ymax, n_span + 1)
    pan = {k: [] for k in KEYS}
    stations = []
    xmin, _y0, xmax, _y1 = poly.bounds
    for j in range(n_span):
        ya, yb = ys[j], ys[j + 1]
        yc = (ya + yb) / 2
        cut = poly.intersection(LineString([(xmin - 1, yc), (xmax + 1, yc)]))
        segs = [cut] if cut.geom_type == "LineString" else [g for g in getattr(cut, "geoms", []) if g.geom_type == "LineString"]
        ivs = sorted((min(c[0] for c in g.coords), max(c[0] for c in g.coords)) for g in segs if g.length > 1e-6)
        if not ivs:
            continue
        le, te = ivs[0][0], ivs[-1][1]
        stations.append({"y": yc, "le": le, "te": te, "intervals": ivs})
        elevon = P.ELEVON["y0"] <= yc <= P.ELEVON["y1"]
        for a, b in ivs:
            c = b - a
            n = max(2, int(round(c / panel)))
            dx = c / n
            for i in range(n):
                x0 = a + i * dx
                xm = x0 + dx / 2
                tag = "elevon" if (elevon and xm > te - P.ELEVON["chord_frac"] * (te - le)) else "wing"
                for sgn in (1, -1):
                    y0, y1 = (ya, yb) if sgn == 1 else (-yb, -ya)
                    _add(pan, (x0 + dx / 4, y0, 0.0), (x0 + dx / 4, y1, 0.0), (x0 + 0.75 * dx, sgn * yc, 0.0), (0.0, 0.0, 1.0),
                         tag, le, te)
    if vtail:
        add_vtail(pan, strip, panel)
    Pn = {k: (np.array(v) if k == "tag" else np.array(v, float)) for k, v in pan.items()}
    for k in KEYS:
        if k not in ("tag", "nx", "ny", "nz"):
            Pn[k] = Pn[k] * scale
    for s in stations:
        s["y"] *= scale; s["le"] *= scale; s["te"] *= scale
        s["intervals"] = [(a * scale, b * scale) for a, b in s["intervals"]]
    return Pn, stations


def aic(Pn):
    """Normal velocity at each control point from each unit horseshoe (trailing legs along +x at the bound vortex's
    height): non-planar, so the V-tail panels see the wing's wake and the wing sees theirs."""
    A_ = np.c_[Pn["xa"], Pn["ya"], Pn["za"]]
    B_ = np.c_[Pn["xb"], Pn["yb"], Pn["zb"]]
    C_ = np.c_[Pn["xc"], Pn["yc"], Pn["zc"]]
    N_ = np.c_[Pn["nx"], Pn["ny"], Pn["nz"]]
    ex = np.array([1.0, 0.0, 0.0])
    out = np.empty((len(C_), len(A_)))
    for i0 in range(0, len(C_), 600):                  # in blocks: the full velocity tensor would not fit in memory
        c = C_[i0:i0 + 600]
        v = -av._semi_inf(c, A_, ex) + av._seg_induced(c, A_, B_) + av._semi_inf(c, B_, ex)
        out[i0:i0 + 600] = np.einsum("nmk,nk->nm", v, N_[i0:i0 + 600])
    return out


def loads(gamma, Pn):
    """Per-panel force (per unit rho V^2) from Kutta-Joukowski with V along +x: F = G x l, l = B - A."""
    lx, ly, lz = Pn["xb"] - Pn["xa"], Pn["yb"] - Pn["ya"], Pn["zb"] - Pn["za"]
    return gamma * ly, -gamma * lz          # lift (z), side force (y)


def geometry_metrics(stations):
    """Reference area (gross: holes included, as conventional), span, mean aerodynamic chord and its LE."""
    y = np.array([s["y"] for s in stations])
    full = np.array([s["te"] - s["le"] for s in stations])
    net = np.array([sum(b - a for a, b in s["intervals"]) for s in stations])
    le = np.array([s["le"] for s in stations])
    dy = np.gradient(y) if len(y) > 1 else np.array([0.01])
    S = 2 * float((full * dy).sum())
    S_net = 2 * float((net * dy).sum())
    b = 2 * float(y.max() + dy[-1] / 2)
    mac = 2 * float((full ** 2 * dy).sum()) / S
    x_le_mac = 2 * float((le * full * dy).sum()) / S
    return {"S_m2": S, "S_net_m2": S_net, "span_m": b, "AR": b * b / S, "mac_m": mac, "x_le_mac_m": x_le_mac}


def derivatives(scale: float = 1.0, ducts: str = "open", strip: float = 0.10, panel: float = 0.12) -> dict:
    Pn, st = lattice(scale, ducts, strip, panel)
    geo = geometry_metrics(st)
    S, c, b = geo["S_m2"], geo["mac_m"], geo["span_m"]
    M = aic(Pn)
    lu = np.linalg.inv(M)
    n = len(Pn["xc"])
    xm = (Pn["xa"] + Pn["xb"]) / 2
    tag = Pn["tag"]
    out = {"geo": geo, "panels": n}
    # right-hand sides: alpha (normal component of the freestream tilt), camber 0, deflections (each panel's own
    # incidence: -1 per radian), and sideslip (+n_y per radian of beta)
    for key, rhs in (("a", -Pn["nz"]), ("0", np.zeros(n)), ("de", -(tag == "elevon").astype(float)),
                     ("ds", -(tag == "vtail").astype(float)), ("dp", -np.isin(tag, ["elevon", "vtail"]).astype(float))):
        L, _Y = loads(lu @ rhs, Pn)
        out["CL" + key] = float(2 * L.sum() / S)
        out["Cm" + key] = float(2 * (L * (0.0 - xm)).sum() / (S * c))
    out["x_np_wing_m"] = -out["Cma"] / out["CLa"] * c
    # yaw: the V-tail's side force per radian of sideslip; yawing moment about a reference x (stable = positive)
    _L, Y = loads(lu @ Pn["ny"], Pn)
    out["_beta_Y"] = Y
    out["_beta_x"] = xm
    out["CYb_tail"] = float(2 * Y.sum() / S)
    # fuselage: the lattice has no body; add its destabilising moment (Gilruth / Raymer eq. 16.25 with K_fus read
    # from Raymer fig. 16.14 against the wing root quarter-chord position along the body)
    dfus = fuselage_cma(geo, scale)
    out["Cma_fus"] = dfus
    out["Cma"] += dfus
    out["x_np_m"] = -out["Cma"] / out["CLa"] * c
    out["Cnb_fus"] = fuselage_cnb(geo, scale)
    return out


def cn_beta(d: dict, x_cg_m: float) -> dict:
    """Directional stability per radian about x_cg: the V-tail from the lattice (sideslip right-hand side) and the
    fuselage's destabilising part (Raymer eq. 16.47). Positive total = weathercock stable."""
    S, b = d["geo"]["S_m2"], d["geo"]["span_m"]
    tail = float(-2 * (d["_beta_Y"] * (d["_beta_x"] - x_cg_m)).sum() / (S * b))
    return {"Cnb_tail": tail, "Cnb_fus": d["Cnb_fus"], "Cnb": tail + d["Cnb_fus"]}


K_FUS = [(0.1, 0.005), (0.2, 0.008), (0.3, 0.013), (0.4, 0.019), (0.5, 0.027), (0.6, 0.040)]


def fuselage_cma(geo: dict, scale: float) -> float:
    """Fuselage pitching-moment slope per radian (positive = destabilising), about the same reference."""
    w = 2 * max(f[1] for f in P.FUS) * scale
    L = P.FUS_LEN * scale
    root_le, root_te = P.OUTLINE[0][0], P.OUTLINE[-1][0]
    pos = (root_le + 0.25 * (root_te - root_le)) / P.FUS_LEN
    k = float(np.interp(pos, [a for a, _ in K_FUS], [b for _, b in K_FUS]))
    return k * w * w * L / (geo["mac_m"] * geo["S_m2"]) * 180 / math.pi


def fuselage_cnb(geo: dict, scale: float) -> float:
    """Raymer eq. 16.47: Cn_beta,fus = -1.3 (fuselage volume / (S b)) (depth / width), per radian. The volume is taken
    as 0.7 x the box of each section (the chined section is fuller than an ellipse at the sides, thinner at the top)."""
    xs = np.linspace(0.0, P.FUS_LEN, 60)
    secs = [P.fus_at(x) for x in xs]
    vol = float(np.trapezoid([0.7 * 2 * w * (zt - zb) for w, zb, zt in secs], xs)) * scale ** 3
    depth = max(zt - zb for _w, zb, zt in secs)
    width = 2 * max(w for w, _zb, _zt in secs)
    return -1.3 * vol / (geo["S_m2"] * geo["span_m"]) * depth / width


def static_margin(d: dict, x_cg_m: float) -> float:
    return 100 * (d["x_np_m"] - x_cg_m) / d["geo"]["mac_m"]


def trim(d: dict, x_cg_m: float, mass_kg: float, V: float, eta: float = 0.8, surf: str = "dp"):
    """(alpha rad, pitch-surface rad, CL) for level flight at V with no help from the lift fans."""
    c, S = d["geo"]["mac_m"], d["geo"]["S_m2"]
    cm = lambda k: d["Cm" + k] + d["CL" + k] * x_cg_m / c          # noqa: E731
    CLreq = mass_kg * G0 / (0.5 * RHO * V * V * S)
    M = np.array([[d["CLa"], eta * d["CL" + surf]], [cm("a"), eta * cm(surf)]])
    a, de = np.linalg.solve(M, np.array([CLreq - d["CL0"], -cm("0")]))
    return float(a), float(de), float(CLreq)


if __name__ == "__main__":
    for ducts in ("open", "closed"):
        d = derivatives(1.0, ducts)
        g = d["geo"]
        xc = P.duct_centre_x()
        print(ducts, {k: round(v, 3) for k, v in g.items()}, "CLa", round(d["CLa"], 3), "NP x", round(d["x_np_m"], 3),
              "SM at duct centre", round(static_margin(d, xc), 1), "%", "Cn_beta", {k: round(v, 4) for k, v in cn_beta(d, xc).items()},
              "panels", d["panels"])
