# Ryujin V21 mini: G12 fixes and the G7 log reader

All ESTIMATE; nothing here has been built, benched or flown.

## Prop tip gap check

The build check measured the prop tip gap against the duct ring. Since G5 the ring is bored out for the drop-in pod
liner, and the prop actually spins inside the liner.

- **Before:** the check read 3.58 mm, which falls in the G7 W0 FIX band (1.5-3.0 mm).
- **Now:** `tools/v21/geometry.py` measures to the pod liner when one is fitted, giving **2.1 mm**, inside the band.

The 157 mm duct with a 152.4 mm prop gives 2.3 mm on paper, so 2.1 mm after the mesh faceting is consistent. W0
measures it with a feeler gauge.

## Twin: EDF thrust and stall speed

**EDF thrust.** The twin's cruise EDF thrust now goes as throttle², matching the G9 taxi study (thrust ~ rpm², rpm ~
throttle on a fixed-pitch fan).

- The scripted fixed-wing demo throttles were rescaled (square root) so each demo still shows what it says.
- RTL/CIRCLE autothrottle was rescaled the same way.
- Water-taxi at the throttle cap now reaches 1.44 m/s in the twin, against 1.46 m/s in the study.
- The thrust stand (G7 W1) fits the real curve.

**Stall speed.** The twin assumed stall = `AIRSPEED_MIN` / 1.2 = 12.5 m/s. The G5 sizing's own stall speed is
**10.5 m/s**, and it set `AIRSPEED_MIN` = ceil(1.35 x stall) = 15 and `Q_ASSIST_SPEED` = ceil(1.2 x stall) = 13.

With the 12.5 m/s guess, a steep turn that bled speed at low throttle stalled before `Q_ASSIST_SPEED` brought the
fans in. That made it look as if 13 m/s was too low. It was the twin's stall guess, not the parameter.

- The twin now takes `stall_ms` from the sizing (`site/data/v21.json`).
- **`Q_ASSIST_SPEED` stays 13.**
- Two new tests in `tests/test_twin.mjs`:
  - The stall speed sits at least 15 % under `Q_ASSIST_SPEED`.
  - The decelerating steep turn never stalls at throttle 0.3, 0.4 or 0.5.

## G7 log reader

`python3 tools/v21/g7_log.py LOG.bin --write` reads a DataFlash binary log, or Mission Planner's text export. It
takes the field layout from the log's own FMT records and fills two fields:

| Field | How it is read |
|---|---|
| W6 `taxi_max_speed_m_s` | Highest 2 s running median of GPS speed in MANUAL. A GPS glitch shorter than 1 s doesn't count. |
| W7 `water_takeoff_peak_a` | Peak battery current, instance 0, in each QSTABILIZE / QHOVER / QLOITER stretch, and the worst of them. |

- It fills only empty fields; `--force` overwrites.
- It does not judge whether a take-off succeeded; that is the pilot's call.
- `--selftest` checks it against binary and text logs it writes itself: a GPS spike, a second battery and junk bytes
  to resync over.
- Reading a real Plane log is **UNCONFIRMED** until the first G7 log goes through it. Compare its MODE, BAT and GPS
  counts with Mission Planner's log browser once.
