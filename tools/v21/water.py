#!/usr/bin/env python3
"""V21 "Ryujin" go/no-go gate for water landings and water-taxi.

    python3 tools/v21/water.py --selftest

water_ops_allowed() is deliberately conservative and fails safe: any missing, non-finite or out-of-range input is a
NO-GO. Every threshold below is an ESTIMATE derived from the G4 sizing (analysis/v21_g4_sizing.json), not from a test.
The G7 float/leak test, the spray-ingestion hover over water and the bollard-pull test replace them; until then
treat a GO as "allowed to try on a tethered freshwater test", never as "safe".

Freshwater only: saltwater has its own corrosion gate (see the project rules) and is NO-GO here by construction
(there is no saltwater input; do not use this function for the sea).
"""
from __future__ import annotations

import math
import sys

# --- thresholds (ESTIMATE) -----------------------------------------------------------------------------------------
# Waves (G9): two limits, the smaller wins.
#  1. Crest: a wave of height H (trough to crest) lifts the water H/2 above still level. Keep 5 mm of the lowest
#     opening's freeboard for heave and spray: H <= 2 * (freeboard - 5 mm). G5 lowest freeboard 22.3 mm -> 34 mm.
#  2. Slope: a short hull follows the wave face, so the wave tilts it by up to atan(pi H / L). Added to the steady heel
#     from a beam wind at MAX_WIND_M_S plus a taxi turn (G9: 1.0 deg) and a 0.5 deg keep, it must stay under the heel at
#     which the lowest rear fan exit reaches still water (G9: 4.4 deg). With L = 1.0 m chop -> 16 mm.
#  Rounded down to 5 mm, since the pilot judges waves by eye -> 15 mm. g7.py re-derives it from the W3 measurements.
LOWEST_FREEBOARD_M = 0.0223         # ESTIMATE (G5 float model, intake)
SPLASH_KEEP_M = 0.005               # ESTIMATE
HEEL_FAN_WET_DEG = 4.4              # ESTIMATE (G9 roll model, plain exits). In force until G7 W1 passes the scarfed pod
HEEL_FAN_WET_SCARFED_DEG = 5.2      # ESTIMATE (G10 option B, 5 mm outboard exit scarf): 20 mm waves, only after W1 passes
STEADY_HEEL_DEG = 1.0               # ESTIMATE (G9: 5 m/s beam wind 0.68 deg + 1.5 m/s turn on 3 m 0.31 deg)
HEEL_KEEP_DEG = 0.5                 # ESTIMATE
WAVELENGTH_M = 1.0                  # ESTIMATE (short wind chop on a pond; longer swell tilts less)


def wave_limit_m(lowest_freeboard_m: float, heel_fan_wet_deg: float) -> float:
    """Largest wave height (m) both the crest rule and the slope rule allow, rounded down to 5 mm."""
    crest = 2 * max(0.0, lowest_freeboard_m - SPLASH_KEEP_M)
    tilt = max(0.0, heel_fan_wet_deg - STEADY_HEEL_DEG - HEEL_KEEP_DEG)
    slope = WAVELENGTH_M * math.tan(math.radians(tilt)) / math.pi
    return math.floor(min(crest, slope) * 200 + 1e-9) / 200


MAX_WAVE_HEIGHT_M = wave_limit_m(LOWEST_FREEBOARD_M, HEEL_FAN_WET_DEG)     # 0.015 m

# Wind: the mini hovers at a 15 m/s minimum airspeed in fixed-wing flight (V20 AIRSPEED_MIN) but on the water it is an
# airboat with almost no keel. A 5 m/s wind is about a third of the stall-free airspeed, which keeps the take-off hover
# drift and the weathercocking on the water manageable. Not from a test.
MAX_WIND_M_S = 5.0                  # ESTIMATE (sustained wind at about 2 m above the water)

# Battery: a water take-off is a full-power hover climb out of the spray, and a failed one means floating until
# recovered. 18.5 min hover on 80 % usable (G4) -> about 4.3 % of pack per minute of hover. 50 % keeps more than
# 8 minutes of hover for the take-off, a go-around and the flight home, plus the ArduPilot battery failsafe margin.
MIN_BATTERY_PCT = 50.0              # ESTIMATE


def _finite(x) -> bool:
    try:
        return x is not None and not isinstance(x, bool) and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def water_ops_allowed(wind_m_s: float, wave_height_m: float, battery_pct: float, leak_detected: bool) -> bool:
    """True only when every condition for a water landing or water-taxi is met (freshwater, ESTIMATE thresholds).

    wind_m_s       sustained wind speed (m/s), >= 0
    wave_height_m  trough-to-crest wave height (m), >= 0
    battery_pct    remaining pack charge (0-100 %)
    leak_detected  the bilge leak sensor's state; must be exactly False (an unknown sensor state is a NO-GO)
    """
    if leak_detected is not False:          # True, None or anything that is not a definite "no leak"
        return False
    if not (_finite(wind_m_s) and _finite(wave_height_m) and _finite(battery_pct)):
        return False
    wind, wave, batt = float(wind_m_s), float(wave_height_m), float(battery_pct)
    if wind < 0 or wave < 0 or not 0 <= batt <= 100:
        return False
    return wind <= MAX_WIND_M_S and wave <= MAX_WAVE_HEIGHT_M and batt >= MIN_BATTERY_PCT


def _selftest() -> int:
    cases = [
        ((0.0, 0.0, 100.0, False), True),
        ((5.0, 0.015, 50.0, False), True),           # exactly on every limit
        ((5.1, 0.0, 100.0, False), False),           # wind
        ((0.0, 0.016, 100.0, False), False),         # waves
        ((0.0, 0.0, 49.9, False), False),            # battery
        ((0.0, 0.0, 100.0, True), False),            # leak
        ((0.0, 0.0, 100.0, None), False),            # leak sensor unknown
        ((0.0, 0.0, 100.0, 0), False),               # not a definite False
        ((float("nan"), 0.0, 100.0, False), False),  # bad input
        ((None, 0.0, 100.0, False), False),
        ((-1.0, 0.0, 100.0, False), False),
        ((0.0, 0.0, 101.0, False), False),
        ((True, 0.0, 100.0, False), False),          # a bool is not a wind speed
    ]
    bad = [(a, want) for a, want in cases if water_ops_allowed(*a) is not want]
    for a, want in bad:
        print(f"FAIL water_ops_allowed{a} != {want}")
    print(f"water_ops_allowed self-test: {len(cases) - len(bad)}/{len(cases)} pass "
          f"(limits ESTIMATE: wind <= {MAX_WIND_M_S} m/s, waves <= {MAX_WAVE_HEIGHT_M * 1000:.0f} mm, battery >= {MIN_BATTERY_PCT:.0f} %)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else 0)
