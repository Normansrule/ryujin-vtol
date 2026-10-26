"""V20 vortex-lattice model: the cranked-delta planform with the four lift-duct holes, at any scale.

The lattice is built strip by strip from the planform polygon (tools/v20/v20params.py). Each strip covers the
chordwise intervals inside the outline; the duct openings are holes ("open": doors open, fans windmilling or
stopped) or are covered ("closed": louvre doors shut in cruise, full scale) - the two bound the real case.
Elevons are the aft ELEVON["chord_frac"] of the outer strips. Same solver and validation as tools/aero_vlm.py
(within 0.3 % of AeroSandbox on the self-test wings). Linear and inviscid: fins, fuselage cross-flow, duct
lips, fan and jet flow are not modelled.
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


def planform_polygon():
    half = P.half_planform()
    full = [(x, y) for x, y in half] + [(x, -y) for x, y in reversed(half)]
    return Polygon(full)


def lattice(scale: float = 1.0, ducts: str = "open", strip: float = 0.10, panel: float = 0.12, stab: dict | None = None):
    """Panels in metres at the given scale. ducts: 'open' (holes) or 'closed' (covered)."""
    poly = planform_polygon()
    if ducts == "open":
        r = P.DUCT_ID / 2 + P.DUCT_LIP * 0.5      # the lip is rounded: count half of it as lifting surface
        for _n, x, y in P.duct_centres():
            poly = poly.difference(Point(x, y).buffer(r, 64))
    ymax = max(abs(y) for _x, y in poly.exterior.coords)
    n_span = int(round(ymax / strip))
    ys = np.linspace(0.0, ymax, n_span + 1)
    pan = {k: [] for k in ("xa", "ya", "xb", "yb", "xc", "yc", "slope", "tag", "x_le", "x_te", "z")}
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
                    pan["xa"].append(x0 + dx / 4); pan["xb"].append(x0 + dx / 4)
                    pan["ya"].append(y0); pan["yb"].append(y1)
                    pan["xc"].append(x0 + 0.75 * dx); pan["yc"].append(sgn * yc)
                    pan["slope"].append(0.0); pan["tag"].append(tag)
                    pan["x_le"].append(le); pan["x_te"].append(te); pan["z"].append(0.0)
    stab = P.STAB if stab is None else stab
    if stab:
        # all-moving stabilators: a flat swept surface each side of the tail cone (tag "stab")
        s_ = {"y_root": stab["y_root"] * 1000, "y_tip": stab["y_tip"] * 1000, "x_le_root": stab["x_le_root"] * 1000,
              "x_le_tip": (stab["x_le_root"] + (stab["y_tip"] - stab["y_root"]) * math.tan(math.radians(stab["le_sweep_deg"]))) * 1000,
              "c_root": stab["c_root"] * 1000, "c_tip": stab["c_tip"] * 1000, "tag": "stab", "flap_frac": 0.0,
              "z_mm": stab.get("z", 0.0) * 1000}
        tmp = {k: [] for k in pan}
        av.add_surface(tmp, s_, strip * 1000, panel * 1000)
        for k in pan:
            vals = tmp[k]
            if k in ("xa", "ya", "xb", "yb", "xc", "yc", "x_le", "x_te", "z"):
                vals = [v / 1000 for v in vals]
            pan[k] += vals
    Pn = {k: np.array(v) for k, v in pan.items()}
    for k in ("xa", "ya", "xb", "yb", "xc", "yc", "x_le", "x_te", "z"):
        Pn[k] = Pn[k] * scale
    for s in stations:
        s["y"] *= scale; s["le"] *= scale; s["te"] *= scale
        s["intervals"] = [(a * scale, b * scale) for a, b in s["intervals"]]
    return Pn, stations


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


def derivatives(scale: float = 1.0, ducts: str = "open", stab: dict | None = None) -> dict:
    Pn, st = lattice(scale, ducts, stab=stab)
    geo = geometry_metrics(st)
    S, c = geo["S_m2"], geo["mac_m"]
    aic = av.solve_lattice(Pn)
    n = len(Pn["xc"])
    out = {"geo": geo, "panels": n}
    for key, rhs in (("a", -np.ones(n)), ("0", Pn["slope"]), ("de", -(Pn["tag"] == "elevon").astype(float)),
                     ("ds", -(Pn["tag"] == "stab").astype(float)),
                     ("dp", -np.isin(Pn["tag"], ["elevon", "stab"]).astype(float))):
        CL, Cm, _ = av.forces(np.linalg.solve(aic, rhs), Pn, S, c, 0.0)
        out["CL" + key], out["Cm" + key] = float(CL), float(Cm)
    out["x_np_wing_m"] = -out["Cma"] / out["CLa"] * c
    # fuselage: the lattice has no body; add its destabilising moment (Gilruth / Raymer eq. 16.25 with K_fus read
    # from Raymer fig. 16.14 against the wing root quarter-chord position along the body)
    dfus = fuselage_cma(geo, scale)
    out["Cma_fus"] = dfus
    out["Cma"] += dfus
    out["x_np_m"] = -out["Cma"] / out["CLa"] * c
    return out


K_FUS = [(0.1, 0.005), (0.2, 0.008), (0.3, 0.013), (0.4, 0.019), (0.5, 0.027), (0.6, 0.040)]


def fuselage_cma(geo: dict, scale: float) -> float:
    """Fuselage pitching-moment slope per radian (positive = destabilising), about the same reference."""
    w = 2 * max(f[1] for f in P.FUS) * scale
    L = P.FUS_LEN * scale
    root_le, root_te = P.OUTLINE[0][0], P.OUTLINE[-1][0]
    pos = (root_le + 0.25 * (root_te - root_le)) / P.FUS_LEN
    k = float(np.interp(pos, [a for a, _ in K_FUS], [b for _, b in K_FUS]))
    return k * w * w * L / (geo["mac_m"] * geo["S_m2"]) * 180 / math.pi


def static_margin(d: dict, x_cg_m: float) -> float:
    return 100 * (d["x_np_m"] - x_cg_m) / d["geo"]["mac_m"]


def trim(d: dict, x_cg_m: float, mass_kg: float, V: float, eta: float = 0.8, surf: str = "dp"):
    """(alpha rad, elevon rad, CL) for level flight at V with no help from the lift fans."""
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
        print(ducts, {k: round(v, 3) for k, v in g.items()}, "CLa", round(d["CLa"], 3), "NP x", round(d["x_np_m"], 3),
              "(wing+stab", round(d["x_np_wing_m"], 3), ")",
              "SM at duct centre", round(static_margin(d, P.duct_centre_x()), 1), "%", "panels", d["panels"])
