# V21 COPY (2026-11-16): copied unchanged from tools/v20 as the V21 "Ryujin" starting point; V20 stays frozen.
# Running this file directly is disabled so it can never overwrite V20 outputs (analysis/v20_*.json, cad/v20/).
# Use tools/v21/amphib.py.
"""SKYFORGE V20 "Falcon Jet" (rev C): one outer mould line, two scales.

All master dimensions are full scale, in metres, in the aircraft frame:
    x aft from the nose tip, y to starboard, z up (wing reference plane z = 0).
The mini is exactly this shape at SCALE["mini"] = 0.1 (6-inch props in 157 mm lift ducts): a true 1:10 model of the
person-carrying aircraft. What changes between the scales is what sits inside (structure, motors, battery, payload).

Layout logic (lift + cruise), and why it looks the way it does (rev C: the Anduril Fury / CCA family look):
  * Four ducted lift fans in a staggered chevron, hidden in the shoulders of a wide blended lifting body under louvres
    that shut in cruise: the front pair beside the cockpit, the rear pair further out along the wing's sweep. Their
    centroid is the hover balance point, so the CG goes there.
  * A chined forebody: the nose's widest line is a sharp chine that runs straight into the wing leading edge, so the
    body, strakes and wing read as one shape. A low canopy fairs into a dorsal spine that runs back to the tail.
  * A V-tail of two all-moving ruddervators replaces the four tail surfaces of rev B (two stabilators, two fins):
    half the tail area for the same job, fewer parts and servos, and the clean silhouette of the CCA designs.
  * A longer, less swept outer wing (aspect ratio up a third over rev B) for range.
  * An internal payload bay in the belly between the four fans, at the CG: a payload can be swapped or dropped
    without re-trimming (the reason the F-35 and the bombers keep their weapons bays at the CG).
  * One jet: side intakes under the chines feed the cruise fan close to the CG; a thrust tube carries its jet to the
    nozzle between the ruddervator roots.
"""
from __future__ import annotations

import math

SCALE = {"mini": 0.1, "full": 1.0}

# ---------------------------------------------------------------------------------------------------
# lift ducts (full scale)
DUCT_ID = 1.57                 # mini: 157 mm, a 6-inch (152.4 mm) prop with a 2.2 mm tip gap
DUCT_LIP = 0.06                # radial width of the bell-mouth lip (outer mould line)
DUCT_DEPTH = 0.276             # duct depth (mini 27.6 mm): the full depth of the body shoulder, louvre to louvre
BODY_Y = 3.30                  # the blended body's shoulders reach out to here (past the rear fans); outer wing outboard
BODY_HALF_T = 0.15             # shoulder half-thickness (full scale m): holds the ducts and louvres
# fan rows, fore to aft: each row is a pair of ducts at +/- y. Staggered (rev C.2): the front pair tucked against the
# body beside the cockpit, the rear pair 0.9 m further out, so the four fans form a chevron that follows the wing's sweep.
#  * the rear fans sit out of the front fans' disturbed inflow and louvre wake in transition (tandem fans in line ingest
#    each other's wake);
#  * their roll and yaw arm grows from 1.43 to 2.33 m (yaw comes from differential exit vanes: arm x vane force);
#  * the bay between the rear fans and the fuselage is free: the main landing gear moves forward to just behind the
#    CG instead of behind the whole fan band, and the rear fans' efflux no longer hits the gear and the belly;
#  * the fore-aft spacing (pitch arm) and the fan centroid - the hover balance point - are unchanged.
DUCT_X = {"front": 2.56, "rear": 4.36}
DUCT_Y = {"front": 1.43, "rear": 2.33}
DUCT_MARGIN = 0.10             # minimum skin between the duct lip and any planform edge

# ---------------------------------------------------------------------------------------------------
# planform (half, starboard, absolute x): chine, body shoulder, outer-wing leading edge to the tip, tip trailing edge,
# trailing edge back to the body, then the wide aft body ('beavertail': it carries the V-tail and the nozzle)
OUTLINE = [(1.15, 0.34), (1.25, 1.30), (1.95, 2.45), (6.10, 5.00), (7.35, 5.00), (7.90, 2.45), (8.70, 1.55), (10.00, 0.70),
           (10.30, 0.55)]
ELEVON = {"y0": 2.95, "y1": 4.80, "chord_frac": 0.28}
T_C = 0.06                     # outer-wing section thickness (fraction of chord), round leading edge

# V-tail: two all-moving ruddervators on the aft body (pitch together, yaw differentially)
VTAIL = {"x_le_root": 8.30, "y_root": 0.42, "z_root": 0.16, "span": 2.30, "c_root": 2.40, "c_tip": 1.00,
         "le_sweep_deg": 40.0, "dihedral_deg": 45.0}

# ---------------------------------------------------------------------------------------------------
# fuselage (half-width at the chine, z bottom, z top) at stations x
FUS = [
    (0.00, 0.000, 0.000, 0.000),
    (0.45, 0.240, -0.140, 0.140),
    (1.05, 0.500, -0.320, 0.330),
    (2.00, 0.550, -0.440, 0.360),
    (3.10, 0.540, -0.500, 0.360),
    (4.40, 0.540, -0.500, 0.360),
    (6.40, 0.530, -0.430, 0.380),
    (8.40, 0.500, -0.360, 0.340),
    (10.00, 0.440, -0.320, 0.300),
    (10.80, 0.400, -0.310, 0.290),
]
FUS_LEN = FUS[-1][0]
CHINE_Z = -0.02
# chine sharpness: the section is z = z_chine + h (1 - |y/w|^q)^r above and below; r = 1 is a sharp chine, r = 0.5 an
# ellipse. Sharp at the nose, softening aft where the body blends into the wing roots
CHINE = {"r_nose": 1.0, "r_aft": 0.75, "x_soft": (2.5, 6.0), "q_up": 2.6, "q_lo": 3.0}
CANOPY = {"x0": 2.10, "x1": 5.40, "z_top": 0.78, "half_width": 0.33, "x_peak": 3.15}
SPINE = {"x0": 5.0, "x1": 9.6, "z_top": 0.46, "half_width": 0.22}       # dorsal spine behind the canopy

# ---------------------------------------------------------------------------------------------------
# cruise fan, intakes, nozzle
CRUISE_FAN_D = 0.64            # mini: 64 mm EDF (the V18 Freewing E7206)
CRUISE_FAN_X = 4.40            # the cruise fan's centre, between the rear lift fans, near the CG
CRUISE_FAN_Z = -0.08
NOZZLE = {"x0": 10.30, "x1": 10.95, "r0": 0.33, "r1": 0.27}
# side intakes: the mouths sit under the chines just ahead of the front lift fans; behind them the duct carries on as a
# cheek under the body shoulder (inboard of the fans' lips, below their exit louvres) back to the cruise fan
INTAKE = {"x0": 1.40, "x_cheek": 1.95, "x1": 3.90, "y_out": 0.88, "y_cheek": 0.60, "z0": -0.46, "z1": -0.03, "z_cheek": -0.19}

# internal payload bay in the belly between the four fans, at the CG (full-scale m; mini = /10). Doors flush in cruise
PAYLOAD_BAY = {"x0": 2.90, "x1": 3.80, "half_width": 0.27, "z_top": -0.29, "door_t": 0.03}

# ---------------------------------------------------------------------------------------------------
# landing gear (tricycle). The mains sit 1.1 m behind the CG, in the bay between the rear fans and the fuselage
GEAR = {"nose_x": 1.60, "main_dx_behind_cg": 1.10, "main_y": 0.85, "height": 0.62, "wheel_d": 0.36,
        "nose_wheel_d": 0.28}

# ---------------------------------------------------------------------------------------------------
# What differs inside the person-carrying version (the outer mould line is the same)
FULL_VARIANT = {
    "CRUISE_FAN_X": 4.55,      # behind the pilot's seat: the intake ducts pass the seat before they turn in
}
_BASE = {k: globals()[k] for k in FULL_VARIANT}
VARIANT = "mini"


def use(variant: str) -> None:
    """Switch the module to the mini's insides ('mini') or the person-carrying aircraft's ('full')."""
    global VARIANT, FUS_LEN
    src = FULL_VARIANT if variant == "full" else _BASE
    for k, v in src.items():
        globals()[k] = v
    FUS_LEN = globals()["FUS"][-1][0]
    VARIANT = "full" if variant == "full" else "mini"


def rows():
    """Fan rows, fore to aft."""
    return sorted(DUCT_X, key=lambda r: DUCT_X[r])


def duct_centres():
    """[(name, x, y)] for every lift duct, full scale."""
    return [(f"{pos}_{side}", DUCT_X[pos], s * DUCT_Y[pos]) for pos in rows() for side, s in (("R", 1), ("L", -1))]


def n_fans():
    return 2 * len(DUCT_X)


def duct_centre_x():
    """The hover balance point: the centroid of the fans (equal fans share the weight equally there)."""
    return sum(DUCT_X.values()) / len(DUCT_X)


def half_planform():
    return list(OUTLINE)


def vtail_frame(side: int = 1):
    """(root LE point, unit vector along the panel's span, unit normal) of one ruddervator, full scale."""
    v = VTAIL
    g = math.radians(v["dihedral_deg"])
    root = (v["x_le_root"], side * v["y_root"], v["z_root"])
    span_dir = (0.0, side * math.cos(g), math.sin(g))
    normal = (0.0, -side * math.sin(g), math.cos(g))
    return root, span_dir, normal


def vtail_outline():
    """Panel outline in its own plane: [(x, s)] with s along the span from the root (for templates and areas)."""
    v = VTAIL
    xt = v["x_le_root"] + v["span"] * math.tan(math.radians(v["le_sweep_deg"]))
    return [(v["x_le_root"], 0.0), (xt, v["span"]), (xt + v["c_tip"], v["span"]), (v["x_le_root"] + v["c_root"], 0.0)]


def vtail_area_each():
    v = VTAIL
    return (v["c_root"] + v["c_tip"]) / 2 * v["span"]


def chine_r(x):
    c = CHINE
    a, b = c["x_soft"]
    f = min(max((x - a) / (b - a), 0.0), 1.0)
    return c["r_nose"] + (c["r_aft"] - c["r_nose"]) * f


def fus_at(x):
    """(half-width, z bottom, z top) at station x."""
    if x <= FUS[0][0]:
        return FUS[0][1:]
    for a, b in zip(FUS[:-1], FUS[1:]):
        if a[0] <= x <= b[0]:
            f = (x - a[0]) / (b[0] - a[0])
            return tuple(a[i] + f * (b[i] - a[i]) for i in (1, 2, 3))
    return FUS[-1][1:]


def sweep_deg(p0, p1):
    return math.degrees(math.atan2(p1[0] - p0[0], p1[1] - p0[1]))
