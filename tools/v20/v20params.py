"""SKYFORGE V20 "Falcon Jet": one outer mould line, two scales.

All master dimensions are full scale, in metres, in the aircraft frame:
    x aft from the nose tip, y to starboard, z up (wing reference plane z = 0).
The mini is the same outer mould line at SCALE["mini"] = 0.1 (6-inch props in the lift ducts); what changes
between the scales is what sits inside it (structure, motors, battery, payload), not the shape.

Layout logic (lift + cruise), and why it looks the way it does:
  * Four ducted lift fans in a 2 x 2 square. Their centre is the hover balance point, so the CG goes there
    (the battery position is the trim variable). Every fan then lifts a quarter of the weight.
  * For wing-borne flight the neutral point has to sit behind that same point. Ducts sunk in a wing sit at
    about half the local chord, while a delta's neutral point sits at about a third of its mean chord - so the
    ducts go into the forward half of a big delta (strakes beside the cockpit and the wing roots), the wing
    carries on well behind them, and all-moving stabilators on the tail cone add the rest of the margin.
    Earlier layouts with the ducts spread through the whole wing were 15-25 % unstable (docs/V20_FALCON_JET.md).
  * One ducted cruise fan in the tail cone, fed by two fighter-style side intakes, exhausting through a round
    nozzle at the tail - the "jet". Twin canted fins with rudders; elevons on the outer wing.
  * The ducts stay open in cruise (fixed-pitch fans stopped and parked). Louvre doors would cut cruise drag but put
    lift back over the front ducts and cost about 10 % static margin; they are not in this layout. A stopped fan
    still blocks part of its duct, so the stability gate is the margin at 25 % blockage, between open and closed.
  * Stabilators of 3.2 m semi-span keep that blocked-duct margin >= 5 %.
  * Fan size is the full-scale design driver. With 1.06 m ducts (v0.7 draft) the disk loading was over 350 kg/m2 and
    the full-scale aircraft did not close under honest assumptions; 1.56 m ducts (6-inch props on the mini) need
    wider strakes and a closer duct spacing, and close as a series hybrid (docs/V20_FALCON_JET.md, trade study).
"""
from __future__ import annotations

import math

SCALE = {"mini": 0.1, "full": 1.0}
NOSE_SHIFT = 1.20             # the forebody ahead of the strakes (slender nose, canopy)

# ---------------------------------------------------------------------------------------------------
# lift ducts (full scale)
DUCT_ID = 1.56                 # mini: 156 mm, a 6-inch (152.4 mm) prop with a 1.8 mm tip gap
DUCT_LIP = 0.06                # radial width of the bell-mouth lip (outer mould line)
DUCT_DEPTH = 0.22              # duct depth at the fan plane (mini 22 mm)
DUCT_Y = 1.39                  # duct centres at y = +/-1.39 (inner lip 0.045 m clear of the fuselage side)
DUCT_X = {"front": 2.46 + NOSE_SHIFT, "rear": 4.26 + NOSE_SHIFT}   # 1.80 m apart: 0.12 m of strake between the lips
                                                                   # (the centre spar runs through it)
DUCT_MARGIN = 0.10             # minimum skin between the duct lip and any planform edge

# ---------------------------------------------------------------------------------------------------
# planform (half, starboard): strake/wing outline from the nose chine to the fuselage side at the trailing edge
_OUT = [(0.70, 0.27), (1.40, 1.40), (1.90, 2.35), (4.55, 3.55), (5.50, 3.55), (7.05, 1.90), (7.05, 0.50)]
OUTLINE = [(x + NOSE_SHIFT, y) for x, y in _OUT]
ELEVON = {"y0": 2.35, "y1": 3.45, "chord_frac": 0.22}

# all-moving stabilators on the tail cone (fighter-style), just below the wing plane
STAB = {"x_le_root": 7.05 + NOSE_SHIFT, "y_root": 0.42, "y_tip": 3.20, "c_root": 2.00, "c_tip": 0.70,
        "le_sweep_deg": 30.0, "z": -0.05}

# ---------------------------------------------------------------------------------------------------
# fuselage (half-width, z bottom, z top) at stations x
FUS = [
    (0.00, 0.000, 0.000, 0.000),
    (0.50, 0.110, -0.090, 0.100),
    (1.30, 0.330, -0.300, 0.270),
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
CRUISE_FAN_X = 5.70           # both scales: the cruise fan sits at the side intakes' throat, near the CG, and a
                              # thrust tube carries its jet (and, full scale, the turbine exhaust) to the nozzle
CRUISE_FAN_X_MINI = 5.70      # mini: EDF at the intake throat, a film thrust tube runs to the nozzle
NOZZLE = {"x0": 9.45, "x1": 10.10, "r0": 0.33, "r1": 0.27}
INTAKE = {"x0": 5.15, "x1": 6.20, "y_out": 0.68, "z0": -0.40, "z1": -0.15}   # under the rear ducts' lower lip

# ---------------------------------------------------------------------------------------------------
# twin canted fins on the fuselage shoulders
FIN = {"x_root_le": 7.55, "root_chord": 1.55, "tip_chord": 0.60, "height": 1.15, "le_sweep_deg": 45.0,
       "cant_deg": 22.0, "y_root": 0.38, "z_root": 0.30, "rudder_frac": 0.30}

# ---------------------------------------------------------------------------------------------------
# landing gear (tricycle). The mains sit just behind the rear ducts (the duct band is no place for a wheel);
# a VTOL lands vertically, so the long wheelbase only costs a heavier nose-wheel share
GEAR = {"nose_x": 1.90, "main_dx_behind_cg": 1.85, "main_y": 0.80, "height": 0.62, "wheel_d": 0.36,
        "nose_wheel_d": 0.28}

# section thickness (fraction of chord, symmetric thin section)
T_C = 0.055


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
