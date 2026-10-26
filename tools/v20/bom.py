"""V20 mini: parts to buy (reference candidates) and the flight-controller port map.

Rows marked "V18 row" reuse the part and link already chosen in bom/bom.csv. Everything is a reference candidate:
buy one lift motor and one prop first and measure them on the repo's thrust stand (firmware/thrust_stand).
"""
from __future__ import annotations

MINI_BOM = [
    {"id": "M01", "item": "Lift motors (4 + 1 spare)", "candidate": "2207 class, 1900-2100 KV, 4S (6-inch long-range quad motors); "
     "measure one with its prop in a printed duct on the thrust stand first: the sizing assumes 0.95 kg", "qty": 5, "usd": "90-130",
     "url": "https://www.miniquadtestbench.com/low-kv/"},
    {"id": "M02", "item": "Lift props, 6-inch 3-blade (2 sets of CW + CCW)", "candidate": "HQProp 6x3x3 / 6x4x3 or similar, 5 mm bore", "qty": 8,
     "usd": "10-18", "url": "https://www.amazon.com/s?k=hqprop+6x3x3"},
    {"id": "M03", "item": "4-in-1 lift ESC", "candidate": "V18 row P06: Hobbywing XRotor Micro 60A 4-in-1", "qty": 1, "usd": "65-100",
     "url": "https://www.hobbywing.com/en/products/xrotor-micro-60a-4in1-blheli-32-dshot1200117"},
    {"id": "M04", "item": "Cruise EDF, 64 mm", "candidate": "V18 row P07: Freewing E7206 64 mm 4S", "qty": 1, "usd": "60-85",
     "url": "https://www.freewingmodel.com/747.html"},
    {"id": "M05", "item": "EDF ESC", "candidate": "V18 row P08: Hobbywing Skywalker 60A V2", "qty": 1, "usd": "35-45",
     "url": "https://www.hobbywingdirect.com/products/skywalker-esc-60a"},
    {"id": "B01", "item": "Li-ion cells for a 4S3P pack (+ 1 spare)", "candidate": "Molicel P45B 21700, 4.5 Ah, 45 A, about 70 g", "qty": 13,
     "usd": "45-70", "url": "https://www.getfpv.com/batteries/18650-batteries/molicel-p45b-21700-4500mah-45a-3-7v-li-ion-battery-2pcs.html"},
    {"id": "B02", "item": "Pack build: nickel strip rated for 135 A, balance lead, XT90, fish paper, heat-shrink (or a pre-built 4S3P P45B pack)",
     "candidate": "spot-welded, never soldered to the cells; two 3 x 2 blocks end to end, 141 x 65 x 43 mm", "qty": 1, "usd": "20-45",
     "url": "https://www.amazon.com/s?k=4s3p+21700+p45b+pack"},
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
    {"id": "A05", "item": "Servos (2 elevons, 2 ruddervators, 2 bottom louvres, 1 payload port + 1 spare)", "candidate": "5 g digital micro servo, metal gear",
     "qty": 8, "usd": "48-80", "url": "https://www.amazon.com/s?k=5g+digital+metal+gear+micro+servo"},
    {"id": "A06", "item": "Lost-model alarm", "candidate": "V18 row A06: VIFLY Finder 2", "qty": 1, "usd": "10-14",
     "url": "https://www.getfpv.com/vifly-finder-2-drone-buzzer.html"},
    {"id": "V01", "item": "FPV camera, 19 mm (pilot's eye)", "candidate": "V18 row V01: RunCam Phoenix 2", "qty": 1, "usd": "30-40",
     "url": "https://shop.runcam.com/runcam-phoenix-2/"},
    {"id": "V02", "item": "VTX + antenna", "candidate": "V18 row V02", "qty": 1, "usd": "25-45",
     "url": "https://www.runcam.com/download/RunCam-TX200U-US-manual.pdf"},
    {"id": "S01", "item": "Carbon tubes: 6 x 4 mm (main spar), 4 x 2 mm (centre spar), 1 m each; 2 mm rod (ruddervator pivots)",
     "candidate": "pultruded carbon", "qty": 3, "usd": "15-30", "url": "https://www.amazon.com/s?k=carbon+fiber+tube+6mm+4mm+1000mm"},
    {"id": "S02", "item": "Clear PETG sheet 0.5 mm (vacuum-formed canopy; spares)", "candidate": "A4 sheets", "qty": 3, "usd": "8-15",
     "url": "https://www.amazon.com/s?k=petg+sheet+0.5mm+clear"},
    {"id": "S06", "item": "Depron 3 mm sheet (the two ruddervators; template in cad/v20/mini/foam)",
     "candidate": "Depron or EPP-free foamboard of similar density", "qty": 1, "usd": "10-18", "url": "https://www.amazon.com/s?k=depron+3mm+sheet"},
    {"id": "S07", "item": "Louvre hinges: 0.8 mm music wire, thin elastic thread (top louvres close by elastic, open by fan suction)",
     "candidate": "", "qty": 1, "usd": "5-8", "url": "https://www.amazon.com/s?k=0.8mm+music+wire"},
    {"id": "S03", "item": "PET film 0.2 mm (EDF thrust tube, intake ducts)", "candidate": "A4 sheets", "qty": 3, "usd": "6-10",
     "url": "https://www.amazon.com/s?k=0.2mm+pet+film+sheet"},
    {"id": "S04", "item": "Landing gear: 1.5 mm music wire, 30 mm foam wheels x3, wheel collars", "candidate": "", "qty": 1, "usd": "10-18",
     "url": "https://www.amazon.com/s?k=30mm+foam+wheels+rc"},
    {"id": "S05", "item": "Pushrods, clevises, horns (elevons, ruddervators, louvres, bay doors)", "candidate": "1.2 mm wire set", "qty": 1, "usd": "8-12",
     "url": "https://www.amazon.com/s?k=rc+pushrod+clevis+control+horn+set"},
    {"id": "C01", "item": "Filament: LW-PLA (airframe), PETG (ducts, nozzle, mounts, stand)", "candidate": "V18 row C05", "qty": 1, "usd": "35-55",
     "url": "https://www.amazon.com/s?k=lw-pla+filament"},
]

# Payload modules: each one sits in the belly bay at the CG (90 x 54 x 18 mm inside), plugs into the payload port (S9)
# and stays within the payload limit from the sizing (lift thrust/weight >= 1.7 with it on board).
PAYLOAD_MODULES = [
    {"id": "P01", "module": "Camera (default)", "what": "4K action camera on a tilt cradle behind a window door; S9 = 7 Mount tilt",
     "candidate": "RunCam Thumb 2 class (about 10 g) + 5 g servo", "grams": 25, "use": "filming, inspection of roofs, masts and solar panels"},
    {"id": "P02", "module": "Mapping", "what": "the same camera fixed looking straight down, triggered by distance (CAM_TRIGG_DIST)",
     "candidate": "RunCam Thumb 2 class + printed nadir mount", "grams": 20, "use": "photogrammetry maps and 3D models of a site"},
    {"id": "P03", "module": "Drop / release", "what": "the bay doors open on S9 (28 Gripper) and let a small package fall",
     "candidate": "printed hook + 5 g servo", "grams": 15, "use": "drop a line, a sample bag, a tracker or a marker; carry up to the payload limit"},
    {"id": "P04", "module": "Sensor", "what": "downward rangefinder + air-quality / weather sensor on I2C",
     "candidate": "Benewake TF-Luna (5 g) + Bosch BME688 breakout (2 g)", "grams": 15,
     "use": "precision landing, terrain following, air sampling; a weather station while perched"},
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
    {"out": "S7", "function": "79 VTail left", "to": "left ruddervator servo (in the spine)", "note": "pitch together, yaw apart; reverse if needed"},
    {"out": "S8", "function": "80 VTail right", "to": "right ruddervator servo (in the spine)", "note": "group 8-10"},
    {"out": "S9", "function": "28 Gripper (or 7 Mount tilt)", "to": "payload port in the bay: door / release servo, or the camera's tilt servo",
     "note": "group 8-10; set per module: 28 for the drop and bay-door modules, 7 for the camera module"},
    {"out": "S10", "function": "94 Script1", "to": "right bottom-louvre servo (front + rear right ducts)", "note": "group 8-10; open in VTOL, shut in cruise, vectored aft in transition - needs a Lua script (open item)"},
    {"out": "S11", "function": "70 Throttle", "to": "EDF ESC signal", "note": "group 11-12; full throttle allowed (the 90 A pack covers EDF + lift fans)"},
    {"out": "S12", "function": "95 Script2", "to": "left bottom-louvre servo (front + rear left ducts)", "note": "group 11-12; same script"},
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
# protocol and the current limits the 4S3P Li-ion pack needs so props-off bring-up can start. Reboot after
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
SERVO7_FUNCTION,79
SERVO8_FUNCTION,80
# payload port: 28 Gripper for the drop / bay-door modules, 7 Mount tilt for the camera module
SERVO9_FUNCTION,28
# bottom louvres / exit vanes: driven by a Lua script (open in VTOL modes, shut in fixed-wing modes, angled aft by the
# forward-speed demand in transition, differential for yaw) - not written yet, an open item; with no script the
# outputs hold their trim - set the trim to OPEN before any hover test
SERVO10_FUNCTION,94
SERVO11_FUNCTION,70
SERVO12_FUNCTION,95
SERIAL1_PROTOCOL,23
SERIAL3_PROTOCOL,5
ARSPD_TYPE,1
# --- battery: 4S3P Molicel P45B class ({b['ah']:.0f} Ah, {b['max_a']:.0f} A continuous) ---
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
