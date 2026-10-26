"""V20 mini: parts to buy (reference candidates) and the flight-controller port map.

Rows marked "V18 row" reuse the part and link already chosen in bom/bom.csv. Everything is a reference candidate:
buy one lift motor and one prop first and measure them on the repo's thrust stand (firmware/thrust_stand).
"""
from __future__ import annotations

MINI_BOM = [
    {"id": "M01", "item": "Lift motors (4 + 1 spare)", "candidate": "2207 class, 2400-2700 KV, 4S (6-inch freestyle class; compare "
     "published thrust tables, then measure your own)", "qty": 5, "usd": "90-130", "url": "https://www.miniquadtestbench.com/"},
    {"id": "M02", "item": "Lift props, 6-inch 3-blade (2 sets of CW + CCW)", "candidate": "6 x 3-4 x 3 tri-blade, 5 mm bore", "qty": 8,
     "usd": "10-18", "url": "https://www.amazon.com/s?k=6+inch+3+blade+fpv+prop"},
    {"id": "M03", "item": "4-in-1 lift ESC", "candidate": "V18 row P06: Hobbywing XRotor Micro 60A 4-in-1", "qty": 1, "usd": "65-100",
     "url": "https://www.hobbywing.com/en/products/xrotor-micro-60a-4in1-blheli-32-dshot1200117"},
    {"id": "M04", "item": "Cruise EDF, 64 mm", "candidate": "V18 row P07: Freewing E7206 64 mm 4S", "qty": 1, "usd": "60-85",
     "url": "https://www.freewingmodel.com/747.html"},
    {"id": "M05", "item": "EDF ESC", "candidate": "V18 row P08: Hobbywing Skywalker 60A V2", "qty": 1, "usd": "35-45",
     "url": "https://www.hobbywingdirect.com/products/skywalker-esc-60a"},
    {"id": "B01", "item": "Li-ion cells for a 4S2P pack (+ 1 spare)", "candidate": "Molicel P45B 21700, 4.5 Ah, 45 A, about 70 g", "qty": 9,
     "usd": "30-45", "url": "https://www.getfpv.com/batteries/18650-batteries/molicel-p45b-21700-4500mah-45a-3-7v-li-ion-battery-2pcs.html"},
    {"id": "B02", "item": "Pack build: nickel strip rated for 90 A, balance lead, XT90, fish paper, heat-shrink (or a pre-built 4S2P P45B pack)",
     "candidate": "spot-welded, never soldered to the cells", "qty": 1, "usd": "20-40", "url": "https://www.amazon.com/s?k=4s2p+21700+p45b+pack"},
    {"id": "B03", "item": "Li-ion-capable 4S balance charger", "candidate": "V18 row X07 (set to Li-ion, 4.2 V/cell, 4.5 A)", "qty": 0,
     "usd": "-", "url": "https://www.amazon.com/s?k=lipo+balance+charger+4s"},
    {"id": "A01", "item": "Flight controller", "candidate": "V18 row A01: SpeedyBee F405 WING", "qty": 1, "usd": "50-80",
     "url": "https://ardupilot.org/plane/docs/common-speedybeef405wing.html"},
    {"id": "A02", "item": "ELRS receiver", "candidate": "V18 row A03: RadioMaster RP1 V2", "qty": 1, "usd": "19-25",
     "url": "https://radiomasterrc.com/products/rp1-expresslrs-2-4ghz-nano-receiver"},
    {"id": "A03", "item": "GNSS + compass", "candidate": "V18 row A04: M10 GNSS with I2C compass", "qty": 1, "usd": "25-50",
     "url": "https://ardupilot.org/plane/docs/common-positioning-landing-page.html"},
    {"id": "A04", "item": "Airspeed sensor + pitot", "candidate": "V18 row A05: Matek ASPD-4525", "qty": 1, "usd": "35-65",
     "url": "https://www.mateksys.com/?portfolio=aspd-4525"},
    {"id": "A05", "item": "Servos (2 elevons, 2 stabilators, 1 rudders, 2 exit vanes + 1 spare)", "candidate": "5 g digital micro servo, metal gear",
     "qty": 8, "usd": "48-80", "url": "https://www.amazon.com/s?k=5g+digital+metal+gear+micro+servo"},
    {"id": "A06", "item": "Lost-model alarm", "candidate": "V18 row A06: VIFLY Finder 2", "qty": 1, "usd": "10-14",
     "url": "https://www.getfpv.com/vifly-finder-2-drone-buzzer.html"},
    {"id": "V01", "item": "FPV camera, 19 mm (pilot's eye)", "candidate": "V18 row V01: RunCam Phoenix 2", "qty": 1, "usd": "30-40",
     "url": "https://shop.runcam.com/runcam-phoenix-2/"},
    {"id": "V02", "item": "VTX + antenna", "candidate": "V18 row V02", "qty": 1, "usd": "25-45",
     "url": "https://www.runcam.com/download/RunCam-TX200U-US-manual.pdf"},
    {"id": "S01", "item": "Carbon tubes: 6 x 4 mm (main spar + keel), 4 x 2 mm (centre spar), 1 m each", "candidate": "pultruded carbon",
     "qty": 3, "usd": "15-30", "url": "https://www.amazon.com/s?k=carbon+fiber+tube+6mm+4mm+1000mm"},
    {"id": "S02", "item": "Clear PETG sheet 0.5 mm (vacuum-formed canopy; spares)", "candidate": "A4 sheets", "qty": 3, "usd": "8-15",
     "url": "https://www.amazon.com/s?k=petg+sheet+0.5mm+clear"},
    {"id": "S03", "item": "PET film 0.2 mm (EDF thrust tube)", "candidate": "A4 sheets", "qty": 2, "usd": "6-10",
     "url": "https://www.amazon.com/s?k=0.2mm+pet+film+sheet"},
    {"id": "S04", "item": "Landing gear: 1.5 mm music wire, 30 mm foam wheels x3, wheel collars", "candidate": "", "qty": 1, "usd": "10-18",
     "url": "https://www.amazon.com/s?k=30mm+foam+wheels+rc"},
    {"id": "S05", "item": "Pushrods, clevises, horns, pull-pull cable for the rudders", "candidate": "1.2 mm wire set", "qty": 1, "usd": "8-12",
     "url": "https://www.amazon.com/s?k=rc+pushrod+clevis+control+horn+set"},
    {"id": "C01", "item": "Filament: LW-PLA (airframe), PETG (ducts, nozzle, mounts)", "candidate": "V18 row C05", "qty": 1, "usd": "35-55",
     "url": "https://www.amazon.com/s?k=lw-pla+filament"},
]

# SpeedyBee F405 WING (ArduPilot hwdef: PWM timer groups 1-2 | 3-4 | 5-7 | 8-10 | 11-12; UART1 = RC, UART3 = GPS).
# QuadPlane quad X motor numbering: M1 front-right CCW, M2 rear-left CCW, M3 front-left CW, M4 rear-right CW.
PINMAP = [
    {"out": "S1", "function": "33 Motor1", "to": "4-in-1 M1: front-right duct (CCW)", "note": "DShot group 1-2"},
    {"out": "S2", "function": "34 Motor2", "to": "4-in-1 M2: rear-left duct (CCW)", "note": "DShot group 1-2"},
    {"out": "S3", "function": "35 Motor3", "to": "4-in-1 M3: front-left duct (CW)", "note": "DShot group 3-4"},
    {"out": "S4", "function": "36 Motor4", "to": "4-in-1 M4: rear-right duct (CW)", "note": "DShot group 3-4"},
    {"out": "S5", "function": "77 Elevon left", "to": "left elevon servo", "note": "PWM 50 Hz, group 5-7"},
    {"out": "S6", "function": "78 Elevon right", "to": "right elevon servo", "note": "PWM 50 Hz, group 5-7"},
    {"out": "S7", "function": "77 Elevon left", "to": "left stabilator servo", "note": "stabilators mix like elevons (pitch + roll); reverse if needed"},
    {"out": "S8", "function": "78 Elevon right", "to": "right stabilator servo", "note": "group 8-10"},
    {"out": "S9", "function": "21 Rudder", "to": "rudder servo (pull-pull to both rudders)", "note": "group 8-10"},
    {"out": "S10", "function": "94 Script1", "to": "right exit-vane servo (front + rear right ducts)", "note": "group 8-10; needs a vane-mixing Lua script (open item)"},
    {"out": "S11", "function": "70 Throttle", "to": "EDF ESC signal", "note": "group 11-12; full throttle allowed (the 90 A pack covers EDF + lift fans)"},
    {"out": "S12", "function": "95 Script2", "to": "left exit-vane servo (front + rear left ducts)", "note": "group 11-12; same script"},
    {"out": "UART1", "function": "SERIAL1_PROTOCOL 23", "to": "ELRS receiver (CRSF)", "note": "Rx TX -> R1, Rx RX -> T1"},
    {"out": "UART3", "function": "SERIAL3_PROTOCOL 5", "to": "M10 GNSS", "note": "compass on I2C"},
    {"out": "I2C", "function": "ARSPD_TYPE 1", "to": "ASPD-4525 airspeed", "note": "pitot through the nose, 30 mm ahead of the skin"},
]

def params_text(mini: dict) -> str:
    """The bench-only parameter file, with the battery and airspeed lines taken from the sizing (analysis/v20_sizing.json)."""
    b, a = mini["battery"], mini["airspeeds"]
    return f"""# SKYFORGE V20 MINI - BENCH-ONLY PORT MAP for ArduPilot Plane (target SpeedyBeeF405WING)
#
# NOT A FLIGHT TUNE, FAILSAFE PACKAGE, SERVO CALIBRATION OR MODE-SWITCH CONFIG. It assigns ports, the motor
# protocol and the current limits the 4S2P Li-ion pack needs so props-off bring-up can start. Reboot after
# Q_ENABLE, then re-load. Generated by tools/v20/bom.py from analysis/v20_sizing.json.
Q_ENABLE,1
Q_FRAME_CLASS,1
Q_FRAME_TYPE,1
# DShot300 to the 4-in-1 ESC (BLHeli_32)
Q_M_PWM_TYPE,5
SERVO1_FUNCTION,33
SERVO2_FUNCTION,34
SERVO3_FUNCTION,35
SERVO4_FUNCTION,36
SERVO5_FUNCTION,77
SERVO6_FUNCTION,78
SERVO7_FUNCTION,77
SERVO8_FUNCTION,78
SERVO9_FUNCTION,21
# exit vanes: driven by a Lua script (vane angle from forward-speed demand, differential for yaw) - not written
# yet, an open item; with no script the outputs hold their trim (vanes neutral)
SERVO10_FUNCTION,94
SERVO11_FUNCTION,70
SERVO12_FUNCTION,95
SERIAL1_PROTOCOL,23
SERIAL3_PROTOCOL,5
ARSPD_TYPE,1
# --- battery: 4S2P Molicel P45B class ({b['ah']:.0f} Ah, {b['max_a']:.0f} A continuous) ---
BATT_MONITOR,4
BATT_CAPACITY,{b['ah'] * 1000:.0f}
BATT_ARM_VOLT,14.8
BATT_LOW_VOLT,13.2
BATT_CRT_VOLT,12.4
# lift motors back off above this total current (hover ~{mini['hover_a']:.0f} A); the EDF runs to full throttle
Q_M_BAT_CURR_MAX,{0.85 * b['max_a']:.0f}
THR_MAX,100
# --- speeds from the model (calibrate in flight test): wing-borne minimum ~{mini['stall_ms']:.1f} m/s
# (trimmed CL {mini['cl_usable']:.2f} at 14 deg, no vortex lift credited). ArduPlane 4.5+ names; older: ARSPD_FBW_MIN/MAX
AIRSPEED_MIN,{a['AIRSPEED_MIN']}
AIRSPEED_CRUISE,{a['AIRSPEED_CRUISE']}
AIRSPEED_MAX,{a['AIRSPEED_MAX']}
Q_ASSIST_SPEED,{a['Q_ASSIST_SPEED']}
"""
