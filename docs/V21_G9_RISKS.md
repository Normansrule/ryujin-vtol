# Ryujin V21 mini: G9 open-risk study

Every number here is an ESTIMATE from the G5 model (`tools/v21/g9.py`, results in `analysis/v21_g9.json`). Nothing
has been floated, benched or flown. The G7 tests (`docs/V21_G7_TEST_PROCEDURES.md`) replace these numbers.

Run it with `python3 tools/v21/g9.py` (about 6 minutes; it re-floats the model four times). Since G10 the G5 model has the 5 mm exit scarf; set `g5.EXIT_SCARF = 0` to reproduce the plain-exit numbers below.

## Summary

| Risk | Result | Status | What changed |
|---|---|---|---|
| Rear fan exit wets at small heel | Still water: about 1.0° of heel (5 m/s beam wind plus a taxi turn) against 4.4° to wet a fan exit. A 30 mm chop can tilt the hull 5.4° | **FLAG** at the old 30 mm wave limit | Wave limit cut to 15 mm (`RYW_WAVE_MAX`, `water.py`) |
| Lower the floats to fix it | +0.3° of heel margin for 15 mm lower, at the cost of nearly half the righting arm and 10 mm of nozzle freeboard | Rejected | Floats stay as G5 |
| Nose stretch and pitch stability | Static margin 7.3 % with the 50 mm stretch in. The floats cost 0.36 points | PASS (ESTIMATE) | None |
| Water-taxi thrust | The throttle cap holds about 1.46 m/s, just under hull speed. The full EDF has 1.17 x the drag at 2 m/s | PASS for taxi (take-off is vertical) | None |
| ArduPilot Lua bindings | All found in `docs.lua` (master, read 2026-11-18). Two were deprecated | Fixed | `get_wind()` and `airspeed_EAS()` used, with the old calls as a fallback |
| Leak sensor pin | No free digital pad on the SpeedyBee F405 WING | Fixed | Analog sensor on ADC pin 14 or 15 with a dry-voltage window |

## 1. Heel and the rear fan exits

The roll curve heels the sealed body and hull about the CG with the wings flooded (G5 method). The lowest rear fan
exit reaches still water at **4.4°** (G5 rounded this to 5°).

| Heel | GZ (mm) | Lowest fan exit above water (mm) |
|---|---|---|
| 1° | 14.1 | 19.3 |
| 2° | 27.6 | 13.8 |
| 3° | 39.7 | 8.1 |
| 4° | 48.4 | 2.2 |
| 5° | 54.7 | -3.8 |
| 10° | 73.3 | -32.4 |
| 30° | 56.1 | -133.9 |

It rights itself at every angle checked. The steady heeling moments are:

| Case | Moment | Heel |
|---|---|---|
| Beam wind at `RYW_WIND_MAX` (5 m/s, side area 0.115 m², Cd 1.1, lever 97 mm) | 0.188 N m | 0.68° |
| Taxi turn, 1.5 m/s on a 3 m radius | 0.085 N m | 0.31° |
| Both | 0.273 N m | 0.99° |

That leaves 3.4° of margin in still water. Waves are the problem. A short hull follows the wave face, which slopes up
to atan(πH/L). At 30 mm and a 1.0 m chop the slope is 5.4°, which is past 4.4° before adding the wind.

**Change:** `water.py` now takes the smaller of two limits:

- **Crest:** 2 x (lowest freeboard − 5 mm). This gives 34 mm.
- **Slope:** the wave slope plus 1.0° of steady heel plus a 0.5° keep must stay under 4.4°. This gives 16 mm.

The result is rounded down to 5 mm, so the limit is **15 mm**. `RYW_WAVE_MAX` defaults to 15. `g7.py` re-derives the
limit from the measured W3 freeboard and heel with the same function, `water.wave_limit_m()`.

The 1.0 m wavelength is an assumption (ESTIMATE). Longer swell tilts the hull less for the same height.

## 2. Lowering the floats (rejected)

Longer struts, same floats; the aircraft is re-floated each time.

| Floats lowered (mm) | Heel to wet a fan exit | GZ at 2° (mm) | Freeboard fan / intake / nozzle (mm) | Trim | Taxi drag at 1.5 m/s |
|---|---|---|---|---|---|
| 0 (G5) | 4.36° | 27.6 | 22.7 / 22.3 / 26.8 | -0.57° | 2.53 N |
| 5 | 4.47° | 25.1 | 25.3 / 25.1 / 23.6 | -0.19° | 2.52 N |
| 10 | 4.59° | 21.4 | 26.7 / 27.9 / 20.3 | +0.21° | 2.51 N |
| 15 | 4.71° | 15.1 | 27.0 / 30.6 / 17.0 | +0.61° | 2.52 N |

Lowering them barely moves the flood heel. The floats lift the hull, but they also take its waterplane, so the
righting arm falls and the nozzle sinks.

A real fix is a geometry change, and that goes back to G3/G5 for your decision:

- Floats further out (a wider track).
- Rear fan exits raised or given a lip.

The bottom louvres are already shut in water mode. That keeps spray out, but they are not a seal.

## 3. Nose stretch and pitch stability

| Configuration | Static margin |
|---|---|
| G5 as built (50 mm nose stretch, floats) | 7.31 % |
| Without the floats' aero drag bodies | 7.67 % |

The nose stretch is already in the fuselage term of `aero.py`. The floats sit ahead of the CG and cost 0.36 points.
7.3 % is inside the usual 5-15 % band for a model this size (ESTIMATE). G7 W2 measures the CG; `g7.py` FIXes it if it
lands more than 3 mm off.

## 4. Water-taxi thrust

The cap is `RYW_TAXI_PWM` 1450, so the throttle is 0.45. EDF static thrust is about 11.8 N. Thrust is taken as
static x throttle², because thrust goes as rpm² and rpm roughly with throttle on a fixed-pitch fan (ESTIMATE). That
gives about 2.38 N at the cap.

| Speed | Hull drag | Full EDF / drag | Capped EDF / drag |
|---|---|---|---|
| 0.5 m/s | 0.13 N | 89 | 18 |
| 1.0 m/s | 0.60 N | 19.7 | 4.0 |
| 1.5 m/s | 2.53 N | 4.65 | 0.94 |
| 2.0 m/s | 10.1 N | 1.17 | 0.24 |

The cap holds about **1.46 m/s**, just under hull speed. The aircraft does not plane, and it does not need to,
because the water take-off is a vertical hover climb. The full EDF can barely get past the hump at 2 m/s. G7 W6
(bollard pull, top taxi speed) measures both.

**Open:** the twin (`site/js/twin_core.js`) models EDF thrust as linear in throttle. At the cap it shows about twice
the thrust of this study, so its taxi demo runs faster than this estimate. W1 measures the real curve; fit both to it.

## 5. ArduPilot Lua bindings

Every call in `ryujin_water.lua` and `ryujin_vanes.lua` was checked against
`libraries/AP_Scripting/docs/docs.lua` on master (read 2026-11-18), with the argument and return types:

- `find_channel` and `set_output_pwm_chan_timeout` are zero-indexed.
- `capacity_remaining_pct`, `get_aux_auth_id` and `get_wind` can return nil.
- `ahrs:wind_estimate()` and `ahrs:airspeed_estimate()` are deprecated. The scripts prefer `get_wind()` and
  `airspeed_EAS()` and fall back to the old calls on older firmware.

**Safety fix:** `wind_estimate()` can read calm while the estimate is not valid. `get_wind()` returns nil then.

- Sitting still, the aircraft weathercocks, so the airspeed sensor reads the wind.
- That reading is held for `RYW_WIND_HOLD` (60 s) while taxiing.
- With no valid source the gate says NO-GO.

UNCONFIRMED until G7 W4: that the firmware flashed has the newer calls, and that every binding behaves as the mock in
`tools/v21/test_g6.py` does.

## 6. Leak sensor

The SpeedyBee F405 WING hwdef has no free digital pad with all 12 outputs used:

- PWM 1-12 are GPIO 50-61.
- GPIO 0 and 1 drive LEDs, 80 the buzzer and 81 PINIO1.

Two ADC pins are free here:

- Pin 14 (PC4, RSSI). Free because the receiver is CRSF.
- Pin 15 (PC5, analog airspeed). Free because the airspeed sensor is I2C (`ARSPD_TYPE 1`).

Which physical pads those are is UNCONFIRMED; check the board manual.

**Wiring (ESTIMATE):** 3.3 V, then 100 kΩ, then the ADC pin, then 1 MΩ to ground, with the two bilge pads across the
1 MΩ.

| Reading | Means | Gate |
|---|---|---|
| About 3.0 V (inside `RYW_LEAK_VLO`-`RYW_LEAK_VHI`, 2.6-3.15 V) | Dry | GO |
| Below 2.6 V | Water across the pads | NO-GO: leak |
| Above 3.15 V | A lead is off (the 1 MΩ side is open) | NO-GO: leak sensor fault |
| Under 0.3 V | Shorted or unpowered | NO-GO: leak sensor fault |

Set `RYW_LEAK_ANA` to 14 or 15. `RYW_LEAK_PIN` (digital) stays as a fallback for other boards.

G7 W3 gained two rows: the dry voltage (`leak_sensor_dry_v`), and unplugging the lead must give NO-GO
(`leak_sensor_open_trips`).

## Still open

- The heel limit rests on the roll model and a 1.0 m chop. W3 measures the heel; `g7.py` re-derives the wave limit.
- A wider float track or raised fan exits would buy back wave margin. That is a design decision, not made here.
- The twin's linear EDF model versus throttle² here. W1 settles it.
- Bench (W4): the bindings, `in_assisted_flight` during transition, VTOL RC-failsafe behaviour, and the leak sensor
  pads.
