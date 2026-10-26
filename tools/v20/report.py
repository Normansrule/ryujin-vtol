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
from bom import MINI_BOM, PINMAP  # noqa: E402
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
    mini_p = {"D": P.DUCT_ID, "L": P.FUS_LEN}
    P.use("full")
    full_p = {"D": P.DUCT_ID, "L": P.FUS_LEN}
    P.use("mini")
    w("# V20 \"Falcon Jet\" (rev B): hidden lift fans, one jet, two scales\n")
    w("> **Status.** The mini is a buildable, 3D-printable experimental RC model: generated parts, a print set that fits "
      "the P1S, foam-tail templates, a parts list and a bench port map - not yet printed, bench-tested or flown. The "
      "full-scale aircraft is an **engineering concept study** of the same layout carrying one person: sizing, packaging "
      "and a regulatory path. It is not a build package and nothing here makes it airworthy. A person-carrying aircraft "
      "needs licensed aerospace engineering, structural and propulsion testing, a hazard analysis and FAA approval before "
      "anyone sits in it.\n")
    w("![V20 mini, three-quarter view: louvres shut over the four lift fans, F-35-style intakes, the hover frame](../analysis/view_v20_mini.png)\n")
    w("## The answer\n")
    a_m, a_f = m["aero"], F["aero"]
    cor_ok = lambda r: all(c["forward_ok"] and c["hover_ok"] for c in r["corridor"]) and r["corridor"]   # noqa: E731
    rows = [
        ["Scale", "1 : 10 of the layout", "1 : 1 (shoulders widened for bigger fans)"],
        ["Length x span", f"{f(mini_p['L'] * 100)} x {f(a_m['span_m'] * 1000)} mm", f"{full_p['L']:.2f} x {a_f['span_m']:.2f} m"],
        ["Lift fans (hidden under louvres)", f"4 x {f(mini_p['D'] * 100)} mm ducts, one 4-inch 3-blade prop each",
         f"4 x {full_p['D']:.2f} m ducts, two contra-rotating 5-blade fans each"],
        ["Jet", "64 mm EDF (Freewing E7206) behind the battery bay, fed by both side intakes",
         f"{P.CRUISE_FAN_D:.2f} m electric ducted fan, {f(F['cruise']['fan_installed_kw'])} kW"],
        ["Power source", f"4S2P Li-ion, {m['battery']['ah']:.0f} Ah, {m['battery']['max_a']:.0f} A",
         f"series hybrid: {f(F['hybrid']['generator_kw'])} kW turbogenerator + {F['battery_kwh']:.0f} kWh battery"],
        ["Mass", f"{f(m['mass_kg'] * 1000)} g", f"{f(F['mtow_kg'])} kg (pilot 100 kg, battery {f(F['battery_kg'])} kg, fuel {f(F['hybrid']['fuel_kg'])} kg)"],
        ["CG from the centre of the 4 fans", f"{m['cg_offset_mm']:+.1f} mm", f"{F['cg_offset_mm']:+.0f} mm"],
        ["Hover power", f"{f(m['hover_w'])} W", f"{f(F['hover_kw'])} kW ({f(F['disk_loading_kg_m2'])} kg/m2 of fan)"],
        ["Lift thrust / weight", f"{m['thrust_to_weight_lift']:.2f}", f"{1.10 * 8 / 6:.2f} rated (one rotor may fail)"],
        ["Static margin, louvres shut (cruise; gate) / open", f"**{a_m['sm_closed_pct']:.1f}** / {a_m['sm_open_pct']:.1f} % (gate 5 %)",
         f"**{a_f['sm_closed_pct']:.1f}** / {a_f['sm_open_pct']:.1f} % (positive; fly-by-wire)"],
        ["Slowest wing-borne flight (trimmed CL at 14 deg)", f"{m['stall_ms']:.1f} m/s (CL {m['cl_usable']:.2f})",
         f"{F['stall_ms']:.1f} m/s, {F['stall_ms'] * 1.944:.0f} kt (CL {F['cl_usable']:.2f})"],
        ["Cruise (louvres shut)", f"{m['cruise']['v_best_range']:.1f} m/s, {f(m['cruise']['power_w'])} W, L/D {m['cruise']['L_over_D']:.1f}",
         f"{f(F['cruise']['v_kmh'])} km/h, {f(F['cruise']['power_kw'])} kW, L/D {F['cruise']['L_over_D']:.1f}"],
        ["Endurance / mission", f"{m['hover_min']:.0f} min hover or {m['cruise']['min']:.0f} min cruise (model)",
         f"{F['mission']['cruise_km']:.0f} km hop + {F['mission']['reserve_cruise_min']:.0f} min VFR reserve"],
        ["Hover and forward flight at every speed (quasi-steady model)",
         f"yes, 0-{m['corridor'][-1]['V']:.0f} m/s" if cor_ok(m) else "no",
         f"yes, 0-{F['corridor'][-1]['V']:.0f} m/s" if cor_ok(F) else "no"],
    ]
    w(table(rows, ["", "V20 mini (printable RC)", "V20 full (single-seat concept)"]))
    w("")
    w("Rev A (v0.7.0) had the four fans in open holes through a big delta wing. It worked on paper but looked like a "
      "drone glued into a jet, and the holes cost drag all the time. Rev B hides them.\n")
    w("![V20 mini from above: the four lift fans in the body shoulders, louvres shut, the CG where the diagonals cross]"
      "(../analysis/view_v20_mini_top.png)\n")

    w("## Why it looks like this\n")
    w("**Hover first.** Four lift fans in a square; the CG goes where their diagonals cross, so each fan lifts a quarter "
      "of the weight and every fan keeps the same control headroom. The battery is the trim weight: on the mini it sits "
      f"in the nose (pack centre x {m['battery_x_m'] * 1000:.0f} mm); on the full-scale aircraft in the nose bay between the "
      f"turbogenerator and the pilot's feet (centroid x {F['battery_x_m']:.2f} m).\n")
    w("**Hidden fans.** The fans live in the shoulders of a wide, blended body, like the F-35's - beside the cockpit, the "
      "front pair right next to the pilot's seat. Louvres close each duct top and bottom in cruise, so the aircraft is a "
      "clean jet with no holes. On top they open by the fan's own suction and close with a light elastic; underneath "
      "they are servo-driven and double as **exit vanes**, turning the fans' efflux aft in transition (as on the 1960s "
      "XV-5 fan-in-wing).\n")
    w("**Then fly.** With the louvres shut the wing's lift comes back over the front fans and the neutral point moves "
      "forward, so the stability gate is the louvres-shut case. That is why the fans sit as far forward as the body "
      "allows, the trapezoidal outer wings sit well aft, and the all-moving stabilators are large: the vortex lattice "
      f"puts the neutral point **{a_m['sm_closed_pct']:.1f} %** of the mean chord behind the CG with the louvres shut "
      f"({a_m['sm_open_pct']:.1f} % with them open), after the fuselage's destabilising moment (Raymer's method). "
      "Stuck-open louvres therefore make it more stable, not less.\n")
    w("**The jet.** F-35-style side intakes sit just ahead of the front fans; behind them each duct carries on as a cheek "
      "under the body shoulder, inboard of the fans' lips and below their louvres, to one cruise fan near the CG. A thrust "
      "tube carries its jet to the round nozzle. On the mini that is the 64 mm EDF right behind the battery bay: an EDF in "
      "the tail would need a nose full of ballast, because the big stabilators and the wing behind the fans make the "
      "airframe tail-heavy. The intakes give "
      f"{100 * GEO_INTAKE_FRAC:.0f} % of the EDF's swept area (EDF practice is 80-100 %); the cruise-power model includes "
      "that penalty, and the Stage 2 thrust test must be run through the printed intakes.\n")
    w("**Lighter tail.** The mini's stabilators, fins and rudders are cut from 3 mm Depron foam with a carbon rod "
      "(templates in `cad/v20/mini/foam/`): half the mass of printed surfaces, and the tail is where its balance is "
      "decided.\n")
    w("**Scaling up is not free.** At constant proportions the disk loading grows with size: mass goes as the cube, fan "
      "area as the square. With the mini's proportions the full-scale aircraft needs more than 350 kg/m2 of fan and does "
      "not close (trade study below), so the full scale widens the shoulders for "
      f"{full_p['D']:.2f} m fans and grows the outer wing and stabilators to keep it stable. Its louvres-shut margin is "
      f"{a_f['sm_closed_pct']:.1f} %: positive, and enough for a triplex fly-by-wire aircraft, but thinner than the mini's.\n")

    w("## Hover at any point, fly forward at any point\n")
    w("![Transition corridor: how the weight moves from the fans to the wing, and the power, at every speed]"
      "(../analysis/v20_corridor.png)\n")
    w("At every speed from a standstill to top speed the model searches the wing's angle of attack and the pitch "
      "surfaces for the cheapest level-flight solution: the wing carries what it can, the four fans carry the rest and "
      "trim the pitch with front/rear differential thrust, and the cruise fan beats the drag - including the lift ducts' "
      "**momentum drag** (air taken in at flight speed and thrown down costs drag in proportion to speed). That drag is "
      "the classic fan-in-wing problem: on the full-scale aircraft it reaches several kilonewtons mid-transition, so "
      "the bottom louvres double as **exit vanes** that turn the efflux aft (up to 30 deg full scale, "
      f"{sz['assumptions']['mini'].get('vane_max_deg', 0):.0f} deg on the mini). The louvres are open whenever the fans run (the "
      "model then uses the open-duct lattice and the holes' drag) and shut once the wing carries it all.\n")
    for key, label in (("mini", "Mini"), ("full", "Full")):
        c = sz[key]["corridor"]
        idx = sorted(set(list(range(0, len(c), max(1, len(c) // 8))) + [len(c) - 1]))
        pick = [c[i] for i in idx]
        unit = 1000 if key == "mini" else 1
        rows = [[f"{r['V']:.1f}", f"{max(0.0, 100 * r['wing_share']):.0f}", f"{r['alpha_deg']:.1f}", f"{r['pitch_surfaces_deg']:.1f}",
                 f"{100 * r['front_duct_load']:.0f} / {100 * r['rear_duct_load']:.0f}", f"{r.get('vane_deg', 0):.0f}",
                 f(r["total_kw"] * unit, 0 if key == "full" else 0), "yes" if r["hover_ok"] else "NO"] for r in pick if r["forward_ok"]]
        w(f"{label} ({'W' if key == 'mini' else 'kW'}):\n")
        w(table(rows, ["m/s", "On wing %", "Alpha deg", "Pitch surfaces deg", "Front / rear duct thrust, % of rated", "Vanes deg",
                       "Power", "Can stop and hover"]))
        w("")
    w("'Can stop and hover' means the four fans alone could take the full weight right now with 20 % of their thrust "
      "still in hand for control, and the power source could supply that 20 % extra on all four. Every solution in the "
      "table also stays inside the power source's limit (on the mini, the 90 A pack carries the lift fans and the EDF "
      "together). It is true at every speed on both scales: the fans are sized for hover, so the aircraft can always "
      "fall back to the drone. This is a **quasi-steady** model: each speed is solved on its own, without gusts, "
      "acceleration, pitch dynamics or fan-wing interference - it says a path exists, not that a pilot or autopilot can "
      "fly it. Flight test on the mini decides that.\n")

    # ---------------- mini build
    gm = geo["mini"]["checks"]
    w("## Build the mini\n")
    w(f"**Print set.** `cad/v20/mini/v20_mini_print_set.3mf` and `cad/v20/mini/stl/`: {len(gm['P1S'])} pieces, every one "
      "a closed solid that fits the P1S bed (larger parts were cut with flat joints). Print the airframe in LW-PLA "
      "(foamed to about 0.6 g/cm3, one 0.45 mm wall, gyroid ribs), ducts and nozzle in PETG, the louvres in LW-PLA, the "
      "canopy as a buck for a 0.5 mm vacuum-formed PETG shell. Cut the stabilators, fins and rudders from 3 mm Depron with "
      "the 1:1 templates in `cad/v20/mini/foam/`. Glue the joints with the carbon spars running through them: a 6 mm main "
      "spar behind the rear fans in two halves that plug into a printed ring around the thrust tube, and a 4 mm centre spar "
      "through the strip between the front and rear fans. Louvres hinge on 0.8 mm music wire: the top ones close with "
      "a thin elastic and open by the fan's suction, the bottom ones are linked to one servo per side.\n")
    pieces = sorted(gm["P1S"].items(), key=lambda kv: kv[0])
    w(table([[f"`{n}`", "fits" if v["fits"] else "**NO**", f"{v['footprint_mm']:.0f}", f"{v['height_mm']:.0f}"] for n, v in pieces],
            ["Piece", "P1S", "Footprint mm", "Height mm"]))
    w("")
    w(f"**Masses** (model, {f(m['mass_kg'] * 1000)} g): " + ", ".join(f"{k} {f(v * 1000)} g" for k, v in m["groups_kg"].items()) + ".\n")
    w("**Parts to buy** (reference candidates; buy one lift motor and one prop first and measure them on the repo's "
      "thrust stand before the rest):\n")
    w(table([[r["id"], r["item"], r["candidate"], r["qty"], r["usd"], f"[link]({r['url']})" if r.get("url") else ""] for r in MINI_BOM],
            ["ID", "Item", "Reference candidate", "Qty", "USD", ""]))
    w("")
    b_ = m["battery"]
    w(f"**Battery.** A 4S2P Li-ion pack of eight 21700 cells (Molicel P45B class: 4.5 Ah, 45 A continuous, about 70 g "
      f"each) as two 2 x 2 bundles end to end in the nose: {b_['ah']:.0f} Ah and {b_['max_a']:.0f} A, {f(b_['kg'] * 1000)} g. "
      f"Hover needs about {m['hover_a']:.0f} A; the model keeps lift fans + EDF under {f(b_['p_max_w'])} W (85 % of "
      f"{b_['max_a']:.0f} A at 13.2 V under load) everywhere in the corridor, so the EDF runs to full throttle and "
      f"`Q_M_BAT_CURR_MAX` is {0.85 * b_['max_a']:.0f} A. Li-ion gives about 40 % more energy per kilogram than LiPo, "
      "which long hovers want; the price is current, which is why the pack is 2P. Lift thrust is limited by the "
      f"{m['rotor_tmax_limit']} (lift thrust/weight {m['thrust_to_weight_lift']:.2f}).\n")
    w("**Wiring.** SpeedyBee F405 WING, ArduPilot QuadPlane (quad X), bench-only port map in "
      "`config/ardupilot/skyforge_v20_mini_BENCH_ONLY.param`:\n")
    w(table([[p["out"], p["function"], p["to"], p["note"]] for p in PINMAP], ["Output", "ArduPilot function", "Goes to", "Note"]))
    w("")
    w("**Gates before the first hover** (on top of the repo's Stage 0-10):\n")
    for g in (f"Thrust stand: one ducted 4-inch prop on its motor gives at least {m['rotor_tmax_kg']:.2f} kg at full throttle on 4S, "
              "with the louvres open; below that, change motor or prop before printing the body.",
              "EDF bench: the E7206 run through the printed intakes and thrust tube - record thrust and current; the model "
              "assumes the intakes cost some thrust (they give about three quarters of the fan's swept area).",
              "Louvres: the top ones open fully at hover throttle and shut with the fan off; the bottom ones open, shut and "
              "vector aft on the servo, and the trim position is OPEN.",
              f"Weigh and balance: the CG within 3 mm of x {P.duct_centre_x() * 100:.0f} mm (centre of the four ducts); move the pack, not ballast.",
              f"Duct tip gap: {gm['prop_tip_gap_mm']:.1f} mm in the model (measured from the meshes) - check it all round with a feeler, "
              "no rub when you flex the body shoulder by hand.",
              "Props off: motor order and direction per the port map, every surface moves the right way in every mode.",
              "Tethered hover: hover throttle 40-50 %, no oscillation; then free hover; then transitions in steps of 2 m/s.",
              f"Battery current: logged peak under {0.85 * m['battery']['max_a']:.0f} A in hover and transition.",
              f"Airspeeds: AIRSPEED_MIN {m['airspeeds']['AIRSPEED_MIN']} m/s and Q_ASSIST_SPEED {m['airspeeds']['Q_ASSIST_SPEED']} m/s "
              f"come from the model's {m['stall_ms']:.1f} m/s slowest wing-borne speed; confirm the real stall in a climb before "
              "lowering them."):
        w(f"- {g}")
    w("")

    # ---------------- full scale concept
    P.use("full")
    H = F["hybrid"]
    w("## The full-scale aircraft (concept study)\n")
    w("![V20 full scale, side view: pilot, nose turbogenerator and battery, cruise fan behind the seat](../analysis/view_v20_full_side.png)\n")
    w("**Why it is a hybrid.** With honest efficiencies (fan figure of merit 0.70, the cruise fan from momentum theory "
      "through the intakes, the delta's drag due to lift, a usable CL from the trimmed lattice) and the legal VFR reserve, "
      "an all-electric version does not close in the trade study below - not at 220 Wh/kg and not at 300. Hidden fans "
      f"are small fans: even widened to {P.DUCT_ID:.2f} m the disk loading is {f(F['disk_loading_kg_m2'])} kg/m2 (an "
      f"open-rotor eVTOL runs 50-100), so hover takes {f(F['hover_kw'])} kW, and the 20-minute reserve at cruise is "
      f"{F['energy_kwh']['reserve']:.0f} kWh. Jet fuel carries that for a fraction of a battery's mass. So the full scale is a "
      "**series hybrid**: a turboshaft-driven generator in the nose, where a fighter has its radar (it is the heaviest "
      "thing that can go forward of a tail-heavy airframe), fed from the intake ducts, its exhaust in two insulated pipes "
      "beside the cockpit into the thrust tube - the exhaust leaves through the jet nozzle. The battery fills the nose bay "
      "between the turbine and the pilot's feet and trims the CG; fuel is in the outer wings. This is what the 1960s "
      "fan-in-wing XV-5 found with turbojets: a fighter-shaped fan lifter is a jet-fuel aircraft, and a heavy one.\n")
    w(f"Closed sizing loop (`tools/v20/sizing.py`): pilot 100 kg; generator {f(H['generator_kw'])} kW (cruise and reserve "
      f"power + 10 %) at {sz['assumptions']['full']['hybrid']['gen_kw_per_kg']} kW/kg and "
      f"{sz['assumptions']['full']['hybrid']['sfc_kg_per_kwh']} kg of fuel per kWh; battery "
      f"{sz['assumptions']['full']['hybrid']['battery_wh_per_kg']:.0f} Wh/kg at pack level, sized by {H['battery_sized_by']} at "
      f"{sz['assumptions']['full']['hybrid']['c_peak']:.0f}C; lift motors and inverters rated so that **any one of the "
      "eight rotors can fail** - re-splitting thrust onto the diagonal keeps pitch and roll trimmed, and the busiest "
      "healthy rotor then carries 1/6 of the weight (+10 % for control), for the 60 s it takes to land; cruise fan sized "
      "to beat the drag from 1.1 x stall to 1.15 x cruise speed and the transition's momentum drag; structure from the "
      "generated wetted areas at composite "
      "areal densities; systems including a triplex flight-control system and a ballistic parachute.\n")
    w(table([[k, f"{f(v)} kg"] for k, v in F["groups_kg"].items()] + [["**MTOW**", f"**{f(F['mtow_kg'])} kg**"]], ["Group", "Mass"]))
    w("")
    e = F["energy_kwh"]
    sp = H["split_kwh"]
    w(f"Mission ({F['mission']['takeoff_hover_s']} s hover + {F['mission']['transition_s']} s transition, "
      f"{F['mission']['cruise_km']:.0f} km at {F['cruise']['v_kmh']:.0f} km/h, transition and {F['mission']['landing_hover_s']} s hover, "
      f"then a {F['mission']['reserve_cruise_min']:.0f} min reserve + {F['mission']['reserve_hover_s']} s hover): hover {e['hover']:.0f}, "
      f"transition {e['transition']:.0f}, cruise {e['cruise']:.0f}, reserve {e['reserve']:.0f} kWh at the bus; the generator "
      f"supplies {sp['generator_kwh']:.0f} kWh ({f(H['fuel_kg'])} kg, {f(H['fuel_l'])} L of Jet A in the outer-wing tanks; "
      f"burning it all moves the CG {abs(H['cg_shift_fuel_burn_mm']):.0f} mm forward) and "
      f"the battery {sp['battery_kwh']:.0f} kWh of its {F['battery_kwh']:.0f} kWh. Battery power is sized for the larger of "
      "hover with 20 % thrust in hand and the transition's peak (from the corridor), less the generator; the cruise fan's "
      "thrust for the transition's momentum drag as well as cruise.\n")
    w(f"**The open safety item: turbine out in a low hover.** The battery is sized for hover power minus the generator, so "
      f"with the turbine stopped it supplies {100 * H['turbine_out_power_frac']:.0f} % of hover power - about "
      f"{100 * H['turbine_out_power_frac'] ** (2 / 3):.0f} % of the thrust needed. Above parachute height that is a "
      "parachute or a powered descent; in a low hover it is a hard landing. Single-engine helicopters live with the same "
      "kind of height-velocity avoid region. The safe rule - the battery alone holds a 60 s hover - is in the trade study; "
      "twin turbogenerators, bigger fans or a lower disk loading are the ways out, and a real program would have to pick "
      "one.\n")
    bp = geo["full"]["checks"].get("battery_pack", {})
    if bp:
        w(f"**Packaging (open).** The generated full-scale model (`cad/v20/full/checks.json`) holds the pilot, the nose "
          f"turbogenerator, the exhaust pipes, the intake ducts, the cruise fan, the parachute, the inverters and "
          f"{bp.get('fuel_capacity_l', 0):.0f} L of wing tanks ({bp.get('fuel_needed_l', 0):.0f} L needed) without collisions - "
          f"but only **{100 * bp.get('battery_volume_fill', 0):.0f} %** of the {f(F['battery_kg'])} kg battery fits the nose bay "
          "between the turbine and the pilot's feet. The rest has nowhere to go in a body this slim: more volume in the "
          "nose (a deeper forebody), a denser pack, or a lighter, less tail-heavy airframe that needs less battery as trim "
          "weight. This is a real finding of the concept, not a rounding error.\n")
    rows = [[r.get("case", ""), f"{r['length_m']:.1f} m, {r['duct_m']:.2f} m fans", f"{r['cruise_km']:.0f}", r["powertrain"],
             f(r["mtow_kg"]) if r["closes"] else "does not close", f(r["battery_kg"]) if r["closes"] else "-",
             f(r["fuel_kg"]) if r["closes"] and r["fuel_kg"] else "-", f(r["hover_kw"]) if r["closes"] else "-"] for r in sz["trade"]]
    w("Trade study (every row carries the 20-minute reserve):\n")
    w(table(rows, ["Case", "Size", "Cruise km", "Powertrain", "MTOW kg", "Battery kg", "Fuel kg", "Hover kW"]))
    w("")
    w("Read it from the top: the mini's own proportions do not close at full scale (fans too small for the weight); the "
      "widened full-scale shape closes only as a hybrid; mass climbs steeply with distance, because every kilogram of fuel "
      "and generator raises the hover power, which sizes the battery and the motors; and a bigger aircraft is heavier, not "
      "better. **This is a heavy aircraft for one person.** If the full scale is the goal, the honest lever is bigger fans - "
      "which means a less fighter-like body - or the F-35B's architecture (one large shaft-driven lift fan and a "
      "swivelling engine nozzle), not more styling.\n")
    w("**Safety architecture (what a real program would have to carry):**\n")
    for s_ in ("Eight motors in four coaxial ducts. Any one motor, inverter or blade-out leaves enough thrust (sized above); the "
               "lost rotor's torque is no longer cancelled, so yaw must be held by the other pairs' differential speed, the "
               "exit vanes and the rudders - not yet checked by this model. A motor failure in mid-transition is also an open "
               "item. Ducts contain blade fragments only if the shroud is designed and tested for it.",
               "Triplex fly-by-wire with independent air-data and attitude sources; the aircraft is a hover machine first and "
               "has no unpowered hover.",
               "Turbine out: see above - the avoid region has to be closed or flown around.",
               "Battery split into isolated strings with contactors, thermal-runaway barriers and venting overboard; the nose "
               "bay is forward of the pilot's feet, so the crash case and the fire case both need a firewall. Fuel tank "
               "crash-resistant and separated from the battery bays.",
               "Ballistic recovery parachute behind the canopy for loss of control or power in cruise and climb. It needs height "
               "and some speed to open, so it does **not** protect a low hover or the start of a transition.",
               "Duct exit vanes for transition thrust and yaw; elevons and stabilators for wing-borne control; the cruise fan "
               "is not needed to land.",
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
      "45 at night. The sizing uses 20 minutes plus a 60 s hover for that vertical landing. Which experimental purpose applies "
      "to a powered-lift one-off, and what testing the FAA would want, is a question for the local FAA office (FSDO/MIDO) "
      "and a Designated Airworthiness Representative before any metal is cut. This is a summary, not legal advice.\n")
    w("**The mini's rules (United States).** At about 1.5 kg it is a small unmanned aircraft: register it with the FAA "
      "(over 250 g), fly it with a standard Remote ID module or broadcast, or at an FAA-recognized identification area; as a "
      "recreational flyer pass TRUST and fly under 400 ft in uncontrolled airspace (or get a LAANC authorization in "
      "controlled airspace) and keep it in sight - FPV needs a visual observer beside you; flying it for work needs a "
      "Part 107 certificate ([FAA recreational flyers](https://www.faa.gov/uas/recreational_flyers), "
      "[Remote ID](https://www.faa.gov/uas/getting_started/remote_id)).\n")
    w("**Before anyone flies in one:** detailed structural design and analysis with test articles; duct and rotor burst "
      "containment testing; battery abuse testing; turbine and fuel-system qualification; a functional hazard assessment "
      "and failure-modes analysis of the flight control system; a scale-model and then unmanned full-scale flight-test "
      "program (the mini is step one); and a team with aerospace engineers who sign for the work.\n")

    w("## How the numbers were made\n")
    w("- `tools/v20/v20params.py`: the master shape (full-scale metres). `tools/v20/geometry.py`: meshes for both scales, the "
      "mini print set and the checks (insides within the fuselage, prop tip gap, P1S fit). `tools/v20/aero.py`: vortex "
      "lattice of the planform with the ducts open (louvres open) or covered (louvres shut) and the stabilators (same solver as `tools/aero_vlm.py`, within 0.3 % "
      "of AeroSandbox) plus Raymer's fuselage correction. `tools/v20/sizing.py`: masses and CG, momentum-theory hover power "
      "with figures of merit, Raymer flat-plate drag build-up, the corridor search, the full-scale sizing loop and the trade study.")
    w("- Assumptions to replace with measurements first: LW-PLA and Depron areal densities (Stage 1 coupons), ducted 4-inch thrust and "
      "current (thrust stand), the EDF's thrust and power at speed, the fan figures of merit (mini 0.48, full 0.70), the "
      "duct-hole drag and blockage, the leading-edge suction (mini 0.2, full 0.5), the turbogenerator's mass and fuel burn. "
      "Every number in this document moves when those do; rerun `make v20`.")
    w("- Not modelled: duct lip suction and fan-wing interference in transition (they help lift and hurt pitch), ground "
      "effect, gusts, the dynamics of the transition (this is a quasi-steady corridor), structural loads and flutter.\n")
    (ROOT / "docs" / "V20_FALCON_JET.md").write_text("\n".join(L) + "\n")
    from bom import params_text
    (ROOT / "config" / "ardupilot" / "skyforge_v20_mini_BENCH_ONLY.param").write_text(params_text(sz["mini"]))
    print("wrote docs/V20_FALCON_JET.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
