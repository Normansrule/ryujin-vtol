#!/usr/bin/env python3
"""V20 "Falcon Jet" sizing at both scales: masses and CG, hover and motor-out power, cruise drag and power,
mission energy, the transition corridor, and stability/trim from tools/v20/aero.py.

    python3 tools/v20/sizing.py          # analysis/v20_sizing.json (+ printed summary)

Mini (scale 0.1): a component build-up of real hobby parts (reference candidates in docs/V20_FALCON_JET.md),
plus printed skins from the generated surfaces at a measured-later areal density.
Full (scale 1.0): a closed sizing loop - pilot, battery from the mission energy, lift/cruise propulsion from
the hover and motor-out power, structure from the wetted areas at composite areal densities, systems.

Everything here is a screening model (momentum theory with figures of merit, flat-plate drag build-up,
linear vortex lattice). It is good for comparing options and for finding what dominates; it is not a
substitute for thrust-stand data, a structural analysis or flight test.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
import aero as A  # noqa: E402
import geometry as GEO  # noqa: E402
import v20params as P  # noqa: E402

RHO, G0 = 1.225, 9.80665
NU = 1.46e-5             # kinematic viscosity of air (sea level, 15 C)


# ---------------------------------------------------------------------------------------------------
# per-scale assumptions (each one is a number to replace with a measurement or a vendor figure)
SCALES = {
    "mini": {
        "scale": 0.1,
        # printed skin areal density per m2 of surface (both sides of a thin part count): LW-PLA foamed to about
        # 0.6 g/cm3, 0.45 mm single wall, +25 % for ribs and joints. Stage 1 coupons replace this.
        "areal_kg_m2": {"skin": 0.34, "controls": 0.20, "glass": 0.45, "propulsion": 0.40, "gear": 0.0},
        # tail surfaces from 3 mm Depron foam sheet with a 2 mm carbon rod and printed roots (templates in cad/v20/mini/foam):
        # half the mass of printed surfaces, and the tail is where the mini's balance is decided
        "foam_kg_m2": 0.10, "foam_parts": ("stabilator", "fin_", "rudder"),
        "rotors_per_duct": 1,
        "fm": 0.48,                # small ducted 4-inch props at low Reynolds number: figure of merit vs ideal ducted
                                   # momentum theory (published small-duct tests run 0.4-0.55)
        "eta_drive": 0.80,         # motor x ESC at hover throttle
        "kappa_coax": 1.0,
        "rotor_tmax_kg": 0.72,     # one 4-inch 3-blade prop, 2204-class motor, 4S: 75 % of a 965 g open-prop test (the
                                   # thrust stand decides); the battery limit below can bind first
        "cruise_static_thrust_kg": 1.20,   # Freewing E7206 64 mm EDF on 4S (vendor figure)
        "cruise_jet_ms": 55.0,     # EDF exit velocity scale for the thrust lapse with speed
        "eta_fan_drive": 0.49,     # 64 mm EDF: fan x motor x ESC (its vendor 1.2 kg / 780 W static point gives 0.49)
        "cruise_max_w": 780.0,     # EDF electrical power at full throttle on 4S (vendor class figure, ~55 A)
        "alpha_max_deg": 14.0,
        "le_suction": 0.2,         # leading-edge suction recovered (0 = sharp edge, 1 = full); thin 5.5 % section, low Re
        "gear_cda_m2": 0.0012,     # fixed gear, drag area
        "duct_hole_cd": 0.12,      # louvres open (transition): per duct area
        "louvre_cd": 0.02,         # louvres shut (cruise): slat gaps and steps, per duct area
        "vane_max_deg": 15.0,      # printed exit vanes, one servo per side (front + rear duct linked): they close the
                                   # 12-13 m/s gap where the EDF alone cannot beat the lift ducts' momentum drag
        # 4S2P Li-ion, 8 x 21700 (Molicel P45B class: 4.5 Ah, 45 A continuous each) -> 9 Ah, 90 A
        "battery": {"cells": 4, "parallel": 2, "cell_ah": 4.5, "cell_a": 45.0, "kg": 0.58, "usable": 0.80,
                    "v_load": 13.2, "margin": 0.85},   # pack power limit = 90 A x 13.2 V under load x 0.85
    },
    "full": {
        "scale": 1.0,
        "areal_kg_m2": {"skin": 3.0, "controls": 2.4, "glass": 4.0, "propulsion": 0.0, "gear": 0.0},
        "rotors_per_duct": 2,      # coaxial, contra-rotating: one rotor can fail
        "fm": 0.70,                # large ducted fans, fixed pitch; 0.75-0.8 only with a well-designed duct and stators
        "eta_drive": 0.93,
        "kappa_coax": 1.08,
        "alpha_max_deg": 14.0,
        "le_suction": 0.5,         # rounded leading edge at full-scale Reynolds number, but a 65-deg outer sweep sheds a
                                   # vortex early: half the suction (Raymer sec. 12.6 gives 0.85-0.95 for unswept, round LEs)
        "gear_cda_m2": 0.0,        # retracted in cruise
        "duct_hole_cd": 0.10,
        "louvre_cd": 0.015,
        "vane_max_deg": 30.0,      # duct exit vanes (as on the XV-5) turn the efflux aft in transition
        "eta_fan_drive": 0.78,     # 0.64 m ducted cruise fan: fan 0.86 x motor + inverter 0.91 (propulsive from momentum)
        "cruise_jet_ms": 110.0,
        "battery": {"wh_per_kg": 220.0, "usable": 0.80, "c_peak": 8.0},   # pack level (cells, structure, cooling); peak
                                                                         # discharge rate the pack must sustain in hover
        "motor_kw_per_kg": 6.0, "inverter_kw_per_kg": 15.0,   # continuous ratings
        "peak_factor": 1.5,        # short-time (60 s) over continuous, for the one-rotor-out landing
        "fan_kg_per_rotor": 7.6,   # hub + 5 composite blades for a 1.56 m rotor (3.5 kg at 1.06 m, scaled with disk area)
        # series hybrid (the full-scale baseline): a turboshaft-driven generator carries cruise and the reserve, a
        # high-power battery carries hover and transition and can hold a hover alone if the turbine stops
        "hybrid": {"gen_kw_per_kg": 1.5,          # turbine + generator + rectifier + mounts, small-turbine class
                   "sfc_kg_per_kwh": 0.50,        # fuel per electrical kWh (small turboshafts are thirsty)
                   "fuel_system_frac": 0.15, "fuel_unusable": 0.05,
                   "battery_wh_per_kg": 180.0,    # high-power pack (10C-capable cells such as the P45B, pack level)
                   "c_peak": 10.0,
                   # 0: the battery is sized for hover power minus the generator, so a turbine failure in a low
                   # hover is not covered (a height-velocity avoid region, as for a single-engine helicopter).
                   # > 0: the battery alone holds a hover this long - the safe rule, which does not close at k = 1.
                   "turbine_out_hover_s": 0.0},
    },
}

# ---------------------------------------------------------------------------------------------------
# the mission (full scale). This is the one set of numbers most worth thinking about: it decides the battery,
# and the battery decides the aircraft. Times in seconds, distance in km.
MISSION = {
    "takeoff_hover_s": 60, "transition_s": 30, "cruise_km": 20.0, "landing_transition_s": 30, "landing_hover_s": 60,
    "reserve_cruise_min": 20.0, "reserve_hover_s": 60,
}
# Reserve: 14 CFR 194.302 (SFAR 120), Table 1 row (l) lets a powered-lift that can land in the vertical-lift mode along
# the whole route use the rotorcraft VFR rule, 91.151(b): 20 minutes at normal cruise. A powered-lift that cannot,
# uses 91.151(a): 30 minutes by day, 45 at night. The hover reserve is the vertical landing that makes (b) apply.


def mission_phases(p_hover_kw: float, p_trans_kw: float, p_cruise_kw: float, v_cruise: float, p_reserve_kw: float,
                   m: dict = MISSION) -> list:
    """The flight as [(phase, seconds, electrical kW at the bus, energy group)]."""
    return [
        ("takeoff hover", m["takeoff_hover_s"], p_hover_kw, "hover"),
        ("transition out", m["transition_s"], p_trans_kw, "transition"),
        ("cruise", m["cruise_km"] * 1000 / v_cruise, p_cruise_kw, "cruise"),
        ("transition in", m["landing_transition_s"], p_trans_kw, "transition"),
        ("landing hover", m["landing_hover_s"], p_hover_kw, "hover"),
        ("reserve cruise", m["reserve_cruise_min"] * 60, p_reserve_kw, "reserve"),
        ("reserve hover", m["reserve_hover_s"], p_hover_kw, "reserve"),
    ]


def mission_energy_kwh(p_hover_kw: float, p_trans_kw: float, p_cruise_kw: float, v_cruise: float, p_reserve_kw: float,
                       m: dict = MISSION) -> dict:
    """Energy for one flight + reserve (kWh at the bus), by group."""
    out = {"hover": 0.0, "transition": 0.0, "cruise": 0.0, "reserve": 0.0}
    for _name, t, p, grp in mission_phases(p_hover_kw, p_trans_kw, p_cruise_kw, v_cruise, p_reserve_kw, m):
        out[grp] += t * p / 3600
    out["total"] = sum(out.values())
    return out


def hybrid_split(phases: list, p_gen_kw: float) -> dict:
    """Series hybrid: the turbogenerator runs at up to p_gen_kw in every phase; the battery covers the rest."""
    e_b = sum(t * max(0.0, p - p_gen_kw) for _n, t, p, _g in phases) / 3600
    e_g = sum(t * min(p, p_gen_kw) for _n, t, p, _g in phases) / 3600
    return {"battery_kwh": e_b, "generator_kwh": e_g}


# ---------------------------------------------------------------------------------------------------
# geometry-derived quantities
_OML = None


def oml():
    global _OML
    if _OML is None or _OML[0] != P.VARIANT:
        _OML = (P.VARIANT, GEO.build_oml(P.duct_centre_x() + P.GEAR["main_dx_behind_cg"]))
    return _OML[1]


def exposed_area(name, mesh):
    """Wetted area (full scale m2) a part shows to the air: wing area inside the fuselage is not skin."""
    a = float(mesh.area)
    if name.startswith("wing_"):
        ys = np.linspace(0, P.FUS[5][1], 30)
        inside = np.trapezoid(GEO.TE_X(ys) - GEO.LE_X(ys), ys)
        a -= 2 * inside
    if name.startswith("duct_"):
        a *= 0.5            # inner wall only; the outer face is buried in the strake
    return a


def centroid(mesh):
    return np.array(mesh.center_mass if mesh.is_volume else mesh.centroid, float)


def drag_buildup(s: float, V: float):
    """Zero-lift drag area CD0*S (m2) at scale s and speed V: Raymer flat-plate skin friction x form factor."""
    rows = []
    total = 0.0
    for name, m, layer in oml():
        if layer in ("gear",) or name.startswith(("nozzle", "duct_", "vanes_")):
            continue
        L = {"fuselage": P.FUS_LEN, "canopy": P.CANOPY["x1"] - P.CANOPY["x0"]}.get(name.split("_")[0], 3.0) * s
        if name.startswith(("wing", "elevon")):
            L = 4.0 * s
        Re = max(V * L / NU, 1e4)
        cf = 0.455 / (math.log10(Re) ** 2.58)
        ff = {"fuselage": 1.12, "canopy": 1.25, "intake": 1.4}.get(name.split("_")[0], 1.18)
        swet = exposed_area(name, m) * s * s
        rows.append((name, swet, cf * ff * swet))
        total += cf * ff * swet
    return total * 1.10, rows       # +10 % excrescences, gaps, intakes spill


# ---------------------------------------------------------------------------------------------------
def hover_power_w(W_n: float, s: float, cfg: dict, thrust_n: float | None = None) -> float:
    """Electrical hover power for total thrust (N) shared by the four ducts (ducted momentum theory, sigma = 1)."""
    T = W_n if thrust_n is None else thrust_n
    A = 4 * math.pi * (P.DUCT_ID * s / 2) ** 2
    ideal_open = T ** 1.5 / math.sqrt(2 * RHO * A)
    return cfg["kappa_coax"] * ideal_open / math.sqrt(2.0) / cfg["fm"] / cfg["eta_drive"]


def duct_induced(T_duct: float, A_duct: float, V: float) -> float:
    """Induced velocity of one duct at edgewise speed V (Glauert: v = T / (2 rho A sqrt(V^2 + v^2))), m/s."""
    if T_duct <= 0:
        return 0.0
    h = T_duct / (2 * RHO * A_duct)
    return math.sqrt((-V * V + math.sqrt(V ** 4 + 4 * h * h)) / 2)


# ---------------------------------------------------------------------------------------------------
def mass_items(scale_key: str, extra: dict, s: float | None = None) -> list:
    """[(name, kg, (x, y, z) full-scale metres, group)] excluding the battery; s = geometric scale."""
    cfg = SCALES[scale_key]
    s = cfg["scale"] if s is None else s
    items = []
    for name, m, layer in oml():
        dens = cfg["areal_kg_m2"].get(layer, 0.0)
        if layer == "gear":
            continue
        if name.startswith("duct_") and scale_key == "full":
            items.append((name, 12.0 * (P.DUCT_ID / 1.06) * s * s, tuple(centroid(m)), "structure"))   # carbon duct, lip, stators, mount
            continue
        if dens <= 0:
            continue
        a = exposed_area(name, m) * s * s
        if name.startswith(cfg.get("foam_parts", ())):
            dens = cfg["foam_kg_m2"]
        items.append((name, a * dens, tuple(centroid(m)), "airframe" if scale_key == "mini" else "structure"))
    for n, x, y, z, kg, grp in extra["items"]:
        items.append((n, kg, (x, y, z), grp))
    return items


def mini_components():
    """Mini hardware (kg) at full-scale-metre positions (positions are scaled with the airframe)."""
    it = []
    for n, x, y in P.duct_centres():
        it.append((f"lift motor {n} (2204-class, 2600-3200 KV)", x, y, -0.02, 0.028, "propulsion"))
        it.append((f"lift prop {n} (4-inch 3-blade)", x, y, 0.02, 0.004, "propulsion"))
    xc = P.duct_centre_x()
    it += [
        ("4-in-1 ESC (Hobbywing XRotor Micro 60A)", 2.60, 0.0, -0.29, 0.016, "propulsion"),
        ("EDF Freewing E7206 64 mm 4S", P.CRUISE_FAN_X_MINI, 0.0, -0.10, 0.142, "propulsion"),
        ("EDF thrust tube + nozzle liner (0.2 mm PET film)", 6.96, 0.0, -0.05, 0.012, "propulsion"),
        ("intake ducts (0.2 mm PET film, two)", 2.9, 0.0, -0.2, 0.006, "propulsion"),
        ("EDF ESC (Hobbywing Skywalker 60A V2)", 2.72, 0.0, -0.15, 0.040, "propulsion"),
        ("flight controller SpeedyBee F405 WING", 2.60, 0.0, 0.0, 0.025, "avionics"),
        ("GPS + compass (M10), under the front of the canopy", 2.63, 0.0, 0.31, 0.012, "avionics"),
        ("ELRS receiver", 2.0, 0.0, 0.15, 0.003, "avionics"),
        ("FPV camera 19 mm (pilot's eye)", 3.22, 0.0, 0.45, 0.008, "avionics"),
        ("VTX 400 mW", 2.2, 0.0, 0.0, 0.006, "avionics"),
        ("airspeed sensor + pitot", 0.6, 0.0, 0.0, 0.006, "avionics"),
        ("servo x2 elevons (5 g digital)", 5.20, 0.0, 0.0, 0.011, "controls"),
        ("servo x2 stabilators (5 g digital, short pushrods)", 7.20, 0.0, 0.0, 0.011, "controls"),
        ("servo x1 rudders (5 g, pull-pull to both rudders)", 6.80, -0.85, 0.0, 0.0055, "controls"),
        ("servo x2 bottom louvres / exit vanes (5 g, one per side, front + rear linked)", 5.05, 0.0, 0.0, 0.011, "controls"),
        ("top louvre hinge wires + elastic closers (suction-opened)", P.duct_centre_x(), 0.0, 0.14, 0.006, "controls"),
        ("linkages, horns, hinges", 7.0, 0.0, 0.0, 0.013, "controls"),
        ("wiring, XT60, connectors", xc, 0.0, -0.1, 0.030, "systems"),
        ("carbon tubes: 6 mm main spar (2 halves), 4 mm centre spar", 4.3, 0.0, 0.0, 0.024, "airframe"),
        ("fixed tricycle gear (wire legs, foam wheels)", P.duct_centre_x() + 0.6, 0.0, -0.6, 0.032, "gear"),
        ("glue, screws, magnets", 5.0, 0.0, 0.0, 0.020, "systems"),
    ]
    return it


def battery_mini(cfg: dict) -> dict:
    """The mini's pack: mass, usable energy and the power the pack can supply (it is also the nose weight)."""
    b = cfg["battery"]
    ah = b["parallel"] * b["cell_ah"]
    amps = b["parallel"] * b["cell_a"]
    return {"kg": b["kg"], "ah": ah, "max_a": amps, "wh_usable": b["cells"] * 3.6 * ah * b["usable"],
            "p_max_w": amps * b["v_load"] * b["margin"]}


TURBO_X = 1.325             # turboshaft + generator in the nose (where a fighter has its radar): the stability layout makes
                            # the airframe tail-heavy, and the turbine is the heaviest thing that can go forward. It breathes
                            # from the intake ducts; two insulated exhaust pipes run aft beside the cockpit into the thrust
                            # tube, so the exhaust still leaves through the jet nozzle
FUEL_X = 3.95               # wing tanks ahead of the main spar, outboard of the body (from the generated tank solids)
FULL_BAY = (1.95, 2.30)     # battery centroid limits: the nose bay between the turbogenerator and the pilot's feet
MINI_VMAX = 23.0            # top of the mini's corridor (m/s): above this the 64 mm EDF cannot beat the drag
MINI_BAY = (1.66, 1.70)     # 4S2P pack centre (full-scale metres): the 141 mm two-block pack needs the nose width from
                            # x 0.95 and must end before the avionics stack at 2.42


def solve_cg(items, battery_kg, bay, target_x):
    """Battery x that puts the CG on target_x (clipped to the bay). Returns (x_batt, mass, cg)."""
    M0 = sum(k for _n, k, _p, _g in items)
    mx = sum(k * p[0] for _n, k, p, _g in items)
    xb = (target_x * (M0 + battery_kg) - mx) / battery_kg
    xb_c = min(max(xb, bay[0]), bay[1])
    M = M0 + battery_kg
    cg = np.array([(mx + battery_kg * xb_c) / M,
                   sum(k * p[1] for _n, k, p, _g in items) / M,
                   (sum(k * p[2] for _n, k, p, _g in items) + battery_kg * -0.15) / M])
    return xb, xb_c, M, cg


# ---------------------------------------------------------------------------------------------------
_AERO = {}


def aero_at(scale: float, ducts: str = "cruise"):
    """'cruise': louvres shut (the closed-duct lattice), carrying the open-duct set under key 'open' for the powered
    part of the corridor; 'open' / 'closed' for either set alone."""
    if ducts == "cruise":
        d = dict(aero_at(scale, "closed"))
        d["open"] = aero_at(scale, "open")
        return d
    key = (P.VARIANT, scale, ducts)
    if key not in _AERO:
        _AERO[key] = dict(A.derivatives(scale, ducts), ducts=ducts)
    return _AERO[key]


def cruise_polar(s: float, V: float, cfg: dict, d: dict):
    cd0S, rows = drag_buildup(s, V)
    S = d["geo"]["S_m2"]
    # louvres open (fans running or parked open): the holes' drag; louvres shut: only the slat gaps and steps
    cd_duct = cfg["duct_hole_cd"] if d.get("ducts") == "open" else cfg["louvre_cd"]
    holes = 4 * math.pi * (P.DUCT_ID * s / 2) ** 2 * cd_duct
    cd0S += holes + cfg["gear_cda_m2"]
    k = induced_k(cfg, d)
    return cd0S / S, k, rows


def induced_k(cfg: dict, d: dict, e: float = 0.75) -> float:
    """Drag-due-to-lift factor of a low-aspect-ratio delta: between no leading-edge suction (CD_i = CL tan(alpha),
    K = 1/CL_alpha) and full suction (K = 1/(pi AR e)), weighted by the suction actually recovered."""
    s = cfg["le_suction"]
    return (1 - s) / d["CLa"] + s / (math.pi * d["geo"]["AR"] * e)


def usable_cl(d: dict, x_cg: float, cfg: dict, eta: float = 0.8) -> float:
    """Trimmed lift coefficient at alpha_max with the pitch surfaces holding Cm = 0 (linear lattice: no vortex lift is
    credited, so this is conservative for a delta). This, not an airfoil CLmax, sets the minimum wing-borne speed."""
    c = d["geo"]["mac_m"]
    xc = x_cg / c
    cm0, cma = d["Cm0"] + d["CL0"] * xc, d["Cma"] + d["CLa"] * xc
    cmd = eta * (d["Cmdp"] + d["CLdp"] * xc)
    a = math.radians(cfg["alpha_max_deg"])
    de = -(cm0 + cma * a) / cmd
    return d["CL0"] + d["CLa"] * a + eta * d["CLdp"] * de


def cruise_fan_areas(cfg: dict):
    """(jet area, intake mouth area) in m2 at this scale: the jet leaves the thrust tube at about 85 % of the fan's
    swept area (the usual EDF rule); the intakes are measured from the generated outer mould line."""
    s = cfg["scale"]
    fsa = math.pi / 4 * (P.CRUISE_FAN_D * s) ** 2 * (1 - 0.39 ** 2)       # hub about 39 % of the diameter
    return 0.85 * fsa, GEO.intake_mouth_area_m2() * s * s, fsa


def edf_power_w(D: float, V: float, cfg: dict, T_avail: float, p_max: float | None) -> float:
    """Cruise-fan electrical power for thrust D at speed V from momentum theory: the jet velocity follows from the
    thrust and the jet area, power = thrust x (V + V_jet) / 2 / (fan x drive efficiency), less an intake penalty when the
    mouths are smaller than 90 % of the fan's swept area. Never less than the fan's own throttle curve (power ~
    thrust^1.5, full power at the thrust available)."""
    if D <= 0:
        return 0.0
    aj, ai, fsa = cruise_fan_areas(cfg)
    vj = (V + math.sqrt(V * V + 4 * D / (RHO * aj))) / 2
    k_int = min(1.0, ai / (0.9 * fsa)) ** 0.5
    p = D * (V + vj) / 2 / (cfg["eta_fan_drive"] * k_int)
    if p_max and T_avail > 0:
        p = max(p, p_max * min(D / T_avail, 1.0) ** 1.5)
    return p


def cruise_power_w(M: float, s: float, V: float, cfg: dict, d: dict, T_static: float | None = None,
                   p_max: float | None = None):
    S = d["geo"]["S_m2"]
    q = 0.5 * RHO * V * V
    CD0, k, _ = cruise_polar(s, V, cfg, d)
    CL = M * G0 / (q * S)
    D = q * S * (CD0 + k * CL * CL)
    T_av = T_static * max(0.0, 1 - V / cfg["cruise_jet_ms"]) if T_static else 0.0
    return edf_power_w(D, V, cfg, T_av, p_max), D, CL


def best_speeds(M, s, cfg, d, vmin, vmax, T_static=None, p_max=None):
    vs = np.linspace(vmin, vmax, 200)
    p = np.array([cruise_power_w(M, s, v, cfg, d, T_static, p_max)[0] for v in vs])
    ve = float(vs[np.argmin(p)])                 # best endurance (min power)
    vr = float(vs[np.argmin(p / vs)])            # best range (min energy per km)
    return ve, vr


def corridor(M, s, cfg, d, x_cg, rotor_tmax_n, cruise_static_n, vmax, p_batt_max, p_cruise_max, cl_use, n=41):
    """The transition corridor. At each speed, search wing angle of attack and pitch-surface deflection for the
    cheapest way to hold level flight: the wing carries what it can, the four lift fans carry the rest and
    balance the pitching moment with front/rear differential thrust, the cruise fan covers the drag (including
    the lift ducts' momentum drag). 'hover_ok' = the fans could take the full weight right now with 20 % control
    headroom (stop and hover from this speed) without the battery going over its power limit; 'forward_ok' = a
    level-flight solution exists at this speed within the fans' thrust, the cruise fan's thrust, the usable wing CL
    and the battery's power limit (lift fans + cruise fan together). Quasi-steady: each speed is solved on its own,
    with no gusts, acceleration or pitch dynamics."""
    # louvres: open whenever the fans run (open-duct lattice, hole drag), shut when the wing carries it all
    dc = d
    d = d.get("open", d)
    S, c = d["geo"]["S_m2"], d["geo"]["mac_m"]
    Ad = math.pi * (P.DUCT_ID * s / 2) ** 2
    xf, xr = P.DUCT_X["front"] * s, P.DUCT_X["rear"] * s
    W = M * G0
    duct_tmax = rotor_tmax_n * cfg["rotors_per_duct"]
    eta = 0.8
    xc = x_cg / c
    cm0 = d["Cm0"] + d["CL0"] * xc
    cma = d["Cma"] + d["CLa"] * xc
    cmd = eta * (d["Cmdp"] + d["CLdp"] * xc)
    cld = eta * d["CLdp"]
    cm0c = dc["Cm0"] + dc["CL0"] * xc
    cmac = dc["Cma"] + dc["CLa"] * xc
    cmdc = eta * (dc["Cmdp"] + dc["CLdp"] * xc)
    cldc = eta * dc["CLdp"]

    # Fans buried in a wing turn the air through 90 deg: the through-flow is set by the fan's own exit velocity,
    # v_e = sqrt(T / (rho A)), not by the flight speed (no translational lift is credited), and every kilogram of
    # air taken in at flight speed costs its forward momentum: ram drag = m_dot V = V sqrt(rho A T) per duct.
    def fan_power(tf, tr, V):
        p = sum(t * math.sqrt(t / (2 * RHO * Ad)) for t in (tf, tf, tr, tr) if t > 0)      # ideal open-rotor, per duct
        return cfg["kappa_coax"] * p / math.sqrt(2.0) / cfg["fm"] / cfg["eta_drive"]          # / sqrt 2: ideal duct

    def ram_drag(tf, tr, V):
        return V * sum(math.sqrt(RHO * Ad * t) for t in (tf, tf, tr, tr) if t > 0)

    out = []
    for V in np.linspace(0.0, vmax, n):
        q = 0.5 * RHO * V * V
        CD0, k, _ = cruise_polar(s, max(V, 3.0), cfg, d)
        CD0c, kc, _ = cruise_polar(s, max(V, 3.0), cfg, dc)
        T_avail = cruise_static_n * max(0.0, 1 - V / cfg["cruise_jet_ms"])
        best = None
        vanes = np.radians(np.arange(0.0, cfg.get("vane_max_deg", 0.0) + 0.1, 5.0))
        alphas = np.radians(np.linspace(-2.0, cfg["alpha_max_deg"], 33))
        deltas = np.radians(np.linspace(-20.0, 20.0, 41))
        for a, de, th in itertools.product(alphas, deltas, vanes):
            CL = d["CL0"] + d["CLa"] * a + cld * de
            if CL > cl_use + 1e-9:
                continue
            L = q * S * CL
            Tf = W - L                                  # vertical share for the fans
            if Tf < -1e-9:
                continue
            Ma = q * S * c * (cm0 + cma * a + cmd * de)
            TR = (Ma + Tf * (x_cg - xf)) / (xr - xf) if Tf > 1e-9 else 0.0
            TF = Tf - TR
            ct = math.cos(th)
            tf, tr = TF / 2 / ct, TR / 2 / ct           # exit vanes tilt the efflux aft by th
            fwd = (TF + TR) / ct * math.sin(th)
            if Tf > 1e-9 and (min(tf, tr) < 0 or max(tf, tr) > 0.8 * duct_tmax):
                continue
            if Tf <= 1e-9 and abs(Ma) > 1e-6 * W * c:
                continue
            ram = ram_drag(tf, tr, V) if Tf > 1e-9 else 0.0
            D = q * S * (CD0 + k * CL * CL) + ram - fwd
            if D > T_avail:
                continue
            D = max(D, 0.0)
            p_f = fan_power(tf, tr, V) if Tf > 1e-9 else 0.0
            p_c = edf_power_w(D, V, cfg, T_avail, p_cruise_max)
            tot = p_f + p_c
            if tot > p_batt_max * 1.0001:
                continue
            if best is None or tot < best[0]:
                best = (tot, a, de, L / W, tf / duct_tmax, tr / duct_tmax, p_f, p_c, D, ram, T_avail, th)
        if q > 0:
            # fully wing-borne: alpha and pitch surfaces from the 2 x 2 trim equations, fans off
            Mx = np.array([[dc["CLa"], cldc], [cmac, cmdc]])
            a_w, de_w = np.linalg.solve(Mx, np.array([W / (q * S) - dc["CL0"], -cm0c]))
            CLw = W / (q * S)
            if (-0.035 <= a_w <= math.radians(cfg["alpha_max_deg"]) + 1e-9 and abs(de_w) <= math.radians(20) and CLw <= cl_use + 1e-9):
                Dw = q * S * (CD0c + kc * CLw * CLw)
                if Dw <= T_avail:
                    pc = edf_power_w(Dw, V, cfg, T_avail, p_cruise_max)
                    if pc <= p_batt_max and (best is None or pc < best[0]):
                        best = (pc, a_w, de_w, 1.0, 0.0, 0.0, 0.0, pc, Dw, 0.0, T_avail, 0.0)
        else:
            best = (best[0], 0.0, 0.0) + best[3:] if best else best
        # stop and hover from here: each duct can lift a quarter of the weight with 20 % thrust to spare for control,
        # and the battery can supply that 20 % extra thrust on all four at once (power ~ thrust^1.5)
        hover_ok = (W / 4) <= 0.8 * duct_tmax and fan_power(1.2 * W / 4, 1.2 * W / 4, 0.0) <= p_batt_max * 1.0001
        row = {"V": round(float(V), 2), "hover_ok": bool(hover_ok), "forward_ok": best is not None,
               "cruise_thrust_avail_n": round(T_avail, 2)}
        if best:
            tot, a, de, ws, lf, lr, pf, pc, D, ram, _, th = best
            row.update({"alpha_deg": round(math.degrees(a), 1), "pitch_surfaces_deg": round(math.degrees(de), 1),
                        "wing_share": round(ws, 3), "front_duct_load": round(lf, 3), "rear_duct_load": round(lr, 3),
                        "fan_kw": round(pf / 1000, 4), "cruise_kw": round(pc / 1000, 4), "total_kw": round(tot / 1000, 4),
                        "drag_n": round(D, 2), "ram_drag_n": round(ram, 2), "vane_deg": round(math.degrees(th), 1)})
        out.append(row)
    return out


# ---------------------------------------------------------------------------------------------------
def size_mini():
    GEO.set_variant("mini")
    cfg = SCALES["mini"]
    s = cfg["scale"]
    d = aero_at(s)
    dc = None
    items = mass_items("mini", {"items": mini_components()})
    xc = P.duct_centre_x()
    pk = battery_mini(cfg)
    batt = pk["kg"]
    xb, xb_c, M, cg = solve_cg(items, batt, MINI_BAY, xc)
    W = M * G0
    # a lift rotor's thrust is the smaller of the motor/prop limit and what a quarter of the pack's power can drive
    rot_tmax_prop = cfg["rotor_tmax_kg"] * G0
    p_quarter = pk["p_max_w"] / 4
    Ad = math.pi * (P.DUCT_ID * s / 2) ** 2
    rot_tmax_batt = (p_quarter * cfg["fm"] * cfg["eta_drive"] * math.sqrt(2.0) * math.sqrt(2 * RHO * Ad) / cfg["kappa_coax"]) ** (2 / 3)
    rot_tmax = min(rot_tmax_prop, rot_tmax_batt)
    p_h = hover_power_w(W, s, cfg)
    T_static = cfg["cruise_static_thrust_kg"] * G0
    cl_use = usable_cl(d, cg[0] * s, cfg)
    vstall = math.sqrt(2 * W / (RHO * d["geo"]["S_m2"] * cl_use))
    ve, vr = best_speeds(M, s, cfg, d, 1.3 * vstall, 30.0, T_static, cfg["cruise_max_w"])
    pc, D, CL = cruise_power_w(M, s, vr, cfg, d, T_static, cfg["cruise_max_w"])
    e_wh = pk["wh_usable"]
    trim16 = A.trim(d, cg[0] * s, M, max(16.0, 1.3 * vstall))
    cor = corridor(M, s, cfg, d, cg[0] * s, rot_tmax, T_static, MINI_VMAX, pk["p_max_w"], cfg["cruise_max_w"], cl_use)
    groups = {}
    for n, k, _p, g in items:
        groups[g] = groups.get(g, 0) + k
    groups["battery"] = batt
    v_min = math.ceil(1.35 * vstall)
    return {
        "scale": s, "mass_kg": M, "groups_kg": groups, "items": [(n, k, list(p), g) for n, k, p, g in items],
        "battery_kg": batt, "battery_x_m": xb_c * s, "battery_x_unclipped_m": xb * s, "cg_m": (cg * s).tolist(),
        "battery": pk, "duct_centre_x_m": xc * s, "cg_offset_mm": (cg[0] - xc) * s * 1000,
        "hover_w": p_h, "hover_a": p_h / cfg["battery"]["v_load"],
        "hover_throttle_frac": W / (4 * rot_tmax), "thrust_to_weight_lift": 4 * rot_tmax / W,
        "rotor_tmax_limit": "battery power" if rot_tmax_batt < rot_tmax_prop else "motor and prop",
        "rotor_tmax_kg": rot_tmax / G0,
        "hover_min": e_wh / p_h * 60, "cruise": {"v_best_range": vr, "v_best_endurance": ve, "power_w": pc, "drag_n": D, "CL": CL,
                                                    "min": e_wh / pc * 60, "range_km": e_wh / pc * vr * 3.6, "L_over_D": W / D},
        "cruise_t_to_w": T_static / W, "stall_ms": vstall, "cl_usable": cl_use, "aero": aero_summary(d, cg[0] * s, dc),
        "trim_16ms": {"V": max(16.0, 1.3 * vstall), "alpha_deg": math.degrees(trim16[0]), "pitch_surfaces_deg": math.degrees(trim16[1]),
                      "CL": trim16[2]},
        "airspeeds": {"AIRSPEED_MIN": v_min, "Q_ASSIST_SPEED": math.ceil(1.2 * vstall),
                      "AIRSPEED_CRUISE": max(v_min + 1, round(vr)), "AIRSPEED_MAX": int(MINI_VMAX) - 1},
        "corridor": cor, "battery_wh_usable": e_wh,
    }


def aero_summary(d, x_cg, dc=None):
    """d: the cruise set (louvres shut, carrying 'open'). The gate is the static margin with the louvres shut - the
    cruise case and the forward-most neutral point. With the louvres open (fans running, or stuck open) the neutral
    point moves aft and the margin grows."""
    do = d.get("open", d)
    sm_c = A.static_margin(d, x_cg)
    sm_o = A.static_margin(do, x_cg)
    return {"sm_open_pct": sm_o, "sm_closed_pct": sm_c, "sm_gate_pct": sm_c, "x_np_closed_m": d["x_np_m"],
            "x_np_open_m": do["x_np_m"], "S_m2": d["geo"]["S_m2"], "span_m": d["geo"]["span_m"], "AR": d["geo"]["AR"],
            "mac_m": d["geo"]["mac_m"], "x_np_m": d["x_np_m"], "x_np_wing_stab_m": d["x_np_wing_m"], "CLa": d["CLa"],
            "sm_pct": sm_c, "Cma_fus": d["Cma_fus"]}


def size_full(mission: dict = MISSION, k: float = 1.0, wh_per_kg: float | None = None, pilots: int = 1, verbose=False,
              with_corridor: bool = True, powertrain: str = "hybrid", probe_mass: float | None = None,
              p_peak_kw: float = 0.0, t_static_min: float = 0.0, variant: str = "full"):
    """k scales the whole aircraft (k = 1: 9.95 m long, 1.06 m ducts). powertrain: 'hybrid' (turbogenerator +
    battery, the baseline) or 'battery' (all-electric)."""
    GEO.set_variant(variant)
    cfg = dict(SCALES["full"])
    hy = cfg["hybrid"]
    hybrid = powertrain == "hybrid"
    if hybrid:
        cfg["battery"] = dict(cfg["battery"], wh_per_kg=hy["battery_wh_per_kg"], c_peak=hy["c_peak"])
    if wh_per_kg:
        cfg["battery"] = dict(cfg["battery"], wh_per_kg=wh_per_kg)
    s = k
    d = aero_at(s)
    dc = None
    cl_use = usable_cl(d, P.duct_centre_x() * s, cfg)
    pilot = 100.0 * pilots
    xc = P.duct_centre_x()
    M = 750.0 if probe_mass is None else probe_mass
    log = []
    prev = None
    converged = False
    batt_prev = 0.0
    for it in range(80 if probe_mass is None else 1):
        W = M * G0
        p_h = hover_power_w(W, s, cfg)
        # motor-out sizing: one rotor of a coaxial pair fails. Re-splitting thrust so the diagonal pair carries more
        # keeps roll and pitch trimmed; the worst-loaded healthy rotor then carries W/6 (the others less). The lost
        # rotor's torque is not cancelled any more: yaw is held by differential speed of the other pairs and the
        # rudders, which this screening model does not check.
        rotor_t_needed = W / 6 * 1.10                  # +10 % control margin while degraded
        rotor_nom = W / 8
        p_rotor_nom = p_h / 8
        p_rotor_max = p_rotor_nom * (rotor_t_needed / rotor_nom) ** 1.5
        # motors and inverters are rated for the larger of continuous hover with 20 % control headroom and the
        # one-rotor-out peak, which only lasts until the landing (short-time rating = peak_factor x continuous)
        p_rotor_rating = max(p_rotor_nom * 1.2 ** 1.5, p_rotor_max / cfg["peak_factor"])
        lift_motor_kg = 8 * p_rotor_rating / 1000 / cfg["motor_kw_per_kg"]
        lift_inv_kg = 8 * p_rotor_rating / 1000 / cfg["inverter_kw_per_kg"]
        fans_kg = 8 * cfg["fan_kg_per_rotor"]
        vst = math.sqrt(2 * M * G0 / (RHO * d["geo"]["S_m2"] * cl_use))
        ve, vr = best_speeds(M, s, cfg, d, 1.3 * vst, 90.0)
        v_cruise = vr
        pc, D, CL = cruise_power_w(M, s, v_cruise, cfg, d)
        pe, _, _ = cruise_power_w(M, s, ve, cfg, d)
        # cruise fan: static thrust that still beats the wing-borne drag (x 1.15) from 1.1 x stall to 1.15 x cruise
        # speed with the jet's thrust lapse; installed power for that thrust at the top speed
        vv = np.linspace(1.1 * vst, 1.15 * v_cruise, 30)
        dd = np.array([cruise_power_w(M, s, v, cfg, d)[1] for v in vv])
        T_static = float(1.15 * np.max(dd / np.maximum(1 - vv / cfg["cruise_jet_ms"], 0.05)))
        cruise_kw = float(1.15 * np.max([edf_power_w(dx, vx, cfg, 0.0, None) for dx, vx in zip(dd, vv)])) / 1000
        if t_static_min > T_static:            # the transition (lift-duct momentum drag) needs more thrust than cruise
            cruise_kw *= t_static_min / T_static
            T_static = t_static_min
        cruise_kg = cruise_kw / cfg["motor_kw_per_kg"] + cruise_kw / cfg["inverter_kw_per_kg"] + 10.0
        E = mission_energy_kwh(p_h / 1000, 0.75 * p_h / 1000, pc / 1000, v_cruise, pe / 1000, mission)
        hyb = {}
        if hybrid:
            phases = mission_phases(p_h / 1000, 0.75 * p_h / 1000, pc / 1000, v_cruise, pe / 1000, mission)
            p_gen = 1.10 * max(pc, pe) / 1000                     # kW: cruise and reserve with 10 % in hand
            sp = hybrid_split(phases, p_gen)
            # battery: the larger of the energy it supplies in a normal flight and the turbine-out rule - hover on the
            # battery alone at full hover power for turbine_out_hover_s, within its peak discharge rate
            need_e = max(sp["battery_kwh"], p_h / 1000 * hy["turbine_out_hover_s"] / 3600) / cfg["battery"]["usable"]
            # power: hover with 20 % thrust in hand for control (power ~ thrust^1.5), less what the generator gives
            # and the transition's peak power (from the corridor, passed in by size_full_with_corridor)
            p_need = max(1.02 * 1.2 ** 1.5 * p_h / 1000, 1.05 * p_peak_kw)
            need_p = (p_need - (0.0 if hy["turbine_out_hover_s"] > 0 else p_gen)) / cfg["battery"]["c_peak"]
            batt_kwh = max(need_e, need_p)
            fuel_kg = sp["generator_kwh"] * hy["sfc_kg_per_kwh"] / (1 - hy["fuel_unusable"])
            gen_kg = p_gen / hy["gen_kw_per_kg"]
            hyb = {"generator_kw": p_gen, "generator_kg": gen_kg, "fuel_kg": fuel_kg, "fuel_l": fuel_kg / 0.80,
                   "battery_energy_kwh_needed": need_e, "battery_power_kwh_needed": need_p,
                   "battery_sized_by": ("power (turbine-out hover)" if hy["turbine_out_hover_s"] > 0 else "power (hover minus generator)")
                   if need_p >= need_e else "energy",

                   "split_kwh": sp}
        else:
            batt_kwh = E["total"] / cfg["battery"]["usable"]
        batt_kg = batt_kwh * 1000 / cfg["battery"]["wh_per_kg"]
        b_sys = max(batt_kg, batt_prev)               # harness and cooling follow the battery actually carried
        extra = [
            ("pilot (with clothing, headset)", 3.40, 0.0, -0.05, pilot, "payload"),
            ("seat, harness, controls, pedals", 3.55, 0.0, -0.20, 22.0, "systems"),
            ("flight-control computers (triplex), air data, AHRS, radios, displays", 2.65, 0.0, 0.07, 18.0, "systems"),
            ("ballistic recovery parachute", P.CRUISE_FAN_X - 0.45, 0.0, 0.25, 22.0, "systems"),
            ("HV harness, contactors, fuses", xc, 0.0, -0.25, 0.03 * b_sys + 8.0, "systems"),
            ("battery thermal management", 2.2, 0.0, -0.1, 0.04 * b_sys + 6.0, "systems"),
            ("lift motors x8", xc, 0.0, 0.0, lift_motor_kg, "propulsion"),
            ("lift inverters x8 (aft body behind the main spar)", P.DUCT_X["rear"] + P.DUCT_ID / 2 + P.DUCT_LIP + 0.50, 0.0, 0.0,
             lift_inv_kg, "propulsion"),
            ("lift fans, hubs, pitch-fixed blades x8", xc, 0.0, 0.0, fans_kg, "propulsion"),
            ("cruise fan, motor, inverter", P.CRUISE_FAN_X, 0.0, P.CRUISE_FAN_Z, cruise_kg, "propulsion"),
            ("intake ducts (2)", 2.9, 0.0, -0.2, 12.0 * s * s, "structure"),
            ("thrust tube to the nozzle (hot-section liner behind the turbine)", (P.CRUISE_FAN_X + P.NOZZLE["x0"]) / 2, 0.0,
             -0.02, 18.0 * s * s, "propulsion"),
            ("landing gear (retractable)", xc + 0.2, 0.0, -0.55, 0.035 * M, "structure"),
        ]
        if hybrid:
            extra += [
                ("turbogenerator (turboshaft + generator + rectifier), in the nose", TURBO_X, 0.0, -0.05, hyb["generator_kg"], "propulsion"),
                ("turbine exhaust pipes (2, insulated) beside the cockpit to the thrust tube", 3.2, 0.0, 0.10, 16.0 * s, "propulsion"),
                ("fuel (Jet A, wing tanks)", FUEL_X, 0.0, 0.0, hyb["fuel_kg"], "fuel"),
                ("fuel tanks, pumps, lines", FUEL_X, 0.0, 0.0, hy["fuel_system_frac"] * hyb["fuel_kg"] + 5.0, "systems"),
            ]
        items = mass_items("full", {"items": extra}, s)
        # the battery is the trim weight: if the pack the mission needs is too light to bring the CG onto the fan
        # centre from the front of the nose bay, carry a bigger pack (it buys turbine-out hover power too)
        M0 = sum(kk for _n, kk, _p, _g in items)
        mx0 = sum(kk * pp[0] for _n, kk, pp, _g in items)
        b_trim = (mx0 - xc * M0) / (xc - FULL_BAY[0])
        trim_sized = b_trim > batt_kg
        if trim_sized:
            batt_kg = b_trim
            batt_kwh = batt_kg * cfg["battery"]["wh_per_kg"] / 1000
            if hybrid:
                hyb["battery_sized_by"] = "CG trim (the pack is the nose weight)"
        batt_prev = batt_kg
        xb, xb_c, M_new, cg = solve_cg(items, batt_kg, FULL_BAY, xc)
        if verbose:
            print(it, round(M_new), {g: round(sum(kk for _n, kk, _p, gg in items if gg == g)) for g in ("structure", "propulsion", "systems")}, round(batt_kg), round(p_h / 1000))
        log.append({"iter": it, "mtow": M_new, "battery_kg": batt_kg, "hover_kw": p_h / 1000, "v_cruise": v_cruise})
        if probe_mass is not None:
            return {"M_in": M, "M_out": M_new, "battery_kg": batt_kg, "hover_kw": p_h / 1000, "cruise_kw": pc / 1000,
                    "groups": {g: sum(kk for _n, kk, _p, gg in items if gg == g) for g in ("structure", "propulsion", "systems", "fuel")},
                    "hybrid": hyb, "v": v_cruise}
        if abs(M_new - M) < 0.5:
            M = M_new
            converged = True
            break
        if M_new > 6000:
            M = M_new
            break
        # secant step on M_new(M) - M = 0 (the growth factor is close to 1, so plain relaxation crawls)
        slope = 0.5
        if prev is not None and abs(M - prev[0]) > 1e-6:
            slope = float(np.clip((M_new - prev[1]) / (M - prev[0]), 0.0, 0.9))
        prev = (M, M_new)
        M = float(np.clip(M + (M_new - M) / (1 - slope), 0.7 * M, 1.4 * M))
    groups = {}
    for n, k, _p, g in items:
        groups[g] = groups.get(g, 0) + k
    groups["battery"] = batt_kg
    W = M * G0
    vstall = math.sqrt(2 * W / (RHO * d["geo"]["S_m2"] * cl_use))
    trim = A.trim(d, cg[0] * s, M, v_cruise)
    rotor_tmax = W / 6 * 1.10
    p_batt_max = batt_kwh * 1000 * cfg["battery"]["c_peak"] + (hyb["generator_kw"] * 1000 if hybrid else 0.0)
    cor = corridor(M, s, cfg, d, cg[0] * s, rotor_tmax, T_static, 1.15 * v_cruise, p_batt_max, cruise_kw * 1000,
                   cl_use) if with_corridor else []
    A_disk = 4 * math.pi * (P.DUCT_ID * s / 2) ** 2
    return {
        "scale": 1.0, "mtow_kg": M, "groups_kg": groups, "items": [(n, k, list(p), g) for n, k, p, g in items],
        "battery_kg": batt_kg, "battery_kwh": batt_kwh, "battery_x_m": xb_c, "battery_x_unclipped_m": xb,
        "cg_m": (cg * s).tolist(), "duct_centre_x_m": xc * s, "cg_offset_mm": (cg[0] - xc) * s * 1000,
        "disk_loading_kg_m2": M / A_disk, "hover_kw": p_h / 1000, "hover_kg_per_kw": M / (p_h / 1000),
        "hover_c_rate": max(0.0, p_h / 1000 - (hyb["generator_kw"] if hybrid else 0.0)) / batt_kwh,   # the battery's share
        "battery_peak_kw": p_batt_max / 1000, "cl_usable": cl_use,
        "powertrain": powertrain, "hybrid": dict(hyb, turbine_out_power_frac=batt_kwh * cfg["battery"]["c_peak"] / (p_h / 1000),
                                                 cg_shift_fuel_burn_mm=1000 * ((cg[0] * s * M - hyb["fuel_kg"] * FUEL_X * s) / (M - hyb["fuel_kg"])
                                                                               - cg[0] * s))
        if hybrid else {}, "converged": converged and M < 4000,
        "motor_out": {"rotor_thrust_needed_x_nominal": rotor_tmax / (W / 8), "rotor_peak_kw": p_rotor_max / 1000,
                      "total_kw_one_rotor_out": p_h / 1000 * 1.10},
        "cruise": {"v_ms": v_cruise, "v_kmh": v_cruise * 3.6, "power_kw": pc / 1000, "drag_n": D, "CL": CL,
                   "L_over_D": W / D, "v_best_endurance": ve, "fan_static_thrust_n": T_static, "fan_installed_kw": cruise_kw},
        "mission": mission, "energy_kwh": E, "stall_ms": vstall, "aero": aero_summary(d, cg[0] * s, dc),
        "trim_cruise": {"alpha_deg": math.degrees(trim[0]), "pitch_surfaces_deg": math.degrees(trim[1]), "CL": trim[2]},
        "corridor": cor, "iterations": log,
    }


def size_full_with_corridor(mission: dict = MISSION, k: float = 1.0, powertrain: str = "hybrid", rounds: int = 4,
                            variant: str = "full"):
    """size_full, then size the cruise fan's thrust and the battery's power for the transition as well. Each round
    runs the corridor twice - with unlimited cruise-fan thrust (what thrust does the cheapest path need?) and with the
    real fan but unlimited battery power (what peak power?) - and re-sizes with both, until they stop moving."""
    peak, treq = 0.0, 0.0
    for _ in range(rounds):
        r = size_full(mission, k=k, powertrain=powertrain, with_corridor=False, p_peak_kw=peak, t_static_min=treq, variant=variant)
        if not r["converged"]:
            break
        cfg = SCALES["full"]
        cor_t = corridor_unlimited(r, k, thrust=1e9)
        t_new = 1.05 * max((c["drag_n"] / max(1 - c["V"] / cfg["cruise_jet_ms"], 0.05) for c in cor_t if c["forward_ok"]), default=0.0)
        cor_p = corridor_unlimited(r, k)
        p_new = max((c.get("total_kw", 0.0) for c in cor_p if c["forward_ok"]), default=0.0)
        moved = p_new > 1.02 * peak + 1e-6 or t_new > 1.02 * treq + 1e-6
        peak, treq = max(peak, p_new), max(treq, t_new)
        if not moved:
            break
    return size_full(mission, k=k, powertrain=powertrain, with_corridor=True, p_peak_kw=peak, t_static_min=treq, variant=variant)


def corridor_unlimited(r: dict, k: float, thrust: float | None = None) -> list:
    cfg = dict(SCALES["full"])
    d = aero_at(k)
    rotor_tmax = r["mtow_kg"] * G0 / 6 * 1.10
    return corridor(r["mtow_kg"], k, cfg, d, r["cg_m"][0], rotor_tmax, thrust or r["cruise"]["fan_static_thrust_n"],
                    1.15 * r["cruise"]["v_ms"], 1e12, r["cruise"]["fan_installed_kw"] * 1000, r["cl_usable"], n=41)


def trade_study():
    """Full-scale closure: the mini's own proportions scaled up (the reason the full scale has bigger fans), then the
    full-scale shape across mission distance and powertrain (series hybrid; hybrid whose battery alone can hold a 60 s
    hover; all-electric at today's and a future pack energy density), and one size up. Every row carries the same
    20-minute VFR reserve; hybrid rows also size the battery and cruise fan for the transition corridor."""
    rows = []
    cases = [("mini proportions (1.06 m fans)", "mini", 1.0, 20.0, "hybrid", None, 0.0),
             ("full shape", "full", 1.0, 10.0, "hybrid", None, 0.0),
             ("full shape", "full", 1.0, 20.0, "hybrid", None, 0.0),
             ("full shape", "full", 1.0, 50.0, "hybrid", None, 0.0),
             ("full shape, battery alone holds a 60 s hover", "full", 1.0, 20.0, "hybrid", None, 60.0),
             ("full shape", "full", 1.0, 20.0, "battery", 220.0, 0.0),
             ("full shape", "full", 1.0, 20.0, "battery", 300.0, 0.0),
             ("full shape, 1.2x larger", "full", 1.2, 20.0, "hybrid", None, 0.0)]
    for label, var, k, km, pt, wh, tout in cases:
        SCALES["full"]["hybrid"]["turbine_out_hover_s"] = tout
        try:
            if pt == "hybrid":
                r = size_full_with_corridor(dict(MISSION, cruise_km=km), k=k, powertrain=pt, variant=var)
            else:                   # all-electric rows: hover headroom only (they do not close even so)
                r = size_full(dict(MISSION, cruise_km=km), k=k, wh_per_kg=wh, with_corridor=False, powertrain=pt, variant=var)
        finally:
            SCALES["full"]["hybrid"]["turbine_out_hover_s"] = 0.0
        ok = bool(r["converged"])
        GEO.set_variant(var)
        rows.append({"case": label, "k": k, "length_m": P.FUS_LEN * k, "duct_m": P.DUCT_ID * k, "cruise_km": km,
                     "powertrain": ("hybrid" if pt == "hybrid" else f"battery {wh:.0f} Wh/kg"),
                     "mtow_kg": round(r["mtow_kg"]) if ok else None, "battery_kg": round(r["battery_kg"]) if ok else None,
                     "fuel_kg": round(r["hybrid"].get("fuel_kg", 0.0)) if ok and r["hybrid"] else None,
                     "hover_kw": round(r["hover_kw"]) if ok else None, "closes": ok})
        print("  trade", rows[-1], flush=True)
    GEO.set_variant("full")
    return rows


def main() -> int:
    mini = size_mini()
    full = size_full_with_corridor()
    trade = trade_study() if "--no-trade" not in sys.argv else []
    out = {"_note": __doc__.strip(), "mini": mini, "full": full, "trade": trade,
           "assumptions": {k: {kk: vv for kk, vv in v.items()} for k, v in SCALES.items()}}
    (ROOT / "analysis").mkdir(exist_ok=True)
    (ROOT / "analysis" / "v20_sizing.json").write_text(json.dumps(out, indent=1, default=float))
    m, f = mini, full
    print(f"MINI  {m['mass_kg'] * 1000:.0f} g  CG offset {m['cg_offset_mm']:+.1f} mm  batt x {m['battery_x_m'] * 1000:.0f} mm "
          f"(unclipped {m['battery_x_unclipped_m'] * 1000:.0f})  SM louvres shut (gate) {m['aero']['sm_closed_pct']:.1f} % open {m['aero']['sm_open_pct']:.1f} %  T/W lift {m['thrust_to_weight_lift']:.2f}  "
          f"hover {m['hover_w']:.0f} W ({m['hover_min']:.1f} min)  cruise {m['cruise']['v_best_range']:.1f} m/s {m['cruise']['power_w']:.0f} W "
          f"({m['cruise']['min']:.1f} min, {m['cruise']['range_km']:.1f} km)  stall {m['stall_ms']:.1f} m/s (CL {m['cl_usable']:.2f})  trim {m['trim_16ms']}  limit {m['rotor_tmax_limit']}  {m['airspeeds']}")
    print("      groups", {k: round(v * 1000) for k, v in m["groups_kg"].items()})
    print(f"FULL  MTOW {f['mtow_kg']:.0f} kg  battery {f['battery_kg']:.0f} kg / {f['battery_kwh']:.1f} kWh  hover {f['hover_kw']:.0f} kW "
          f"DL {f['disk_loading_kg_m2']:.0f} kg/m2  cruise {f['cruise']['v_kmh']:.0f} km/h {f['cruise']['power_kw']:.0f} kW L/D {f['cruise']['L_over_D']:.1f}  "
          f"CG offset {f['cg_offset_mm']:+.0f} mm  batt x {f['battery_x_m']:.2f} (unclipped {f['battery_x_unclipped_m']:.2f})  SM shut {f['aero']['sm_closed_pct']:.1f} % open {f['aero']['sm_open_pct']:.1f} %  C {f['hover_c_rate']:.1f}  "
          f"stall {f['stall_ms']:.1f} m/s  trim {f['trim_cruise']}")
    print("      groups", {k: round(v) for k, v in f["groups_kg"].items()}, "energy", {k: round(v, 1) for k, v in f["energy_kwh"].items()})
    print("      hybrid", {k: (round(float(v), 2) if not isinstance(v, (str, dict)) else v) for k, v in f["hybrid"].items()})
    for tag, r in (("mini", m), ("full", f)):
        bad = [c["V"] for c in r["corridor"] if not (c["hover_ok"] and c["forward_ok"])]
        print(f"      corridor {tag}: not ok at V = {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
