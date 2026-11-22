# Ryujin V21 mini: G13 flight-log replay in the twin

Nothing here has flown. The replay compares the twin (an ESTIMATE model) with a real log, so its value starts at the
first G7 log.

## How to use it

1. `python3 tools/v21/g7_log.py LOG.bin --replay replay.json` (a DataFlash `.bin` or Mission Planner's text export).
2. Open the V21 twin tab, choose **Replay a log**, and load `replay.json`.
3. Tick or untick "Starts on the water" to match the session.

The twin is flown twice from the logged sticks and mode changes, once with the bench protections and once without.
The plots draw roll and pitch for both runs and the measured attitude (dashed). The side panel gives the RMS
difference between the protected run and the log for roll, pitch and battery current.

## What the replay file holds

| Field | Source |
|---|---|
| Sticks (roll, pitch, yaw, throttle) | RCIN, normalised with the log's own `RCMAP_*` and `RCn_MIN/TRIM/MAX` from PARM |
| Mode changes | MODE. QLOITER and QSTABILIZE are flown as QHOVER; modes the twin lacks are held and listed |
| Measured attitude | ATT.Roll, ATT.Pitch |
| Measured current | BAT instance 0 |

The stick sign is checked against the log itself: the roll stick must correlate positively with ATT.DesRoll, and the
pitch stick negatively with ATT.DesPitch (in the twin, back stick is -1). If a sign is the wrong way it is flipped and a
note says so, with the correlation. A correlation under 0.3 also gives a note: the reader cannot tell the direction.

## Reading the result

- **Small RMS in a hover (a few degrees):** the twin's attitude loop and inertias are close enough to plan with.
- **A steady offset:** trim, CG or an IMU mounting angle the twin doesn't model. Check against W2.
- **The twin lags or overshoots:** its inertias or `Q_A_*` loop gains are off. That is what the replay is for: fit
  them, then re-run the demos.
- **Large RMS after a take-off or a touch-down:** expected. Hull and ground contact are the roughest parts of the
  model, and a small timing difference there grows.

The replay is open-loop on the sticks, so the twin can drift away from the real aircraft over a long log even when
each part of the model is right. Compare short stretches first.

## Checks

- `node --test tests/test_twin.mjs`: a twin flight is logged, replayed and must match itself within 1°; QLOITER maps to
  QHOVER; a file of the wrong kind is refused.
- `python3 tools/v21/g7_log.py --selftest`: the synthetic log has its pitch reversed, and the reader must flip it back.
- The end-to-end chain (synthetic `.bin`, then `--replay`, then the tab) was run in a headless browser. The synthetic
  log's attitude is made up, so its RMS (roll 17.9°, pitch 4.6°) says nothing about the model.

**UNCONFIRMED** until the first G7 log: the RCIN channel order on the real radio, and that a real Plane 4.x log has
the fields the reader expects.

## Also in G13

The twin's "fan exit is wet" warning now quotes the flood heel from the sizing (5.2° with the scarf) instead of a fixed
5°.
