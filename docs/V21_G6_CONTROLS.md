# Ryujin V21 mini: G6 controls and water mode (BENCH ONLY)

Nothing here has been on a bench, on the water or in the air. Every gain and threshold is an ESTIMATE. The G7 test
procedures replace them with measured values.

## Files

| File | What it does |
|---|---|
| `config/ardupilot/ryujin_v21_mini_BENCH_ONLY.param` | Port map, 4S2P pack limits, scripting on, water-mode switch on RC7. Not a flight tune. |
| `config/ardupilot/scripts/ryujin_vanes.lua` | Bottom louvre / exit-vane mixer (SERVO10 left, SERVO12 right). |
| `config/ardupilot/scripts/ryujin_water.lua` | Water mode: the go/no-go gate, the taxi throttle cap, the arming and VTOL locks. |
| `tools/v21/water.py` | The same gate in Python (the reference; `--selftest`). |
| `tools/v21/test_g6.py` | Runs both scripts in Lua 5.4 against a mock of the ArduPilot API and checks the gate matches `water.py` (1,176 input combinations). `pip install lupa`. |

## Water-taxi

ArduPilot Plane has no boat mode. Water-taxi is **MANUAL with the water switch high**:

- The lift fans are off, as in every fixed-wing mode.
- The cruise EDF pushes (an airboat), and the ruddervators steer.
- The louvres are shut, which keeps spray out of the fans.
- The script caps the EDF at `RYW_TAXI_PWM`, about hull speed (ESTIMATE: set it on the bench).
- The cap never applies in the air, because capping the cruise fan in wing-borne flight would stall it.

## The gate (water switch high)

| Input | Source | Unknown means |
|---|---|---|
| Wind <= `RYW_WIND_MAX` (5 m/s) | `ahrs:get_wind()` (nil when the estimate is not valid); sitting still, the airspeed sensor (the aircraft weathercocks), and that reading is held for `RYW_WIND_HOLD` (60 s) while taxiing | NO-GO |
| Waves <= `RYW_WAVE_MAX` (15 mm, G9) | **The pilot**, in `RYW_WAVE_MM` after looking at the water (no sensor) | NO-GO (default -1) |
| Battery >= `RYW_BATT_MIN` (50 %) | Battery monitor | NO-GO |
| No leak | Analog bilge sensor on ADC pin `RYW_LEAK_ANA` (dry window `RYW_LEAK_VLO`-`RYW_LEAK_VHI` V; outside it is a leak or a wiring fault), or a digital one on GPIO `RYW_LEAK_PIN` | NO-GO (both default -1, not wired) |

When the gate says NO-GO:

- **Disarmed:** arming is refused, and the reason goes to the GCS.
- **Armed on the water:** a VTOL mode is refused and the aircraft goes back to MANUAL, so there is no water take-off.
- **Armed in the air:** only a critical warning. The script never changes mode in the air, because MANUAL would stop the lift fans.

The state is published in `RYW_STATE`: 0 means water mode is off, 1 means GO, 2 means NO-GO.

## Exit-vane mixer

| Situation | Vanes |
|---|---|
| Any fixed-wing mode | Shut (`SERVOn_MIN`) |
| VTOL hover (QHOVER, QLOITER) | Open (`TRIM`), straight down |
| Assisted flight or transition | Open, plus an aft bias of `RYV_FWD_MAX` x airspeed / `AIRSPEED_MIN` (15° at `AIRSPEED_MIN`). G8 change: this bias used to apply in every VTOL mode, and the G8 twin showed it pushing a drifting hover forward harder the faster it drifted. `in_assisted_flight` covering the transition is UNCONFIRMED until the bench. |
| VTOL, yaw input | A differential of `RYV_YAW_MAX` (10°) at full yaw stick |
| A VTOL mode on the water (the water take-off) | Open, like any hover |
| Script stopped | The outputs hold `TRIM` (open), the safe hover position |

The aft bias and the yaw differential add together. The result is clamped between straight down and `RYV_RANGE` (30°) aft. The vanes are slew-limited to `RYV_SLEW` (120°/s).

## UNCONFIRMED and open items

- G9: every binding both scripts call is in ArduPilot's scripting reference (`libraries/AP_Scripting/docs/docs.lua`, master branch, read 2026-11-18), with the argument and return types the scripts assume (`find_channel` and `set_output_pwm_chan_timeout` zero-indexed; `capacity_remaining_pct`, `get_aux_auth_id` and `get_wind` may return nil). `ahrs:wind_estimate()` and `ahrs:airspeed_estimate()` are marked deprecated there, so the scripts now prefer `get_wind()` / `airspeed_EAS()` and fall back to the old calls. Still UNCONFIRMED until the bench (G7 W4): that the firmware release flashed has the newer calls, and that every binding behaves as the mock does.
- G9: the SpeedyBee F405 WING hwdef has no free digital pad with all 12 outputs used (PWM 1-12 are GPIO 50-61; the others drive LEDs, the buzzer and PINIO1). Its ADC pins 14 (PC4, RSSI) and 15 (PC5, analog airspeed) are free here (CRSF receiver, I2C airspeed), so the leak sensor is analog. Which physical pads those are: check the board manual (UNCONFIRMED).
- Yaw is taken from the stick (RC4), not the yaw controller's output. In QLOITER this adds authority but no rate damping.
- Wave height has no sensor. G9 cut the limit from 30 mm to 15 mm: a 30 mm chop can tilt the hull 5.4°, past the 4.4° at which a rear fan exit reaches the water (see `docs/V21_G9_RISKS.md`). G7 W3 measures the heel and `g7.py` re-derives the limit.
- No water take-off logic beyond the locks above: the pilot selects QHOVER from MANUAL taxi. That is the G7 tethered test.
