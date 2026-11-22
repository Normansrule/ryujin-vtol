# Ryujin V21 mini: G7 test procedures

Every V21 number so far is an ESTIMATE from `tools/v21/g5.py`. These tests replace those numbers with measured ones, in an order where each test protects the next. Water-to-air take-off is the V21 main goal, and it stays **UNCONFIRMED** until W7 passes.

## How to record results

1. Record every measurement in `config/v21_measurements.json` (the template has every field set to `null`).
2. Run `python3 tools/v21/g7.py`. It prints PASS / FIX / STOP / NOT MEASURED for every gate below, and the water limits the measured margins support. A FIX or STOP ends the session. Fix the cause, then re-run that stage before moving on.

## Rules for every stage

- Freshwater only. The sea needs its own corrosion gate first.
- Props off until a stage says props on.
- A tether and a second person for every powered water test (W5-W7).
- Nobody in a prop plane.
- The pack goes in a LiPo-safe bag when it is out of the aircraft.

Predictions in the tables come from `analysis/v21_g5.json`.

---

## W0: print and fit (no power)

**Print** the `cad/v21/mini/` print set. Any piece the slicer reports over the P1S bed is a FIX.

| Measurement | How | PASS | FIX | STOP |
|---|---|---|---|---|
| Pack fit | Two 2 x 2 bundles of 21700 cells in the nose bay, nose hatch closed | Both bundles go in and out through the hatch by hand; the hatch closes on its gasket without pressing on the cells | Trim pads or reprint the hatch | Cells do not fit: the G5 nose stretch is wrong; back to G5 |
| Fan pods | Each of the 4 printed pod liners in each of the 4 ducts, scarf facing outboard (a left pod is a right pod turned 180°; mark the scarf side) | All 16 combinations drop in by hand; prop tip gap 1.5-3.0 mm everywhere (feeler gauge; the model predicts 2.1 mm to the liner) | Sand or reprint the liner | Tip gap under 1.0 mm anywhere |
| Wing shear bolts | Nylon M4 bolts through the wing root into the inserts | Wing seats flush; spars slide out once the bolts are cut | Re-tap or move the insert | - |
| Payload bay drains | Pour 50 ml into the bay with the doors shut | Drains out of the door holes in under 10 s | Open the holes | - |

## W1: thrust stand (replaces the 0.95 kg-per-fan and 1.20 kg EDF assumptions)

Use the V20 Stage-2 rig and `tools/ingest_bench.py`. Test one lift fan inside its printed pod and duct section, so the figure includes duct effects, and the EDF with its inlet screened.

| Measurement | Field | PASS | FIX | STOP |
|---|---|---|---|---|
| Lift-fan static thrust, worst of 4, loaded pack voltage | `lift_fan_thrust_g_min` | >= 1.9 x measured mass / 4 (predicted need: 947 g) | Within 5 % below: lighten, or change the prop and re-bench | More than 5 % below: no hover tests |
| EDF static thrust | `edf_static_thrust_g` | >= 1.25 x the predicted taxi drag at 1.5 m/s (2.53 N, so >= 322 g) | 258-322 g | Under 258 g: taxi below hull speed is not possible |
| Pack sag at hover current (about 24 A) | `pack_v_at_hover` | >= 14.0 V | 13.2-14.0 V | Under 13.2 V |
| Scarfed exit (G10 option B): one scarfed pod and one plain pod (`cad/v21/mini/test/duct_pod_PLAIN_W1_test_and_fallback.stl`), same fan, same duct section, same pack voltage | `scarfed_pod_thrust_g`, `plain_pod_thrust_g` | Scarfed >= 1.9 x mass / 4 and >= 99 % of plain: the wave limit may later rise to 20 mm (W3 heel decides) | Otherwise: fit plain pods, keep the 15 mm wave limit | - |

## W2: weigh and balance (dry, complete, pack in)

| Measurement | How | Field | PASS | FIX | STOP |
|---|---|---|---|---|---|
| All-up mass | 1 g scale | `all_up_mass_g` | <= 1.03 x 1,994 g | <= 1.08 x | Over 1.08 x: re-run sizing with the measured mass first |
| CG x | Two-scale method, from the nose tip, convert to the model frame (the tip is at x = -50 mm) | `cg_x_mm` | 346 +/- 3 mm (the fan centroid) | +/- 3-6 mm: slide the pack bundles or ESC | More than 6 mm off: back to G5 |

## W3: float, leak and heel (no power, tethered in a pool or tank)

| Measurement | How | Field | PASS | FIX | STOP |
|---|---|---|---|---|---|
| Leak | Sealed hull with a dry paper towel inside, held 30 mm under water for 30 min. Weigh the towel before and after | `leak_ingress_g_30min` | <= 1 g | 1-5 g: find the leak (soapy water at 0.1 bar) and reseal | Over 5 g |
| Leak sensor | Wet the sensor pads | `leak_sensor_trips` | `RYW_STATE` goes to 2 and the GCS shows LEAK within 1 s | - | Does not trip: no water tests |
| Leak sensor wiring (G9, analog) | Dry and connected, read the pin voltage on the GCS (or a meter at the pads' divider) | `leak_sensor_dry_v` | 2.7-3.1 V (window `RYW_LEAK_VLO`-`RYW_LEAK_VHI` 2.6-3.15 V) | Inside the window but within 0.1 V of an edge: check the resistors | Outside the window when dry |
| Leak sensor open circuit (G9) | Unplug the sensor lead with water mode on | `leak_sensor_open_trips` | `RYW_STATE` goes to 2 and the GCS shows "leak sensor fault" | - | Stays GO: no water tests |
| Trim | Phone inclinometer on the canopy rail, at rest | `float_trim_deg` (nose up +) | -2.0 to +1.0° (predicted -0.6°) | Within 1° outside that range: move the pack | - |
| Freeboard, lowest point of each opening above still water | Steel rule, 3 readings each | `freeboard_fan_mm`, `freeboard_intake_mm`, `freeboard_nozzle_mm` | Each >= 20 mm (predicted 22.7 / 22.3 / 26.8) | 15-20 mm: lower the `water.py` wave limit to suit (g7.py prints it) | Under 15 mm at any opening |
| Heel to wet a fan exit | Push one wingtip down slowly with a stick; read the angle when the lowest rear fan exit touches the water | `heel_fan_wet_deg` | >= 5.2° with scarfed pods after W1 passes (G10 prediction), else >= 4.4° (G9, plain pods) | 3-4.4°: g7.py lowers the wave limit (slope rule in `water.wave_limit_m`) | Under 3° |
| Self-righting | Release from 20° of heel | `rights_from_20deg` | Comes back upright with no help | - | Stays heeled or capsizes |

## W4: bench scripts on the SpeedyBee (props off)

Load the bench param file and the two scripts. Check each binding the off-board test (`tools/v21/test_g6.py`) only mocked.

| Check | Field | PASS |
|---|---|---|
| Both scripts load; RYW_ and RYV_ parameters appear | `bench_scripts_load` | true |
| Water switch high, wave height unset: arming is refused with "water NO-GO" | `bench_arming_refused` | true |
| Water mode, armed, MANUAL, full throttle: EDF output held at `RYW_TAXI_PWM` | `bench_taxi_cap` | true |
| QHOVER selected on the bench with NO-GO: back to MANUAL | `bench_vtol_refused` | true |
| Vanes: MIN in FBWA, TRIM in QHOVER, differential with yaw stick | `bench_vanes` | true |
| A log replay shows `get_likely_flying` false on the bench | `bench_likely_flying_false` | true |

## W5: spray-ingestion hover (tethered, 1 m over water, props on)

Do this over a pool or a calm, shallow, empty lake, on a tether short enough that the aircraft cannot reach anyone. Hover for 60 s at 1 m, then 30 s at 0.5 m. Land on a pad beside the water, not on it.

| Measurement | Field | PASS | FIX | STOP |
|---|---|---|---|---|
| Water inside the sealed hull | `spray_hull_water_g` | 0 g (towel) | Up to 1 g: seal and repeat | Over 1 g |
| Motor and ESC behaviour | `spray_motor_events` | No desyncs, no current spikes over 1.3 x hover in the log | - | Any desync |
| Lowest height before a visible spray plume reaches the intakes | `spray_plume_height_m` | Recorded (sets the take-off climb rate in G8) | - | - |

## W6: water-taxi and bollard pull (tethered, props on, EDF only)

After each W6 or W7 session: `python3 tools/v21/g7_log.py LOG.bin --write` reads the flight log and fills `taxi_max_speed_m_s` (2 s running median of GPS speed in MANUAL) and `water_takeoff_peak_a` (peak battery current in each QHOVER/QLOITER/QSTABILIZE stretch). Check its MODE/BAT/GPS counts against Mission Planner once, on the first log (UNCONFIRMED until then). Then `python3 tools/v21/g7_log.py LOG.bin --replay replay.json` and load the file in the twin's "Replay a log" tab: the twin flies the logged sticks and modes, and its roll, pitch and current are compared with the log (see `docs/V21_G13_REPLAY.md`).

| Measurement | How | Field | PASS | FIX | STOP |
|---|---|---|---|---|---|
| Bollard pull | Spring scale on a bow line, full EDF | `bollard_pull_g` | >= 1.25 x predicted drag at 1.5 m/s (322 g) | 258-322 g | Under 258 g |
| Top taxi speed | GPS log, 20 m straight run with `RYW_TAXI_PWM` at max | `taxi_max_speed_m_s` | >= 1.0 m/s | 0.6-1.0 m/s | Under 0.6 m/s |
| Steering | Ruddervators only, at 0.5 m/s | `taxi_turn_ok` | Turns both ways within 3 m | - | Cannot turn one way |
| Water in the hull after 5 min of taxi | Towel | `taxi_hull_water_g` | 0 g | Up to 1 g | Over 1 g |

## W7: water take-off (tethered; the V21 main goal)

Only after W0-W6 pass. Taxi to a clear area, then switch to QHOVER on the water (`RYW_STATE` must be 1). Climb to 1 m, hold for 10 s, then land on the pad. Repeat 3 times.

| Measurement | Field | PASS | FIX | STOP |
|---|---|---|---|---|
| Clean lift-offs out of 3 | `water_takeoffs_ok` | 3 of 3 | 2 of 3: read the log (spray, trim, current) and repeat | 0-1 of 3 |
| Peak current during the lift-off | `water_takeoff_peak_a` | <= 76 A (`Q_M_BAT_CURR_MAX`) | - | Over 76 A |

**Only W7 PASS lets the README call water-to-air take-off demonstrated, and only for a tethered take-off in calm freshwater.**
