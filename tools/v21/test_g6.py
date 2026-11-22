#!/usr/bin/env python3
"""V21 G6 off-board tests: the ArduPilot Lua scripts run in a real Lua 5.4 (lupa) against a mock of the ArduPilot
scripting API, plus a cross-check that the on-board gate and tools/v21/water.py agree.

    pip install lupa && python3 tools/v21/test_g6.py

This proves the scripts' logic and that they parse; it does NOT prove the ArduPilot bindings behave as mocked (the
bench test on the SpeedyBee, G7, does that).
"""
from __future__ import annotations

import itertools
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = ROOT / "config" / "ardupilot" / "scripts"
sys.path.insert(0, str(HERE))
import water  # noqa: E402

try:
    from lupa import lua54
except ImportError:                       # pragma: no cover
    sys.exit("test_g6: pip install lupa (Lua 5.4 runtime) to run these tests")


class Vec:
    def __init__(self, *v): self.v = v
    def x(self, *_): return self.v[0]
    def y(self, *_): return self.v[1]
    def length(self, *_): return math.hypot(*self.v)


class World:
    """The mocked aircraft. Methods take a leading self-argument because Lua calls them with ':' (obj:method())."""

    def __init__(self, servo_params=None):
        self.params = {"AIRSPEED_MIN": 15.0, **(servo_params or {})}
        self.tables = {}
        self.text = []
        self.wind = (0.0, 0.0)
        self.gs = 0.0
        self.airspeed = 0.0
        self.batt = 80.0
        self.gpio_level = {}
        self.switch = 0                    # aux switch position 0/1/2 on the water-mode channel
        self.yaw = 0.0
        self.armed = False
        self.vtol = False
        self.assisted = False
        self.mode = 0
        self.flying = False
        self.auth = None                   # (passed?, message)
        self.pwm_out = {}                  # function -> pwm the script set
        self.chan_override = {}            # channel -> pwm
        self.functions = {94: 9, 95: 11, 70: 10}     # function -> 0-based output channel (SERVO10, SERVO12, SERVO11)
        self.edf_pwm = 1000
        self.t = 0
        self.rc_ok = True
        self.volts = {}
        self.adc_pin = None

    def install(self, L):
        g = L.globals()
        w = self
        mk = lambda **kw: L.table(**kw)  # noqa: E731
        g.param = mk(add_table=lambda _s, key, prefix, n: w.tables.setdefault(key, prefix) is not None,
                     add_param=lambda _s, key, idx, name, default: w.params.setdefault(w.tables[key] + name, default) is not None,
                     get=lambda _s, n: w.params.get(n),
                     set=lambda _s, n, v: w.params.__setitem__(n, v) or True)
        g.gcs = mk(send_text=lambda _s, sev, msg: w.text.append((sev, msg)))
        g.ahrs = mk(wind_estimate=lambda _s: Vec(*(w.wind or (0.0, 0.0))), groundspeed_vector=lambda _s: Vec(w.gs, 0.0),
                    airspeed_estimate=lambda _s: w.airspeed,
                    get_wind=lambda _s: Vec(*w.wind) if w.wind is not None else None,
                    airspeed_EAS=lambda _s: w.airspeed)
        adc = mk(set_pin=lambda _s, pin: setattr(w, "adc_pin", pin) or True, voltage_average=lambda _s: w.volts.get(w.adc_pin, 0.0))
        g.analog = mk(channel=lambda _s: adc)
        g.battery = mk(capacity_remaining_pct=lambda _s, i: w.batt)
        g.gpio = mk(pinMode=lambda _s, pin, mode: None, read=lambda _s, pin: bool(w.gpio_level.get(pin, 0)))
        sw = mk(get_aux_switch_pos=lambda _s: w.switch)
        ych = mk(norm_input=lambda _s: w.yaw)
        g.rc = mk(find_channel_for_option=lambda _s, opt: sw if opt == 300 else None,
                  get_channel=lambda _s, n: ych if n == 4 else None,
                  has_valid_input=lambda _s: w.rc_ok)
        g.arming = mk(get_aux_auth_id=lambda _s: 1, is_armed=lambda _s: w.armed,
                      set_aux_auth_passed=lambda _s, i: setattr(w, "auth", (True, "")),
                      set_aux_auth_failed=lambda _s, i, msg: setattr(w, "auth", (False, msg)))
        g.quadplane = mk(in_vtol_mode=lambda _s: w.vtol, in_assisted_flight=lambda _s: w.assisted)
        g.vehicle = mk(set_mode=lambda _s, m: setattr(w, "mode", m) or True, get_likely_flying=lambda _s: w.flying)
        g.SRV_Channels = mk(find_channel=lambda _s, f: w.functions.get(f),
                            set_output_pwm=lambda _s, f, pwm: w.pwm_out.__setitem__(f, pwm),
                            get_output_pwm=lambda _s, f: w.edf_pwm if f == 70 else None,
                            set_output_pwm_chan_timeout=lambda _s, ch, pwm, ms: w.chan_override.__setitem__(ch, pwm))
        g.millis = lambda: mk(toint=lambda _s: w.t)


def load(name: str, world: World):
    L = lua54.LuaRuntime(unpack_returned_tuples=True)
    world.install(L)
    src = (SCRIPTS / name).read_text()
    fn, _ms = L.execute(src)
    return L, fn


def run(fn, world, n=1, dt=200):
    for _ in range(n):
        world.t += dt
        fn, _ms = fn()
    return fn


FAILS: list[str] = []


def check(cond, what):
    print(f"  {'PASS' if cond else 'FAIL'}  {what}")
    if not cond:
        FAILS.append(what)


def test_gate_matches_water_py():
    print("on-board gate == tools/v21/water.py")
    w = World()
    L, _fn = load("ryujin_water.lua", w)
    lua_gate = L.globals().water_ops_allowed
    winds = [None, float("nan"), -1.0, 0.0, 4.9, 5.0, 5.1, 12.0]
    waves = [None, -0.001, 0.0, 0.014, 0.015, 0.016, 0.2]
    batts = [None, -1.0, 0.0, 49.9, 50.0, 100.0, 100.1]
    leaks = [False, True, None]
    n = bad = 0
    for a in itertools.product(winds, waves, batts, leaks):
        n += 1
        ok_lua = lua_gate(*a)[0]
        if bool(ok_lua) != water.water_ops_allowed(*a):
            bad += 1
            if bad < 5:
                print("    differ:", a, ok_lua)
    check(bad == 0, f"{n} input combinations agree ({bad} differ)")
    p = w.params
    check(abs(p["RYW_WIND_MAX"] - water.MAX_WIND_M_S) < 1e-9 and abs(p["RYW_WAVE_MAX"] / 1000 - water.MAX_WAVE_HEIGHT_M) < 1e-9
          and abs(p["RYW_BATT_MIN"] - water.MIN_BATTERY_PCT) < 1e-9, "default thresholds equal water.py's constants")


def test_water_mode():
    print("water mode")
    w = World()
    _L, fn = load("ryujin_water.lua", w)
    fn = run(fn, w)
    check(w.params["RYW_STATE"] == 0 and w.auth == (True, ""), "switch off: state 0, arming allowed")
    w.switch = 2
    fn = run(fn, w)
    check(w.params["RYW_STATE"] == 2 and w.auth[0] is False, "switch on, wave height and leak sensor unknown: NO-GO, arming refused")
    w.params["RYW_WAVE_MM"] = 20
    w.params["RYW_LEAK_PIN"] = 5
    w.wind = (2.0, 1.0)
    fn = run(fn, w)
    check(w.params["RYW_STATE"] == 2 and w.auth[0] is False, "20 mm waves: NO-GO since G9 (limit 15 mm, heel)")
    w.params["RYW_WAVE_MM"] = 10
    fn = run(fn, w)
    check(w.params["RYW_STATE"] == 1 and w.auth == (True, ""), "calm, dry, 80 %: GO, arming allowed")
    w.armed, w.edf_pwm = True, 1900
    fn = run(fn, w)
    check(w.chan_override.get(10) == 1450, "armed taxi: EDF capped to RYW_TAXI_PWM (1450)")
    w.chan_override.clear()
    w.flying = True
    fn = run(fn, w)
    check(10 not in w.chan_override, "water switch on in wing-borne flight: EDF NOT capped")
    w.flying = False
    w.gs, w.airspeed = 0.2, 6.5           # sitting still in a 6.5 m/s breeze the estimator has not caught yet
    fn = run(fn, w)
    check(w.params["RYW_STATE"] == 2, "airspeed while stationary counts as wind: 6.5 m/s -> NO-GO")
    w.gs, w.airspeed = 0.0, 0.0
    w.gpio_level[5] = 1
    w.vtol, w.mode = True, 19
    fn = run(fn, w)
    check(w.mode == 0, "leak while armed on the water in a VTOL mode: put back in MANUAL (no take-off)")
    w.mode, w.flying = 19, True
    fn = run(fn, w)
    check(w.mode == 19, "leak while hovering: mode NOT changed (MANUAL would stop the lift fans), warning only")
    w.flying = False
    check(any(sev == 2 and "LEAK" in m for sev, m in w.text), "leak raises a critical GCS message")
    w.gpio_level[5] = 0
    w.batt = None
    fn = run(fn, w)
    check(w.params["RYW_STATE"] == 2, "battery percentage unavailable: NO-GO")
    w.batt, w.vtol, w.mode, w.edf_pwm = 80.0, False, 0, 1900
    w.params["SERVO11_MIN"] = 1000
    w.rc_ok = False
    w.chan_override.clear()
    fn = run(fn, w)
    check(w.chan_override.get(10) == 1000, "RC lost while taxiing: EDF held at idle (SERVO11_MIN)")
    w.flying = True
    w.chan_override.clear()
    fn = run(fn, w)
    check(10 not in w.chan_override, "RC lost in wing-borne flight: EDF NOT touched (failsafe modes own it)")
    w.flying, w.rc_ok = False, True
    # G9: analog leak sensor with a dry window; faults are NO-GO
    w.params["RYW_LEAK_PIN"], w.params["RYW_LEAK_ANA"] = -1, 15
    for v, want, what in [(3.0, 1, "analog leak sensor dry (3.0 V): GO"), (1.2, 2, "analog leak sensor wet (1.2 V): NO-GO"),
                          (0.0, 2, "analog leak sensor wire broken (0 V): NO-GO"), (3.3, 2, "analog leak sensor shorted to 3.3 V: NO-GO")]:
        w.volts[15] = v
        fn = run(fn, w)
        check(w.params["RYW_STATE"] == want, what)
    w.volts[15] = 3.0
    # G9: no valid EKF wind while taxiing: the reading taken sitting still is held for RYW_WIND_HOLD s
    w.armed = False
    w.wind, w.gs, w.airspeed = None, 0.0, 2.0
    fn = run(fn, w)
    w.gs, w.airspeed = 1.2, 3.0
    fn = run(fn, w, n=5)
    check(w.params["RYW_STATE"] == 1, "EKF wind invalid while taxiing: held still-water reading (2 m/s) keeps GO")
    fn = run(fn, w, n=300)
    check(w.params["RYW_STATE"] == 2, "held wind older than RYW_WIND_HOLD: wind unknown, NO-GO")
    w.gs, w.airspeed, w.wind = 0.0, 0.0, (2.0, 1.0)


def test_vanes():
    print("exit-vane mixer")
    servo = {"SERVO10_MIN": 1000, "SERVO10_TRIM": 1300, "SERVO10_MAX": 1900,
             "SERVO12_MIN": 1000, "SERVO12_TRIM": 1300, "SERVO12_MAX": 1900}
    w = World(servo)
    _L, fn = load("ryujin_vanes.lua", w)
    fn = run(fn, w, dt=20)
    check(w.pwm_out == {94: 1000, 95: 1000}, "fixed-wing: both sides shut (MIN)")
    w.vtol = True
    fn = run(fn, w, dt=20)
    check(w.pwm_out == {94: 1300, 95: 1300}, "hover, no airspeed, no yaw: open straight down (TRIM)")
    w.airspeed = 15.0
    fn = run(fn, w, n=200, dt=20)
    check(w.pwm_out == {94: 1300, 95: 1300}, "pure hover with airspeed: NO aft bias (G8: it fed back on drift)")
    w.assisted = True
    fn = run(fn, w, n=200, dt=20)
    want = 1300 + round(600 * 15 / 30)
    check(w.pwm_out == {94: want, 95: want}, f"assisted / transition at AIRSPEED_MIN: 15 deg aft on both sides ({want})")
    w.yaw = 1.0
    fn = run(fn, w, n=200, dt=20)
    check(w.pwm_out[94] == 1300 + round(600 * 25 / 30) and w.pwm_out[95] == 1300 + round(600 * 5 / 30), "full yaw: 25 / 5 deg")
    w.assisted = False
    w.airspeed, w.yaw = 0.0, -1.0
    fn = run(fn, w, n=200, dt=20)
    check(w.pwm_out == {94: 1300, 95: 1300 + round(600 * 10 / 30)}, "yaw in hover: one side aft, the other clamped at straight down")
    w.params["RYW_STATE"] = 1
    w.vtol = False
    fn = run(fn, w, dt=20)
    check(w.pwm_out == {94: 1000, 95: 1000}, "MANUAL water-taxi: shut (spray out of the fans)")
    w.vtol = True
    fn = run(fn, w, dt=20)
    check(w.pwm_out[94] >= 1300 and w.pwm_out[95] >= 1300, "QHOVER on the water (water take-off): open")
    w.params["RYW_STATE"] = 0
    w.vtol = False
    fn = run(fn, w, dt=20)
    w.vtol = w.assisted = True
    w.airspeed, w.yaw = 15.0, 0.0
    fn = run(fn, w, n=1, dt=20)
    before = w.pwm_out[94]
    check(before < want, f"slew-limited: one 20 ms step from shut does not jump to {want} ({before})")


def test_param_file():
    print("bench param file")
    txt = (ROOT / "config" / "ardupilot" / "ryujin_v21_mini_BENCH_ONLY.param").read_text()
    kv = dict(re.findall(r"^([A-Z0-9_]+),([-0-9.]+)", txt, re.M))
    check(kv.get("SERVO10_FUNCTION") == "94" and kv.get("SERVO12_FUNCTION") == "95", "vane outputs are Script1 / Script2")
    check(kv.get("SCR_ENABLE") == "1", "scripting enabled")
    check(any(k.startswith("RC") and k.endswith("_OPTION") and v == "300" for k, v in kv.items()), "a water-mode switch (RCx_OPTION 300)")
    check("BENCH" in txt.splitlines()[0], "header says BENCH ONLY")


if __name__ == "__main__":
    test_gate_matches_water_py()
    test_water_mode()
    test_vanes()
    test_param_file()
    print(f"G6 tests: {len(FAILS)} FAIL")
    sys.exit(1 if FAILS else 0)
