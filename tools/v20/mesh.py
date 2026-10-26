"""Small mesh helpers for the V20 geometry (lofts, thick surfaces, revolves, booleans, P1S splitting)."""
from __future__ import annotations

import math

import numpy as np
import trimesh


def surface_solid(Pm: np.ndarray, N: np.ndarray, H: np.ndarray, hmin: float = 1e-4) -> trimesh.Trimesh:
    """Closed mesh between Pm + H*N and Pm - H*N over a structured (nv, nu) grid."""
    nv, nu, _ = Pm.shape
    H = np.maximum(H, hmin)[..., None]
    top = (Pm + H * N).reshape(-1, 3)
    bot = (Pm - H * N).reshape(-1, 3)
    V = np.vstack([top, bot])
    off = nv * nu
    idx = np.arange(nv * nu).reshape(nv, nu)
    a, b, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
    F = [np.c_[a, b, c], np.c_[a, c, d], np.c_[a + off, c + off, b + off], np.c_[a + off, d + off, c + off]]
    loop = np.array(list(idx[0, :]) + list(idx[1:, -1]) + list(idx[-1, -2::-1]) + list(idx[-2:0:-1, 0]))
    nxt = np.roll(loop, -1)
    F += [np.c_[nxt, loop, loop + off], np.c_[nxt, loop + off, nxt + off]]
    m = trimesh.Trimesh(V, np.vstack(F), process=True)
    if m.volume < 0:
        m.invert()
    return m


def loft_rings(rings, cap_start=True, cap_end=True, start_point=None, end_point=None) -> trimesh.Trimesh:
    """Closed mesh through closed rings (each (k, 3), same k); start/end points close a ring to an apex."""
    k = len(rings[0])
    V = np.vstack(rings)
    F = []
    for i in range(len(rings) - 1):
        for j in range(k):
            a, b = i * k + j, i * k + (j + 1) % k
            F += [[a, b, b + k], [a, b + k, a + k]]
    extra = []
    if cap_start:
        extra.append(np.mean(rings[0], 0) if start_point is None else np.asarray(start_point, float))
        ci = len(V) + len(extra) - 1
        F += [[ci, (j + 1) % k, j] for j in range(k)]
    if cap_end:
        extra.append(np.mean(rings[-1], 0) if end_point is None else np.asarray(end_point, float))
        ci = len(V) + len(extra) - 1
        base = (len(rings) - 1) * k
        F += [[ci, base + j, base + (j + 1) % k] for j in range(k)]
    if extra:
        V = np.vstack([V, np.array(extra)])
    m = trimesh.Trimesh(V, np.array(F), process=True)
    if m.volume < 0:
        m.invert()
    return m


def revolve(profile_rz, sections=96) -> trimesh.Trimesh:
    """Solid of revolution about +z from a closed (r, z) profile (counter-clockwise, r >= 0)."""
    pts = np.asarray(profile_rz, float)
    k = len(pts)
    rings = []
    for t in np.linspace(0, 2 * math.pi, sections, endpoint=False):
        rings.append(np.c_[pts[:, 0] * math.cos(t), pts[:, 0] * math.sin(t), pts[:, 1]])
    V = np.vstack(rings)
    F = []
    for i in range(sections):
        i2 = (i + 1) % sections
        for j in range(k):
            j2 = (j + 1) % k
            a, b, c, d = i * k + j, i * k + j2, i2 * k + j2, i2 * k + j
            F += [[a, b, c], [a, c, d]]
    m = trimesh.Trimesh(V, np.array(F), process=True)
    m.merge_vertices()
    if m.volume < 0:
        m.invert()
    return m


def naca_t(u, t):
    """Half-thickness of a NACA 00xx section as a fraction of chord (closed trailing edge)."""
    u = np.clip(u, 0, 1)
    return 5 * t * (0.2969 * np.sqrt(u) - 0.1260 * u - 0.3516 * u ** 2 + 0.2843 * u ** 3 - 0.1036 * u ** 4)


def box(x0, x1, y0, y1, z0, z1) -> trimesh.Trimesh:
    b = trimesh.creation.box([x1 - x0, y1 - y0, z1 - z0])
    b.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
    return b


def cyl(p0, p1, r, sections=48) -> trimesh.Trimesh:
    return trimesh.creation.cylinder(radius=r, segment=[p0, p1], sections=sections)


def mirror_y(m: trimesh.Trimesh) -> trimesh.Trimesh:
    m = m.copy()
    m.vertices[:, 1] *= -1
    m.invert()
    return m


def diff(a, *cutters):
    cutters = [c for c in cutters if c is not None]
    if not cutters:
        return a
    return trimesh.boolean.difference([a, *cutters], engine="manifold")


def union(*ms):
    ms = [m for m in ms if m is not None]
    return ms[0] if len(ms) == 1 else trimesh.boolean.union(ms, engine="manifold")


def inter(a, b):
    return trimesh.boolean.intersection([a, b], engine="manifold")


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def split_to_fit(mesh: trimesh.Trimesh, fits, max_depth: int = 4):
    """Cut a solid with planes normal to its longest bounding-box axis until every piece passes fits(mesh).
    Returns a list of watertight pieces (capped cuts)."""
    if fits(mesh) or max_depth == 0:
        return [mesh]
    lo, hi = mesh.bounds
    ax = int(np.argmax(hi - lo))
    n = np.zeros(3)
    n[ax] = 1.0
    # a cut plane that grazes a vertex row or a spar hole can leave a cap that does not close; try a few offsets
    # around the middle and keep the first cut whose pieces are all watertight
    halves = None
    for f in (0.0, 0.017, -0.029, 0.043, -0.061, 0.083):
        o = np.zeros(3)
        o[ax] = (lo[ax] + hi[ax]) / 2 + f * (hi[ax] - lo[ax])
        cand = []
        for sgn in (1, -1):
            half = mesh.slice_plane(o, sgn * n, cap=True)
            if half is None or len(half.faces) == 0:
                continue
            half.merge_vertices()
            for part in half.split(only_watertight=False):
                if part.volume < 1e-9 * max(1.0, mesh.volume):
                    continue
                cand.append(part)
        if halves is None:
            halves = cand
        if cand and all(p.is_watertight for p in cand):
            halves = cand
            break
    out = []
    for part in halves or []:
        out += split_to_fit(part, fits, max_depth - 1)
    return out
