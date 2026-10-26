// V19 web data: every variant the viewer can switch to has its model, its moves name real V18 parts,
// and the recommended variant passes.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';

const root = new URL('..', import.meta.url).pathname;
const j = (p) => JSON.parse(readFileSync(join(root, p), 'utf8'));
const V = j('site/data/variants.json');
const v18 = new Set(j('site/data/parts.json').parts.map((p) => p.name));

test('recommended variant passes', () => {
  const r = V.variants[V.recommended];
  assert.ok(r.eval.passes, 'gates');
  assert.equal(r.checks.collisions, 0, 'collisions');
});

for (const slug of V.order) {
  test(`variant ${slug} is complete`, () => {
    const v = V.variants[slug];
    assert.ok(existsSync(join(root, 'site/models', `${slug}.glb`)), 'glb');
    for (const n of Object.keys(v.moves)) assert.ok(v18.has(n), `move for unknown part ${n}`);
    for (const n of [...v.hidden, ...v.modified]) assert.ok(v18.has(n), `unknown hidden/modified part ${n}`);
    assert.ok(v.new.length > 0 && v.changes.length > 0);
    assert.ok(v.length_mm >= 810);
  });
}

// V20: two standalone variants (the mini at real size, the full-scale aircraft at 1:10) and the page data
for (const slug of V.order20 || []) {
  test(`V20 variant ${slug} is complete`, () => {
    const v = V.variants[slug];
    assert.ok(v.standalone, 'standalone');
    assert.ok(existsSync(join(root, 'site/models', `${slug}.glb`)), 'glb');
    assert.ok(v.new.length > 20, 'parts');
    // the full scale is a concept study: its flight gates must pass; its packaging gaps are reported, not hidden
    if (slug === 'v20_full') assert.ok(v.eval.hover_ok && v.eval.flight_ok, 'flight gates');
    else assert.ok(v.eval.passes, 'gates');
    assert.ok(Math.abs(v.eval.cg_mm[0] - v.eval.rotor_centroid_x_mm) < 3, 'CG on the fan centre (display mm)');
    assert.ok(v.eye_mm && v.eye_mm.length === 3, 'pilot eye');
  });
}
test('V20 page data', () => {
  const D = j('site/data/v20.json');
  for (const k of ['mini', 'full']) assert.ok(D[k].corridor.every((r) => r.forward_ok && r.hover_ok), `${k} corridor`);
  assert.ok(D.bom.length > 10 && D.pinmap.length >= 12 && D.trade.length > 0);
  // rev C: payload modules, the payload limit, directional stability and the ground uses are in the page data
  assert.ok(D.payload_modules.length >= 3 && D.payload_modules.every((m) => m.grams <= D.mini.payload.max_kg * 1000), 'payload modules within the limit');
  for (const k of ['mini', 'full']) assert.ok(D[k].aero.Cnb > 0 && D[k].aero.sm_gate_pct >= 5, `${k} stability`);
  assert.ok(D.mini.ground.perch_h_half_pack > 1 && D.full.cargo.bay_l > 0, 'missions');
});
