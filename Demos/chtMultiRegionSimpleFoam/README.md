# chtMultiRegionSimpleFoam Demo

Conjugate heat transfer between a fluid channel and a solid aluminium plate.

## Geometry

- **Fluid domain**: 100 mm × 20 mm × 5 mm rectangular channel
- **Solid domain**: 100 mm × 5 mm × 5 mm aluminium plate below the channel
- Flow direction: X axis (left to right)

## Physics

- Solver: `chtMultiRegionSimpleFoam` (steady-state conjugate heat transfer)
- Flow: laminar (Re ≈ 3 based on channel height)
- Fluid: air (compressible, ideal gas)
- Solid: aluminium (k = 204 W/m/K)

## Boundary Conditions

| Patch | Type | Value |
|-------|------|-------|
| inlet | velocity inlet | U = 0.01 m/s, T = 300 K |
| outlet | pressure outlet | p = 0 Pa |
| topWall | no-slip wall | adiabatic |
| fluidSideWalls | symmetry | — |
| hotWall (solid bottom) | fixed temperature | T = 400 K |
| solidOtherWalls | no-slip wall | adiabatic |
| fluid_to_solid interface | coupled | `turbulentTemperatureCoupledBaffleMixed` |

## Running

1. Open FreeCAD with the CfdOF workbench
2. Run `00-RunAll.FCMacro` to set up the full case
3. Generate the mesh using CfdOF meshing tools
4. Write the case and run via the Allrun script

## Expected Result

Temperature in the fluid increases from 300 K at inlet to ~350 K at outlet
due to heat conduction from the hot aluminium plate.
