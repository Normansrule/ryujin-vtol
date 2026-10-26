"""SKYFORGE V20 "Falcon Jet" (rev B): one layout, two scales.

All master dimensions are full scale, in metres, in the aircraft frame:
    x aft from the nose tip, y to starboard, z up (wing reference plane z = 0).
The mini is this shape at SCALE["mini"] = 0.1 (4-inch props in the lift ducts). The person-carrying version keeps the
layout and lines but widens the shoulders for bigger fans (FULL_VARIANT below, switched in with use("full")).

Layout logic (lift + cruise), and why it looks the way it does:
  * Four ducted lift fans in a 2 x 2 square, hidden in the shoulders of a wide, blended F-35-style body beside the
    cockpit. Their centre is the hover balance point, so the CG goes there (the battery is the trim weight).
  * Louvres close the ducts top and bottom in cruise (rev A had open holes): the aircraft is then a clean jet, the
    wing keeps its lift over the ducts and the hole drag is gone. The bottom louvres double as exit vanes that turn
    the fan efflux aft in transition (as on the XV-5).
  * With the louvres shut the neutral point moves forward (lift comes back over the front ducts), so the gate is the
    static margin with the ducts closed. The fans therefore sit as far forward as the body allows - right beside the
    pilot - and the trapezoidal outer wings and all-moving stabilators sit well aft.
  * One jet: F-35-style side intakes under the chines feed the cruise fan, which sits close to the CG (the airframe is
    tail-heavy; an aft engine would need a nose full of ballast); a light thrust tube carries its jet to the round
    nozzle. Twin canted fins with rudders on the aft body, all-moving stabilators.
"""
from __future__ import annotations

import math

SCALE = {"mini": 0.1, "full": 1.0}
NOSE_SHIFT = 1.20             # the forebody ahead of the strakes (slender nose, canopy)

# ---------------------------------------------------------------------------------------------------
# lift ducts (full scale)
DUCT_ID = 1.06                 # mini: 106 mm, a 4-inch (101.6 mm) prop with a 2.2 mm tip gap
DUCT_LIP = 0.06                # radial width of the bell-mouth lip (outer mould line)
DUCT_DEPTH = 0.276             # duct depth (mini 27.6 mm): the full depth of the body shoulder, louvre to louvre
BODY_Y = 1.95                  # the blended body's shoulders reach out to here; the thin outer wing starts outboard
BODY_HALF_T = 0.15             # shoulder half-thickness (full scale m): holds the ducts and louvres
DUCT_Y = 1.18                  # duct centres at y = +/-1.18 (inner lip 0.04 m clear of the fuselage side)
DUCT_X = {"front": 2.71, "rear": 4.01}   # 1.30 m apart: 0.12 m of body between the lips (the centre spar runs through it)
DUCT_MARGIN = 0.10             # minimum skin between the duct lip and any planform edge

# ---------------------------------------------------------------------------------------------------
# planform (half, starboard): strake/wing outline from the nose chine to the fuselage side at the trailing edge
# planform (half, starboard, absolute x): chine, body shoulder, outer-wing leading edge to the tip, tip trailing edge,
# forward-swept trailing edge back to the body, body trailing edge to the fuselage side
OUTLINE = [(1.10, 0.30), (1.80, 1.05), (2.35, 1.90), (4.90, 3.80), (6.30, 3.80), (7.00, 1.95), (7.80, 1.25), (8.20, 0.55)]
ELEVON = {"y0": 2.30, "y1": 3.62, "chord_frac": 0.25}

# all-moving stabilators on the tail cone (fighter-style), just below the wing plane
STAB = {"x_le_root": 8.30, "y_root": 0.42, "y_tip": 3.40, "c_root": 2.50, "c_tip": 1.00,
        "le_sweep_deg": 38.0, "z": -0.05}

# ---------------------------------------------------------------------------------------------------
# fuselage (half-width, z bottom, z top) at stations x
FUS = [
    (0.00, 0.000, 0.000, 0.000),
    (0.50, 0.160, -0.140, 0.140),
    (1.30, 0.390, -0.350, 0.300),
    (2.20, 0.450, -0.400, 0.330),
    (3.10, 0.495, -0.440, 0.360),
    (4.20, 0.505, -0.450, 0.360),
    (6.40, 0.505, -0.430, 0.340),
    (8.10, 0.450, -0.370, 0.320),
    (9.30, 0.380, -0.330, 0.300),
    (9.95, 0.350, -0.320, 0.300),
]
FUS_LEN = FUS[-1][0]
CHINE_Z = -0.02
CANOPY = {"x0": 2.05, "x1": 4.75, "z_top": 0.84, "half_width": 0.34, "x_peak": 3.10}

# ---------------------------------------------------------------------------------------------------
# cruise fan, intakes, nozzle
CRUISE_FAN_D = 0.64            # mini: 64 mm EDF (the V18 Freewing E7206)
CRUISE_FAN_X = 4.10           # the cruise fan's centre, between the rear lift fans, near the CG
CRUISE_FAN_Z = -0.08
CRUISE_FAN_X_MINI = 4.10      # mini: the 64 mm EDF in the same place
NOZZLE = {"x0": 9.45, "x1": 10.10, "r0": 0.33, "r1": 0.27}
# F-35-style side intakes: the mouths sit just ahead of the front lift fans; behind them the duct carries on as a cheek
# under the body shoulder (inboard of the fans' lips, below their exit louvres) back to the cruise fan
INTAKE = {"x0": 1.60, "x_cheek": 2.10, "x1": 4.00, "y_out": 0.72, "y_cheek": 0.57, "z0": -0.42, "z1": 0.05, "z_cheek": -0.17}

# ---------------------------------------------------------------------------------------------------
# twin canted fins on the fuselage shoulders
FIN = {"x_root_le": 6.45, "root_chord": 1.55, "tip_chord": 0.55, "height": 1.25, "le_sweep_deg": 40.0,
       "cant_deg": 25.0, "y_root": 0.95, "z_root": 0.10, "rudder_frac": 0.30}

# ---------------------------------------------------------------------------------------------------
# landing gear (tricycle). The mains sit just behind the rear ducts (the duct band is no place for a wheel);
# a VTOL lands vertically, so the long wheelbase only costs a heavier nose-wheel share
GEAR = {"nose_x": 1.70, "main_dx_behind_cg": 1.45, "main_y": 0.80, "height": 0.62, "wheel_d": 0.36,
        "nose_wheel_d": 0.28}

# section thickness (fraction of chord, symmetric thin section)
T_C = 0.05

# ---------------------------------------------------------------------------------------------------
# The person-carrying version. A VTOL cannot simply be scaled up: at constant proportions the disk loading grows with
# size (mass ~ k^3, fan area ~ k^2), and with the mini's 1.06 m-equivalent fans the full-scale aircraft needs more
# than 350 kg/m2 and does not close (trade study). The full scale therefore keeps the mini's layout and lines but
# widens the body shoulders for 1.56 m fans (2.2x the fan area), with a bigger outer wing and stabilators, a longer
# tail cone and the intakes moved forward. With the louvres shut its static margin is positive but small: it relies on
# its triplex fly-by-wire for handling, as fighters do. The mini keeps the 5 % margin a simple autopilot wants.
FULL_VARIANT = {
    "DUCT_ID": 1.56, "DUCT_Y": 1.43, "DUCT_X": {"front": 2.56, "rear": 4.36}, "BODY_Y": 2.45,
    "OUTLINE": [(0.90, 0.30), (1.50, 1.40), (2.00, 2.45), (4.90, 4.40), (6.50, 4.40), (7.40, 2.45), (8.30, 1.50), (8.80, 0.55)],
    "ELEVON": {"y0": 2.85, "y1": 4.20, "chord_frac": 0.25},
    "STAB": {"x_le_root": 8.90, "y_root": 0.42, "y_tip": 4.00, "c_root": 3.00, "c_tip": 1.20, "le_sweep_deg": 38.0, "z": -0.05},
    "FUS": [(0.00, 0.000, 0.000, 0.000), (0.50, 0.160, -0.140, 0.140), (1.30, 0.390, -0.350, 0.300),
            (2.20, 0.450, -0.400, 0.330), (3.10, 0.495, -0.440, 0.360), (4.20, 0.505, -0.450, 0.360),
            (6.40, 0.505, -0.430, 0.340), (8.40, 0.450, -0.370, 0.320), (10.00, 0.380, -0.330, 0.300),
            (10.80, 0.350, -0.320, 0.300)],
    "NOZZLE": {"x0": 10.30, "x1": 10.95, "r0": 0.33, "r1": 0.27},
    "INTAKE": {"x0": 1.30, "x_cheek": 1.80, "x1": 3.80, "y_out": 0.72, "y_cheek": 0.57, "z0": -0.42, "z1": 0.05, "z_cheek": -0.17},
    "FIN": {"x_root_le": 7.00, "root_chord": 1.75, "tip_chord": 0.60, "height": 1.40, "le_sweep_deg": 40.0,
            "cant_deg": 25.0, "y_root": 1.15, "z_root": 0.10, "rudder_frac": 0.30},
    "GEAR": {"nose_x": 1.70, "main_dx_behind_cg": 1.75, "main_y": 0.80, "height": 0.62, "wheel_d": 0.36, "nose_wheel_d": 0.28},
    "CRUISE_FAN_X": 4.45,      # behind the pilot's seat: the intake ducts pass the seat before they turn in
}
_BASE = {k: globals()[k] for k in FULL_VARIANT}
VARIANT = "mini"


def use(variant: str) -> None:
    """Switch the module's shape to the mini outline ('mini') or the person-carrying one ('full')."""
    global VARIANT, FUS_LEN
    src = FULL_VARIANT if variant == "full" else _BASE
    for k, v in src.items():
        globals()[k] = v
    FUS_LEN = globals()["FUS"][-1][0]
    VARIANT = "full" if variant == "full" else "mini"


def duct_centres():
    """[(name, x, y)] for the four lift ducts, full scale."""
    return [(f"{pos}_{side}", DUCT_X[pos], s * DUCT_Y) for pos in ("front", "rear") for side, s in (("R", 1), ("L", -1))]


def duct_centre_x():
    return (DUCT_X["front"] + DUCT_X["rear"]) / 2


def half_planform():
    return list(OUTLINE)


def stab_outline(side: int = 1):
    s = STAB
    xt = s["x_le_root"] + (s["y_tip"] - s["y_root"]) * math.tan(math.radians(s["le_sweep_deg"]))
    return [(s["x_le_root"], side * s["y_root"]), (xt, side * s["y_tip"]), (xt + s["c_tip"], side * s["y_tip"]),
            (s["x_le_root"] + s["c_root"], side * s["y_root"])]


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
