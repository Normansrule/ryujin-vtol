# Changelog

## 0.9.0 - 2026-10-26

V20 rev C: a professional Fury / CCA-style shape, a payload bay, longer endurance, uses on the ground, a cleaner app.

- **Shape:** chined forebody running into the wing leading edge; the wing root blends into the body ahead of and
  behind the fans; low frameless canopy and dorsal spine; a wide aft body carrying the nozzle; a V-tail of two
  all-moving ruddervators replaces rev B's two stabilators and two fins (half the tail area, one servo fewer).
- **One shape at both scales:** the mini is an exact 1:10 model of the full-scale aircraft (6-inch props in 157 mm ducts).
- **Aero model:** the vortex lattice is now non-planar (per-panel normals), so the V-tail's pitch and yaw authority
  come from the solver; added a weathercock-stability check (Cn_beta, V-tail less fuselage). Static margin with the
  louvres shut: mini 5.5 %, full 5.5 % - the 5 % gate now holds at both scales.
- **Mini:** 1,991 g, 4S3P pack (also the nose weight), 27 min hover (rev B 16.8),
  36 min / 38 km cruise (rev B 25.7 min / 28.4 km), payload bay at the CG with four
  modules (camera, mapping, drop, sensor) up to 269 g with the corridor re-checked at that mass, one
  payload port (S9); perch-and-watch, power-bank and a printed balance / charging stand; 45 print pieces.
- **Full scale:** 2,237 kg series hybrid, L/D 7.9, 55 L cargo bay, uncrewed
  cargo version, ground power export; battery fill 42 % (rev B 31 %), turbine-out
  106 % of hover power. The wetted area now counts the blended body once
  (the union of its overlapping parts), which lowers the structure estimate; much of the mass drop from rev B is this
  correction.
- **App:** painted model (medium grey, smoked canopy), the engineering overlay is a toggle on V20, a spec sheet, a
  missions panel with the payload modules and ground uses.

## 0.8.0 - 2026-10-26

V20 rev B: the four lift fans hidden in an F-35-style blended body, one jet that works the way a jet should.

- **Layout:** the fans moved from open holes in a delta into the shoulders of a wide, blended body beside the cockpit,
  under louvres that shut in cruise (top louvres open by fan suction, bottom louvres are servo-driven and double as
  exit vanes). Trapezoidal outer wings, larger all-moving stabilators, canted fins, F-35-style side intakes.
- **Stability:** the gate is now the louvres-shut case (the forward-most neutral point): mini 6.7 % (gate 5 %), stuck-open
  louvres 17.3 %. Found by a planform search with the vortex lattice; open and closed duct lattices both in the model.
- **Engine:** the cruise fan sits near the CG fed by both intakes through internal ducts, with a thrust tube to the
  nozzle; its power now comes from momentum theory with the intake area measured from the outer mould line.
- **Mini:** 1,548 g, 4-inch props, 4S2P Li-ion, EDF behind the battery bay, Depron foam tail (SVG templates) to keep the
  CG on the fan centre without ballast; 35 watertight print pieces; no internal collisions; cruise 18 m/s at 242 W.
- **Full scale:** the mini's proportions do not close at full scale (disk loading), so the full scale widens the
  shoulders for 1.56 m fans: 2,844 kg series hybrid with a nose turbogenerator, 1,263 kW hover, 20 km + 20-minute
  reserve; static margin 1.9 % (fly-by-wire). Open items reported: only 31 % of the battery fits the nose bay;
  turbine failure in a low hover.
- Tools: shape variants (`v20params.use`), internal collision check, foam templates, the ruler measures the gap to
  the nearest edge of the CG window and takes a per-variant static-margin window.

## 0.7.0 - 2026-10-26

V20 "Falcon Jet": a fighter-styled lift + cruise VTOL, drawn once and sized at two scales.

- `tools/v20/`: master shape (`v20params.py`), vortex lattice of the cranked delta with the duct holes and stabilators
  plus Raymer's fuselage correction (`aero.py`), geometry for both scales with the mini's P1S print set (`geometry.py`),
  masses/CG, hover and motor-out power, drag build-up, the transition-corridor search, the full-scale sizing loop and a
  trade study (`sizing.py`), parts list and port map (`bom.py`), report and web data.
- **Mini (1:10, printable):** 1,540 g, four 6-inch props in 156 mm ducts with printed exit vanes, the 64 mm EDF, a
  4S2P 21700 Li-ion pack (90 A) in the nose; CG on the centre of the fans, static margin 5.5 % at 25 % duct blockage,
  level flight at every speed from hover to 23 m/s inside the pack's power limit; 33 watertight printed pieces, all fit
  the P1S; no internal collisions.
- **Full scale (single-seat concept):** 1,540 kg series hybrid - 397 kW turbogenerator behind the seat, 28 kWh battery
  in the nose, fuel in wing tanks - eight motors in four 1.56 m coaxial ducts (any one can fail), 503 kW hover,
  201 km/h cruise, 20 km hop + 20-minute VFR reserve (14 CFR 194.302 / 91.151(b)). A concept study, not a build package.
- Independent review fixes: fan figures of merit (0.48 mini / 0.70 full), cruise-fan efficiencies (0.30 / 0.55), the
  delta's drag due to lift with partial leading-edge suction, a usable CL from the trimmed lattice (stall 13.6 m/s mini),
  the stability gate at 25 % duct blockage, battery power limits in the corridor and in hover headroom, DShot300,
  airspeed parameters from the model, measured prop tip gap, watertight print pieces, an internal collision check.
- Layout findings: four ducts spread through a delta put the CG 15-25 % of the mean chord behind the neutral point; with
  1.06 m ducts the full scale did not close (disk loading over 350 kg/m2); all-electric does not close with the legal
  reserve at any size tried; the trade study covers size, distance and powertrain.
- Web app: a V20 tab with a Mini/Full switch, readouts, the corridor chart, mass breakdown, parts list, port map and the
  trade study; standalone variants in the 3D viewer (the full-scale aircraft shown at 1:10), pilot's-eye view, ruler in metres.
- `make v20`; repo checks for V20; `config/ardupilot/skyforge_v20_mini_BENCH_ONLY.param`.


## 0.6.0 - 2026-10-06

Hover first: the CG on the centre of the four motors, and three looks to choose from.

- The stoop-and-crest layout now balances the hover exactly: the battery slides up to 15 mm in your V18 tray so the CG
  sits where the diagonals between the four lift motors cross, and the search only picks configurations within 3 mm of
  that point.
- Three looks on that layout, all passing every model gate:
  - **V19-F deep stoop (recommended):** outer panels 340 mm back, slim 0.055 m2 crest (45 deg, aspect ratio 8).
    CG 0.2 mm from the motor centre, every motor 24.9-25.1 %, static margin 7.5 / 13.3 %, 2,829 g, 1,228 mm.
  - **V19-S:** 300 mm stoop and the 0.07 m2 crest from 0.5.0, now 1.0 mm from the motor centre.
  - **V19-G:** 300 mm stoop with the slim crest (concept look).
- The crest's leading edge now always crosses the fin tops 10 mm ahead of them, whatever its sweep.
- Web app: a hover frame (the motor rectangle and its diagonals) replaces the rotor bar, so the CG marker visibly sits on
  the crossing; the ruler reads "rotor centre". Screenshots reset the camera between views.


## 0.5.0 - 2026-10-06

V19-S: the four-rotor layout without the big tail.

- New variant V19-S, now the recommendation. It keeps V19-W's four lift motors in your V18 wing wells, the pilot's-eye
  camera and the single EDF, and drops the 0.18 m2 boom tail. Two features take over its job. The outer falcon panels
  and elevons sweep 300 mm back at the wrist (the "stoop"), carried by a swept 10 x 10 carbon spar per side. A 0.07 m2
  falcon crest sits on the tips of your V18 fins, 4 deg leading edge down, with a 30 % elevator on one slim servo.
  The wing group moves 235 mm aft and the battery stays in the V18 tray. Result: 2,832 g (183 g lighter than V19-W),
  1,188 mm long (168 mm shorter), static margin 8.0 / 13.9 %, heaviest motor 25.5 %, no new collisions.
- For the record: a fixed crest (no elevator) gets the margin but needs 16-38 deg of elevon at 16 m/s with the wells
  open, outside the 10 deg gate; the search keeps those rows in the V19 document.
- Fixes: tail incidence and position are now part of the aero cache key; the web viewer maps GLB node names with dots
  back to part names, so the outer servo cassettes follow their panels; F4 is no longer slotted for a removed gear
  crossbar (V19-W).
- Web app and docs: V19-S in the switcher, V19-S gates in TEST_GATES.md (wrist load, crest tufts, crest elevator).


## 0.4.0 - 2026-10-04

V19-W: four rotors in the wings, pilot's-eye camera, one EDF.

- New variant V19-W, now the recommendation. All four lift motors sit in your V18 wing wells, the front pair in the holes
  V19-R closes. The wing group moves 200 mm aft with a 0.18 m2 falcon tail on the EDF outrigger booms. Two short
  under-wing booms carry the rear motors, so the rear crossrail can sit ahead of the D1 intake; the main gear legs bolt to
  the rear motor backing plates, and the gear crossbar goes. Static margin 8.2 %, heaviest motor
  26.2 %, no new collisions.
- Cockpit: the FPV camera moves back to a pilot's eye point (x 120-140, z 44) on a printed pilot-seat mount, under a
  vacuum-formed clear PETG canopy on a printed frame cut from your C1 cover. The GPS moves off the nose (it sat in the
  camera's view) to the H2 hatch. All V19 variants get the cockpit.
- Cruise engine: one Freewing E7206 64 mm EDF stays in the jet bay (1,200 g, 44 A, 142 g). Twin 50 mm fans would draw
  about 80 A and add a second ESC, with no lift redundancy gained; the comparison is in the V19 document.
- The V19-R slug becomes `v19r_boom_rotors`. Large tails are split spanwise so every piece fits the P1S.
- Web app: Pilot view (look around from the FPV camera with a HUD); V19-W in the switcher.


## 0.3.0 - 2026-10-02

V19: the three requested directions, built and checked, and a recommendation that passes.

- `tools/v19/`: configuration engine, search over 44 configurations (long nose, falcon tail, forward rotors,
  combined) with masses from the V19 construction itself, variant geometry from the V18 meshes (moved parts,
  cut panels, new booms, pods, risers, hangers, well caps, glove, root fairings, tail booms, fins, stabiliser,
  elevator, nose-bay floor), full-assembly collision checks against the V18 baseline, and a generated report.
- **Result:** V19-R (wing 250 mm aft + forward rotors on booms + 0.05 m2 tail) and V19-C (wing 275 mm aft +
  forward rotors) pass every model gate; the long nose alone and the tail alone do not.
- Web app redesign: environment lighting, soft shadows, grid floor, intro, animated V18/V19 switching with an
  X-ray ghost of V18, a V19 tab with variant cards, change lists, part cards and a comparison table; refreshed
  visual style throughout (light and dark).
- Easy setup: `scripts/setup_ubuntu.sh`, `scripts/publish_github.sh`, `Makefile` (`make help`).
- Repo checks and tests cover the V19 data; CI's manual analysis job re-runs the V19 search and geometry.


## 0.2.0 - 2026-10-02

Rebuilt around the actual V18 assembly instead of a proxy layout.

- V18 geometry: extraction of all 90 objects, P1S placement search, G10 cutting DXFs, carbon cut list.
- Mass and CG model from V18 positions; vortex-lattice aero model (validated against AeroSandbox);
  geometry checks on both sides; balance study over 576 design combinations.
- **Finding:** the V18 CG (x418) is aft of the rotor centroid (x330) and of the neutral-point band
  (x285-332); no silhouette-preserving change passes both hover and wing-borne gates.
- BOM reconciled with the V18 BOM (APC B5x3E, Freewing E7206, Skywalker 60A V2, RP1 V2, generic M10 GNSS);
  added rows kept; every item placed on the V18 model.
- Interface parts redesigned for the V18 structure and fit-checked in place (the 0.1 beam/pad/cradle
  parts and the proxy layout are removed - they conflicted with the V18 crossrails).
- Harness cut list from V18 positions; wiring updated to V18 parts and trays.
- Thrust-stand firmware (Arduino Nano + HX711) and log ingest.
- Web app (GitHub Pages, offline) and Tauri desktop app; CI for checks, firmware, Pages and releases.

## 0.1.0 - 2026-09-30

First repo: improved BOM, budget tool, pin-by-pin wiring, interface CAD on a proxy layout, test gates.
