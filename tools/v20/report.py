#!/usr/bin/env python3
"""Write docs/V20_FALCON_JET.md and analysis/v20_corridor.png from analysis/v20_sizing.json and v20_geometry.json.

    python3 tools/v20/report.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import v20params as P  # noqa: E402
from bom import MINI_BOM, PAYLOAD_MODULES, PINMAP  # noqa: E402
import geometry as GEO  # noqa: E402


def f(v, n=0):
    return f"{v:,.{n}f}"


def table(rows, head):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" if i == 0 else "---:" for i in range(len(head))) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def corridor_png(sz, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), dpi=110)
    for ax, key, unit in ((axes[0], "mini", "W"), (axes[1], "full", "kW")):
        c = [r for r in sz[key]["corridor"] if r["forward_ok"]]
        V = [r["V"] for r in c]
        k = 1000 if unit == "W" else 1
        ax.fill_between(V, 0, [100 * r["wing_share"] for r in c], color="#9DB4CC", alpha=0.6, label="weight on the wing, %")
        ax.plot(V, [100 * max(r["front_duct_load"], r["rear_duct_load"]) for r in c], color="#B3443A", lw=1.6,
                label="busiest duct, % of its max thrust")
        ax.set_ylim(0, 105)
        ax.set_xlabel("airspeed, m/s")
        ax.set_ylabel("%")
        ax2 = ax.twinx()
        ax2.plot(V, [r["fan_kw"] * k for r in c], color="#2F363E", lw=1.4, ls="--", label=f"lift fans, {unit}")
        ax2.plot(V, [r["total_kw"] * k for r in c], color="#3F6E9E", lw=1.8, label=f"total, {unit}")
        ax2.set_ylabel(f"electrical power, {unit}")
        ax2.set_ylim(0, max(r["total_kw"] * k for r in c) * 1.15)
        ax.set_title(f"V20 {key}: level flight at every speed", fontsize=10)
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper right")
        for s in ("top",):
            ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# rev B (v0.8.0) reference values for the comparison table (from analysis/v20_sizing.json at tag v0.8.0)
REV_B_MINI = {"mass_g": 1548, "span_mm": 760, "hover_min": 16.8, "cruise_min": 25.7, "range_km": 28.4, "LD": 4.5, "sm": 6.7,
              "tw": 1.86, "payload_g": 0, "AR": 1.65}


def main() -> int:
    sz = json.loads((ROOT / "analysis" / "v20_sizing.json").read_text())
    geo = json.loads((ROOT / "analysis" / "v20_geometry.json").read_text())
    m, F = sz["mini"], sz["full"]
    corridor_png(sz, ROOT / "analysis" / "v20_corridor.png")
    global GEO_INTAKE_FRAC
    GEO.set_variant("mini")
    GEO_INTAKE_FRAC = GEO.intake_mouth_area_m2() / (math.pi / 4 * P.CRUISE_FAN_D ** 2 * (1 - 0.39 ** 2))
    L = []
    w = L.append
    P.use("mini")
    D, LEN = P.DUCT_ID, P.FUS_LEN
    a_m, a_f = m["aero"], F["aero"]
    pl, gr = m["payload"], m["ground"]
    H = F["hybrid"]
    cor_ok = lambda r: all(c["forward_ok"] and c["hover_ok"] for c in r["corridor"]) and r["corridor"]   # noqa: E731
    w("# V20 \"Falcon Jet\" (rev C.2): one blended body, staggered hidden fans, a V-tail and a payload bay\n")
    w("> **Status.** The mini is a buildable, 3D-printable experimental RC model: generated parts, a print set that fits "
      "the P1S (with a balance stand), a foam template, a parts list and a bench port map - not yet printed, bench-tested "
      "or flown. The full-scale aircraft is an **engineering concept study** of the same shape carrying one person: "
      "sizing, packaging and a regulatory path. It is not a build package and nothing here makes it airworthy. A "
      "person-carrying aircraft needs licensed aerospace engineering, structural and propulsion testing, a hazard analysis "
      "and FAA approval before anyone sits in it.\n")
    w("![V20 rev C mini: chined blended body, four lift fans under louvres, V-tail](../analysis/view_v20_mini.png)\n")
    w("## The answer\n")
    nP = int(round(m["battery"]["ah"] / 4.5))
    rows = [
        ["Scale", "1 : 10 of the full-scale shape (exactly)", "1 : 1"],
        ["Length x span", f"{f(LEN * 100)} x {f(a_m['span_m'] * 1000)} mm", f"{LEN:.1f} x {a_f['span_m']:.1f} m"],
        ["Lift fans (hidden under louvres, staggered chevron)", f"4 x {f(D * 100)} mm ducts, one 6-inch 3-blade prop each",
         f"4 x {D:.2f} m ducts, two contra-rotating 5-blade fans each"],
        ["Tail", "V-tail: two all-moving ruddervators (3 mm Depron)", "V-tail: two all-moving ruddervators"],
        ["Jet", "64 mm EDF (Freewing E7206), fed by both side intakes",
         f"{P.CRUISE_FAN_D:.2f} m electric ducted fan, {f(F['cruise']['fan_installed_kw'])} kW"],
        ["Power source", f"4S{nP}P Li-ion, {m['battery']['ah']:.1f} Ah, {m['battery']['max_a']:.0f} A",
         f"series hybrid: {f(H['generator_kw'])} kW turbogenerator + {F['battery_kwh']:.0f} kWh battery"],
        ["Mass", f"{f(m['mass_kg'] * 1000)} g", f"{f(F['mtow_kg'])} kg (pilot 100 kg, battery {f(F['battery_kg'])} kg, fuel {f(H['fuel_kg'])} kg)"],
        ["Payload", f"up to {f(pl['max_kg'] * 1000)} g in a {' x '.join(str(v) for v in pl['bay_mm'])} mm bay at the CG",
         f"{F['cargo']['bay_l']:.0f} L belly bay; uncrewed cargo version {F['cargo']['uncrewed_cargo_kg']:.0f} kg"],
        ["CG from the centre of the 4 fans", f"{m['cg_offset_mm']:+.1f} mm", f"{F['cg_offset_mm']:+.0f} mm"],
        ["Hover power", f"{f(m['hover_w'])} W", f"{f(F['hover_kw'])} kW ({f(F['disk_loading_kg_m2'])} kg/m2 of fan)"],
        ["Lift thrust / weight", f"{m['thrust_to_weight_lift']:.2f}", f"{1.10 * 8 / 6:.2f} rated (one rotor may fail)"],
        ["Static margin, louvres shut (gate) / open", f"**{a_m['sm_closed_pct']:.1f}** / {a_m['sm_open_pct']:.1f} % (gate 5 %)",
         f"**{a_f['sm_closed_pct']:.1f}** / {a_f['sm_open_pct']:.1f} % (gate 5 %)"],
        ["Weathercock stability (Cn_beta, per rad)", f"{a_m['Cnb']:+.3f}", f"{a_f['Cnb']:+.3f}"],
        ["Slowest wing-borne flight (trimmed CL at 14 deg)", f"{m['stall_ms']:.1f} m/s (CL {m['cl_usable']:.2f})",
         f"{F['stall_ms']:.1f} m/s, {F['stall_ms'] * 1.944:.0f} kt (CL {F['cl_usable']:.2f})"],
        ["Cruise (louvres shut)", f"{m['cruise']['v_best_range']:.1f} m/s, {f(m['cruise']['power_w'])} W, L/D {m['cruise']['L_over_D']:.1f}",
         f"{f(F['cruise']['v_kmh'])} km/h, {f(F['cruise']['power_kw'])} kW, L/D {F['cruise']['L_over_D']:.1f}"],
        ["Endurance / mission", f"{m['hover_min']:.0f} min hover or {m['cruise']['min']:.0f} min cruise ({m['cruise']['range_km']:.0f} km)",
         f"{F['mission']['cruise_km']:.0f} km hop + {F['mission']['reserve_cruise_min']:.0f} min VFR reserve"],
        ["Hover and forward flight at every speed (quasi-steady model)",
         f"yes, 0-{m['corridor'][-1]['V']:.0f} m/s" if cor_ok(m) else "no",
         f"yes, 0-{F['corridor'][-1]['V']:.0f} m/s" if cor_ok(F) else "no"],
    ]
    w(table(rows, ["", "V20 mini (printable RC)", "V20 full (single-seat concept)"]))
    w("")
    rb = REV_B_MINI
    w("**Rev B to rev C.2, the mini** (rev B is v0.8.0):\n")
    w(table([["Span", f"{rb['span_mm']} mm", f"{f(a_m['span_m'] * 1000)} mm"],
             ["Aspect ratio", f"{rb['AR']:.2f}", f"{a_m['AR']:.2f}"],
             ["Mass", f"{f(rb['mass_g'])} g", f"{f(m['mass_kg'] * 1000)} g"],
             ["Hover endurance", f"{rb['hover_min']:.1f} min", f"{m['hover_min']:.1f} min"],
             ["Cruise endurance / range", f"{rb['cruise_min']:.1f} min / {rb['range_km']:.1f} km", f"{m['cruise']['min']:.1f} min / {m['cruise']['range_km']:.1f} km"],
             ["Cruise L/D", f"{rb['LD']:.1f}", f"{m['cruise']['L_over_D']:.1f}"],
             ["Payload", "none", f"up to {f(pl['max_kg'] * 1000)} g"],
             ["Lift thrust / weight", f"{rb['tw']:.2f}", f"{m['thrust_to_weight_lift']:.2f}"],
             ["Static margin (louvres shut)", f"{rb['sm']:.1f} %", f"{a_m['sm_closed_pct']:.1f} %"],
             ["Fan layout", "2 x 2 square", "staggered chevron (rear pair 0.9 m further out at full scale)"],
             ["Tail surfaces / servos", "4 surfaces, 3 servos", "2 surfaces, 2 servos"]], ["", "Rev B", "Rev C.2"]))
    w("")
    w("Bigger 6-inch fans (they hover on less power per kilogram) and a 50 % bigger pack, which the chined nose now holds "
      "and which is also the nose weight that puts the CG on the fan centre. Cruise gains are modest: the 64 mm EDF's "
      "efficiency, not the airframe, is what limits the mini's range. Lift thrust/weight stays below the 2.0 the repo "
      "wants - the thrust stand decides; a stronger 2207 or a 6x4 prop is the fix if it comes in short.\n")
    w("![V20 rev C from above: the chined forebody running into the wing, the four fans in the body shoulders, the V-tail]"
      "(../analysis/view_v20_mini_top.png)\n")

    w("## Why it looks like this\n")
    w("**One body.** A chined forebody - the nose's widest line is a sharp edge - runs straight into the wing leading edge, "
      "and the wing root thickens into the body ahead of and behind the fans, so nose, body, wing and aft body read as one "
      "lifting shape, the way the Anduril Fury and the other collaborative combat aircraft (CCA) designs do. A low "
      "frameless canopy fairs into a dorsal spine that runs back to the tail.\n")
    w("**Hover first.** Four equal lift fans; the CG goes on their centroid, so each fan lifts a quarter of the weight "
      "and every fan keeps the same control headroom. The fans live in the shoulders of the body beside the "
      "cockpit, under louvres that shut in cruise: on top they open by the fan's own suction and close with a light "
      "elastic; underneath they are servo-driven and double as **exit vanes**, turning the efflux aft in transition (as "
      "on the 1960s XV-5 fan-in-wing). The battery is the trim weight: the mini's pack sits in the nose (centre x "
      f"{m['battery_x_m'] * 1000:.0f} mm), the full-scale pack in the nose bay (centroid x {F['battery_x_m']:.2f} m).\n")
    yf, yr = P.DUCT_Y["front"], P.DUCT_Y["rear"]
    overlap = max(0.0, (D - abs(yr - yf)) / D)
    w("**Where the fans go (rev C.2).** The four fans form a staggered chevron that follows the wing's sweep: the front "
      f"pair tucked against the body beside the cockpit (y = +/-{yf:.2f} m full scale), the rear pair {yr - yf:.1f} m "
      f"further out (y = +/-{yr:.2f} m). Rev C had them in a square. The stagger is there for physical reasons, not just "
      "the look:\n")
    for t in (f"**Wake.** In transition a fan in line behind another ingests its disturbed inflow and the open louvres' "
              f"wake. Staggered, the rear fan's disk overlaps the front fan's track by {100 * overlap:.0f} % of its "
              "width instead of 100 %.",
              f"**Control arms.** Roll from differential fan thrust and yaw from differential exit vanes both scale with "
              f"lateral distance: the rear pair's arm grows from {yf:.2f} to {yr:.2f} m (x{yr / yf:.1f}). The fore-aft "
              f"spacing - the pitch arm - stays {P.DUCT_X['rear'] - P.DUCT_X['front']:.2f} m, and the fan centroid, which "
              "is the hover balance point, does not move.",
              "**Room underneath.** The bay between the rear fans and the fuselage is free, so the main landing gear "
              f"moves forward to {P.GEAR['main_dx_behind_cg']:.1f} m behind the CG (rev C: {1.85:.2f} m, behind the whole fan "
              "band), the rear fans' efflux no longer blasts the wheels and belly, and the mini's louvre servos sit "
              "there on a short linkage.",
              "**Clean leading edge.** The leading-edge extension now reaches further forward, so even the front fans "
              "have skin ahead of their lips: a better inflow at the front lip in transition (where fan-in-wing designs "
              "first separate) and no duct showing at the edge. That area is ahead of the CG, so the outer wing moved "
              "aft to keep the stability margin.",
              "**Grilles that follow the planform.** The top louvres run parallel to the outer leading edge (they open "
              "by the fan's suction, so their direction is free); the bottom louvres stay spanwise, because they turn "
              "the efflux aft in transition."):
        w(f"- {t}")
    w("")
    w("**A V-tail.** Two all-moving ruddervators replace rev B's two stabilators and two fins: they pitch together and "
      "yaw apart. The vortex lattice is now non-planar - each panel has its own normal - so the tail's pitch "
      "authority (cos^2 of the dihedral) and yaw authority (sin^2) come out of the solver, not a rule of thumb. At "
      f"{P.VTAIL['dihedral_deg']:.0f} deg dihedral it gives a static margin of **{a_m['sm_closed_pct']:.1f} %** with the "
      "louvres shut (the forward-most neutral point; the gate) and a weathercock stability Cn_beta of "
      f"{a_m['Cnb']:+.3f} per radian after the fuselage's destabilising part (Raymer eq. 16.47). Half the tail area of rev "
      "B, two servos instead of three.\n")
    w("**A payload bay at the CG.** The belly between the four fans holds a "
      f"{' x '.join(str(v) for v in pl['bay_mm'])} mm bay (mini) behind two conformal doors. Anything carried there - a "
      "camera, a sensor, a package to drop - sits on the hover balance point, so swapping or dropping it does not "
      "re-trim the aircraft. Bombers and the F-35 keep their weapons bays at the CG for the same reason.\n")
    w("**The jet.** Side intakes under the chines feed one cruise fan near the CG through internal ducts; a thrust tube "
      "carries the jet to the nozzle between the ruddervator roots. The intakes give "
      f"{100 * GEO_INTAKE_FRAC:.0f} % of the EDF's swept area (EDF practice is 80-100 %); the cruise-power model includes "
      "the penalty, and the Stage 2 thrust test runs through the printed intakes.\n")
    w("**One shape at both scales.** Rev B needed a wider-shouldered shape for the full scale (disk loading grows with "
      "size). Rev C starts from the full-scale shape, so the mini is an exact 1:10 model with 6-inch props - and the "
      "same 5 % stability gate now holds at both scales, so the full scale no longer leans on its fly-by-wire for "
      "static stability.\n")

    w("## What it is for\n")
    w("**The mini** carries one payload module at a time in the bay, all plugged into one payload port (output S9):\n")
    w(table([[r["module"], r["what"], r["candidate"], f"{r['grams']}", r["use"]] for r in PAYLOAD_MODULES],
            ["Module", "What", "Reference parts", "g", "Use"]))
    w("")
    w(f"Payload limit **{f(pl['max_kg'] * 1000)} g**: the heaviest module that keeps lift thrust/weight at 1.7 or more "
      f"({pl['limited_by']}); the corridor was re-run at that mass and {'still passes' if pl['corridor_ok_at_max'] else 'does NOT pass'}. "
      f"Full, it hovers {pl['hover_min_at_max']:.0f} min or cruises {pl['cruise_min_at_max']:.0f} min.\n")
    w("**On the ground** it keeps working:\n")
    w(f"- **Perch and watch.** Land on a roof, a ridge or a pole top and stop the motors: the camera, flight controller and "
      f"a 25 mW video link draw about {gr['perch_w']:.0f} W, so half the pack runs them for about "
      f"{gr['perch_h_half_pack']:.0f} h and the other half flies it home - wildlife, a building site, a weather station "
      "with the sensor module.")
    w(f"- **Field power bank.** The {gr['power_bank_wh']:.0f} Wh pack charges a phone or a laptop through an XT90 to "
      "USB-C PD adapter.")
    w("- **Balance and charging stand.** A printed stand (in the print set) holds the aircraft on the fan-centre line by "
      "its body shoulders: if it sits level, the CG is right. A slot passes the charging lead to the pack under the "
      "canopy hatch, so it charges on display.")
    w("")
    G_ = F["ground"]
    w(f"**The full-scale aircraft** is a one-seat personal VTOL for {F['mission']['cruise_km']:.0f} km hops with the VFR "
      f"reserve; its {F['cargo']['bay_l']:.0f} L belly bay at the CG takes a medical kit, survival gear or baggage "
      f"(about {F['cargo']['bay_kg']:.0f} kg); an uncrewed version swaps the cockpit for "
      f"{F['cargo']['uncrewed_cargo_kg']:.0f} kg of cargo on the same flight-control computers (same mass and CG, so "
      "the sizing holds). On the ground its turbogenerator is a mobile generator: through a ground inverter (an added "
      f"part) it could export about {G_['export_kw']:.0f} kW for about {G_['hours_on_mission_fuel']:.1f} h on one "
      f"mission's fuel ({G_['fuel_kg_per_h']:.0f} kg/h at part load) - a field hospital, a disaster site.\n")

    w("## Hover at any point, fly forward at any point\n")
    w("![Transition corridor: how the weight moves from the fans to the wing, and the power, at every speed]"
      "(../analysis/v20_corridor.png)\n")
    w("At every speed from a standstill to top speed the model searches the wing's angle of attack and the pitch "
      "surfaces for the cheapest level-flight solution: the wing carries what it can, the four fans carry the rest and "
      "trim the pitch with front/rear differential thrust, and the cruise fan beats the drag - including the lift ducts' "
      "**momentum drag** (air taken in at flight speed and thrown down costs drag in proportion to speed). The bottom "
      "louvres double as exit vanes that turn the efflux aft (up to 30 deg full scale, "
      f"{sz['assumptions']['mini'].get('vane_max_deg', 0):.0f} deg on the mini). The louvres are open whenever the fans "
      "run (the model then uses the open-duct lattice and the holes' drag) and shut once the wing carries it all.\n")
    for key, label in (("mini", "Mini"), ("full", "Full")):
        c = sz[key]["corridor"]
        idx = sorted(set(list(range(0, len(c), max(1, len(c) // 8))) + [len(c) - 1]))
        pick = [c[i] for i in idx]
        unit = 1000 if key == "mini" else 1
        rows = [[f"{r['V']:.1f}", f"{max(0.0, 100 * r['wing_share']):.0f}", f"{r['alpha_deg']:.1f}", f"{r['pitch_surfaces_deg']:.1f}",
                 f"{100 * r['front_duct_load']:.0f} / {100 * r['rear_duct_load']:.0f}", f"{r.get('vane_deg', 0):.0f}",
                 f(r["total_kw"] * unit, 0), "yes" if r["hover_ok"] else "NO"] for r in pick if r["forward_ok"]]
        w(f"{label} ({'W' if key == 'mini' else 'kW'}):\n")
        w(table(rows, ["m/s", "On wing %", "Alpha deg", "Pitch surfaces deg", "Front / rear duct thrust, % of rated", "Vanes deg",
                       "Power", "Can stop and hover"]))
        w("")
    w("'Can stop and hover' means the four fans alone could take the full weight right now with 20 % of their thrust "
      "still in hand for control, and the power source could supply that 20 % extra on all four. This is a "
      "**quasi-steady** model: each speed is solved on its own, without gusts, acceleration, pitch dynamics or fan-wing "
      "interference - it says a path exists, not that a pilot or autopilot can fly it. Flight test on the mini decides "
      "that.\n")

    # ---------------- mini build
    gm = geo["mini"]["checks"]
    w("## Build the mini\n")
    w(f"**Print set.** `cad/v20/mini/v20_mini_print_set.3mf` and `cad/v20/mini/stl/`: {len(gm['P1S'])} pieces including "
      "the stand, every one a closed solid that fits the P1S bed (larger parts were cut with flat joints). Print the "
      "airframe, louvres and bay doors in LW-PLA (foamed to about 0.6 g/cm3, one 0.45 mm wall, gyroid ribs), ducts, "
      "nozzle and stand in PETG, the canopy as a buck for a 0.5 mm vacuum-formed PETG shell - the canopy is also the "
      "battery hatch (magnets). Cut the two ruddervators from 3 mm Depron with the 1:1 template in "
      "`cad/v20/mini/foam/`; each pivots on a 2 mm carbon rod into the spine, where its servo sits. Glue the joints with "
      "the carbon spars running through them: a 6 mm main spar behind the rear fans in two halves, and a 4 mm centre spar "
      "through the strip between the front and rear fans. Louvres hinge on 0.8 mm music wire.\n")
    pieces = sorted(gm["P1S"].items(), key=lambda kv: kv[0])
    w(table([[f"`{n}`", "fits" if v["fits"] else "**NO**", f"{v['footprint_mm']:.0f}", f"{v['height_mm']:.0f}"] for n, v in pieces],
            ["Piece", "P1S", "Footprint mm", "Height mm"]))
    w("")
    w(f"**Masses** (model, {f(m['mass_kg'] * 1000)} g): " + ", ".join(f"{k} {f(v * 1000)} g" for k, v in m["groups_kg"].items()) + ".\n")
    w("**Parts to buy** (reference candidates; buy one lift motor and one prop first and measure them in a printed duct "
      "on the repo's thrust stand before the rest):\n")
    w(table([[r["id"], r["item"], r["candidate"], r["qty"], r["usd"], f"[link]({r['url']})" if r.get("url") else ""] for r in MINI_BOM],
            ["ID", "Item", "Reference candidate", "Qty", "USD", ""]))
    w("")
    b_ = m["battery"]
    w(f"**Battery.** A 4S{nP}P Li-ion pack of {4 * nP} 21700 cells (Molicel P45B class: 4.5 Ah, 45 A continuous, about "
      f"70 g each) as two 3 x 2 blocks end to end in the nose: {b_['ah']:.1f} Ah and {b_['max_a']:.0f} A, "
      f"{f(b_['kg'] * 1000)} g. Hover needs about {m['hover_a']:.0f} A; the model keeps lift fans + EDF under "
      f"{f(b_['p_max_w'])} W (85 % of {b_['max_a']:.0f} A at 13.2 V under load) everywhere in the corridor, and "
      f"`Q_M_BAT_CURR_MAX` is {0.85 * b_['max_a']:.0f} A. Lift thrust is limited by the {m['rotor_tmax_limit']} "
      f"(lift thrust/weight {m['thrust_to_weight_lift']:.2f}).\n")
    w("**Wiring.** SpeedyBee F405 WING, ArduPilot QuadPlane (quad X), bench-only port map in "
      "`config/ardupilot/skyforge_v20_mini_BENCH_ONLY.param`:\n")
    w(table([[p["out"], p["function"], p["to"], p["note"]] for p in PINMAP], ["Output", "ArduPilot function", "Goes to", "Note"]))
    w("")
    w("**Gates before the first hover** (on top of the repo's Stage 0-10):\n")
    for g in (f"Thrust stand: one 6-inch prop on its motor in a printed duct gives at least {m['rotor_tmax_kg']:.2f} kg at full "
              "throttle on 4S with the louvres open; below that, change motor or prop before printing the body.",
              "EDF bench: the E7206 run through the printed intakes and thrust tube - record thrust and current.",
              "Louvres: the top ones open fully at hover throttle and shut with the fan off; the bottom ones open, shut and "
              "vector aft on the servo, and the trim position is OPEN.",
              f"Weigh and balance on the printed stand: the CG within 3 mm of x {P.duct_centre_x() * 100:.0f} mm (centre of the "
              "four ducts) with the payload module fitted; move the pack, not ballast.",
              f"Duct tip gap: {gm['prop_tip_gap_mm']:.1f} mm in the model (measured from the meshes) - check it all round with a "
              "feeler, no rub when you flex the body shoulder by hand.",
              "Props off: motor order and direction per the port map; the ruddervators pitch together and yaw apart the "
              "right way in every mode; the payload port works.",
              "Tethered hover: hover throttle 45-60 %, no oscillation; then free hover; then transitions in steps of 2 m/s.",
              f"Battery current: logged peak under {0.85 * m['battery']['max_a']:.0f} A in hover and transition.",
              f"Airspeeds: AIRSPEED_MIN {m['airspeeds']['AIRSPEED_MIN']} m/s and Q_ASSIST_SPEED {m['airspeeds']['Q_ASSIST_SPEED']} m/s "
              f"come from the model's {m['stall_ms']:.1f} m/s slowest wing-borne speed; confirm the real stall in a climb before "
              "lowering them."):
        w(f"- {g}")
    w("")

    # ---------------- full scale concept
    P.use("full")
    w("## The full-scale aircraft (concept study)\n")
    w("![V20 full scale, side view: pilot, nose turbogenerator and battery, cruise fan behind the seat](../analysis/view_v20_full_side.png)\n")
    w("**Why it is a hybrid.** With honest efficiencies (fan figure of merit 0.70, the cruise fan from momentum theory "
      "through the intakes, the wing's drag due to lift with partial leading-edge suction, a usable CL from the trimmed "
      "lattice) and the legal VFR reserve, an all-electric version does not close at today's 220 Wh/kg packs (trade "
      f"study below). Hidden fans are small fans: the disk loading is {f(F['disk_loading_kg_m2'])} kg/m2 (an open-rotor "
      f"eVTOL runs 50-100), so hover takes {f(F['hover_kw'])} kW. Jet fuel carries the cruise and the reserve for a "
      "fraction of a battery's mass, so the full scale is a **series hybrid**: a turboshaft-driven generator in the nose, "
      "where a fighter has its radar, fed from the intake ducts, its exhaust in two insulated pipes beside the cockpit "
      "into the thrust tube. The battery fills the nose bay between the turbine and the pilot's feet and trims the CG; "
      "fuel is in the outer wings ahead of the main spar.\n")
    w(f"Closed sizing loop (`tools/v20/sizing.py`): pilot 100 kg; generator {f(H['generator_kw'])} kW (cruise and reserve "
      f"power + 10 %) at {sz['assumptions']['full']['hybrid']['gen_kw_per_kg']} kW/kg and "
      f"{sz['assumptions']['full']['hybrid']['sfc_kg_per_kwh']} kg of fuel per kWh; battery "
      f"{sz['assumptions']['full']['hybrid']['battery_wh_per_kg']:.0f} Wh/kg at pack level, sized by {H['battery_sized_by']} at "
      f"{sz['assumptions']['full']['hybrid']['c_peak']:.0f}C; lift motors and inverters rated so that **any one of the "
      "eight rotors can fail** (the busiest healthy rotor then carries 1/6 of the weight +10 % for control, for the 60 s "
      "it takes to land); cruise fan sized to beat the drag from 1.1 x stall to 1.15 x cruise and the transition's "
      "momentum drag; structure from the wetted area of the blended body at composite areal densities; systems including "
      "triplex flight control and a ballistic parachute.\n")
    w("**A modelling change to know about.** The blended body is several overlapping solids (fuselage, wings with root "
      "fillets, canopy, spine, intakes). Rev C counts their wetted area once - the outside of their union, "
      f"{100 * (1 - sz.get('_overlap', 0.7)):.0f} % less than the sum of the parts - for both skin mass and friction drag. "
      "Rev B summed the parts, which over-counted the wing root inside the fuselage. Much of the full-scale mass drop "
      "from rev B (2,844 kg) comes from this correction, not from the new shape.\n")
    w(table([[k, f"{f(v)} kg"] for k, v in F["groups_kg"].items()] + [["**MTOW**", f"**{f(F['mtow_kg'])} kg**"]], ["Group", "Mass"]))
    w("")
    e = F["energy_kwh"]
    sp = H["split_kwh"]
    w(f"Mission ({F['mission']['takeoff_hover_s']} s hover + {F['mission']['transition_s']} s transition, "
      f"{F['mission']['cruise_km']:.0f} km at {F['cruise']['v_kmh']:.0f} km/h, transition and {F['mission']['landing_hover_s']} s hover, "
      f"then a {F['mission']['reserve_cruise_min']:.0f} min reserve + {F['mission']['reserve_hover_s']} s hover): hover {e['hover']:.0f}, "
      f"transition {e['transition']:.0f}, cruise {e['cruise']:.0f}, reserve {e['reserve']:.0f} kWh at the bus; the generator "
      f"supplies {sp['generator_kwh']:.0f} kWh ({f(H['fuel_kg'])} kg, {f(H['fuel_l'])} L of Jet A; burning it all moves the CG "
      f"{abs(H['cg_shift_fuel_burn_mm']):.0f} mm) and the battery {sp['battery_kwh']:.0f} kWh of its {F['battery_kwh']:.0f} kWh.\n")
    w(f"**Turbine out in a low hover.** With the turbine stopped the battery supplies {100 * H['turbine_out_power_frac']:.0f} % "
      "of hover power" + (" - enough to land." if H["turbine_out_power_frac"] >= 1.0 else
                          f", about {100 * H['turbine_out_power_frac'] ** (2 / 3):.0f} % of the thrust: a firm landing from a low "
                          "hover rather than a held hover, and a small height-velocity avoid region like a single-engine "
                          "helicopter's. The pack is heavier than the energy needs because it is also the nose weight, which "
                          "is what buys this much. The strict rule - the battery alone holds a 60 s hover - is in the trade study.") + "\n")
    bp = geo["full"]["checks"].get("battery_pack", {})
    if bp:
        fill = bp.get("battery_volume_fill", 0)
        w(f"**Packaging{' (open)' if fill < 0.98 else ''}.** The generated full-scale model (`cad/v20/full/checks.json`) "
          f"holds the pilot, the cargo bay, the nose turbogenerator, the exhaust pipes, the intake ducts, the cruise fan, the "
          f"parachute, the inverters and {bp.get('fuel_capacity_l', 0):.0f} L of wing tanks ({bp.get('fuel_needed_l', 0):.0f} L "
          f"needed){' without collisions' if not geo['full']['checks'].get('internal_collisions') else ''}; "
          f"**{100 * fill:.0f} %** of the {f(F['battery_kg'])} kg battery fits the nose bay between the turbine and the "
          "pilot's feet." + (" The rest needs a home: the wing-root fillets beside the nose, or a denser pack." if fill < 0.98 else "") + "\n")
    rows = [[r.get("case", ""), f"{r['length_m']:.1f} m, {r['duct_m']:.2f} m fans", f"{r['cruise_km']:.0f}", r["powertrain"],
             f(r["mtow_kg"]) if r["closes"] else "does not close", f(r["battery_kg"]) if r["closes"] else "-",
             f(r["fuel_kg"]) if r["closes"] and r["fuel_kg"] else "-", f(r["hover_kw"]) if r["closes"] else "-"] for r in sz["trade"]]
    w("Trade study (every row carries the 20-minute reserve):\n")
    w(table(rows, ["Case", "Size", "Cruise km", "Powertrain", "MTOW kg", "Battery kg", "Fuel kg", "Hover kW"]))
    w("")
    w("Read it from the top: the hybrid closes and grows slowly with distance; the strict turbine-out rule does not close; "
      "all-electric does not close at today's pack energy and only closes with a future 300 Wh/kg pack; and a bigger "
      "aircraft is heavier, not better. **It is a heavy aircraft for one person** - hidden fans cost disk loading, and "
      "disk loading costs power.\n")
    w("**Safety architecture (what a real program would have to carry):**\n")
    for s_ in ("Eight motors in four coaxial ducts. Any one motor, inverter or blade-out leaves enough thrust (sized above); the "
               "lost rotor's torque is no longer cancelled, so yaw must be held by the other pairs' differential speed, the "
               "exit vanes and the ruddervators - not yet checked by this model. A motor failure in mid-transition is also an "
               "open item. Ducts contain blade fragments only if the shroud is designed and tested for it.",
               "Triplex fly-by-wire with independent air-data and attitude sources; the aircraft is a hover machine first and "
               "has no unpowered hover.",
               "Turbine out: see above.",
               "Battery split into isolated strings with contactors, thermal-runaway barriers and venting overboard; a firewall "
               "between the nose bay and the pilot's feet. Fuel tanks crash-resistant and separated from the battery bays.",
               "Ballistic recovery parachute behind the canopy for loss of control or power in cruise and climb. It needs height "
               "and some speed to open, so it does **not** protect a low hover or the start of a transition.",
               "Fuel and energy state and power margin shown to the pilot at all times."):
        w(f"- {s_}")
    w("")
    w("**Regulatory path, full scale (United States).** This aircraft is far outside Part 103 ultralight limits (single "
      "occupant, under 254 lb empty, 55 kt maximum, 24 kt stall: see [EAA's summary of 14 CFR 103](https://www.eaa.org/eaa/aviation-interests/ultralights/getting-started-in-ultralight-flying/about-faa-part-103-for-ultralights)), "
      "so it would need an FAA airworthiness certificate - for a privately built one-off, a special airworthiness certificate "
      "in the experimental category - and a pilot qualified for powered-lift under the FAA's 2024 powered-lift rule, SFAR 120 "
      "([FAA](https://www.faa.gov/newsroom/integration-powered-lift-pilot-certification-and-operations-miscellaneous-amendments)). "
      "**Reserve:** under 14 CFR 194.302 (SFAR 120, Table 1, row l) a powered-lift that can land in the vertical-lift mode "
      "along the whole route may use the rotorcraft VFR rule, 14 CFR 91.151(b): fuel to the first intended landing plus 20 "
      "minutes at normal cruise ([final rule](https://public-inspection.federalregister.gov/2024-30331.pdf), "
      "[91.151](https://www.law.cornell.edu/cfr/text/14/91.151)); otherwise the airplane rule applies, 30 minutes by day and "
      "45 at night. The sizing uses 20 minutes plus a 60 s hover for that vertical landing. An uncrewed cargo version would "
      "be a large unmanned aircraft under a different set of rules altogether. Ask the local FAA office (FSDO/MIDO) and a "
      "Designated Airworthiness Representative before any metal is cut. This is a summary, not legal advice.\n")
    w(f"**The mini's rules (United States).** At about {m['mass_kg']:.1f} kg it is a small unmanned aircraft: register it "
      "with the FAA (over 250 g), fly it with a standard Remote ID module or broadcast, or at an FAA-recognized "
      "identification area; as a recreational flyer pass TRUST and fly under 400 ft in uncontrolled airspace (or get a "
      "LAANC authorization in controlled airspace) and keep it in sight - FPV needs a visual observer beside you; flying "
      "it for work (mapping, inspection, the payload modules for hire) needs a Part 107 certificate "
      "([FAA recreational flyers](https://www.faa.gov/uas/recreational_flyers), "
      "[Remote ID](https://www.faa.gov/uas/getting_started/remote_id)). Dropping a payload from a small drone is restricted: "
      "under Part 107 nothing may be dropped that creates an undue hazard (14 CFR 107.23).\n")
    w("**Before anyone flies in one:** detailed structural design and analysis with test articles; duct and rotor burst "
      "containment testing; battery abuse testing; turbine and fuel-system qualification; a functional hazard assessment "
      "and failure-modes analysis of the flight control system; a scale-model and then unmanned full-scale flight-test "
      "program (the mini is step one); and a team with aerospace engineers who sign for the work.\n")

    w("## How the numbers were made\n")
    w("- `tools/v20/v20params.py`: the master shape (full-scale metres). `tools/v20/geometry.py`: meshes for both scales, the "
      "mini print set and stand, and the checks (insides within the body, no internal collisions, prop tip gap, P1S fit). "
      "`tools/v20/aero.py`: a non-planar vortex lattice of the planform (ducts open or covered) and the V-tail - same "
      "Biot-Savart kernel as `tools/aero_vlm.py`, which agrees with AeroSandbox within 0.3 %; it reproduces the planar solver "
      "exactly for a flat wing and the cos^2 law for a tilted tail - plus Raymer's fuselage corrections in pitch and yaw. "
      "`tools/v20/sizing.py`: masses and CG, momentum-theory hover power with figures of merit, Raymer flat-plate drag "
      "build-up on the union's wetted area, the corridor search, the payload limit, the full-scale sizing loop and the trade study.")
    w("- Assumptions to replace with measurements first: LW-PLA and Depron areal densities (Stage 1 coupons), ducted 6-inch "
      "thrust and current (thrust stand: the model assumes 0.95 kg per fan), the EDF's thrust and power at speed, the fan "
      "figures of merit (mini 0.50, full 0.70), the duct-hole drag and blockage, the leading-edge suction (mini 0.2, full "
      "0.5), the turbogenerator's mass and fuel burn. Every number in this document moves when those do; rerun `make v20`.")
    w("- Not modelled: duct lip suction and fan-wing interference in transition (they help lift and hurt pitch), ground "
      "effect, gusts, the dynamics of the transition (this is a quasi-steady corridor), lateral-directional dynamics beyond "
      "the static Cn_beta, structural loads and flutter.\n")
    (ROOT / "docs" / "V20_FALCON_JET.md").write_text("\n".join(L) + "\n")
    from bom import params_text
    (ROOT / "config" / "ardupilot" / "skyforge_v20_mini_BENCH_ONLY.param").write_text(params_text(sz["mini"]))
    print("wrote docs/V20_FALCON_JET.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
