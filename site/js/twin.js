// V21 tab: the Ryujin digital twin. Ten scripted pilot mistakes, each flown twice from the same start with the same
// stick inputs: once with the G8 protections (the bench param file) and once without (a red ghost). Plus a free
// "Fly it" mode on the keyboard or a gamepad. The model is site/js/twin_core.js: a teaching model, not ArduPilot.
import { DEMOS, DT, Twin, replayLog, runDemo } from './twin_core.js';
import { $, $$, badge, esc, fmt, html } from './util.js';

let live = null;                 // the running scene (one at a time); torn down when the tab re-renders or closes

const CHANNELS = {
  roll: { label: 'Roll, deg', keys: [['reqRoll', 'stick request', 'req'], ['tgtRoll', 'shaped target', 'tgt'], ['roll', 'actual', 'act']] },
  pitch: { label: 'Pitch, deg', keys: [['reqPitch', 'stick request', 'req'], ['tgtPitch', 'shaped target', 'tgt'], ['pitch', 'actual', 'act']] },
  climb: { label: 'Climb rate, m/s', keys: [['climbReq', 'stick request', 'req'], ['climbT', 'shaped target', 'tgt'], ['climb', 'actual', 'act']] },
  alt: { label: 'Height, m', keys: [['alt', 'actual', 'act']] },
  speed: { label: 'Speed over the water, m/s', keys: [['gs', 'actual', 'act']] },
};

export function v21(ctx, el, sub) {
  stop();
  const D = ctx.data.v21;
  if (!D) { html(el, '<h2>V21 digital twin</h2><p>The V21 data has not been generated. Run <code>python3 tools/v21/web.py</code>.</p>'); return; }
  const fly = sub === 'fly';
  const rep = sub === 'replay';
  const demo = DEMOS.find((d) => d.id === sub) || DEMOS[0];
  html(el, `
    <div class="twin">
      <div class="twin-head">
        <div>
          <p class="eyebrow">Ryujin V21 mini · digital twin · G8</p>
          <h2>Protections against pilot mistakes</h2>
          <p class="lede-s">Each demo flies the same stick inputs twice from the same start: the solid aircraft with the protections in the <a href="#docs/v21-pilot-error-protections">bench param file</a>, the red ghost with none. ${badge('ESTIMATE')} A teaching model of the G5 aircraft with ArduPilot's control structure and parameter values, not ArduPilot itself; nothing here has flown.</p>
        </div>
        <div class="seg" role="group" aria-label="Twin mode">
          <button data-go="${esc(demo.id)}" aria-pressed="${!fly && !rep}">Demos</button><button data-go="fly" aria-pressed="${fly}">Fly it</button><button data-go="replay" aria-pressed="${rep}">Replay a log</button>
        </div>
      </div>
      <div class="twin-grid">
        <div class="twin-stage">
          <canvas class="twin-3d" aria-label="3D replay of the digital twin"></canvas>
          <canvas class="twin-hud" aria-hidden="true"></canvas>
          <div class="twin-tags"></div>
          <div class="twin-bar">
            <button class="btn" data-act="play" aria-label="Play or pause">Pause</button>
            <input type="range" class="twin-scrub" min="0" max="1000" value="0" aria-label="Replay time">
            <span class="twin-time num">0.0 s</span>
            <select class="twin-speed" aria-label="Replay speed"><option value="0.25">¼×</option><option value="0.5">½×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="5">5×</option></select>
          </div>
        </div>
        <aside class="twin-side">${fly ? flyPanel() : rep ? replayPanel() : demoPanel(demo)}</aside>
      </div>
      <div class="twin-plots">
        <figure><canvas class="plot" data-plot="0"></canvas><figcaption class="small muted plot-cap0"></figcaption></figure>
        <figure><canvas class="plot" data-plot="1"></canvas><figcaption class="small muted plot-cap1"></figcaption></figure>
      </div>
      ${explainer(D)}
    </div>`);
  $$(el, '[data-go]').forEach((b) => b.addEventListener('click', () => { location.hash = `#v21/${b.dataset.go}`; }));
  if (rep) { setupReplay(ctx, el, D); return; }
  start(ctx, el, D, fly ? null : demo).catch((e) => {
    const s = $(el, '.twin-stage');
    if (s) s.insertAdjacentHTML('beforeend', `<p class="twin-err">3D view unavailable: ${esc(e.message)}. The plots still work.</p>`);
  });
}

function demoPanel(demo) {
  return `
    <ol class="twin-demos">${DEMOS.map((d, i) => `<li><a href="#v21/${d.id}" ${d.id === demo.id ? 'aria-current="true"' : ''}><span class="num">${i + 1}</span>${esc(d.title)}</a></li>`).join('')}</ol>
    <h3>${esc(demo.title)}</h3>
    <p class="small"><b>The mistake.</b> ${esc(demo.what)}</p>
    <p class="small"><b>The protection.</b> ${esc(demo.how)}</p>
    <div class="twin-legend small"><span><i class="sw on"></i>Protections on</span><span><i class="sw off"></i>Off (ghost)</span></div>
    <div class="twin-events"></div>`;
}

function flyPanel() {
  const modes = ['MANUAL', 'FBWA', 'QHOVER', 'QLAND', 'QRTL'];
  return `
    <p class="small">Keyboard: <kbd>W</kbd>/<kbd>S</kbd> throttle, <kbd>A</kbd>/<kbd>D</kbd> yaw, arrow keys roll and pitch (they spring back to centre like a real stick), <kbd>Space</kbd> arm. A gamepad works too (left stick throttle/yaw, right stick roll/pitch). Click the 3D view first.</p>
    <label class="check"><input type="checkbox" data-k="protect" checked><span><b>Protections on</b> <span class="muted small">the G8 bench param set</span></span></label>
    <div class="row"><button class="btn primary" data-k="arm">Arm</button><button class="btn" data-k="reset-air">Reset: hover 3 m</button><button class="btn" data-k="reset-water">Reset: on the water</button><button class="btn" data-k="reset-fw">Reset: wing-borne</button></div>
    <div class="seg twin-modes" role="group" aria-label="Flight mode">${modes.map((m) => `<button data-mode="${m}">${m}</button>`).join('')}</div>
    <label class="check"><input type="checkbox" data-k="water"><span>Water switch (RC7) <span class="muted small">turns on the water gate</span></span></label>
    <div class="field"><label>Waves <span class="num" data-v="wave"></span><input type="range" data-k="wave" min="0" max="100" value="10"></label></div>
    <label class="check"><input type="checkbox" data-k="waveknown" checked><span>Pilot entered the wave height <span class="muted small">(RYW_WAVE_MM; unknown = NO-GO)</span></span></label>
    <div class="field"><label>Wind <span class="num" data-v="wind"></span><input type="range" data-k="wind" min="0" max="10" step="0.5" value="0"></label></div>
    <div class="field"><label>Gusts <span class="num" data-v="gust"></span><input type="range" data-k="gust" min="0" max="4" step="0.5" value="0"></label></div>
    <div class="field"><label>Battery at reset <span class="num" data-v="batt"></span><input type="range" data-k="batt" min="20" max="100" value="90"></label></div>
    <label class="check"><input type="checkbox" data-k="rc"><span>Radio link lost</span></label>
    <label class="check"><input type="checkbox" data-k="leak"><span>Leak sensor wet</span></label>
    <div class="twin-readout small num"></div>
    <div class="twin-events"></div>`;
}

function replayPanel() {
  return `
    <p class="small">Load a replay file made from a flight log: <code>python3 tools/v21/g7_log.py LOG.bin --replay replay.json</code>. The twin flies the logged stick inputs and mode changes; the measured attitude is drawn beside it. Where the two part, the model is wrong (or the log is). ${badge('ESTIMATE')}</p>
    <div class="field"><label>Replay file (.json) <input type="file" accept=".json,application/json" data-k="replay-file"></label></div>
    <label class="check"><input type="checkbox" data-k="replay-water" checked><span>Starts on the water <span class="muted small">(untick for a ground or hand launch)</span></span></label>
    <div class="twin-legend small"><span><i class="sw on"></i>Twin, protections on</span><span><i class="sw off"></i>Twin, off</span><span><i class="sw" style="background:var(--ink)"></i>Measured</span></div>
    <div class="twin-readout small num" data-v="replay-stats"><span class="muted">No file loaded.</span></div>
    <div class="twin-events"></div>`;
}

function setupReplay(ctx, el, D) {
  const input = $(el, '[data-k="replay-file"]');
  const water = $(el, '[data-k="replay-water"]');
  const out = $(el, '[data-v="replay-stats"]');
  let file = null;
  const run = async () => {
    if (!file) return;
    let log;
    try { log = JSON.parse(await file.text()); } catch (e) { out.innerHTML = `<span class="ev bad">Not a JSON file: ${esc(e.message)}</span>`; return; }
    let on; let off;
    try {
      on = replayLog(D, log, { protect: true, onWater: water.checked });
      off = replayLog(D, log, { protect: false, onWater: water.checked });
    } catch (e) { out.innerHTML = `<span class="ev bad">${esc(e.message)}</span>`; return; }
    const v = (x, u) => (x == null ? '<span class="muted">not in the log</span>' : `${fmt(x, 1)} ${u}`);
    out.innerHTML = `<p><b>Twin (on) against the log, RMS:</b> roll ${v(on.rmsRollDeg, '°')}, pitch ${v(on.rmsPitchDeg, '°')}, current ${v(on.rmsCurrA, 'A')}</p>`
      + (on.mapped.length ? `<p>Modes mapped: ${on.mapped.map(esc).join(', ')}</p>` : '')
      + (on.notes.length ? `<ul class="plist">${on.notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul>` : '');
    stop();
    await start(ctx, el, D, { id: 'replay', title: file.name, channel: 'replay', env: { wave: 0 } }, [on, off]).catch((e) => {
      const s = $(el, '.twin-stage');
      if (s) s.insertAdjacentHTML('beforeend', `<p class="twin-err">3D view unavailable: ${esc(e.message)}. The plots still work.</p>`);
    });
  };
  input.addEventListener('change', () => { file = input.files[0] || null; run(); });
  water.addEventListener('change', run);
}

function explainer(D) {
  const p = D.params;
  const rows = [
    ['Command shaping', 'Q_A_INPUT_TC', `${p.Q_A_INPUT_TC} s`, 'The stick sets a target the attitude follows along a smooth curve (a square-root controller: proportional near the target, acceleration-limited further out), so a slammed stick becomes a fast but bounded lean.'],
    ['', 'Q_A_RATE_R/P/Y_MAX', `${p.Q_A_RATE_R_MAX} / ${p.Q_A_RATE_P_MAX} / ${p.Q_A_RATE_Y_MAX} deg/s`, 'Rate limits on that target.'],
    ['', 'Q_A_ACC_R/P/Y_MAX', `${p.Q_A_ACC_R_MAX} / ${p.Q_A_ACC_P_MAX} / ${p.Q_A_ACC_Y_MAX} deg/s²`, 'Acceleration limits: together with the rate limits, a jerk-bounded trajectory the motors can follow without saturating.'],
    ['', 'Q_PLT_Y_RATE, _TC', `${p.Q_PLT_Y_RATE} deg/s, ${p.Q_PLT_Y_RATE_TC} s`, 'Yaw rate limit and its first-order filter.'],
    ['', 'Q_PILOT_SPD_UP/DN, ACCEL_Z', `${p.Q_PILOT_SPD_UP} / ${p.Q_PILOT_SPD_DN} m/s, ${p.Q_PILOT_ACCEL_Z} m/s²`, 'In a hover the throttle asks for a climb rate (a velocity loop), not thrust.'],
    ['Envelope limits', 'Q_A_ANGLE_MAX, Q_P_ANGLE_MAX', `${p.Q_A_ANGLE_MAX}°, ${p.Q_P_ANGLE_MAX}°`, 'Hard lean limits in VTOL (all modes, and position-controlled modes).'],
    ['', 'ROLL_LIMIT_DEG, PTCH_LIM_MAX/MIN_DEG', `${p.ROLL_LIMIT_DEG}°, +${p.PTCH_LIM_MAX_DEG}° / ${p.PTCH_LIM_MIN_DEG}°`, 'Bank and pitch limits in the stabilised fixed-wing modes.'],
    ['', 'STALL_PREVENTION', p.STALL_PREVENTION ? 'on' : 'off', 'Bank limit from the load factor the wing can give at this airspeed: cos(bank) ≥ (AIRSPEED_MIN / V)².'],
    ['', 'THR_SLEWRATE', `${p.THR_SLEWRATE} %/s`, 'A slammed EDF throttle ramps over 2 s.'],
    ['Assist', 'Q_ASSIST_SPEED / ANGLE / ALT / DELAY', `${p.Q_ASSIST_SPEED} m/s, ${p.Q_ASSIST_ANGLE}°, ${p.Q_ASSIST_ALT} m, ${p.Q_ASSIST_DELAY} s`, 'The lift fans catch a slow, upset or low fixed-wing aircraft.'],
    ['', 'Q_TRANS_FAIL, _ACT', `${p.Q_TRANS_FAIL} s, QRTL`, 'A forward transition that does not finish is abandoned.'],
    ['Self-protection', 'FENCE_ALT_MAX, FENCE_RADIUS', `${p.FENCE_ALT_MAX} m, ${p.FENCE_RADIUS} m`, 'Fly too high or too far and it comes home (RTL, QRTL near home).'],
    ['', 'THR_FAILSAFE, FS_SHORT/LONG_ACTN', 'on, CIRCLE / RTL', 'Radio lost: circle, then come home (QLAND in a VTOL mode in this model; check the exact rule on the bench).'],
    ['', 'BATT_LOW_MAH, BATT_CRT_MAH', `${p.BATT_LOW_MAH} / ${p.BATT_CRT_MAH} mAh`, 'Low battery: RTL. Critical: QLAND.'],
    ['Water', 'RYW_* (ryujin_water.lua)', `wind ${p.RYW_WIND_MAX} m/s, waves ${p.RYW_WAVE_MAX} mm, battery ${p.RYW_BATT_MIN} %`, 'No arming and no VTOL mode on the water on NO-GO; the EDF capped to taxi speed; with the radio lost on the water, the EDF idles.'],
  ];
  return `
    <details class="twin-explain" open><summary><h2>What each layer does</h2></summary>
      <div class="table-wrap"><table class="cmp"><thead><tr><th>Layer</th><th>Parameter</th><th>Bench value</th><th>What it does</th></tr></thead><tbody>
      ${rows.map(([a, b, c, d]) => `<tr><td>${esc(a)}</td><td><code>${esc(b)}</code></td><td class="num">${esc(c)}</td><td class="small">${esc(d)}</td></tr>`).join('')}
      </tbody></table></div>
      <p class="small">Behind them the stabiliser itself: an attitude P loop (4.5 /s) feeding a rate PID with a filtered derivative and an anti-windup integrator, a motor mixer that gives up yaw before roll and pitch when a fan saturates, and speed-scaled control surfaces in forward flight. Parameter names, units and ranges were checked against the ArduPilot Plane 4.8 parameter reference; the values are first-flight ESTIMATES in <code>config/ardupilot/ryujin_v21_mini_BENCH_ONLY.param</code>. The aircraft numbers come from G5 (${fmt(D.mass_kg * 1000)} g, lift T/W ${fmt(D.tw_lift, 2)}, static margin ${fmt(D.static_margin_pct, 1)} %); its aerodynamics, inertias and hull dynamics are ESTIMATES that G7 replaces with measurements.</p>
      <p class="small"><b>Found by the twin:</b> the G6 vane mixer added its aft bias in every VTOL mode, which in a hover pushed a drifting aircraft forward harder the faster it drifted. G8 limits the bias to assisted flight and transitions (UNCONFIRMED until the bench shows <code>in_assisted_flight</code> covers the transition).</p>
    </details>`;
}

// ---------------------------------------------------------------------------------------------------------------

function stop() {
  if (!live) return;
  live.dead = true;
  cancelAnimationFrame(live.raf);
  live.cleanup?.forEach((f) => f());
  live.renderer?.dispose();
  live = null;
}

async function start(ctx, el, D, demo, preRuns = null) {
  const me = { dead: false, cleanup: [] };
  live = me;
  const runs = preRuns || (demo ? [runDemo(D, demo, true), runDemo(D, demo, false)] : null);
  const state = { t: 0, playing: true, speed: 1, fly: null };
  if (runs) {
    renderEvents(el, runs);
    drawPlots(el, demo, runs, 0);
  }

  const THREE = await import('three');
  const { OrbitControls } = await import('three/addons/controls/OrbitControls.js');
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const { MeshoptDecoder } = await import('three/addons/libs/meshopt_decoder.module.js');
  if (me.dead) return;
  const canvas = $(el, '.twin-3d');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  me.renderer = renderer;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NeutralToneMapping;
  const scene = new THREE.Scene();
  const sky = new THREE.Color(0xbcd3e6);
  scene.background = sky;
  scene.fog = new THREE.Fog(sky, 40, 260);
  const camera = new THREE.PerspectiveCamera(40, 1, 0.05, 2000);
  camera.position.set(-3.2, 1.6, 2.4);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.minDistance = 0.8;
  controls.maxDistance = 120;
  scene.add(new THREE.HemisphereLight(0xeef6ff, 0x30506a, 1.4));
  const sun = new THREE.DirectionalLight(0xfff3e0, 2.2);
  sun.position.set(-20, 40, 10);
  scene.add(sun);

  // water: a dense patch that follows the aircraft (for waves) over a big flat lake
  const lake = new THREE.Mesh(new THREE.CircleGeometry(900, 64), new THREE.MeshStandardMaterial({ color: 0x2f6d8a, roughness: 0.35, metalness: 0.1 }));
  lake.rotation.x = -Math.PI / 2;
  lake.position.y = -0.004;
  scene.add(lake);
  const patchGeo = new THREE.PlaneGeometry(14, 14, 112, 112);
  patchGeo.rotateX(-Math.PI / 2);
  const patch = new THREE.Mesh(patchGeo, new THREE.MeshStandardMaterial({ color: 0x2f6d8a, roughness: 0.35, metalness: 0.1 }));
  scene.add(patch);
  // home pad, fence ring, a few buoys for scale and motion
  const pad = new THREE.Mesh(new THREE.RingGeometry(0.5, 0.6, 40), new THREE.MeshBasicMaterial({ color: 0xffc04a, side: THREE.DoubleSide }));
  pad.rotation.x = -Math.PI / 2; pad.position.y = 0.01;
  scene.add(pad);
  const fenceR = D.params.FENCE_RADIUS;
  const ring = new THREE.Mesh(new THREE.TorusGeometry(fenceR, 0.25, 6, 180), new THREE.MeshBasicMaterial({ color: 0xff6040 }));
  ring.rotation.x = Math.PI / 2;
  scene.add(ring);
  const buoyGeo = new THREE.SphereGeometry(0.12, 16, 12);
  const buoyMat = new THREE.MeshStandardMaterial({ color: 0xf2f2f2 });
  for (let i = 0; i < 40; i += 1) {
    const b = new THREE.Mesh(buoyGeo, buoyMat);
    const a = i * 2.39996; const r = 4 + i * 3.4;
    b.position.set(r * Math.cos(a), 0.03, r * Math.sin(a));
    scene.add(b);
  }

  // the aircraft: model mm (x aft, y right, z up) -> body FRD -> three (x north, y up, z east)
  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  const gltf = await loader.loadAsync('models/v21_mini.glb');
  if (me.dead) { renderer.dispose(); return; }
  const cg = [D.cg_x_mm, 0, -9.9];
  const makeCraft = (ghost) => {
    const outer = new THREE.Group();
    const inner = ghost ? gltf.scene.clone(true) : gltf.scene;
    const m = new THREE.Matrix4().set(-1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1)
      .multiply(new THREE.Matrix4().makeScale(0.001, 0.001, 0.001))
      .multiply(new THREE.Matrix4().makeTranslation(-cg[0], -cg[1], -cg[2]));
    inner.matrixAutoUpdate = false;
    inner.matrix.copy(m);
    const fans = [];
    inner.traverse((o) => {
      if (o.isMesh && ghost) {
        o.material = new THREE.MeshStandardMaterial({ color: 0xff4a3a, transparent: true, opacity: 0.38, depthWrite: false, roughness: 0.6 });
      }
    });
    // spin the fan blades about their own centres
    const names = ['front_R', 'front_L', 'rear_R', 'rear_L'];
    for (const n of names) {
      const blade = inner.getObjectByName(`fan_blades_${n}`);
      if (!blade) { fans.push(null); continue; }
      const box = new THREE.Box3().setFromObject(blade);
      const inv = new THREE.Matrix4().copy(inner.matrixWorld).invert();
      const c = box.getCenter(new THREE.Vector3()).applyMatrix4(inv);
      const pivot = new THREE.Group();
      pivot.position.copy(c);
      blade.parent.add(pivot);
      blade.position.sub(c);
      pivot.add(blade);
      fans.push(pivot);
    }
    outer.add(inner);
    scene.add(outer);
    const trail = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: ghost ? 0xff4a3a : 0x1b3a5a, transparent: true, opacity: ghost ? 0.5 : 0.8 }));
    trail.frustumCulled = false;
    scene.add(trail);
    return { outer, fans, trail, spin: [0, 0, 0, 0] };
  };
  const craft = makeCraft(false);
  const ghost = runs ? makeCraft(true) : null;

  const place = (c, row) => {
    c.outer.position.set(row.x, row.alt, row.y);
    const [w, x, y, z] = row.q;
    c.outer.quaternion.set(x, -z, y, w);
  };
  const setTrail = (c, rows, upto) => {
    const pts = [];
    const step = Math.max(1, Math.floor(upto / 400));
    for (let i = 0; i <= upto; i += step) pts.push(rows[i].x, rows[i].alt, rows[i].y);
    c.trail.geometry.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  };

  // resize
  const stage = $(el, '.twin-stage');
  const hud = $(el, '.twin-hud');
  const resize = () => {
    const r = stage.getBoundingClientRect();
    const h = Math.max(260, r.width * 0.56);
    canvas.style.height = `${h}px`;
    renderer.setSize(r.width, h, false);
    camera.aspect = r.width / h;
    camera.updateProjectionMatrix();
    hud.width = r.width * devicePixelRatio; hud.height = h * devicePixelRatio;
    hud.style.height = `${h}px`;
  };
  resize();
  const ro = new ResizeObserver(resize);
  ro.observe(stage);
  me.cleanup.push(() => ro.disconnect());

  // controls bar
  const scrub = $(el, '.twin-scrub');
  const tlabel = $(el, '.twin-time');
  const playBtn = $(el, '[data-act="play"]');
  $(el, '.twin-speed').addEventListener('change', (e) => { state.speed = +e.target.value; });
  playBtn.addEventListener('click', () => { state.playing = !state.playing; playBtn.textContent = state.playing ? 'Pause' : 'Play'; });
  const dur = runs ? runs[0].rows[runs[0].rows.length - 1].t : 0;
  if (runs) scrub.addEventListener('input', () => { state.t = (scrub.value / 1000) * dur; state.playing = false; playBtn.textContent = 'Play'; });
  else { scrub.hidden = true; $(el, '.twin-speed').hidden = true; }

  if (!runs) state.fly = setupFly(el, D, me);

  const tags = $(el, '.twin-tags');
  let last = performance.now();
  const camOff = new THREE.Vector3();
  const prevTarget = new THREE.Vector3();
  const frame = (now) => {
    if (me.dead || !canvas.isConnected || el.closest('[hidden]')) { if (live === me) stop(); return; }
    const dtw = Math.max(0, Math.min(0.1, (now - last) / 1000));
    last = now;
    let rowOn; let rowOff = null; let idx = 0;
    if (runs) {
      if (state.playing) state.t += dtw * state.speed;
      if (state.t > dur + 1.5) state.t = 0;
      const tt = Math.min(state.t, dur);
      idx = Math.min(runs[0].rows.length - 1, Math.round(tt * 50));
      rowOn = runs[0].rows[idx];
      rowOff = runs[1].rows[Math.min(runs[1].rows.length - 1, idx)];
      scrub.value = String(Math.round((tt / dur) * 1000));
      tlabel.textContent = `${fmt(tt, 1)} s`;
      place(craft, rowOn); setTrail(craft, runs[0].rows, idx);
      place(ghost, rowOff); setTrail(ghost, runs[1].rows, Math.min(runs[1].rows.length - 1, idx));
      if (now - (state.lastPlot || 0) > 120) { drawPlots(el, demo, runs, tt); state.lastPlot = now; highlightEvents(el, tt); }
    } else {
      rowOn = state.fly.tick(dtw * state.speed, state.playing);
      place(craft, rowOn);
      setTrail(craft, state.fly.rows, state.fly.rows.length - 1);
      tlabel.textContent = `${fmt(rowOn.t, 1)} s`;
      if (now - (state.lastPlot || 0) > 150) { drawLive(el, state.fly.rows); state.lastPlot = now; }
    }
    // fans spin with thrust (visual rate, not the real rpm)
    const spin = (c, row) => c.fans.forEach((f, i) => { if (!f) return; c.spin[i] += (row.fans[i] > 0.01 ? 18 + 50 * row.fans[i] : 0) * dtw * (i % 3 === 0 ? 1 : -1); f.rotation.z = c.spin[i]; });
    spin(craft, rowOn);
    if (ghost && rowOff) spin(ghost, rowOff);
    // waves on the patch around the aircraft (the same surface the twin floats on)
    const wave = runs ? (demo.env?.wave || 0) : state.fly.twin.env.wave;
    const tw = rowOn.t;
    patch.position.set(Math.round(rowOn.x), 0, Math.round(rowOn.y));
    const pos = patchGeo.attributes.position;
    for (let i = 0; i < pos.count; i += 1) {
      const x = pos.getX(i) + patch.position.x;
      pos.setY(i, wave > 0 ? -(wave / 2) * Math.sin(2 * Math.PI * (x / 1.2 - tw / 0.85)) : 0);
    }
    pos.needsUpdate = true;
    // chase camera: keep the user's orbit offset, follow the aircraft
    const target = craft.outer.position;
    camOff.subVectors(camera.position, controls.target);
    controls.target.lerp(target, 0.25);
    camera.position.copy(controls.target).add(camOff);
    if (target.y > 8 && camOff.length() < 6) camera.position.add(camOff.clone().normalize().multiplyScalar(0.06));
    prevTarget.copy(target);
    controls.update();
    renderer.render(scene, camera);
    drawHud(hud, rowOn, rowOff);
    tags.innerHTML = tagLine(rowOn, rowOff);
    me.raf = requestAnimationFrame(frame);
  };
  me.raf = requestAnimationFrame(frame);
}

function tagLine(a, b) {
  const t = (row, cls) => {
    const flags = [row.mode, row.assist ? 'ASSIST' : '', row.trans ? 'TRANSITION' : '', row.water === 2 ? (!row.prot ? 'WATER NO-GO (ignored)' : 'WATER NO-GO') : row.water === 1 ? 'WATER GO' : '',
      row.stalled ? 'STALL' : '', row.wet ? 'FAN EXIT WET' : '', row.spray ? 'SPRAY ZONE' : '', row.capsized ? 'CAPSIZED' : '', row.crashed ? 'HIT THE WATER' : ''].filter(Boolean);
    return `<div class="tag ${row.prot ? 'on' : 'off'}"><b>${row.prot ? 'ON' : 'OFF'}</b> ${flags.map((f) => `<span>${esc(f)}</span>`).join('')}<span class="num">${fmt(row.alt, 1)} m · ${fmt(row.airspeed, 1)} m/s · ${fmt(row.batt)} %</span></div>`;
  };
  return t(a, 'on') + (b ? t(b, 'off') : '');
}

// artificial horizon: actual attitude, with the shaped target (cyan) and the raw stick request (amber)
function drawHud(cv, a, b) {
  const g = cv.getContext('2d');
  const W = cv.width; const H = cv.height; const k = devicePixelRatio;
  g.clearRect(0, 0, W, H);
  const R = 62 * k; const cx = W - R - 16 * k; const cy = R + 16 * k;
  g.save();
  g.beginPath(); g.arc(cx, cy, R, 0, 2 * Math.PI); g.clip();
  g.translate(cx, cy);
  g.rotate((-a.roll * Math.PI) / 180);
  const pp = (a.pitch * R) / 40;
  g.fillStyle = '#5d9fd1'; g.fillRect(-2 * R, -2 * R + pp, 4 * R, 2 * R);
  g.fillStyle = '#7b5a3c'; g.fillRect(-2 * R, pp, 4 * R, 2 * R);
  g.strokeStyle = 'rgba(255,255,255,0.8)'; g.lineWidth = k;
  for (const d of [-20, -10, 10, 20]) { const y = pp - (d * R) / 40; g.beginPath(); g.moveTo(-R * 0.25, y); g.lineTo(R * 0.25, y); g.stroke(); }
  g.restore();
  // the fixed aircraft symbol rotated to show where each layer wants the wings
  const wings = (roll, pitch, col, w, dash) => {
    g.save(); g.translate(cx, cy); g.rotate(((roll - a.roll) * Math.PI) / 180);
    g.strokeStyle = col; g.lineWidth = w * k; g.setLineDash(dash.map((d) => d * k));
    const y = ((a.pitch - pitch) * R) / 40;
    g.beginPath(); g.moveTo(-R * 0.75, y); g.lineTo(-R * 0.2, y); g.moveTo(R * 0.2, y); g.lineTo(R * 0.75, y); g.stroke();
    g.restore();
  };
  if (a.reqRoll !== undefined) wings(a.reqRoll, a.reqPitch, '#ffb020', 2, [5, 4]);
  if (a.tgtRoll !== undefined) wings(a.tgtRoll, a.tgtPitch, '#3ee0ff', 2.5, []);
  g.save(); g.translate(cx, cy); g.strokeStyle = '#ffffff'; g.lineWidth = 3 * k;
  g.beginPath(); g.moveTo(-R * 0.6, 0); g.lineTo(-R * 0.15, 0); g.lineTo(0, R * 0.1); g.lineTo(R * 0.15, 0); g.lineTo(R * 0.6, 0); g.stroke(); g.restore();
  g.strokeStyle = 'rgba(255,255,255,0.9)'; g.lineWidth = 2 * k; g.beginPath(); g.arc(cx, cy, R, 0, 2 * Math.PI); g.stroke();
  g.fillStyle = 'rgba(10,22,32,0.66)';
  g.beginPath(); g.roundRect(cx - 70 * k, cy + R + 4 * k, 140 * k, (b ? 44 : 30) * k, 4 * k); g.fill();
  g.font = `${11 * k}px system-ui, sans-serif`; g.fillStyle = '#ffffff'; g.textAlign = 'center';
  g.fillText(`roll ${Math.round(a.roll)}° pitch ${Math.round(a.pitch)}°`, cx, cy + R + 14 * k);
  g.fillStyle = '#ffb020'; g.fillText('- - stick', cx - 30 * k, cy + R + 29 * k);
  g.fillStyle = '#3ee0ff'; g.fillText('— target', cx + 30 * k, cy + R + 29 * k);
  if (b) { g.fillStyle = '#ff9a8c'; g.fillText(`ghost roll ${Math.round(b.roll)}°`, cx, cy + R + 43 * k); }
}

// ---------------------------------------------------------------------------------------------------------------
// plots

function plotAxes(cv, series, { t0, t1, ylab, now, ymin, ymax }) {
  const r = cv.getBoundingClientRect();
  const k = devicePixelRatio;
  cv.width = Math.max(300, r.width) * k; cv.height = 200 * k;
  const g = cv.getContext('2d');
  const W = cv.width; const H = cv.height; const L = 46 * k; const B = 22 * k; const T = 10 * k; const Rr = 10 * k;
  let lo = ymin ?? Infinity; let hi = ymax ?? -Infinity;
  for (const s of series) for (const p of s.pts) if (Number.isFinite(p[1])) { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); }
  if (!Number.isFinite(lo)) { lo = -1; hi = 1; }
  if (hi - lo < 1e-6) { hi += 1; lo -= 1; }
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  const X = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - Rr);
  const Y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const css = getComputedStyle(document.documentElement);
  const ink = css.getPropertyValue('--ink-soft').trim() || '#666';
  const rule = css.getPropertyValue('--rule').trim() || '#ccc';
  g.font = `${10 * k}px system-ui, sans-serif`; g.fillStyle = ink; g.strokeStyle = rule; g.lineWidth = k;
  const nice = (span) => { const p = 10 ** Math.floor(Math.log10(span / 4)); return [1, 2, 5, 10].map((m) => m * p).find((s) => span / s <= 6); };
  const ys = nice(hi - lo);
  for (let v = Math.ceil(lo / ys) * ys; v <= hi; v += ys) { g.beginPath(); g.moveTo(L, Y(v)); g.lineTo(W - Rr, Y(v)); g.stroke(); g.textAlign = 'right'; g.fillText(fmt(v, ys < 1 ? 1 : 0), L - 4 * k, Y(v) + 3 * k); }
  const xs = nice(t1 - t0);
  for (let t = Math.ceil(t0 / xs) * xs; t <= t1; t += xs) { g.textAlign = 'center'; g.fillText(`${fmt(t, xs < 1 ? 1 : 0)} s`, X(t), H - 6 * k); }
  g.save(); g.translate(11 * k, (H - B) / 2); g.rotate(-Math.PI / 2); g.textAlign = 'center'; g.fillText(ylab, 0, 0); g.restore();
  for (const s of series) {
    g.strokeStyle = s.color; g.lineWidth = (s.w || 1.6) * k; g.setLineDash((s.dash || []).map((d) => d * k));
    g.beginPath();
    let pen = false;
    for (const [t, v] of s.pts) { if (!Number.isFinite(v)) { pen = false; continue; } const x = X(t); const y = Y(Math.max(lo, Math.min(hi, v))); if (pen) g.lineTo(x, y); else g.moveTo(x, y); pen = true; }
    g.stroke();
  }
  g.setLineDash([]);
  if (now !== undefined) { g.strokeStyle = ink; g.lineWidth = k; g.beginPath(); g.moveTo(X(now), T); g.lineTo(X(now), H - B); g.stroke(); }
}

const COL = { on: '#1d5f99', off: '#d8402f', tgt: '#00a4c8', req: '#e09a10' };

function drawPlots(el, demo, runs, now) {
  if (demo.channel === 'replay') { drawReplay(el, runs, now); return; }
  const ch = CHANNELS[demo.channel];
  const [on, off] = runs;
  const s = [];
  for (const [key, label, kind] of ch.keys) {
    if (kind === 'req') s.push({ color: COL.req, dash: [5, 4], w: 1.4, pts: on.rows.map((r) => [r.t, r[key] ?? NaN]), label });
    if (kind === 'tgt') s.push({ color: COL.tgt, w: 1.6, pts: on.rows.map((r) => [r.t, r[key]]), label: `${label} (on)` });
    if (kind === 'act') { s.push({ color: COL.off, w: 1.8, pts: off.rows.map((r) => [r.t, r[key]]), label: `${label} (off)` }); s.push({ color: COL.on, w: 2.2, pts: on.rows.map((r) => [r.t, r[key]]), label: `${label} (on)` }); }
  }
  const t1 = on.rows[on.rows.length - 1].t;
  const cv0 = $(el, '[data-plot="0"]'); const cv1 = $(el, '[data-plot="1"]');
  if (!cv0) return;
  const cap = demo.channel === 'alt' || demo.channel === 'speed' ? null : 'alt';
  const y0 = demo.channel === 'alt' ? { ymin: 0, ymax: Math.min(80, Math.max(...on.rows.map((r) => r.alt)) * 1.3 + 1) } : {};
  plotAxes(cv0, s, { t0: 0, t1, ylab: ch.label, now, ...y0 });
  $(el, '.plot-cap0').innerHTML = legend(s) + (demo.channel === 'alt' ? ' <span class="muted">(clipped at 80 m)</span>' : '');
  const second = cap === 'alt' ? 'alt' : demo.channel === 'speed' ? 'airspeed' : 'gs';
  const lab = second === 'alt' ? 'Height, m' : second === 'gs' ? 'Speed over the water, m/s' : 'Air speed, m/s';
  const s2 = [{ color: COL.off, w: 1.8, pts: off.rows.map((r) => [r.t, r[second]]), label: 'off' }, { color: COL.on, w: 2.2, pts: on.rows.map((r) => [r.t, r[second]]), label: 'on' }];
  plotAxes(cv1, s2, { t0: 0, t1, ylab: lab, now, ...(second === 'alt' ? { ymin: 0, ymax: Math.min(80, Math.max(...on.rows.map((r) => r.alt), ...off.rows.map((r) => r.alt)) + 1) } : {}) });
  $(el, '.plot-cap1').innerHTML = `${legend(s2)}${second === 'alt' ? ' <span class="muted">(clipped at 80 m; 0 = the water)</span>' : ''}`;
}

const legend = (s) => s.map((x) => `<span class="lg"><i style="background:${x.color}${x.dash ? ';opacity:.7' : ''}"></i>${esc(x.label)}</span>`).join(' ');

function drawLive(el, rows) {
  const cv0 = $(el, '[data-plot="0"]'); const cv1 = $(el, '[data-plot="1"]');
  if (!cv0 || !rows.length) return;
  const t1 = rows[rows.length - 1].t; const t0 = Math.max(0, t1 - 12);
  const rr = rows.filter((r) => r.t >= t0);
  const s = [{ color: COL.req, dash: [5, 4], w: 1.4, pts: rr.map((r) => [r.t, r.reqRoll]), label: 'roll stick request' },
    { color: COL.tgt, w: 1.6, pts: rr.map((r) => [r.t, r.tgtRoll]), label: 'shaped target' },
    { color: COL.on, w: 2.2, pts: rr.map((r) => [r.t, r.roll]), label: 'actual roll' }];
  plotAxes(cv0, s, { t0, t1: Math.max(t1, 12), ylab: 'Roll, deg' });
  $(el, '.plot-cap0').innerHTML = legend(s);
  const s2 = [{ color: COL.on, w: 2.2, pts: rr.map((r) => [r.t, r.alt]), label: 'height' }, { color: COL.tgt, w: 1.6, pts: rr.map((r) => [r.t, r.airspeed]), label: 'air speed' }];
  plotAxes(cv1, s2, { t0, t1: Math.max(t1, 12), ylab: 'm, m/s' });
  $(el, '.plot-cap1').innerHTML = legend(s2);
}

function drawReplay(el, runs, now) {
  const [on, off] = runs;
  const cv0 = $(el, '[data-plot="0"]'); const cv1 = $(el, '[data-plot="1"]');
  if (!cv0 || !on.rows.length) return;
  const t1 = on.rows[on.rows.length - 1].t;
  const ink = getComputedStyle(document.documentElement).getPropertyValue('--ink').trim() || '#222';
  const trio = (key, meas, what) => [
    { color: COL.off, w: 1.6, pts: off.rows.map((r) => [r.t, r[key]]), label: `${what}, twin off` },
    { color: COL.on, w: 2.2, pts: on.rows.map((r) => [r.t, r[key]]), label: `${what}, twin on` },
    { color: ink, w: 1.6, dash: [4, 3], pts: on.rows.map((r) => [r.t, r[meas] ?? NaN]), label: `${what}, measured` }];
  const s0 = trio('roll', 'measRoll', 'roll');
  plotAxes(cv0, s0, { t0: 0, t1, ylab: 'Roll, deg', now });
  $(el, '.plot-cap0').innerHTML = legend(s0);
  const s1 = trio('pitch', 'measPitch', 'pitch');
  plotAxes(cv1, s1, { t0: 0, t1, ylab: 'Pitch, deg', now });
  $(el, '.plot-cap1').innerHTML = legend(s1);
}

function renderEvents(el, runs) {
  const host = $(el, '.twin-events');
  if (!host) return;
  const col = (r, name) => `<div><h4>${name}</h4><ul class="plist small">${r.events.length ? r.events.map((e) => `<li data-t="${e.t}" class="ev ${e.sev}"><span class="num">${fmt(e.t, 1)} s</span> ${esc(e.msg)}</li>`).join('') : '<li class="muted">nothing to report</li>'}</ul></div>`;
  host.innerHTML = `<div class="twin-evcols">${col(runs[0], 'On')}${col(runs[1], 'Off')}</div>`;
}
function highlightEvents(el, t) { $$(el, '.twin-events li[data-t]').forEach((li) => li.classList.toggle('past', +li.dataset.t <= t)); }

// ---------------------------------------------------------------------------------------------------------------
// Fly it: the keyboard or a gamepad drives the twin in real time

function setupFly(el, D, me) {
  const panel = $(el, '.twin-side');
  const opts = { protect: true };
  let twin;
  const rows = [];
  const keys = new Set();
  const stick = { roll: 0, pitch: 0, yaw: 0, thr: 0.5 };
  const val = (k) => $(panel, `[data-k="${k}"]`);
  const show = () => {
    $(panel, '[data-v="wave"]').textContent = `${val('wave').value} mm`;
    $(panel, '[data-v="wind"]').textContent = `${val('wind').value} m/s`;
    $(panel, '[data-v="gust"]').textContent = `${val('gust').value} m/s`;
    $(panel, '[data-v="batt"]').textContent = `${val('batt').value} %`;
  };
  const applyEnv = () => {
    Object.assign(twin.env, { wave: +val('wave').value / 1000, waveKnown: val('waveknown').checked, wind: [+val('wind').value, 0], gust: +val('gust').value,
      rcOk: !val('rc').checked, leak: val('leak').checked, waterSwitch: val('water').checked });
    show();
  };
  const reset = (kind) => {
    twin = new Twin(D, { protect: val('protect').checked, seed: 3 });
    applyEnv();
    const batteryPct = +val('batt').value;
    if (kind === 'water') { twin.reset({ onWater: true, mode: 'MANUAL', batteryPct }); stick.thr = 0; }
    else if (kind === 'fw') { twin.reset({ onWater: false, alt: 30, airspeed: 17, mode: 'FBWA', batteryPct }); stick.thr = 0.4; }
    else { twin.reset({ onWater: false, alt: 3, mode: 'QHOVER', batteryPct }); stick.thr = 0.5; }
    rows.length = 0;
    acc = 0;
    syncModes();
  };
  const syncModes = () => $$(panel, '[data-mode]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === twin.mode)));
  $$(panel, 'input').forEach((i) => i.addEventListener('input', () => { if (i.dataset.k === 'protect') { twin.P = new Twin(D, { protect: i.checked }).P; } applyEnv(); }));
  val('arm').addEventListener('click', () => { twin.arm(); });
  val('reset-air').addEventListener('click', () => reset('air'));
  val('reset-water').addEventListener('click', () => reset('water'));
  val('reset-fw').addEventListener('click', () => reset('fw'));
  $$(panel, '[data-mode]').forEach((b) => b.addEventListener('click', () => { twin.setMode(b.dataset.mode); syncModes(); }));
  const kd = (e) => {
    if (!el.isConnected) return;
    if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(e.key) && document.activeElement?.tagName !== 'INPUT') e.preventDefault();
    if (e.key === ' ') { twin.arm(); return; }
    keys.add(e.key.toLowerCase());
  };
  const ku = (e) => keys.delete(e.key.toLowerCase());
  window.addEventListener('keydown', kd);
  window.addEventListener('keyup', ku);
  me.cleanup.push(() => { window.removeEventListener('keydown', kd); window.removeEventListener('keyup', ku); });
  let acc = 0;
  reset('air');
  const readout = $(panel, '.twin-readout');
  let lastEv = 0;
  return {
    get twin() { return twin; },
    rows,
    tick(dtw, playing) {
      // sticks: keys push toward full deflection at a finite rate and spring back to centre when released
      const pad = navigator.getGamepads ? [...navigator.getGamepads()].find(Boolean) : null;
      const k = (a, b) => (keys.has(a) ? 1 : 0) - (keys.has(b) ? 1 : 0);
      const toward = (cur, want, rate) => cur + Math.max(-rate * dtw, Math.min(rate * dtw, want - cur));
      if (pad) {
        const dz = (v) => (Math.abs(v) < 0.06 ? 0 : v);
        stick.yaw = dz(pad.axes[0] || 0); stick.thr = Math.max(0, Math.min(1, 0.5 - dz(pad.axes[1] || 0) / 2));
        stick.roll = dz(pad.axes[2] || 0); stick.pitch = dz(pad.axes[3] || 0);
      } else {
        stick.roll = toward(stick.roll, k('arrowright', 'arrowleft'), 6);
        stick.pitch = toward(stick.pitch, k('arrowdown', 'arrowup') * -1, 6);
        stick.yaw = toward(stick.yaw, k('d', 'a'), 6);
        stick.thr = Math.max(0, Math.min(1, stick.thr + k('w', 's') * 0.6 * dtw));
      }
      if (playing) {
        acc += dtw;
        let n = 0;
        while (acc >= DT && n < 200) { twin.step({ ...stick }); acc -= DT; n += 1; if (Math.round(twin.t / DT) % 8 === 0) rows.push(twin.sample()); }
        if (rows.length > 3000) rows.splice(0, rows.length - 3000);
      }
      const r = twin.sample();
      syncModes();
      readout.innerHTML = `<div>Mode <b>${esc(r.mode)}</b>${r.armed ? '' : ' (disarmed)'} · water ${['off', 'GO', 'NO-GO'][r.water]}</div>
        <div>Sticks: roll ${fmt(stick.roll, 2)} · pitch ${fmt(stick.pitch, 2)} · yaw ${fmt(stick.yaw, 2)} · throttle ${fmt(stick.thr, 2)}</div>
        <div>Fans ${r.fans.map((f) => fmt(f * 100)).join(' / ')} % · EDF ${fmt(r.edf * 100)} % · ${fmt(r.amps)} A</div>`;
      if (twin.events.length !== lastEv) {
        lastEv = twin.events.length;
        const host = $(panel, '.twin-events');
        host.innerHTML = `<ul class="plist small">${twin.events.slice(-8).reverse().map((e) => `<li class="ev ${e.sev}"><span class="num">${fmt(e.t, 1)} s</span> ${esc(e.msg)}</li>`).join('')}</ul>`;
      }
      return r;
    },
  };
}

