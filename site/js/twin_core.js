// Ryujin V21 mini digital twin: the flight, float and control model (no DOM, so Node can test it).
//
// A TEACHING MODEL, NOT ARDUPILOT. It runs a 6-DOF rigid body (four lift fans, the cruise EDF, a wing, a hull that
// floats) under a control stack with the same STRUCTURE as ArduPilot QuadPlane and the same parameter NAMES and
// VALUES as config/ardupilot/ryujin_v21_mini_BENCH_ONLY.param, so you can watch what each protection does before the
// bench. Every aerodynamic, hydrodynamic and inertia number below is an ESTIMATE; G7 measures the real ones.
//
// Frames: earth NED (x north, y east, z down, water surface at z = 0); body FRD (x forward, y right, z down).
// Angles in radians inside, degrees at the edges (params, traces).

const D2R = Math.PI / 180;
const R2D = 180 / Math.PI;
const G = 9.81;
const RHO = 1.225;
const RHO_W = 1000;
export const DT = 0.0025;                 // 400 Hz, the QuadPlane attitude loop rate on an F405
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const sgn = (x) => (x > 0 ? 1 : x < 0 ? -1 : 0);
const wrapPi = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const lerpTable = (tab, x) => {
  if (x <= tab[0][0]) return tab[0][1];
  for (let i = 1; i < tab.length; i += 1) if (x <= tab[i][0]) { const [x0, y0] = tab[i - 1]; const [x1, y1] = tab[i]; return y0 + ((y1 - y0) * (x - x0)) / (x1 - x0); }
  return tab[tab.length - 1][1];
};

// ---------------------------------------------------------------------------------------------------------------
// Control-theory building blocks (each is the textbook form of what the named ArduPilot parameter configures)

// Square-root controller, the same form as ArduPilot's sqrt_controller (AP_Math/control.cpp): a P controller near the
// target that turns into the minimum-time, acceleration-limited profile further away, so a large error never
// demands more deceleration than accel_max can provide. Used by input shaping (Q_A_INPUT_TC, Q_A_ACC_*_MAX).
export function sqrtController(error, p, accelMax, dt) {
  let out;
  if (accelMax <= 0) out = error * p;
  else if (p === 0) out = sgn(error) * Math.sqrt(2 * accelMax * Math.abs(error));
  else {
    const lin = accelMax / (p * p);
    if (error > lin) out = Math.sqrt(2 * accelMax * (error - lin / 2));
    else if (error < -lin) out = -Math.sqrt(2 * accelMax * (-error - lin / 2));
    else out = error * p;
  }
  return dt > 0 ? clamp(out, -Math.abs(error) / dt, Math.abs(error) / dt) : out;
}

// One axis of input shaping: the pilot's angle request becomes a smooth, rate- and acceleration-limited target.
// tc = Q_A_INPUT_TC (s), rateMax = Q_A_RATE_x_MAX (rad/s), accMax = Q_A_ACC_x_MAX (rad/s/s). tc = 0 means no shaping.
export class AngleShaper {
  constructor() { this.angle = 0; this.rate = 0; }
  reset(a) { this.angle = a; this.rate = 0; }
  step(request, { tc, rateMax, accMax }, dt) {
    if (!(tc > 0)) { this.rate = (request - this.angle) / dt; this.angle = request; return this; }
    let want = sqrtController(request - this.angle, 1 / tc, accMax, dt);
    if (rateMax > 0) want = clamp(want, -rateMax, rateMax);
    this.rate = accMax > 0 ? this.rate + clamp(want - this.rate, -accMax * dt, accMax * dt) : want;
    this.angle += this.rate * dt;
    return this;
  }
}

// First-order low-pass, y' = (x - y) / tc. Q_PLT_Y_RATE_TC uses it on the yaw-rate request.
export const lowPass = (y, x, tc, dt) => (tc > 0 ? y + ((x - y) * dt) / (tc + dt) : x);

// Slew limiter: |dy/dt| <= rate. THR_SLEWRATE (%/s) uses it on the EDF throttle.
export const slew = (y, x, rate, dt) => (rate > 0 ? y + clamp(x - y, -rate * dt, rate * dt) : x);

// PID with a filtered derivative and a clamped integrator (anti-windup: the integrator cannot store more than
// imax of output, and stops integrating while the output saturates in the same direction).
export class PID {
  constructor(kp, ki, kd, imax, dFilterHz = 20) { Object.assign(this, { kp, ki, kd, imax, dFilterHz }); this.reset(); }
  reset() { this.i = 0; this.prev = null; this.d = 0; }
  step(err, dt, saturated = 0) {
    if (!(saturated && sgn(err) === sgn(saturated))) this.i = clamp(this.i + this.ki * err * dt, -this.imax, this.imax);
    const raw = this.prev === null ? 0 : (err - this.prev) / dt;
    this.prev = err;
    const a = dt / (dt + 1 / (2 * Math.PI * this.dFilterHz));
    this.d += a * (raw - this.d);
    return this.kp * err + this.i + this.kd * this.d;
  }
}

// Seeded random numbers, so every demo and every test is repeatable.
export function rng(seed) {
  let s = seed >>> 0;
  return () => { s = (s + 0x6D2B79F5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// The water go/no-go gate: the same rules as tools/v21/water.py and ryujin_water.lua (anything unknown is NO-GO).
export function waterOpsAllowed(windMs, waveM, batteryPct, leak, gate) {
  const fin = (x) => typeof x === 'number' && Number.isFinite(x);
  if (leak !== false) return [false, 'leak sensor not reading dry'];
  if (!(fin(windMs) && fin(waveM) && fin(batteryPct))) return [false, 'input unknown'];
  if (windMs < 0 || waveM < 0 || batteryPct < 0 || batteryPct > 100) return [false, 'input out of range'];
  if (windMs > gate.wind_max_m_s) return [false, `wind ${windMs.toFixed(1)} m/s`];
  if (waveM > gate.wave_max_m) return [false, `waves ${Math.round(waveM * 1000)} mm`];
  if (batteryPct < gate.battery_min_pct) return [false, `battery ${Math.round(batteryPct)} %`];
  return [true, 'GO'];
}

// Stall prevention: the bank limit that keeps the load factor 1/cos(bank) within what the wing can give at this
// airspeed, (V / AIRSPEED_MIN)^2, never below 25 deg. The form of ArduPlane's STALL_PREVENTION roll limit.
export function stallBankLimitDeg(airspeed, aspdMin, rollLimitDeg) {
  const lf = airspeed / Math.max(aspdMin, 1);
  if (lf <= 1) return Math.min(rollLimitDeg, 25);
  const allowed = Math.acos(clamp(1 / (lf * lf), -1, 1)) * R2D;
  return Math.min(rollLimitDeg, Math.max(25, allowed));
}

// ---------------------------------------------------------------------------------------------------------------
// Quaternion helpers (w, x, y, z), body -> earth

const qMul = (a, b) => [a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3], a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
  a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1], a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0]];
const qNorm = (q) => { const n = Math.hypot(...q); return q.map((v) => v / n); };
function qRot(q, v) { const p = qMul(qMul(q, [0, ...v]), [q[0], -q[1], -q[2], -q[3]]); return [p[1], p[2], p[3]]; }
const qRotInv = (q, v) => qRot([q[0], -q[1], -q[2], -q[3]], v);
export function qFromEuler(r, p, y) {
  const [cr, sr, cp, sp, cy, sy] = [Math.cos(r / 2), Math.sin(r / 2), Math.cos(p / 2), Math.sin(p / 2), Math.cos(y / 2), Math.sin(y / 2)];
  return [cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy];
}
export function eulerOf(q) {
  const [w, x, y, z] = q;
  return [Math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)), Math.asin(clamp(2 * (w * y - z * x), -1, 1)), Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))];
}

// ---------------------------------------------------------------------------------------------------------------
// The airframe (ESTIMATE everywhere except where it says G5)

export function airframe(d) {
  const m = d.mass_kg;                                            // G5
  const tMax = (d.tw_lift * m * G) / 4;                           // G5 thrust/weight, per fan
  // level stall speed: the G5 sizing's (AIRSPEED_MIN = ceil(1.35 x stall), Q_ASSIST_SPEED = ceil(1.2 x stall)); older data
  // without it falls back to the same 1.35 rule. G9: this was AIRSPEED_MIN / 1.2, 17 % above the sizing's stall.
  const vs = d.stall_ms || d.airspeeds.AIRSPEED_MIN / 1.35;
  const S = 0.18;                                                 // m², wing reference area (ESTIMATE)
  const CL0 = 0.2;
  const CLmax = (2 * m * G) / (RHO * vs * vs * S);
  const CLa = 4.5;
  const sm = d.static_margin_pct / 100;                           // G5 static margin
  const yawDir = { front_R: 1, rear_L: 1, front_L: -1, rear_R: -1 };
  return {
    m, tMax, S, b: 1.0, c: 0.18, CL0, CLa, CLmax, alphaStall: (CLmax - CL0) / CLa, CD0: 0.04, kInd: 0.06,
    Cm0: 0.03, Cma: -CLa * sm, Cmq: -8, Cmde: 0.8, Clda: 0.25, Clp: -0.45, Cnb: 0.06, Cnr: -0.12, Cndr: 0.06, CYb: -0.5,
    I: [0.032, 0.045, 0.072],                                     // kg m², roll / pitch / yaw (ESTIMATE from the mass layout)
    fans: d.fans.map((f) => ({ ...f, dir: yawDir[f.name] ?? 1 })),
    kq: 0.016,                                                    // m, fan reaction torque per newton of thrust
    fanTau: 0.04, edfTau: 0.15,                                   // s, motor spin-up lags
    edfMax: 1.2 * G,                                              // N static (the V21 1.20 kg EDF assumption; W1 measures it)
    edfVzero: 40,                                                 // m/s, thrust falls linearly to zero here
    cdA: [0.012, 0.06, 0.22],                                     // m², body-axis bluff-body drag at low speed
    hoverW: d.hover_w, battMah: d.battery_mah,
    // the hull and floats (G5 waterline, trim, GZ curve; the rest ESTIMATE)
    hullBottom: d.float.waterline_below_cg_m + 0.055,            // m below the CG; 55 mm draft at rest
    draft0: 0.055,
    trim: d.float.trim_deg * D2R,
    reserve: 1 + d.float.reserve_pct / 100,
    gz: [...d.float.gz_mm, [90, 0]].map(([deg, mm]) => [deg * D2R, mm / 1000]),
    gmL: 0.45,                                                    // m, longitudinal metacentric height (long hull, stiff in pitch)
    wetHeel: d.float.fan_exit_wet_heel_deg * D2R,
    freeboard: Math.min(...Object.values(d.float.freeboard_mm)) / 1000,
    hullDrag: [[0, 0], [1, 0.6], [1.5, 2.53], [2, 10.1], [4, 14], [8, 12]], // N vs m/s (G5 to 2 m/s; planing beyond is a guess)
    sideDrag: 9,                                                  // N/(m/s)², the V-belly and floats as a keel
  };
}

// ---------------------------------------------------------------------------------------------------------------
// The two parameter sets the twin compares

// "Protections on": the bench param file. "Protections off": a teaching what-if, a vehicle with none of the above
// (direct stick-to-angle, no rate or acceleration limits, direct throttle, no assist, fence, failsafes or water gate).
// ArduPilot itself cannot be configured this bare; the point is to see what each layer is doing.
export function protections(p, on) {
  const A = p;
  if (on) {
    return {
      on: true,
      tc: A.Q_A_INPUT_TC, rateMax: [A.Q_A_RATE_R_MAX * D2R, A.Q_A_RATE_P_MAX * D2R, A.Q_A_RATE_Y_MAX * D2R],
      accMax: [A.Q_A_ACC_R_MAX * D2R, A.Q_A_ACC_P_MAX * D2R, A.Q_A_ACC_Y_MAX * D2R],
      angleMax: A.Q_A_ANGLE_MAX * D2R, posAngleMax: A.Q_P_ANGLE_MAX * D2R,
      yawRate: A.Q_PLT_Y_RATE * D2R, yawTc: A.Q_PLT_Y_RATE_TC,
      spdUp: A.Q_PILOT_SPD_UP, spdDn: A.Q_PILOT_SPD_DN || A.Q_PILOT_SPD_UP, accZ: A.Q_PILOT_ACCEL_Z,
      rollLimit: A.ROLL_LIMIT_DEG, pitchMax: A.PTCH_LIM_MAX_DEG, pitchMin: A.PTCH_LIM_MIN_DEG, stallPrevention: A.STALL_PREVENTION === 1,
      thrSlew: A.THR_SLEWRATE,
      assistSpeed: A.Q_ASSIST_SPEED, assistAngle: A.Q_ASSIST_ANGLE, assistAlt: A.Q_ASSIST_ALT, assistDelay: A.Q_ASSIST_DELAY,
      transFail: A.Q_TRANS_FAIL, transMs: A.Q_TRANSITION_MS || 5000,
      fence: A.FENCE_ENABLE === 1, fenceAlt: A.FENCE_ALT_MAX, fenceRadius: A.FENCE_RADIUS, fenceMargin: A.FENCE_MARGIN,
      rcFailsafe: A.THR_FAILSAFE === 1, battLowMah: A.BATT_LOW_MAH, battCrtMah: A.BATT_CRT_MAH,
      waterGate: true,
    };
  }
  return {
    on: false, tc: 0, rateMax: [0, 0, 0], accMax: [0, 0, 0], angleMax: 60 * D2R, posAngleMax: 60 * D2R, yawRate: 200 * D2R, yawTc: 0,
    spdUp: 0, spdDn: 0, accZ: 0, rollLimit: 80, pitchMax: 60, pitchMin: -60, stallPrevention: false, thrSlew: 0,
    assistSpeed: 0, assistAngle: 0, assistAlt: 0, assistDelay: 0, transFail: 0, transMs: A.Q_TRANSITION_MS || 5000,
    fence: false, rcFailsafe: false, battLowMah: 0, battCrtMah: 0, waterGate: false,
  };
}

export const MODES = { MANUAL: 'MANUAL', FBWA: 'FBWA', CIRCLE: 'CIRCLE', RTL: 'RTL', QHOVER: 'QHOVER', QLAND: 'QLAND', QRTL: 'QRTL' };
const VTOL = new Set(['QHOVER', 'QLAND', 'QRTL']);

// ---------------------------------------------------------------------------------------------------------------
// The twin

export class Twin {
  constructor(data, { protect = true, seed = 1 } = {}) {
    this.data = data;
    this.af = airframe(data);
    this.params = data.params;
    this.P = protections(data.params, protect);
    this.rand = rng(seed);
    this.t = 0;
    // environment: wind (m/s from the north/east, earth frame), gusts (m/s rms), waves (m crest to trough)
    this.env = { wind: [0, 0], gust: 0, wave: 0, waveKnown: true, leak: false, rcOk: true, waterSwitch: false };
    this.gustState = [0, 0, 0];
    this.events = [];
    this.reset();
  }

  reset({ onWater = true, alt = 0, airspeed = 0, mode = 'MANUAL', batteryPct = 90 } = {}) {
    const af = this.af;
    const z = onWater ? -(af.hullBottom - af.draft0) : -alt;
    this.pos = [0, 0, z];
    this.vel = [airspeed, 0, 0];
    this.q = qFromEuler(0, onWater ? af.trim : (airspeed > 0 ? 5 * D2R : 0), 0);
    this.w = [0, 0, 0];
    this.fanT = af.fans.map(() => (onWater ? 0 : (af.m * G) / 4));
    if (airspeed > 0 && !onWater) this.fanT = this.fanT.map(() => 0);
    this.edf = airspeed > 0 ? 0.55 : 0;                       // about 0.3 of static thrust (thrust ~ throttle^2)
    this.edfCmd = this.edf;
    this.thrOut = this.edf;
    this.armed = !onWater || mode !== 'MANUAL';
    this.mode = mode;
    this.mah = this.af.battMah * (1 - batteryPct / 100);
    this.home = [0, 0];
    this.shapers = [new AngleShaper(), new AngleShaper(), new AngleShaper()];
    const e = eulerOf(this.q);
    this.shapers.forEach((s, i) => s.reset(e[i]));
    this.yawRateT = 0;
    this.climbT = 0;
    this.pid = { r: new PID(9, 6, 0.25, 4), p: new PID(9, 6, 0.25, 4), y: new PID(5, 2, 0, 2), z: new PID(3.5, 1.2, 0, 4), fwR: new PID(3, 0.6, 0, 0.3), fwP: new PID(3, 0.6, 0, 0.3) };
    this.vane = [0, 0];
    this.surf = [0, 0, 0];                       // aileron, elevator, rudder, -1..1
    this.assist = 0;
    this.assistTimer = 0;
    this.trans = null;                           // forward transition state
    this.rcLostAt = null;
    this.waterState = 0;
    this.fsDone = { low: false, crt: false, fence: false };
    this.flags = { stalled: false, fanExitWet: false, sprayZone: false, capsized: false, crashed: false };
    this.cmd = { roll: 0, pitch: 0, yaw: 0, thr: onWater ? 0 : 0.5 };
    this.dbg = { tgt: [0, 0, 0], req: [0, 0, 0], climbReq: 0 };
    this.prevMode = mode;
  }

  log(msg, sev = 'info') {
    const last = this.events[this.events.length - 1];
    if (last && last.msg === msg && this.t - last.t < 3) return;
    this.events.push({ t: +this.t.toFixed(2), msg, sev });
  }

  get euler() { return eulerOf(this.q); }
  get alt() { return -this.pos[2]; }
  get batteryPct() { return clamp(100 * (1 - this.mah / this.af.battMah), 0, 100); }
  get waterline() { return this.waveAt(this.pos[0], this.t); }
  waveAt(x, t) { return this.env.wave > 0 ? (this.env.wave / 2) * Math.sin(2 * Math.PI * (x / 1.2 - t / 0.85)) : 0; }
  immersion() { return this.pos[2] + this.af.hullBottom - this.waterline; }   // m of hull below the surface (> 0 = in the water)
  onWater() { return this.immersion() > -0.005; }
  likelyFlying() { return !this.onWater() && (this.alt > 0.3 || Math.hypot(...this.vel) > 3); }
  airVel() { const g = this.gustState; return [this.vel[0] - this.env.wind[0] - g[0], this.vel[1] - this.env.wind[1] - g[1], this.vel[2] - g[2]]; }
  airspeed() { return Math.hypot(...this.airVel()); }
  windAtAircraft() { return Math.hypot(this.env.wind[0], this.env.wind[1]); }

  // the water gate, as the Lua script evaluates it (wave height is the pilot's entry; unknown = NO-GO)
  gate() {
    const wave = this.env.waveKnown ? this.env.wave : undefined;
    return waterOpsAllowed(this.windAtAircraft(), wave, this.batteryPct, this.env.leak, this.data.water_gate);
  }

  // pilot actions that ArduPilot can refuse
  arm() {
    if (this.armed) return true;
    if (this.P.waterGate && this.env.waterSwitch) {
      const [ok, why] = this.gate();
      if (!ok) { this.log(`Arming refused: water NO-GO (${why})`, 'warn'); return false; }
    }
    this.armed = true;
    this.log('Armed');
    return true;
  }

  setMode(mode, why = '') {
    if (mode === this.mode) return;
    if (VTOL.has(mode) && this.P.waterGate && this.env.waterSwitch && this.onWater() && !this.likelyFlying()) {
      const [ok, r] = this.gate();
      if (!ok) { this.log(`${mode} refused on the water: NO-GO (${r}), back to MANUAL`, 'warn'); this.mode = 'MANUAL'; return; }
    }
    const wasVtol = VTOL.has(this.mode);
    this.mode = mode;
    if (mode === 'FBWA' && wasVtol) this.trans = { t0: this.t, blendFrom: null };
    if (VTOL.has(mode)) { this.trans = null; const e = this.euler; this.shapers[2].reset(e[2]); this.climbT = this.vel[2] * -1; }
    this.log(`Mode ${mode}${why ? ` (${why})` : ''}`, why ? 'warn' : 'info');
  }

  // ------------------------------------------------------------------------------------------------------------
  step(cmd) {
    if (cmd) this.cmd = cmd;
    const dt = DT;
    this.t += dt;
    this.supervise(dt);
    const out = this.control(dt);
    this.physics(out, dt);
  }

  run(seconds, cmdFn) {
    const n = Math.round(seconds / DT);
    for (let i = 0; i < n; i += 1) this.step(cmdFn ? cmdFn(this.t, this) : undefined);
  }

  // failsafes, fence, assist and transition timers: the "aircraft protects itself" layer
  supervise(dt) {
    const P = this.P;
    const flying = this.likelyFlying();
    // RC loss
    if (!this.env.rcOk) {
      if (this.rcLostAt === null) this.rcLostAt = this.t;
      const lost = this.t - this.rcLostAt;
      if (P.rcFailsafe && this.armed) {
        if (!flying && this.onWater() && this.mode === 'MANUAL') { /* the Lua guard idles the EDF, see control() */ }
        else if (VTOL.has(this.mode)) { if (this.mode !== 'QLAND' && lost > 1.5) this.setMode('QLAND', 'RC lost'); }
        else if (lost > 20 && this.mode !== 'RTL') this.setMode('RTL', 'RC lost, long');
        else if (lost > 1.5 && this.mode !== 'CIRCLE' && this.mode !== 'RTL') this.setMode('CIRCLE', 'RC lost, short');
      }
    } else this.rcLostAt = null;
    // battery
    if (P.battLowMah && this.armed && flying) {
      const left = this.af.battMah - this.mah;
      if (!this.fsDone.crt && left <= P.battCrtMah) { this.fsDone.crt = true; this.setMode('QLAND', 'battery critical'); }
      else if (!this.fsDone.low && left <= P.battLowMah) { this.fsDone.low = true; this.setMode(VTOL.has(this.mode) ? 'QRTL' : 'RTL', 'battery low'); }
    }
    // fence: max altitude and circle around home, with the margin
    if (P.fence && this.armed && flying && !this.fsDone.fence) {
      const dist = Math.hypot(this.pos[0] - this.home[0], this.pos[1] - this.home[1]);
      if (this.alt > P.fenceAlt - P.fenceMargin || dist > P.fenceRadius - P.fenceMargin) {
        this.fsDone.fence = true;
        this.setMode(VTOL.has(this.mode) ? 'QRTL' : 'RTL', this.alt > P.fenceAlt - P.fenceMargin ? 'fence: altitude' : 'fence: radius');
      }
    }
    if (this.fsDone.fence && this.mode !== 'RTL' && this.mode !== 'QRTL') this.fsDone.fence = this.likelyFlying() && this.mode === 'QLAND';
    // RTL turns into QRTL near home (Q_RTL_MODE 1)
    if (this.mode === 'RTL' && Math.hypot(this.pos[0] - this.home[0], this.pos[1] - this.home[1]) < 40) this.setMode('QRTL', 'near home');
    // forward transition: fans hold the aircraft up until AIRSPEED_MIN, then fade out over Q_TRANSITION_MS
    if (this.trans) {
      const as = this.airspeed();
      if (this.trans.blendFrom === null && as >= this.params.AIRSPEED_MIN) { this.trans.blendFrom = this.t; this.log('Transition: AIRSPEED_MIN reached, fans fading out'); }
      if (this.trans.blendFrom !== null && this.t - this.trans.blendFrom > P.transMs / 1000) { this.trans = null; this.log('Transition complete'); }
      else if (P.transFail > 0 && this.trans.blendFrom === null && this.t - this.trans.t0 > P.transFail) { this.trans = null; this.setMode('QRTL', 'transition failed'); }
    }
    // assist in fixed-wing flight: slow, upset, or low, for Q_ASSIST_DELAY -> the lift fans help
    if (!VTOL.has(this.mode) && this.mode !== 'MANUAL' && !this.trans && flying && P.assistSpeed > 0) {
      const e = this.euler;
      const tgt = this.dbg.tgt;
      const angErr = Math.max(Math.abs(wrapPi(tgt[0] - e[0])), Math.abs(wrapPi(tgt[1] - e[1]))) * R2D;
      const need = this.airspeed() < P.assistSpeed || angErr > P.assistAngle || (P.assistAlt > 0 && this.alt < P.assistAlt);
      this.assistTimer = need ? this.assistTimer + dt : 0;
      const was = this.assist > 0;
      this.assist = this.assistTimer >= P.assistDelay && need ? 1 : 0;
      if (this.assist && !was) this.log(`Q_ASSIST: lift fans helping (${this.airspeed() < P.assistSpeed ? 'slow' : angErr > P.assistAngle ? 'attitude upset' : 'low'})`, 'warn');
    } else this.assist = 0;
    // water state and the hazards it watches
    const imm = this.immersion();
    const e = this.euler;
    this.flags.fanExitWet = imm > 0 && Math.abs(e[0]) > this.af.wetHeel;
    if (this.flags.fanExitWet) this.log(`Heel past ${(this.af.wetHeel / D2R).toFixed(1)} deg on the water: a fan exit is wet`, 'warn');
    this.flags.sprayZone = this.fanT.some((t) => t > 1) && this.alt - (this.af.hullBottom) < 0.5 && this.alt > -0.1;
    if (Math.abs(e[0]) > 80 * D2R && imm > 0) { if (!this.flags.capsized) this.log('Capsized', 'stop'); this.flags.capsized = true; }
    if (this.env.waterSwitch) this.waterState = this.gate()[0] ? 1 : 2; else this.waterState = 0;
  }

  // ------------------------------------------------------------------------------------------------------------
  control(dt) {
    const P = this.P;
    const c = this.cmd;
    const e = this.euler;
    const af = this.af;
    const out = { fans: [0, 0, 0, 0], edf: 0, surf: [0, 0, 0] };
    if (!this.armed || this.flags.capsized) { this.dbg.req = [0, 0, 0]; return out; }
    const mode = this.mode;
    const vtol = VTOL.has(mode);
    const fanWeight = vtol ? 1 : this.trans ? (this.trans.blendFrom === null ? 1 : clamp(1 - (this.t - this.trans.blendFrom) / (P.transMs / 1000), 0, 1)) : this.assist;

    // ---- the pilot's request (or the autopilot's in QRTL / RTL / QLAND / CIRCLE) ----
    let rollReq; let pitchReq; let yawRateReq; let climbReq;
    const fw = !vtol;
    if (vtol) {
      if (mode === 'QRTL' || (mode === 'QLAND' && !this.env.rcOk)) {
        // position controller: fly home at <= 3 m/s, lean limited to Q_P_ANGLE_MAX
        const dx = this.home[0] - this.pos[0]; const dy = this.home[1] - this.pos[1];
        const d = Math.hypot(dx, dy);
        const vWant = mode === 'QRTL' ? Math.min(3, 0.5 * d) : 0;
        const vx = d > 0.01 ? (vWant * dx) / d : 0; const vy = d > 0.01 ? (vWant * dy) / d : 0;
        const ax = 1.2 * (vx - this.vel[0]); const ay = 1.2 * (vy - this.vel[1]);
        const yaw = e[2];
        const fx = ax * Math.cos(yaw) + ay * Math.sin(yaw); const fy = -ax * Math.sin(yaw) + ay * Math.cos(yaw);
        const lim = Math.min(P.posAngleMax, P.angleMax);
        pitchReq = clamp(-Math.atan2(fx, G), -lim, lim);
        rollReq = clamp(Math.atan2(fy, G), -lim, lim);
        yawRateReq = 0;
        climbReq = mode === 'QRTL' && d > 2 ? clamp(0.5 * (15 - this.alt), -1.5, 1) : -(this.alt > 2 ? 1.5 : 0.5);
      } else {
        rollReq = c.roll * P.angleMax;
        pitchReq = -c.pitch * P.angleMax;                          // stick forward (+) = nose down
        yawRateReq = c.yaw * P.yawRate;
        if (mode === 'QLAND') climbReq = -(this.alt > 2 ? 1.0 : 0.5);
        else {
          const s = (c.thr - 0.5) * 2;                             // throttle stick: centre = hold height
          const dz = 0.1;
          const sd = Math.abs(s) < dz ? 0 : (s - sgn(s) * dz) / (1 - dz);
          climbReq = P.spdUp > 0 ? (sd >= 0 ? sd * P.spdUp : sd * P.spdDn) : null;   // null = direct throttle (no protection)
        }
      }
    } else {
      // fixed wing: stick = bank and pitch angles, limited
      let bankLim = P.rollLimit;
      if (P.stallPrevention) bankLim = stallBankLimitDeg(this.airspeed(), this.params.AIRSPEED_MIN, bankLim);
      this.dbg.bankLim = bankLim;
      if (mode === 'MANUAL') { rollReq = 0; pitchReq = 0; }
      else if (mode === 'CIRCLE' || mode === 'RTL') {
        let bank = 20 * D2R;
        if (mode === 'RTL') {
          const brg = Math.atan2(this.home[1] - this.pos[1], this.home[0] - this.pos[0]);
          bank = clamp(1.2 * wrapPi(brg - e[2]), -bankLim * D2R, bankLim * D2R);
        }
        rollReq = Math.min(bank, bankLim * D2R);
        const altT = Math.min(Math.max(this.alt, 15), 40);
        pitchReq = clamp(0.06 * (altT - this.alt) + 0.1 * -this.vel[2] * -1 + 3 * D2R, P.pitchMin * D2R, P.pitchMax * D2R);
      } else {
        rollReq = c.roll * bankLim * D2R;
        // neutral stick = the cruise attitude (the job of ArduPlane's pitch trim), full stick = the pitch limits
        const trim = this.fwPitchTrim();
        pitchReq = c.pitch >= 0 ? trim + c.pitch * (P.pitchMin * D2R - trim) : trim - c.pitch * (P.pitchMax * D2R - trim);
      }
      yawRateReq = 0;
      climbReq = 0;
    }
    this.dbg.req = [rollReq, pitchReq, yawRateReq];

    // ---- input shaping: request -> smooth target (Q_A_INPUT_TC with the rate and acceleration limits) ----
    const sh = this.shapers;
    const cfg = (i) => ({ tc: P.tc, rateMax: P.rateMax[i], accMax: P.accMax[i] });
    sh[0].step(rollReq, cfg(0), dt);
    sh[1].step(pitchReq, cfg(1), dt);
    this.yawRateT = lowPass(this.yawRateT, yawRateReq, P.yawTc, dt);
    if (P.rateMax[2] > 0) this.yawRateT = clamp(this.yawRateT, -P.rateMax[2], P.rateMax[2]);
    sh[2].angle = wrapPi(sh[2].angle + this.yawRateT * dt);
    // hard envelope on the shaped target (Q_A_ANGLE_MAX in VTOL, the stabilised-mode limits in fixed wing)
    const lim = vtol ? P.angleMax : null;
    if (lim) { sh[0].angle = clamp(sh[0].angle, -lim, lim); sh[1].angle = clamp(sh[1].angle, -lim, lim); }
    const tgt = [sh[0].angle, sh[1].angle, sh[2].angle];
    if (fw && mode !== 'MANUAL' && fanWeight === 0) { sh[2].reset(e[2]); tgt[2] = e[2]; }
    this.dbg.tgt = tgt;

    // ---- attitude P -> rate PID (both the fans and, in forward flight, the surfaces) ----
    const angErr = [wrapPi(tgt[0] - e[0]), wrapPi(tgt[1] - e[1]), wrapPi(tgt[2] - e[2])];
    const ff = [sh[0].rate, sh[1].rate, this.yawRateT];
    const rateT = angErr.map((er, i) => 4.5 * er + ff[i]);
    if (P.rateMax[0] > 0) for (let i = 0; i < 3; i += 1) rateT[i] = clamp(rateT[i], -P.rateMax[i], P.rateMax[i]);
    // Euler-rate targets to body rates
    const [cr, sr, cp, sp] = [Math.cos(e[0]), Math.sin(e[0]), Math.cos(e[1]), Math.sin(e[1])];
    const bodyT = [rateT[0] - sp * rateT[2], cr * rateT[1] + sr * cp * rateT[2], -sr * rateT[1] + cr * cp * rateT[2]];
    // coordinated-turn pitch rate in fixed wing, so a banked turn does not sink (ArduPlane's pitch controller does this)
    if (fw && mode !== 'MANUAL') { const ph = clamp(e[0], -1.05, 1.05); bodyT[1] += (G / Math.max(this.airspeed(), 8)) * Math.tan(ph) * Math.sin(ph); }
    this.dbg.rateT = bodyT;

    if (fanWeight > 0) {
      const sat = this.lastSat || [0, 0, 0];
      const acc = [this.pid.r.step(bodyT[0] - this.w[0], dt, sat[0]), this.pid.p.step(bodyT[1] - this.w[1], dt, sat[1]), this.pid.y.step(bodyT[2] - this.w[2], dt, sat[2])];
      const moments = acc.map((a, i) => a * af.I[i]);
      // vertical: climb-rate request -> shaped (Q_PILOT_ACCEL_Z) -> velocity PI -> thrust, with angle boost
      let total;
      const tilt = Math.max(Math.cos(e[0]) * Math.cos(e[1]), 0.5);
      if (climbReq === null) {
        // no protection: the throttle stick is the collective (mid-stick = hover thrust, like QSTABILIZE)
        const hov = af.m * G;
        total = c.thr <= 0.5 ? (c.thr / 0.5) * hov : hov + ((c.thr - 0.5) / 0.5) * (4 * af.tMax - hov);
        this.climbT = -this.vel[2];
      } else {
        this.climbT = P.accZ > 0 ? slew(this.climbT, climbReq, P.accZ, dt) : climbReq;
        const climb = -this.vel[2];
        const aCmd = this.pid.z.step(this.climbT - climb, dt) + 0;
        total = (af.m * (G + aCmd)) / tilt;
        if (!vtol) total = Math.max(total, 0);
      }
      this.dbg.climbReq = climbReq;
      if (fw && !this.trans) total = Math.max(0, Math.min(total, (af.m * G) / tilt));   // assist only holds height
      const res = mixQuad(af, total * fanWeight, moments.map((m) => m * fanWeight));
      out.fans = res.T;
      this.lastSat = res.sat;
    } else { this.pid.r.reset(); this.pid.p.reset(); this.pid.y.reset(); this.pid.z.reset(); this.lastSat = [0, 0, 0]; }

    // ---- fixed-wing surfaces: rate loop with speed scaling (authority ~ q, so the demand is divided by q) ----
    const as = this.airspeed();
    const qd = 0.5 * RHO * Math.max(as, 6) ** 2;
    if (mode === 'MANUAL') {
      out.surf = [c.roll, -c.pitch, c.yaw];
    } else if (fw || this.trans) {
      const ar = af.I[0] * (this.pid.fwR.step(bodyT[0] - this.w[0], dt) * 3 + 0) - qd * af.S * af.b * af.Clp * (this.w[0] * af.b) / (2 * Math.max(as, 6));
      const ap = af.I[1] * (this.pid.fwP.step(bodyT[1] - this.w[1], dt) * 3);
      const alpha = Math.atan2(this.airVelBody()[2], Math.max(this.airVelBody()[0], 1));
      const cmTrim = af.Cm0 + af.Cma * alpha;
      out.surf = [clamp(ar / (qd * af.S * af.b * af.Clda), -1, 1), clamp(ap / (qd * af.S * af.c * af.Cmde) - cmTrim / af.Cmde, -1, 1), 0];
    }

    // ---- cruise EDF: stick throttle (fixed wing), autopilot speed hold (RTL/CIRCLE), full in transition ----
    let thr = 0;
    if (mode === 'MANUAL' || mode === 'FBWA') thr = c.thr;
    if (mode === 'RTL' || mode === 'CIRCLE') thr = Math.sqrt(clamp(0.35 + 0.08 * (this.params.AIRSPEED_CRUISE - as), 0, 1));   // thrust ~ throttle^2
    if (this.trans && this.trans.blendFrom === null) thr = 1;
    if (vtol) thr = 0;
    this.edfCmd = thr;
    // water mode: the taxi cap and the RC-loss idle (ryujin_water.lua), only on the water and never in VTOL
    if (this.P.waterGate && this.env.waterSwitch && !vtol && !this.likelyFlying()) {
      const cap = (this.params.RYW_TAXI_PWM - 1000) / 1000;
      thr = Math.min(thr, cap);
      if (!this.env.rcOk) { thr = 0; this.log('RC lost on the water: EDF idle', 'warn'); }
    }
    this.thrOut = slew(this.thrOut, thr, P.thrSlew / 100, dt);
    out.edf = this.thrOut;

    // ---- exit vanes (ryujin_vanes.lua): shut in fixed wing, open in hover, aft bias with speed, yaw differential ----
    const vtolOrAssist = vtol || this.assist > 0 || !!this.trans;
    let vl = null; let vr = null;
    if (vtolOrAssist) {
      const assisted = this.assist > 0 || !!this.trans;          // aft bias only in assisted flight (the G8 fix)
      const fwd = assisted ? this.params.RYV_FWD_MAX * clamp(as / this.params.AIRSPEED_MIN, 0, 1) : 0;
      const y = this.params.RYV_YAW_MAX * clamp(c.yaw, -1, 1);
      vl = clamp(fwd + y, 0, this.params.RYV_RANGE); vr = clamp(fwd - y, 0, this.params.RYV_RANGE);
    }
    const st = (this.params.RYV_SLEW || 120) * dt;
    this.vane = [vl === null ? null : (this.vane[0] ?? 0) + clamp(vl - (this.vane[0] ?? 0), -st, st), vr === null ? null : (this.vane[1] ?? 0) + clamp(vr - (this.vane[1] ?? 0), -st, st)];
    return out;
  }

  airVelBody() { return qRotInv(this.q, this.airVel()); }

  // angle of attack for level flight at AIRSPEED_CRUISE
  fwPitchTrim() {
    const af = this.af; const v = this.params.AIRSPEED_CRUISE;
    return ((af.m * G) / (0.5 * RHO * v * v * af.S) - af.CL0) / af.CLa;
  }

  // ------------------------------------------------------------------------------------------------------------
  physics(out, dt) {
    const af = this.af;
    // gusts: first-order filtered noise per axis (a Dryden-like spectrum at one length scale)
    if (this.env.gust > 0) {
      const tau = 1.2;
      const k = Math.sqrt((2 * dt) / tau) * this.env.gust;
      this.gustState = this.gustState.map((g, i) => g - (g * dt) / tau + k * (this.rand() * 2 - 1) * Math.sqrt(3) * (i === 2 ? 0.4 : 1));
      // each fan sees its own vertical gust (the gust field is not uniform across a 0.5 m aircraft)
      const tf = 0.25; const kf = Math.sqrt((2 * dt) / tf) * this.env.gust * 0.6;
      this.gustFan = (this.gustFan || [0, 0, 0, 0]).map((g) => g - (g * dt) / tf + kf * (this.rand() * 2 - 1) * Math.sqrt(3));
    }
    // actuator lags
    this.fanT = this.fanT.map((T, i) => T + ((clamp(out.fans[i], 0, af.tMax) - T) * dt) / af.fanTau);
    this.edf += ((out.edf - this.edf) * dt) / af.edfTau;
    this.surf = this.surf.map((s, i) => s + ((out.surf[i] - s) * dt) / 0.05);

    const Fb = [0, 0, 0];
    const Mb = [0, 0, 0];
    // lift fans (with the exit vanes tilting each side's efflux aft, which pushes that side forward)
    af.fans.forEach((f, i) => {
      // an upward gust through a fan unloads it (thrust ~ 1 - w / 2 v_induced, v_induced about 10 m/s at hover)
      const T = this.fanT[i] * (1 - (this.gustFan ? -this.gustFan[i] : 0) / 21);
      const vdeg = f.y_m < 0 ? this.vane[0] : this.vane[1];
      const v = (vdeg ?? 0) * D2R;
      const fx = T * Math.sin(v); const fz = -T * Math.cos(v);
      Fb[0] += fx; Fb[2] += fz;
      Mb[0] += f.y_m * fz;                                      // r x F with r = (x, y, 0)
      Mb[1] += -f.x_m * fz;
      Mb[2] += -f.y_m * fx + f.dir * af.kq * T;
    });
    // cruise EDF on the centreline
    const vb = this.airVelBody();
    const V = Math.hypot(...vb);
    // static thrust ~ rpm^2 and rpm ~ throttle on a fixed-pitch fan: thrust ~ throttle^2 (ESTIMATE, as tools/v21/g9.py; W1 fits it)
    const Tedf = af.edfMax * this.edf * this.edf * Math.max(0, 1 - Math.max(vb[0], 0) / af.edfVzero);
    Fb[0] += Tedf;
    // wing and tail
    const u = vb[0]; const v = vb[1]; const w = vb[2];
    const qd = 0.5 * RHO * V * V;
    if (V > 0.5) {
      const alpha = Math.atan2(w, u);
      const beta = Math.asin(clamp(v / V, -1, 1));
      const a = Math.abs(alpha) < Math.PI / 2 ? alpha : 0;
      let CL; let CD;
      if (Math.abs(a) <= af.alphaStall) { CL = af.CL0 + af.CLa * a; CD = af.CD0 + af.kInd * CL * CL; }
      else { CL = sgn(a) * 0.7 * af.CLmax * Math.max(0, Math.cos(a)) * 1.2; CD = af.CD0 + 1.1 * Math.sin(Math.abs(a)) ** 2 + 0.1; }
      const stalled = Math.abs(a) > af.alphaStall && u > 5 && V > 7;
      if (stalled && !this.flags.stalled) this.log('Wing stalled', 'stop');
      this.flags.stalled = stalled;
      const L = qd * af.S * CL; const Dd = qd * af.S * CD;
      const ca = Math.cos(alpha); const sa = Math.sin(alpha);
      const fade = clamp((u - 2) / 4, 0, 1);                   // no "lift" from a wing moving sideways or backwards
      Fb[0] += fade * (L * sa - Dd * ca);
      Fb[2] += fade * (-L * ca - Dd * sa);
      Fb[1] += fade * qd * af.S * af.CYb * beta;
      const Vs = Math.max(V, 3);
      const hat = (r, len) => (r * len) / (2 * Vs);
      // stall: the wing drops toward the low side (whichever way it is already rolling or banked)
      const drop = stalled ? 0.03 * sgn(this.w[0] + 0.5 * this.euler[0] || 1) : 0;
      Mb[0] += fade * qd * af.S * af.b * (af.Clda * this.surf[0] + af.Clp * hat(this.w[0], af.b) + drop);
      Mb[1] += fade * qd * af.S * af.c * (af.Cm0 + af.Cma * a + af.Cmq * hat(this.w[1], af.c) + af.Cmde * this.surf[1]);
      Mb[2] += fade * qd * af.S * af.b * (af.Cnb * beta + af.Cnr * hat(this.w[2], af.b) + af.Cndr * this.surf[2]);
    }
    // low-speed bluff-body drag (hover, taxi, falling flat)
    const blend = clamp(1 - Math.abs(u) / 10, 0, 1);
    for (let i = 0; i < 3; i += 1) Fb[i] -= 0.5 * RHO * af.cdA[i] * vb[i] * Math.abs(vb[i]) * (i === 0 ? 1 : blend);
    // the ruddervators in the EDF exhaust steer on the water (an airboat rudder; W6 measures it)
    Mb[2] += -0.12 * Tedf * this.surf[2] * 0.4;
    // rotational damping in air (ESTIMATE)
    for (let i = 0; i < 3; i += 1) Mb[i] -= 0.004 * this.w[i];

    // to earth frame, plus gravity
    const Fe = qRot(this.q, Fb);
    Fe[2] += af.m * G;

    // the hull: buoyancy, heave damping, hull drag, roll and pitch righting
    const imm = this.immersion();
    if (imm > 0) {
      const frac = Math.min(imm / af.draft0, af.reserve);
      const k = (af.m * G) / af.draft0;
      const cHeave = 2 * 0.6 * Math.sqrt(k * af.m);
      Fe[2] += -Math.min(k * imm, af.m * G * af.reserve) - cHeave * this.vel[2] * Math.min(frac, 1);
      const yaw = this.euler[2];
      const vxb = this.vel[0] * Math.cos(yaw) + this.vel[1] * Math.sin(yaw);
      const vyb = -this.vel[0] * Math.sin(yaw) + this.vel[1] * Math.cos(yaw);
      const wet = Math.min(frac, 1);
      const dx = -sgn(vxb) * lerpTable(af.hullDrag, Math.abs(vxb)) * wet;
      const dy = -af.sideDrag * vyb * Math.abs(vyb) * wet - 4 * vyb * wet;
      Fe[0] += dx * Math.cos(yaw) - dy * Math.sin(yaw);
      Fe[1] += dx * Math.sin(yaw) + dy * Math.cos(yaw);
      const e = this.euler;
      const heel = Math.abs(e[0]);
      Mb[0] += -sgn(e[0]) * af.m * G * lerpTable(af.gz, heel) * wet - 0.35 * this.w[0] * wet;
      Mb[1] += -af.m * G * af.gmL * Math.sin(e[1] - af.trim) * wet - 0.9 * this.w[1] * wet;
      Mb[2] += -0.25 * this.w[2] * wet;
      // waves rock the hull: a roll and pitch forcing from the surface slope
      if (this.env.wave > 0) {
        const slope = (Math.PI * this.env.wave) / 1.2 * Math.cos(2 * Math.PI * (this.pos[0] / 1.2 - this.t / 0.85));
        Mb[1] += af.m * G * af.gmL * slope * 0.5 * wet;
        Mb[0] += af.m * G * 0.04 * slope * wet;
      }
    }

    // integrate (semi-implicit Euler)
    for (let i = 0; i < 3; i += 1) { this.vel[i] += (Fe[i] / af.m) * dt; this.pos[i] += this.vel[i] * dt; }
    const I = af.I; const wv = this.w;
    const gyro = [(I[1] - I[2]) * wv[1] * wv[2], (I[2] - I[0]) * wv[2] * wv[0], (I[0] - I[1]) * wv[0] * wv[1]];
    this.w = wv.map((x, i) => x + ((Mb[i] + gyro[i]) / I[i]) * dt);
    this.q = qNorm(this.q.map((x, i) => x + 0.5 * dt * qMul(this.q, [0, ...this.w])[i]));
    // battery: fan power ~ T^1.5 (momentum theory), EDF ~ throttle^1.5 (ESTIMATE 600 W at full)
    const Th = (af.m * G) / 4;
    const pw = this.fanT.reduce((s, T) => s + (af.hoverW / 4) * (Math.max(T, 0) / Th) ** 1.5, 0) + 600 * this.edf ** 1.5 + 4;
    const volts = 14.8 - 0.012 * (pw / 14.8);
    this.amps = pw / volts;
    this.mah += (this.amps * dt * 1000) / 3600;
    if (this.pos[2] > 0.5 && !this.flags.crashed) { this.flags.crashed = true; this.log('Hit the water hard (more than 0.5 m under)', 'stop'); }
  }

  // one telemetry row (what the plots and the 3D replay read)
  sample() {
    const e = this.euler;
    return {
      t: +this.t.toFixed(3), x: this.pos[0], y: this.pos[1], alt: this.alt, q: [...this.q],
      roll: e[0] * R2D, pitch: e[1] * R2D, yaw: e[2] * R2D,
      reqRoll: this.dbg.req[0] * R2D, reqPitch: this.dbg.req[1] * R2D, tgtRoll: this.dbg.tgt[0] * R2D, tgtPitch: this.dbg.tgt[1] * R2D,
      p: this.w[0] * R2D, qr: this.w[1] * R2D, r: this.w[2] * R2D,
      climb: -this.vel[2], climbT: this.climbT, climbReq: this.dbg.climbReq, airspeed: this.airspeed(), gs: Math.hypot(this.vel[0], this.vel[1]),
      fans: this.fanT.map((T) => T / this.af.tMax), edf: this.edf, vanes: [...this.vane], surf: [...this.surf],
      mode: this.mode, assist: this.assist, trans: !!this.trans, bankLim: this.dbg.bankLim ?? null,
      batt: this.batteryPct, amps: this.amps || 0, water: this.waterState, onWater: this.onWater(), waterline: this.waterline,
      stalled: this.flags.stalled, wet: this.flags.fanExitWet, spray: this.flags.sprayZone, capsized: this.flags.capsized, crashed: this.flags.crashed,
      wind: this.windAtAircraft(), gust: [...this.gustState], armed: this.armed, prot: this.P.on,
    };
  }
}

// Mixer: total thrust + roll/pitch/yaw moments -> four fan thrusts, with ArduPilot's priorities when a fan saturates:
// yaw gives way first, then the collective moves to keep roll and pitch, then everything is clipped.
let MIX_INV = null;
function invert4(A) {
  const n = 4; const M = A.map((r, i) => [...r, ...Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))]);
  for (let c = 0; c < n; c += 1) {
    let p = c; for (let r = c + 1; r < n; r += 1) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    const d = M[c][c]; for (let j = 0; j < 2 * n; j += 1) M[c][j] /= d;
    for (let r = 0; r < n; r += 1) if (r !== c) { const f = M[r][c]; for (let j = 0; j < 2 * n; j += 1) M[r][j] -= f * M[c][j]; }
  }
  return M.map((r) => r.slice(n));
}
export function mixQuad(af, total, [L, M, N]) {
  if (!MIX_INV || MIX_INV.af !== af) {
    const A = [af.fans.map(() => 1), af.fans.map((f) => -f.y_m), af.fans.map((f) => f.x_m), af.fans.map((f) => f.dir * af.kq)];
    MIX_INV = { af, inv: invert4(A) };
  }
  const inv = MIX_INV.inv;
  const col = (k) => inv.map((r) => r[k]);
  const base = col(0).map((v) => v * total);
  const rp = col(1).map((v, i) => v * L + col(2)[i] * M);
  const yw = col(3).map((v) => v * N);
  const tMax = af.tMax;
  const sat = [0, 0, 0];
  // roll + pitch first; shift the collective if the spread fits
  let T = base.map((b, i) => b + rp[i]);
  const lo = Math.min(...T); const hi = Math.max(...T);
  if (hi - lo <= tMax) { if (lo < 0) T = T.map((x) => x - lo); if (Math.max(...T) > tMax) { const s = Math.max(...T) - tMax; T = T.map((x) => x - s); } }
  else { sat[0] = sgn(L); sat[1] = sgn(M); }
  // then yaw, scaled to whatever room is left
  let k = 1;
  for (let i = 0; i < 4; i += 1) {
    if (yw[i] > 0 && T[i] + yw[i] > tMax) k = Math.min(k, Math.max(0, (tMax - T[i]) / yw[i]));
    if (yw[i] < 0 && T[i] + yw[i] < 0) k = Math.min(k, Math.max(0, T[i] / -yw[i]));
  }
  if (k < 1) sat[2] = sgn(N);
  T = T.map((x, i) => clamp(x + k * yw[i], 0, tMax));
  return { T, sat };
}

// ---------------------------------------------------------------------------------------------------------------
// Scripted demonstrations: each runs twice (protections on and off) from the same start, same inputs, same seed.

const stick = (roll = 0, pitch = 0, yaw = 0, thr = 0.5) => ({ roll, pitch, yaw, thr });
const pulse = (t, a, b, v) => (t >= a && t < b ? v : 0);

export const DEMOS = [
  {
    id: 'stick-slam', title: 'Stick slam in a hover', channel: 'roll', secs: 6,
    what: 'Hovering at 3 m, the pilot slams the roll stick full right for 1 s, then lets go.',
    how: 'Input shaping (Q_A_INPUT_TC 0.2 s, Q_A_RATE_R_MAX 120 deg/s, Q_A_ACC_R_MAX 720 deg/s/s) turns the step into a smooth, rate-limited lean, and Q_A_ANGLE_MAX caps it at 25 deg.',
    start: { onWater: false, alt: 3, mode: 'QHOVER' },
    input: (t) => stick(pulse(t, 0.5, 1.5, 1)),
  },
  {
    id: 'stick-pumping', title: 'Over-correcting (stick pumping)', channel: 'roll', secs: 6,
    what: 'A nervous pilot pumps the roll stick left-right at 2.5 Hz.',
    how: 'The shaping filter passes slow, deliberate inputs and smooths fast ones, so a twitchy thumb cannot drive the airframe through big, fast swings (the start of a pilot-induced oscillation).',
    start: { onWater: false, alt: 3, mode: 'QHOVER' },
    input: (t) => stick(t > 0.5 && t < 4.5 ? (Math.sin(2 * Math.PI * 2.5 * t) > 0 ? 0.8 : -0.8) : 0),
  },
  {
    id: 'throttle-slam', title: 'Throttle slam near the water', channel: 'climb', secs: 8,
    what: 'Hovering at 2 m, the pilot pushes the throttle full up for 1.5 s, then chops it to zero.',
    how: 'In QHOVER the throttle stick asks for a climb rate, not thrust: at most Q_PILOT_SPD_UP 1.5 m/s up and Q_PILOT_SPD_DN 1.0 m/s down, reached at Q_PILOT_ACCEL_Z 1.5 m/s/s. Without it the throttle is the thrust, and chopping it drops the aircraft into the water.',
    start: { onWater: false, alt: 2, mode: 'QHOVER' },
    input: (t) => stick(0, 0, 0, t > 0.5 && t < 2 ? 1 : t >= 2 && t < 4.5 ? 0 : 0.5),
  },
  {
    id: 'slow-bank', title: 'Steep turn too slow', channel: 'roll', secs: 8,
    what: 'Flying wing-borne at 15.5 m/s in FBWA, the pilot holds full right stick for a steep turn.',
    how: 'STALL_PREVENTION limits the bank to what the wing can hold at this speed (load factor (V / AIRSPEED_MIN)²); ROLL_LIMIT_DEG caps it at 45 deg anyway. Q_ASSIST_SPEED / Q_ASSIST_ANGLE bring the lift fans in if it still gets slow or upset.',
    start: { onWater: false, alt: 30, airspeed: 15.5, mode: 'FBWA' },
    input: (t) => ({ ...stick(t > 0.5 ? 1 : 0, 0, 0, 0.57) }),
  },
  {
    id: 'pull-up', title: 'Pulling up too hard', channel: 'pitch', secs: 8,
    what: 'Wing-borne at 16 m/s with low throttle, the pilot holds full back stick.',
    how: 'PTCH_LIM_MAX_DEG caps the nose at 20 deg; as the speed bleeds away, Q_ASSIST_SPEED (13 m/s) brings the fans in after Q_ASSIST_DELAY so it does not stall and drop.',
    start: { onWater: false, alt: 30, airspeed: 16, mode: 'FBWA' },
    input: (t) => stick(0, t > 0.5 ? -1 : 0, 0, 0.39),
  },
  {
    id: 'fence', title: 'Flying too high', channel: 'alt', secs: 70,
    what: 'The pilot holds the throttle up in a hover and keeps climbing.',
    how: 'FENCE_ALT_MAX 60 m (minus FENCE_MARGIN 5 m) switches to QRTL: the aircraft comes home and descends on its own.',
    start: { onWater: false, alt: 10, mode: 'QHOVER' },
    input: () => stick(0, 0, 0, 1),
  },
  {
    id: 'gust', title: 'Gusty hover', channel: 'roll', secs: 12,
    what: 'Hovering at 3 m in 3 m/s of wind with 2.5 m/s gusts, hands off.',
    how: 'The same attitude loops hold the aircraft level; the plot shows how much the gusts move it. Protections do not change gust rejection much (the rate PID does that), which is the point: shaping slows the pilot, not the stabiliser.',
    start: { onWater: false, alt: 3, mode: 'QHOVER' },
    env: { wind: [3, 0], gust: 2.5 },
    input: () => stick(),
  },
  {
    id: 'water-gate', title: 'Water take-off in waves', channel: 'alt', secs: 8,
    what: 'Floating with 60 mm waves (the limit is 15 mm), the pilot selects QHOVER and pushes the throttle up.',
    how: 'The water gate (ryujin_water.lua) says NO-GO and puts it back in MANUAL: no take-off. Without it, the fans spin up while the hull rolls in the waves.',
    start: { onWater: true, mode: 'MANUAL' },
    env: { waterSwitch: true, wave: 0.06 },
    actions: [[0.2, (tw) => { tw.armed = true; }], [1, (tw) => tw.setMode('QHOVER')]],
    input: (t) => stick(0, 0, 0, t > 1 && t < 2.5 ? 0.85 : t >= 2.5 ? 0.5 : 0),
  },
  {
    id: 'water-takeoff', title: 'Water take-off, calm (the V21 goal)', channel: 'alt', secs: 10,
    what: 'Calm water, GO: armed in MANUAL, then QHOVER and climb to about 1 m.',
    how: 'The gate says GO. The climb is the Q_PILOT_SPD_UP-limited one; the spray zone (fans running under 0.5 m) is marked. UNCONFIRMED until G7 W7.',
    start: { onWater: true, mode: 'MANUAL' },
    env: { waterSwitch: true, wave: 0.01 },
    actions: [[0.2, (tw) => tw.arm()], [1, (tw) => tw.setMode('QHOVER')]],
    input: (t) => stick(0, 0, 0, t > 1 && t < 2.6 ? 0.85 : 0.5),
  },
  {
    id: 'taxi', title: 'Full throttle on the water', channel: 'speed', secs: 15,
    what: 'Water-taxi in MANUAL: the pilot slams the throttle to full, then loses the radio link at 9 s.',
    how: 'The water script caps the EDF at RYW_TAXI_PWM (about hull speed) and THR_SLEWRATE ramps it; with RC lost it idles the EDF instead of a fixed-wing failsafe pushing it across the lake.',
    start: { onWater: true, mode: 'MANUAL' },
    env: { waterSwitch: true, wave: 0.01 },
    actions: [[0.2, (tw) => tw.arm()], [9, (tw) => { tw.env.rcOk = false; }]],
    input: () => stick(0, 0, 0, 1),
  },
];

export function runDemo(data, demo, protect, { hz = 50 } = {}) {
  const tw = new Twin(data, { protect, seed: 7 });
  Object.assign(tw.env, demo.env || {});
  tw.reset(demo.start || {});
  const rows = [];
  const acts = [...(demo.actions || [])];
  const every = Math.round(1 / hz / DT);
  let i = 0;
  const n = Math.round(demo.secs / DT);
  for (let k = 0; k < n; k += 1) {
    while (acts.length && tw.t >= acts[0][0]) acts.shift()[1](tw);
    tw.step(demo.input(tw.t, tw));
    if (i % every === 0) rows.push(tw.sample());
    i += 1;
  }
  return { rows, events: tw.events, protect };
}

// ---------------------------------------------------------------------------------------------------------------
// Flight-log replay (G13): the sticks and mode changes of a real flight (tools/v21/g7_log.py --replay) drive the
// twin; the measured attitude rides along so the two can be compared. Modes the twin does not model are mapped to the
// nearest one it does (QLOITER and QSTABILIZE fly as QHOVER here) and listed in `mapped`.
const REPLAY_MODES = { MANUAL: 'MANUAL', FBWA: 'FBWA', STABILIZE: 'FBWA', FBWB: 'FBWA', CRUISE: 'FBWA', RTL: 'RTL', CIRCLE: 'CIRCLE',
  QHOVER: 'QHOVER', QLOITER: 'QHOVER', QSTABILIZE: 'QHOVER', QLAND: 'QLAND', QRTL: 'QRTL' };

export function replayLog(data, log, { protect = true, onWater = true, hz = 50 } = {}) {
  if (!log || log.kind !== 'ryujin-v21-replay' || !Array.isArray(log.rows) || log.rows.length < 2) throw new Error('not a V21 replay file (tools/v21/g7_log.py --replay)');
  const L = log.rows;
  const mapped = new Set();
  const twinMode = (m) => { const t = REPLAY_MODES[m]; if (!t) { mapped.add(`${m} (not modelled: held)`); return null; } if (t !== m) mapped.add(`${m} -> ${t}`); return t; };
  const tw = new Twin(data, { protect, seed: 7 });
  Object.assign(tw.env, { waterSwitch: onWater, wave: 0 });
  tw.reset({ onWater, mode: twinMode(L[0].mode) || 'MANUAL' });
  tw.arm();
  const rows = [];
  const every = Math.max(1, Math.round(1 / hz / DT));
  let j = 0; let lastLogMode = L[0].mode; let k = 0;
  const tEnd = L.at(-1).t;
  while (tw.t < tEnd) {
    while (j + 1 < L.length && L[j + 1].t <= tw.t) j += 1;
    const a = L[j]; const b = L[Math.min(j + 1, L.length - 1)];
    const f = b.t > a.t ? Math.min(1, Math.max(0, (tw.t - a.t) / (b.t - a.t))) : 0;
    const lerp = (key) => a[key] + f * (b[key] - a[key]);
    if (a.mode !== lastLogMode) { lastLogMode = a.mode; const m = twinMode(a.mode); if (m) tw.setMode(m, 'log'); }
    tw.step({ roll: lerp('roll_cmd'), pitch: lerp('pitch_cmd'), yaw: lerp('yaw_cmd'), thr: lerp('thr') });
    if (k % every === 0) {
      const s = tw.sample();
      s.measRoll = a.roll == null ? null : a.roll + f * (b.roll - a.roll);
      s.measPitch = a.pitch == null ? null : a.pitch + f * (b.pitch - a.pitch);
      s.measCurr = a.curr == null ? null : a.curr + f * (b.curr - a.curr);
      s.logMode = a.mode;
      rows.push(s);
    }
    k += 1;
  }
  const rms = (key, meas) => {
    const v = rows.filter((r) => r[meas] != null);
    return v.length ? Math.sqrt(v.reduce((acc, r) => acc + (r[key] - r[meas]) ** 2, 0) / v.length) : null;
  };
  return { rows, events: tw.events, protect, mapped: [...mapped], notes: log.notes || [],
    rmsRollDeg: rms('roll', 'measRoll'), rmsPitchDeg: rms('pitch', 'measPitch'), rmsCurrA: rms('amps', 'measCurr') };
}
