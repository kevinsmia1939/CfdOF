# How to set up a CHT case in CfdOF

Conjugate heat transfer (CHT) simulates heat conduction in a solid coupled to a
convecting fluid. The simplest case is a fluid channel sitting on top of a solid
plate with a hot bottom wall.

## Prerequisites

- FreeCAD with the CfdOF workbench active
- OpenFOAM installed and configured in CfdOF preferences
- gmsh installed (used as the mesh utility)

---

## 1. Geometry

### Topology requirement — IMPORTANT

For a conformal mesh (required for CHT coupling), the fluid and solid bodies must
**share a face** in the geometry. There are two supported topologies:

**A. Adjacent bodies (touching at one face)**
The solid body sits against the outside of the fluid region. Example: a solid
plate below a fluid channel, sharing the bottom face of the channel.

| Body | Example size |
|------|-------------|
| **FluidBox** — the flow channel | 100 × 20 × 5 mm |
| **SolidBox** — the solid plate below | 100 × 5 × 5 mm |

```
FluidBox: Box  position (0, 0, 0)   L=100, W=5, H=20  mm
SolidBox: Box  position (0, 0, -5)  L=100, W=5, H=5   mm
```

The bottom face of FluidBox and the top face of SolidBox are co-planar — this
becomes the coupled interface after meshing.

Combine using **Part → Create a compound** → select FluidBox and SolidBox.

**B. Enclosed solid (heatsink inside a fluid box)**
The solid body is fully surrounded by fluid. The compound **must** be created
using **Part → Boolean → BooleanFragments** so that gmsh sees the shared
surfaces and creates a conformal mesh. A simple `Part → Create a compound` of
two non-touching boxes produces overlapping, non-conformal meshes and CHT
coupling will fail.

1. In the Part workbench, select the FluidBox and the heatsink.
2. **Part → Boolean → BooleanFragments** → apply.
3. The result is a compound with correctly shared surfaces at the heatsink boundary.

---

## 2. Analysis object

Switch to the **CfdOF workbench** and create a new analysis.

Open **Physics model** and set:

| Setting | Value |
|---------|-------|
| Time | Steady |
| Phase | **Multi-region (conjugate heat transfer)** |
| Turbulence | Laminar |
| Gravity | gz = −9.81 m/s² (optional for this case) |

Choosing Multi-region automatically selects NonIsothermal flow and selects the
`chtMultiRegionSimpleFoam` solver.

---

## 3. Materials

### Fluid material

Click **Add fluid properties** (`CfdOF_FluidMaterial`).

- Pick a compressible gas from the library — **AirCompressible** works well.
- Set `RegionName` = `fluid` (must match the mesh zone name used later).
- Do **not** assign a shape reference here; the fluid region is defined by the
  mesh refinement zone (step 5).

### Solid material

Click **Add solid properties** (`CfdOF_SolidMaterial`).

- Pick a solid from the library — **AluminiumSolid** (k = 204 W/m·K).
- Set `RegionName` = `solid`.
- Under **Solid body**, select `SolidBox`. This tells CfdOF which geometry
  belongs to this region; no separate mesh zone object is needed for the solid.

---

## 4. Initial conditions

Open **Initialise fields**.

| Field | Value | Why |
|-------|-------|-----|
| Pressure | **101325 Pa** | Must be absolute — the compressible `heRhoThermo` EOS requires non-zero absolute pressure |
| Temperature | 300 K | Ambient starting temperature |
| Potential flow | off | Not needed for CHT |

---

## 5. Mesh

Use the compound created in step 1 (either `Part → Create a compound` for
adjacent bodies, or the BooleanFragments result for an enclosed heatsink) as the
mesh shape. Name it `CombinedGeom`.

Add a **CFD mesh** (`CfdOF_MeshFromShape`) on `CombinedGeom` and set:

- Mesh utility: **gmsh**
- Characteristic length: ~3 mm (coarse is fine for testing)

Optionally add a **mesh refinement zone** (Internal volume) to explicitly name the fluid region:

- `Internal` = ✓
- Shape reference: `FluidBox`
- Label: `fluid`  ← this becomes the OpenFOAM region name

If no Internal zone is added, the case writer automatically derives the fluid region
from the compound's non-solid bodies. The fluid region name defaults to the fluid
material's Label (e.g. `Air`).

The solid region geometry is already recorded on `CfdSolidMaterial` (step 3);
no separate refinement zone is needed for the solid.

Click **Run meshing**.

---

## 6. Boundary conditions

Add `CfdFluidBoundary` objects for every external face. The fluid-solid
interface (defaultFaces) is handled automatically by the solver — do not assign
a boundary condition to it.

### Fluid faces

| Boundary | Type | Sub-type | Thermal |
|----------|------|----------|---------|
| Inlet (x=0) | inlet | Uniform velocity | Fixed value 300 K |
| Outlet (x=100) | outlet | Static pressure **101325 Pa** | Zero gradient |
| Top wall | wall | Fixed (no-slip) | Zero gradient (adiabatic) |
| Side walls | constraint | Symmetry | — |

> **Outlet pressure**: use absolute pressure (101325 Pa), not gauge (0 Pa).
> Gauge pressure causes a floating-point exception in the compressible solver at
> the second iteration.

### Solid faces

| Boundary | Type | Sub-type | Thermal |
|----------|------|----------|---------|
| Bottom face (hot wall) | wall | Fixed (no-slip) | Fixed value **400 K** |
| Remaining solid faces | wall | Fixed (no-slip) | Zero gradient (adiabatic) |

---

## 7. Solver settings

Open **CFD solver** and set:

- End time (iterations): 300–500 for a quick test; 2000 for converged result
- Convergence tolerance: 1×10⁻⁴

---

## 8. Write case and run

Click **Write** then **Run** in the solver panel, or run the generated `Allrun`
script directly in the case directory.

The Allrun script:

1. Runs `blockMesh` to create a background mesh
2. Runs gmsh to generate the combined mesh
3. Converts to OpenFOAM format (`gmshToFoam`)
4. Runs `splitMeshRegions -cellZones` to produce `constant/fluid/` and
   `constant/solid/` region meshes
5. Patches the interface boundary type to `mappedWall` (required for CHT
   coupling; gmsh co-located faces are not automatically coupled)
6. Runs `chtMultiRegionSimpleFoam`

---

## 9. Expected result

| Location | Temperature |
|----------|-------------|
| Fluid inlet | 300 K |
| Fluid outlet | ~350–390 K (depends on mesh/iterations) |
| Solid bottom (hot wall) | 400 K (fixed) |
| Solid top (interface) | ~340–380 K |

Inspect results in ParaView by loading `case.foam` — use the **Region** filter
to view fluid and solid separately.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Floating point exception` at iteration 2 | Outlet/initial pressure is 0 Pa (gauge) | Set outlet pressure and initial pressure to 101325 Pa |
| `Cannot find patchField entry for defaultFaces` | No conformal interface — non-conformal mesh | Use BooleanFragments (enclosed heatsink) or ensure bodies touch at a common face |
| Air region has no `defaultFaces` patch after `splitMeshRegions` | Compound created with simple `Create a compound` for an enclosed heatsink — produces non-conformal mesh | Replace with `Part → Boolean → BooleanFragments` to create shared surfaces |
| Solver exits immediately with region error | Region name mismatch | Ensure `RegionName` on the material objects matches the mesh zone label |
| `splitMeshRegions` produces only one region | Solid not a separate cell zone | Confirm `CfdSolidMaterial.ShapeRefs` points to the solid body |
