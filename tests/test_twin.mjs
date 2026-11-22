// V21 G8 digital twin (site/js/twin_core.js): it runs the bench param file's protections, its building blocks do
// what their names say, and in every scripted pilot mistake the protected run ends up safer than the unprotected one.
// A teaching model: these tests check the model is self-consistent, not that the aircraft will fly this way.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';
import { AngleShaper, DEMOS, DT, Twin, airframe, mixQuad, replayLog, runDemo, sqrtController, stallBankLimitDeg, waterOpsAllowed } from '../site/js/twin_core.js';

const root = new URL('..', import.meta.url).pathname;
const D = JSON.parse(readFileSync(join(root, 'site/data/v21.json'), 'utf8'));
const paramFile = readFileSync(join(root, 'config/ardupilot/ryujin_v21_mini_BENCH_ONLY.param'), 'utf8');
const PF = Object.fromEntries([...paramFile.matchAll(/^([A-Z0-9_]+),([-0-9.]+)\s*$/gm)].map((m) => [m[1], +m[2]]));
const max = (rows, k) => Math.max(...rows.map((r) => Math.abs(r[k])));
const runs = Object.fromEntries(DEMOS.map((d) => [d.id, { on: runDemo(D, d, true), off: runDemo(D, d, false) }]));

test('the twin runs the bench param file (no drift)', () => {
  for (const [k, v] of Object.entries(PF)) assert.equal(D.params[k], v, k);
  for (const k of ['Q_A_INPUT_TC', 'Q_A_ANGLE_MAX', 'Q_PILOT_SPD_UP', 'ROLL_LIMIT_DEG', 'STALL_PREVENTION', 'FENCE_ALT_MAX', 'BATT_CRT_MAH', 'RYW_TAXI_PWM', 'RYV_FWD_MAX']) assert.ok(k in D.params, k);
  assert.ok(existsSync(join(root, 'site/models/v21_mini.glb')), 'compressed model');
});

test('sqrt controller: proportional near the target, acceleration-limited far from it', () => {
  assert.equal(sqrtController(0.01, 5, 10, 0), 0.05);
  const far = sqrtController(2, 5, 10, 0);
  assert.ok(Math.abs(far - Math.sqrt(2 * 10 * (2 - 10 / 25 / 2))) < 1e-12);
  assert.ok(far < 2 * 5, 'slower than pure P far away');
});

test('input shaping respects its rate and acceleration limits', () => {
  const s = new AngleShaper();
  const cfg = { tc: 0.2, rateMax: 2, accMax: 12 };
  let prev = 0; let maxAcc = 0; let maxRate = 0;
  for (let i = 0; i < 2000; i += 1) { s.step(0.5, cfg, DT); maxRate = Math.max(maxRate, Math.abs(s.rate)); maxAcc = Math.max(maxAcc, Math.abs(s.rate - prev) / DT); prev = s.rate; }
  assert.ok(maxRate <= 2 + 1e-9 && maxAcc <= 12 + 1e-6, `${maxRate} ${maxAcc}`);
  assert.ok(Math.abs(s.angle - 0.5) < 1e-3, 'reaches the target');
});

test('stall prevention bank limit', () => {
  assert.equal(stallBankLimitDeg(14, 15, 45), 25);
  assert.ok(Math.abs(stallBankLimitDeg(15 * Math.SQRT2, 15, 80) - 60) < 1e-9);    // load factor 2 -> 60 deg
  assert.equal(stallBankLimitDeg(40, 15, 45), 45);
});

test('water gate: unknown is NO-GO, thresholds as water.py', () => {
  const g = D.water_gate;
  assert.equal(waterOpsAllowed(2, 0.01, 80, false, g)[0], true);
  assert.equal(waterOpsAllowed(2, undefined, 80, false, g)[0], false);
  assert.equal(waterOpsAllowed(2, 0.01, 80, null, g)[0], false);
  assert.equal(waterOpsAllowed(5.1, 0.01, 80, false, g)[0], false);
  assert.equal(waterOpsAllowed(2, 0.031, 80, false, g)[0], false);
  assert.equal(waterOpsAllowed(2, 0.01, 49.9, false, g)[0], false);
});

test('mixer: exact when it can be, yaw gives way first when it cannot', () => {
  const af = airframe(D);
  const want = [0.3, -0.2, 0.02];
  const { T } = mixQuad(af, af.m * 9.81, want);
  const L = af.fans.reduce((s, f, i) => s - f.y_m * T[i], 0); const M = af.fans.reduce((s, f, i) => s + f.x_m * T[i], 0);
  assert.ok(Math.abs(L - want[0]) < 1e-9 && Math.abs(M - want[1]) < 1e-9);
  const r = mixQuad(af, 4 * af.tMax * 0.95, [0.5, 0, 0.5]);
  assert.equal(r.sat[2], 1, 'yaw saturates');
  assert.ok(Math.abs(af.fans.reduce((s, f, i) => s - f.y_m * r.T[i], 0) - 0.5) < 1e-6, 'roll kept');
});

test('equilibria: hover holds, the hull floats at the G5 waterline and trim', () => {
  const h = new Twin(D); h.reset({ onWater: false, alt: 3, mode: 'QHOVER' }); h.run(5, () => ({ roll: 0, pitch: 0, yaw: 0, thr: 0.5 }));
  assert.ok(Math.abs(h.alt - 3) < 0.02 && Math.abs(h.euler[0]) < 0.01);
  const f = new Twin(D); f.reset({ onWater: true }); f.run(5);
  assert.ok(Math.abs(-f.pos[2] - D.float.waterline_below_cg_m) < 0.003, 'waterline');
  assert.ok(Math.abs(f.euler[1] * 57.3 - D.float.trim_deg) < 0.3, 'trim');
});

test('stick slam: lean bounded by Q_A_ANGLE_MAX and rate by Q_A_RATE_R_MAX', () => {
  const { on, off } = runs['stick-slam'];
  assert.ok(max(on.rows, 'roll') <= D.params.Q_A_ANGLE_MAX + 3);
  assert.ok(max(on.rows, 'p') < max(off.rows, 'p') / 2);
  assert.ok(Math.min(...on.rows.map((r) => r.alt)) > 2.5, 'protected run keeps its height');
});

test('stick pumping: shaping cuts the swing', () => {
  const { on, off } = runs['stick-pumping'];
  assert.ok(max(on.rows, 'roll') < 0.5 * max(off.rows, 'roll'));
});

test('throttle slam: climb and descent limited, never reaches the water', () => {
  const { on, off } = runs['throttle-slam'];
  assert.ok(Math.max(...on.rows.map((r) => r.climb)) <= D.params.Q_PILOT_SPD_UP + 0.2);
  assert.ok(Math.min(...on.rows.map((r) => r.climb)) >= -D.params.Q_PILOT_SPD_DN - 0.2);
  assert.ok(Math.min(...on.rows.map((r) => r.alt)) > 1);
  assert.ok(Math.min(...off.rows.map((r) => r.alt)) < 0.2, 'without it the aircraft reaches the water');
});

for (const id of ['slow-bank', 'pull-up']) {
  test(`${id}: the protected run does not hit the water; the unprotected one does`, () => {
    const { on, off } = runs[id];
    assert.ok(!on.rows.some((r) => r.crashed || r.capsized) && Math.min(...on.rows.map((r) => r.alt)) > 10);
    assert.ok(off.rows.some((r) => r.crashed || r.alt < 0.5));
  });
}

test('steep slow turn: bank stays inside ROLL_LIMIT_DEG', () => {
  assert.ok(max(runs['slow-bank'].on.rows, 'roll') <= D.params.ROLL_LIMIT_DEG + 3);
});

test('fence: QRTL before FENCE_ALT_MAX, comes back down', () => {
  const { on, off } = runs.fence;
  assert.ok(Math.max(...on.rows.map((r) => r.alt)) <= D.params.FENCE_ALT_MAX);
  assert.ok(on.events.some((e) => /fence/.test(e.msg)) && on.rows.at(-1).alt < 5);
  assert.ok(Math.max(...off.rows.map((r) => r.alt)) > D.params.FENCE_ALT_MAX);
});

test('gusty hover stays airborne and near level', () => {
  const { on } = runs.gust;
  assert.ok(Math.min(...on.rows.map((r) => r.alt)) > 2 && max(on.rows, 'roll') < 20);
});

test('water gate in waves: no take-off, back to MANUAL', () => {
  const { on, off } = runs['water-gate'];
  assert.equal(on.rows.at(-1).mode, 'MANUAL');
  assert.ok(Math.max(...on.rows.map((r) => r.alt)) < 0.3);
  assert.ok(Math.max(...off.rows.map((r) => r.alt)) > 1, 'without the gate it lifts off in the waves');
});

test('calm water take-off: GO, lifts off to about 1-2 m, no capsize', () => {
  const { on } = runs['water-takeoff'];
  const top = Math.max(...on.rows.map((r) => r.alt));
  assert.ok(top > 0.8 && top < 3, `${top}`);
  assert.ok(!on.rows.some((r) => r.capsized || r.wet));
});

test('water taxi: EDF capped at RYW_TAXI_PWM, idles on RC loss', () => {
  const { on, off } = runs.taxi;
  const cap = (D.params.RYW_TAXI_PWM - 1000) / 1000;
  assert.ok(Math.max(...on.rows.map((r) => r.edf)) <= cap + 1e-6);
  assert.ok(on.rows.at(-1).edf < 0.05, 'idle after RC loss');
  assert.ok(Math.max(...off.rows.map((r) => r.gs)) > Math.max(...on.rows.map((r) => r.gs)));
});

test('G12: stall speed comes from the sizing, below Q_ASSIST_SPEED with margin', () => {
  assert.ok(D.stall_ms > 9 && D.stall_ms < D.airspeeds.Q_ASSIST_SPEED / 1.15, `${D.stall_ms}`);
});

test('G12: a steep turn that bleeds speed at low throttle never stalls (assist comes in first)', () => {
  const base = DEMOS.find((d) => d.id === 'slow-bank');
  for (const thr of [0.3, 0.4, 0.5]) {
    const r = runDemo(D, { ...base, secs: 12, input: (t) => ({ roll: t > 0.5 ? 1 : 0, pitch: 0, yaw: 0, thr }) }, true);
    assert.ok(!r.rows.some((x) => x.stalled), `stalled at throttle ${thr}`);
    assert.ok(max(r.rows, 'roll') <= D.params.ROLL_LIMIT_DEG + 3, `bank at throttle ${thr}`);
  }
});


// G13: a "flight log" recorded from the twin itself must replay to the same attitude (the replay plumbing adds no error)
function selfLog() {
  const tw = new Twin(D, { protect: true, seed: 7 });
  Object.assign(tw.env, { waterSwitch: true, wave: 0 });
  tw.reset({ onWater: true, mode: 'MANUAL' });
  tw.arm();
  const cmd = (t) => ({ roll: t > 4 && t < 5 ? 0.6 : t > 7 && t < 8 ? -0.6 : 0, pitch: t > 9 && t < 10 ? -0.4 : 0, yaw: 0, thr: t > 1 ? 0.72 : 0 });
  const rows = [];
  let mode = 'MANUAL';
  for (let k = 0; tw.t < 12; k += 1) {
    if (tw.t >= 1 && mode === 'MANUAL') { mode = 'QHOVER'; tw.setMode('QHOVER'); }
    const c = cmd(tw.t);
    if (k % 8 === 0) {
      const s = tw.sample();
      rows.push({ t: +tw.t.toFixed(4), roll_cmd: c.roll, pitch_cmd: c.pitch, yaw_cmd: c.yaw, thr: c.thr, mode, roll: s.roll, pitch: s.pitch, curr: s.amps });
    }
    tw.step(c);
  }
  return { kind: 'ryujin-v21-replay', version: 1, hz: 50, rows, notes: [] };
}

test('G13: log replay reproduces a flight recorded from the twin', () => {
  const log = selfLog();
  const r = replayLog(D, log, { protect: true, onWater: true });
  assert.ok(Math.max(...r.rows.map((x) => x.alt)) > 0.5, 'it took off in the replay');
  assert.ok(r.rmsRollDeg < 1.0 && r.rmsPitchDeg < 1.0, `rms roll ${r.rmsRollDeg} pitch ${r.rmsPitchDeg}`);
});

test('G13: replay maps unmodelled modes and rejects other files', () => {
  const log = selfLog();
  log.rows = log.rows.map((x) => ({ ...x, mode: x.mode === 'QHOVER' ? 'QLOITER' : x.mode }));
  const r = replayLog(D, log);
  assert.ok(r.mapped.includes('QLOITER -> QHOVER'));
  assert.throws(() => replayLog(D, { rows: [] }));
});
