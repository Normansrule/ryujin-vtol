# Ryujin V21 mini: G8 pilot-error protections and the digital twin

Nothing here has been on a bench, on the water or in the air. Every value is a first-flight ESTIMATE. The G7 tests replace the aircraft numbers with measured ones, and the logs from those tests set the final values.

G8 adds two things:

- **On the aircraft:** a bench-only set of ArduPilot protections, plus one more guard in the water script.
- **In the app:** a digital twin that flies the same protections. Open the **V21 twin** tab to see what each one does before the bench.

## On the aircraft

The new section is at the end of `config/ardupilot/ryujin_v21_mini_BENCH_ONLY.param`. Every name, unit and range was checked against the ArduPilot Plane 4.8 parameter reference.

| Layer | Parameters | What it stops |
|---|---|---|
| Command shaping | `Q_A_INPUT_TC` 0.2 s, `Q_A_RATE_R/P/Y_MAX` 120/120/60 deg/s, `Q_A_ACC_R/P/Y_MAX` 720/720/180 deg/s², `Q_PLT_Y_RATE` 60 deg/s, `Q_PLT_Y_RATE_TC` 0.3 s | A slammed or pumped stick: it becomes a smooth lean with bounded rate and acceleration. |
| Hover height | `Q_PILOT_SPD_UP` 1.5, `Q_PILOT_SPD_DN` 1.0 m/s, `Q_PILOT_ACCEL_Z` 1.5 m/s² | A slammed or chopped throttle near the water. The stick asks for a climb rate, not thrust. |
| Envelope | `Q_A_ANGLE_MAX` 25°, `Q_P_ANGLE_MAX` 20°, `ROLL_LIMIT_DEG` 45°, `PTCH_LIM_MAX/MIN_DEG` +20/-20°, `STALL_PREVENTION` 1, `THR_SLEWRATE` 50 %/s | Over-banking, over-pitching, steep turns too slow, a slammed EDF throttle. |
| Assist | `Q_ASSIST_SPEED` 13 m/s (G6), `Q_ASSIST_ANGLE` 30°, `Q_ASSIST_ALT` 5 m, `Q_ASSIST_DELAY` 0.5 s, `Q_TRANS_FAIL` 15 s, `Q_TRANS_FAIL_ACT` QRTL | A slow, upset or low fixed-wing aircraft; a transition that never finishes. |
| Fence and failsafes | `FENCE_*` (60 m ceiling, 150 m radius, RTL, on when armed), `Q_RTL_MODE` 1, `THR_FAILSAFE` 1, `FS_SHORT_ACTN` CIRCLE, `FS_LONG_ACTN` RTL, `BATT_LOW/CRT_MAH` 2700/1800, `BATT_FS_LOW/CRT_ACT` RTL/QLand | Flying away or too high, a lost radio link, a flat pack. |

Deliberately NOT set, both UNCONFIRMED:

- `Q_M_SLEW_*`: slowing the motors also slows the stabiliser's own corrections.
- `INS_HNTCH_*`: this needs an FFT of this airframe first, from the G7 W5 log.

### Changes to the G6 scripts

- **`ryujin_water.lua`:** if the radio link is lost on the water, the EDF idles. Without this, a fixed-wing failsafe mode would keep the airboat pushing across the lake. `rc:has_valid_input()` is in the scripting docs; it is UNCONFIRMED on this board until G7 W4.
- **`ryujin_vanes.lua`, a fix:**
  - The aft bias used to apply in every VTOL mode. The twin showed that in a hover it pushes a drifting aircraft forward harder the faster it drifts, which is positive feedback.
  - The bias now applies only in assisted flight and transitions.
  - Whether `quadplane:in_assisted_flight()` is true during a transition is UNCONFIRMED until the bench.
- **`tools/v21/test_g6.py`:** covers both changes.

## The digital twin (`site/js/twin_core.js`, the V21 twin tab)

The twin is a 6-DOF model of the G5 aircraft. It has:

- four lift fans with motor lag, and the exit vanes
- the EDF
- a wing with a stall
- a hull that floats at the G5 waterline and trim, with G5's righting curve and taxi drag

It runs the same control structure as ArduPilot:

- input shaping: a square-root controller with rate and acceleration limits
- an attitude P loop feeding a rate PID with anti-windup
- a mixer that gives up yaw first when a fan saturates
- speed-scaled control surfaces
- the hover climb-rate loop
- stall prevention, assist, transition, the fence, the failsafes and the water gate

It reads its parameters from `site/data/v21.json`, which `tools/v21/web.py` builds from the param file, the scripts, `water.py` and `analysis/v21_g5.json`. The model and the files therefore cannot disagree. `tests/test_twin.mjs` checks this.

**It is a teaching model, not ArduPilot.** The aerodynamics, inertias and hull dynamics are ESTIMATES. "Protections off" is a what-if with every layer removed, which ArduPilot itself cannot be set to.

### The ten demos

Each demo flies the same stick inputs from the same start, twice: once with the protections on and once with them off. In the 3D view, the protected run is solid and the unprotected run is a red ghost. Below the view, plots show the stick request, the shaped target and the actual response, with an event log for each run. Results in the model (ESTIMATE):

| # | Pilot mistake | Protections on | Off |
|---|---|---|---|
| 1 | Roll stick slammed in a 3 m hover | 27° lean at most, holds height | 67° lean, drops to the water |
| 2 | Stick pumped left-right at 2.5 Hz | ±8° | ±22°, sinks |
| 3 | Throttle slammed up, then chopped, at 2 m | Climb ≤ 1.5 m/s, never under 2 m | Climbs to 19 m, then hits the water |
| 4 | Full bank at 15.5 m/s | Bank held near 25-30°, stays airborne | Rolls past 90°, stalls, hits the water |
| 5 | Full back stick at 16 m/s | Still stalls (ArduPilot has no angle-of-attack limiter), but the assist catches it and holds height | Stalls and hits the water |
| 6 | Throttle held up in a hover | Fence at 55 m, QRTL home and down | Keeps climbing |
| 7 | Gusty hover (3 m/s wind, 2.5 m/s gusts) | About the same: shaping slows the pilot, not the stabiliser | Same |
| 8 | Take-off attempted in 60 mm waves | Refused, back to MANUAL | Lifts off |
| 9 | Take-off in calm water (the V21 goal) | GO, climbs to about 1.7 m | Keeps climbing: no height hold |
| 10 | Full throttle on the water, then the radio is lost | EDF capped at taxi speed, then idles | Faster, keeps going |

### Fly it

You can fly the twin yourself, with a keyboard or a gamepad. The controls let you:

- turn the protections on or off
- reset to a hover, the water, or wing-borne flight
- select a mode, arm, and set the water switch
- set the waves, wind, gusts and battery
- simulate a lost radio link or a wet leak sensor

## Open items

- Every protection value needs the G7 bench and tethered logs. Q_AUTOTUNE and the real rate gains come after G7, not before.
- Confirm on the bench how the RC failsafe behaves in VTOL modes (the twin uses QLAND), and what `in_assisted_flight` covers.
- Water take-off stays UNCONFIRMED until G7 W7.
