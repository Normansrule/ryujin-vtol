# Ryujin V21 mini: G10 wave-margin design study

Every number here is an ESTIMATE from the G5 model (`tools/v21/g10.py`, results in `analysis/v21_g10.json`). The study
changes parameters, re-floats the model and puts them back.

**Decision (Alek, 2026-11-18): option B, scarfed exits, gated on thrust.** The scarf is now in the G5 model and print
set (`EXIT_SCARF` in `tools/v21/g5.py`): the outboard half of every lift-fan exit is cut up 5 mm (mini), on the duct
ring and the drop-in pod, and the exit vanes sit 5 mm higher. One pod design for all four (the left ones are the
right ones turned 180°). The roll model with the half-scarf gives a flood heel of 5.19°, the same as the full-ring
raise below. G7 W1 compares a scarfed pod with a plain one. Until it passes, the wave limit stays at 15 mm.

The study below predates the decision; `g10.py` models plain exits.

Run it with `python3 tools/v21/g10.py` (about 15 minutes). `python3 tools/v21/g10.py A` re-runs only option A.

## The problem (from G9)

- A rear lift-fan exit reaches still water at 4.4° of heel.
- A 30 mm chop can tilt the hull 5.4°, so G9 cut the wave limit to 15 mm.
- The goal is to buy back wave margin without breaking another gate.

## Results

The wave limit comes from `water.wave_limit_m()` (the G9 crest and slope rules), using each case's own steady heel.
The steady heel is a 5 m/s beam wind plus a 1.5 m/s taxi turn.

| Case | Heel to wet a fan exit | Steady heel | Wave limit | GZ at 2° | Mass | Lift T/W | SM | Lowest freeboard | Taxi drag 1.5 m/s |
|---|---|---|---|---|---|---|---|---|---|
| G5 as built | 4.36° | 0.99° | 15 mm | 27.6 mm | 1,994 g | 1.906 | 7.31 % | 22.3 mm | 2.53 N |
| A: floats out to y 325 mm | 4.29° | 0.70° | 15 mm | 38.5 mm | 1,994 g | 1.906 | 7.31 % | 22.3 mm | 2.53 N |
| A: y 325, lowered 10 mm | 4.50° | 0.90° | 15 mm | 28.6 mm | 1,994 g | 1.906 | 7.31 % | 20.3 mm | 2.51 N |
| A: y 375, floats moved aft (wing sweep) | 4.21° | 0.50° | 0 | 50.7 mm | 1,994 g | 1.906 | 6.83 % | **-0.4 mm (intake under)** | 2.77 N |
| A: y 325, floats r 35 mm, lowered 5 mm | 4.78° | 0.60° | 20 mm | 47.5 mm | 2,006 g | **1.894** | 7.18 % | 19.6 mm | 2.46 N |
| A: y 325, floats r 40 mm, lowered 5 mm | 5.17° | 0.51° | 20 mm | 56.3 mm | 2,018 g | **1.883** | 7.03 % | 16.7 mm | 2.45 N |
| **B: rear exits raised 5 mm** | **5.19°** | 0.99° | **20 mm** | 27.6 mm | 1,994 g | 1.906 | 7.31 % | 22.3 mm | 2.53 N |
| B: rear exits raised 10 mm | 5.92° (front exits now first) | 0.99° | 20 mm | 27.6 mm | 1,994 g | 1.906 | 7.31 % | 22.3 mm | 2.53 N |

Bold marks the numbers that decide it.

## Why a wider track alone doesn't help

At the G5 height the floats sit clear of the water at rest and only touch after a degree or two. So below about 4°,
the hull still pivots about its own V-belly, and the rear exits sit about 310 mm out from the centreline. The flood
angle stays near atan(22.7 / 310), about 4.2°, whatever the track. Lowering them so they carry weight at rest helps
only a little (4.5° at 10 mm), because the hull then floats higher and its own waterplane gives way.

Moving the floats out does double the righting arm, so the boat stiffens against wind and turns (steady heel falls
from 0.99° to 0.70°). But that is not what floods the exits. The waves are.

Only bigger floats move the pivot outboard, and they cost mass:

- r 35 mm: +12 g, lift T/W 1.894. **FAIL** against the 1.9 gate.
- r 40 mm: +24 g, lift T/W 1.883. **FAIL**.

At r 40 mm the nozzle freeboard also drops to 16.7 mm, below the 20 mm target.

Past y ~330 mm the swept wing's leading edge is aft of the G5 floats. Moving them aft under the wing trims the hull
5.5° nose down and puts the intakes under water, so that is out.

Wing-root moment if one float is pushed fully under:

| Case | Moment |
|---|---|
| G5 | 1.52 N m |
| y 325 mm | 1.80 N m |
| r 40 mm | 3.20 N m |

That is a structural cost the G5 build has not been checked for.

## Why B works

Raising the rear exits by 5 mm (mini) moves the flood heel from 4.4° to 5.2°, and the wave limit from 15 mm to 20 mm.

- It costs no mass in this model (the louvre frame moves up, ESTIMATE about 0 g).
- No drag, trim, SM or freeboard change.

At 10 mm the front exits wet first at 5.9°. The slope rule then still rounds to 20 mm, so 5 mm is the useful amount.

**The risk is thrust.** A raised exit is a shallower duct: 22.6 mm instead of 27.6 mm. That shortens the part of
the duct below the prop, and nothing in this model says what that does to static thrust.

The build has only **5.9 g** of headroom under the T/W gate (1,994 g against a 2,000 g limit at 0.95 kg per fan). A 1 %
thrust loss on the rear pair lowers that limit by about 10 g. So B is only safe if the thrust stand shows no loss.

## Recommendation: B, made as a scarfed exit, gated on the thrust stand

1. **Shape:** cut the outboard half of each duct exit up by 5 mm (a scarf) instead of raising the whole ring.
   - At heel the outboard rim is what reaches the water first.
   - The inboard half keeps the full duct depth, which should keep most of the thrust (UNCONFIRMED).
2. **Interchangeable pods:** give all four pods the same scarf.
   - The front exits are not the limit until 10 mm, so scarfing them costs nothing.
   - This keeps the W0 check "4 fan pods interchangeable".
3. **Gate it in G7 W1:** test one scarfed pod against one plain pod on the thrust stand.
   - Go ahead only if the scarfed pod still makes at least 0.95 kg (the G5 assumption).
   - Then set `RYW_WAVE_MAX` to 20 and update `water.py` (`HEEL_FAN_WET_DEG` 5.2).
4. **For extra T/W margin:** fly the water take-off tests without the 25 g default payload module.
   - That takes the mass to about 1,969 g, giving lift T/W 1.93 and 31 g of headroom.
   - No design change is needed. It is an operating rule for G7 W5-W7 (ESTIMATE).

Option A's bigger floats fail the T/W gate unless the thrust stand shows at least 0.953 kg per fan (r 35 mm) or 0.959 kg (r 40 mm). If W1 comes
in high, A with r 35 mm becomes possible. It also stiffens the boat against wind and turns, which B does not.

## Still open

- The heel numbers rest on the G5 roll model. G7 W3 measures them.
- The scarf's thrust effect is unknown until W1.
- The wing-root load from a float driven under has not been checked for any case. G7 W3 pushes a wingtip down by hand.
