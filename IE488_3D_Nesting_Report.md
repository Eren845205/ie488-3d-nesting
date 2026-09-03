# IE 488 Project Report — Voxel-Based 3D Nesting for Additive Manufacturing

Prepared by: Eren Kutlu
Date: 13 June 2026

## Abstract

This project developed a placement algorithm that packs a 48-part production set into the build volume of a powder-bed additive manufacturing machine. The objective is to reduce build height while guaranteeing at least 1 mm of clearance between parts in every direction. The engine combines a voxel representation, a greedy constructive placer (deepest bottom-left fill, DBLF) and simulated annealing (SA) over part order and part orientation. The first valid solution stood at 265.0 mm. Redesigning the clearance accounting brought it to 217.5 mm, and SA combined with a hybrid orientation policy for the large plates brought it to the final 181.5 mm, a 31.5% total reduction. The result was reproduced from scratch in two independent runs with zero deviation, and the true minimum distance between placed parts was measured on the original geometry as 1.50 mm.

## 1. Problem definition

The input is a single customer order of 48 parts: 12 large plates and a mix of brackets, housings and disc-shaped components, in quantities between 1 and 16 per model. Figure 1 shows the eight distinct models with their real dimensions.

![Figure 1. The production set: eight part models, real dimensions and quantities (48 parts in total).](results/numune_overview.png)

The machine has a 335 × 335 mm build plate and a maximum build height of 600 mm. Build cost grows with height, so the goal is to nest the whole set as low as possible. Two constraints shape the problem:

- Parts must keep at least 1 mm of distance from each other in every direction (side by side, stacked, diagonal). In powder-bed fusion, parts that touch fuse together.
- Optimization may work on simplified geometry, but the delivered layout must use the original design files. The parts carry embossed text and thin details that must survive to production.

Because the process is powder-bed, parts need no support structures and float freely in the powder. Any orientation is printable, which makes orientation a genuine optimization variable rather than a manufacturing constraint.

A note on the target: a build height of 170 mm or less was discussed verbally as a stretch goal. The best height we reached is 181.5 mm; section 3.4 discusses why the gap is structural in the current configuration.

## 2. Method

### 2.1 Voxelization with conservative surface wrapping

Each part is rasterized into a voxel grid at the chosen resolution (1.5 mm in the final runs). Early in the project we used a center-in-mesh test: a cell counted as occupied if its center fell inside the part. This silently dropped thin walls. We caught it only because a post-placement distance check measured 0.77 mm between two parts where the guarantee said at least 1 mm. The fix samples every surface triangle at half-voxel spacing and marks all touched cells, then merges this with a slice-based interior fill. The resulting wrap is conservative: a part can be modeled slightly fatter than it is, never thinner.

### 2.2 The clearance scheme

The 1 mm guarantee is enforced at the voxel level by two mechanisms. Horizontally, each part's footprint is dilated by one cell. Vertically, the placer leaves one empty cell between a part and whatever it rests on. The worst case is diagonal adjacency, where the lower bound is sqrt(2) x resolution, about 2.1 mm at 1.5 mm resolution, comfortably above the 1 mm requirement.

Our first scheme dilated in all directions on both parts, which pays the clearance cost twice. Switching to single-sided accounting, with no other change, took the DBLF height from 265.0 mm to 217.5 mm. The single largest gain of the project came not from a smarter search but from correcting how the clearance budget was spent.

### 2.3 Constructive placement: DBLF

The base placer is deepest bottom-left fill. Parts are sorted by volume, largest first, and each is dropped at the lowest valid position on a height map of the build plate. It runs in seconds and lands around 214.5 mm on this set. Its weakness is also its character: a greedy placer never lifts a part once placed, and it never chooses an unusual orientation on its own.

### 2.4 Search: simulated annealing

SA explores the joint space of part order and per-part orientation. A move is one of: swapping two positions in the order, relocating a part to another position, reversing a segment, or changing one part's orientation. Each candidate is decoded back into a layout by running DBLF on the modified sequence, and the height of that layout is the energy. Acceptance follows the standard Metropolis rule with initial temperature 3.0; the best layout seen so far is kept separately, so the final answer can never be worse than the starting point.

Decode cost scales with the inverse square of resolution. At 1.5 mm, a 2000-iteration run takes 75 to 80 minutes on a single core, which set the practical budget for our experiments.

![Figure 2. SA convergence in the final run. The curve tracks the best height found so far; the long plateaus are typical of order-based encodings, where many moves decode to equivalent layouts.](results/numune_sa/sa3d_convergence_numune.png)

### 2.5 Orientation policy: from free, to forbidden, to hybrid

The 12 large plates dominate the problem, and most of the optimization story is about what they are allowed to do.

With all eight axis-aligned orientations free, SA discovered it could stand plates upright and reached 190.5 mm. But the analysis showed this was a ceiling, not a solution: the four plate models have upright heights of 178.3, 180.9, 187.5 and 190.1 mm, and the tallest standing plate was setting the build height directly.

Forbidding upright plates entirely did not help either. The plates' summed raw thickness is 202.5 mm, so a purely flat stack runs into a different ceiling near 198 mm (the best all-flat SA run).

The answer was a hybrid: only the two short plate models (178.3 and 180.9 mm) may stand upright; the taller two must lie flat. SA then built the structure we hoped for, upright short plates with the tall ones stacked flat beside them, and reached 181.5 mm. Three different random seeds landed in a 181.5 to 184.5 mm band, so the gain comes from the structure, not from one lucky run.

### 2.6 A final attempt: tilted plates

As a last push toward 170 mm we added tilted orientations (20 to 35 degrees from vertical) so plates could lean like plates in a dish rack, nesting into each other's stair profiles. Individually, tilted plates have bounding heights of 148 to 160 mm, which looked promising. Three 2000-iteration SA runs returned 181.5, 183.0 and 192.0 mm: the best tilted result exactly matches the hybrid record but does not beat it. Within this search budget, 181.5 mm behaves like a plateau.

## 3. Results

### 3.1 The optimization journey

| Stage | Height (mm) | Measured min. clearance (mm) | What changed |
|---|---|---|---|
| DBLF, double-sided dilation | 265.0 | 3.82 | first valid solution |
| DBLF, single-sided scheme | 217.5 | 2.68 | clearance accounting fixed |
| DBLF, upright plates forbidden | 214.5 | 1.60 | baseline for SA |
| SA, all orientations free | 190.5 | 1.50 | plates stand; tallest plate = ceiling |
| SA, upright forbidden | 198.0 | 1.50 | flat-stack ceiling appears |
| **SA, hybrid orientation (final)** | **181.5** | **1.50** | short plates stand, tall plates lie |
| SA, tilted-rack experiment | 181.5 | 1.62 | matches but does not beat the record |

### 3.2 Baseline and final layout

Figure 3 shows the DBLF baseline; figure 4 shows the final SA layout. The visible difference is exactly the hybrid policy at work: in the final layout the two short plate models stand on edge along one side while the tall plates form a flat stack, and the small parts fill the gaps the greedy placer left unused.

![Figure 3. DBLF baseline layout, 214.5 mm. Greedy placement, plates flat.](results/numune_dblf/nesting3d_numune.png)

![Figure 4. Final SA layout, 181.5 mm. Short plates standing, tall plates stacked flat, small parts filling the remaining pockets.](results/numune_sa/nesting3d_numune.png)

Figure 5 puts the two side by side with the height and packing-density numbers. SA buys 33.0 mm of height (15.4% versus its own baseline) and raises volumetric density from 0.189 to 0.229.

![Figure 5. DBLF baseline versus final SA result: layouts, build height and packing density.](results/numune_comparison.png)

The tilted-rack experiment is shown in figure 6 for completeness. The leaning plates are clearly visible; the build height still ends at 181.5 mm because the rack itself sits on other parts.

![Figure 6. Tilted-rack experiment (best seed): plates leaning at 20-35 degrees, 181.5 mm.](results/_tilt_s42/nesting3d_numune.png)

### 3.3 Final configuration

Resolution 1.5 mm, margin 1 cell, hybrid orientation set, 2000 SA iterations, seed 13. Total improvement over the first valid solution: 83.5 mm (31.5%). Packing density 0.229, which is within the expected range for powder-bed nesting given the mandatory gaps. Measured minimum clearance over all part pairs: 1.50 mm.

### 3.4 On the 170 mm target

We cannot call 170 mm impossible. The plates have through-holes, so parts can interpenetrate in ways that invalidate simple lower-bound arguments; we verified this directly when SA found a 198.0 mm flat stack although a naive bound said 206 mm. What we can say is that every arrangement that stands a plate upright inherits the shortest plate's 178.3 mm as a floor, the all-flat route has a ceiling near 198 mm, and the tilted route, despite favorable per-part heights, did not break 181.5 mm within a 2000-iteration budget. Reaching 170 mm would need either a substantially larger search budget or an idea we have not tried yet.

## 4. Verification and reproducibility

Two independent checks back the result.

Clearance is verified on the real geometry, not the voxels: after placement, the original meshes are moved to their final poses and the true minimum distance is computed for every part pair (a KD-tree with an axis-aligned bounding-box prefilter keeps this fast). The final layout measures 1.50 mm.

Reproducibility is enforced by a single-command script that reruns the full final configuration and compares against the expected value. Two separate sessions both returned 181.5 mm with 0.0 mm deviation; each run takes 75 to 80 minutes. The engine's unit-test suite grew from 92 to 96 tests during the project and stayed green through every change. All randomness flows through seeded generators, so any reported number can be regenerated exactly.

The delivered layout is exported back to STL using the original part meshes (the voxel model is only the optimizer's internal view), so embossed text and thin features are preserved in the production files.

## 5. Possible next steps

Three directions look worth the effort: widening the orientation set to all 24 axis-aligned poses, running several seeds in parallel as a matter of course instead of as an experiment, and adding alternative search methods (a genetic algorithm in particular) so different instances can pick whichever performs best. First versions of some of these exist; judging which ones actually pay requires a systematic benchmark, which is the natural next phase of the work.

## Appendix: delivered code

The accompanying archive contains the full source of the engine, the STL files of the 48 parts, the dependency list and the reproduction script. Setup and usage are described in the archive's README. The reproduction command is:

```
python scripts/repro_numune.py
```
