# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Part of the CfdOF addon.

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import FreeCAD
import FreeCADGui

from CfdOF import CfdTools
from CfdOF.Mesh import CfdMeshTools
from CfdOF.Solve import CfdCaseWriterFoam


HOME_PATH = CfdTools.getModulePath()
DEFAULT_TIMEOUT = int(os.environ.get("CFDOF_SOLVE_TIMEOUT", "300"))

FOAM_ALIASES = {
    "openfoam2606": "/usr/lib/openfoam/openfoam2606",
    "2606": "/usr/lib/openfoam/openfoam2606",
    "openfoam14": "/usr/lib/openfoam/openfoam-foundation14",
    "foundation14": "/usr/lib/openfoam/openfoam-foundation14",
    "openfoam-foundation14": "/usr/lib/openfoam/openfoam-foundation14",
    "14": "/usr/lib/openfoam/openfoam-foundation14",
    "openfoam13": "/usr/lib/openfoam/openfoam-foundation13",
    "foundation13": "/usr/lib/openfoam/openfoam-foundation13",
    "openfoam-foundation13": "/usr/lib/openfoam/openfoam-foundation13",
    "13": "/usr/lib/openfoam/openfoam-foundation13",
}

DEMO_CASES = [
    ("Duct", "Duct", ["01-geom.FCMacro", "02-mesh.FCMacro", "03-porous.FCMacro", "04-screen.FCMacro"]),
    ("LESStep", "LESStep", ["backwardStep.FCMacro"]),
]


def fccPrint(message):
    FreeCAD.Console.PrintMessage("{}\n".format(message))


def _normalise_foam_selection(selection):
    if selection in FOAM_ALIASES:
        return selection, FOAM_ALIASES[selection]
    if os.path.isdir(selection):
        return os.path.basename(selection), selection
    raise ValueError("Unknown OpenFOAM selection '{}'. Use one of: {}".format(
        selection, ", ".join(sorted(FOAM_ALIASES))))


def _foam_selections_from_args():
    env_selection = os.environ.get("CFDOF_SOLVE_FOAMS", "").strip()
    if env_selection:
        tokens = re.split(r"[\s,]+", env_selection)
    else:
        tokens = []
        for arg in sys.argv[1:]:
            if arg.startswith("-") or arg in ("TestCfdOF-solve", "TestCfdOF_solve"):
                continue
            if arg.endswith(".py"):
                continue
            if arg in FOAM_ALIASES or os.path.isdir(arg):
                tokens.append(arg)

    if not tokens:
        current = CfdTools.getFoamDir()
        if not current:
            raise RuntimeError("No OpenFOAM version specified and no CfdOF installation path is configured")
        tokens = [current]

    selections = []
    seen = set()
    for token in tokens:
        name, path = _normalise_foam_selection(token)
        if path not in seen:
            seen.add(path)
            selections.append((name, path))
    return selections


def _selected_demos():
    env_selection = os.environ.get("CFDOF_SOLVE_DEMOS", "").strip()
    if not env_selection:
        return DEMO_CASES
    selected = {token.strip() for token in re.split(r"[\s,]+", env_selection) if token.strip()}
    return [case for case in DEMO_CASES if case[0] in selected or case[1] in selected]


def _find_analysis():
    analysis = CfdTools.getActiveAnalysis()
    if analysis:
        return analysis
    for obj in FreeCAD.ActiveDocument.Objects:
        if hasattr(obj, "IsActiveAnalysis") and hasattr(obj, "OutputPath"):
            return obj
    raise RuntimeError("No active analysis found")


def _close_documents():
    for doc_name in list(FreeCAD.listDocuments().keys()):
        try:
            FreeCAD.closeDocument(doc_name)
        except Exception:
            pass


def _set_one_iteration_controls(solver):
    solver.Parallel = False
    solver.MaxIterations = 1
    solver.SteadyWriteInterval = 1
    try:
        solver.EndTime = "0.001 s"
        solver.TimeStep = "0.001 s"
        solver.TransientWriteInterval = "0.001 s"
    except Exception:
        pass


def _patch_control_dict_for_one_step(case_dir):
    path = os.path.join(case_dir, "system", "controlDict")
    with open(path, "r") as handle:
        contents = handle.read()

    delta_t = "1"
    match = re.search(r"(?m)^deltaT\s+([^;]+);", contents)
    if match:
        delta_t = match.group(1).strip()

    if re.search(r"(?m)^application\s+(simpleFoam|porousSimpleFoam|SRFSimpleFoam)\s*;", contents):
        end_time = "1"
    else:
        end_time = delta_t

    replacements = {
        r"(?m)^endTime\s+[^;]+;": "endTime         {};".format(end_time),
        r"(?m)^writeInterval\s+[^;]+;": "writeInterval   {};".format(end_time),
        r"(?m)^purgeWrite\s+[^;]+;": "purgeWrite      0;",
    }
    for pattern, replacement in replacements.items():
        contents = re.sub(pattern, replacement, contents)

    with open(path, "w") as handle:
        handle.write(contents)


def _run_script(script_dir, script_name):
    script_path = os.path.join(script_dir, script_name)
    result = subprocess.run(
        ["bash", script_path],
        cwd=script_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=DEFAULT_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError("{} failed in {}\n{}".format(script_name, script_dir, result.stdout[-8000:]))


class CfdSolveSmokeTest(unittest.TestCase):
    def test_demo_cases_solve_one_iteration(self):
        prefs = CfdTools.getPreferencesLocation()
        original_installation_path = FreeCAD.ParamGet(prefs).GetString("InstallationPath", "")
        original_output_path = FreeCAD.ParamGet(prefs).GetString("DefaultOutputPath", "")
        original_append_setting = FreeCAD.ParamGet(prefs).GetBool("AppendDocNameToOutputPath", 0)
        output_root = tempfile.mkdtemp(prefix="cfdof_solve_")
        failures = []

        try:
            FreeCAD.ParamGet(prefs).SetBool("AppendDocNameToOutputPath", 0)
            FreeCAD.ParamGet(prefs).SetString("DefaultOutputPath", output_root)

            for foam_name, foam_path in _foam_selections_from_args():
                FreeCAD.ParamGet(prefs).SetString("InstallationPath", foam_path)
                fccPrint("Testing OpenFOAM selection {} at {}".format(foam_name, foam_path))
                fccPrint("Detected {}".format(CfdTools.getFoamVersionInfo()))

                for demo_dir, case_name, macros in _selected_demos():
                    started = time.time()
                    _close_documents()
                    try:
                        for macro in macros:
                            macro_path = os.path.join(HOME_PATH, "Demos", demo_dir, macro)
                            fccPrint("Running {} macro {} ...".format(demo_dir, macro_path))
                            CfdTools.executeMacro(macro_path)

                        analysis = _find_analysis()
                        analysis.OutputPath = os.path.join(output_root, foam_name)
                        solver = CfdTools.getSolver(analysis)
                        solver.InputCaseName = "case" + case_name
                        _set_one_iteration_controls(solver)

                        mesh_obj = CfdTools.getMeshObject(analysis)
                        mesh_obj.CaseName = "meshCase" + case_name
                        mesh_writer = CfdMeshTools.CfdMeshTools(mesh_obj)
                        mesh_writer.writeMesh()
                        _run_script(mesh_writer.mesh_case_dir, "Allmesh")

                        writer = CfdCaseWriterFoam.CfdCaseWriterFoam(analysis)
                        writer.writeCase()
                        _patch_control_dict_for_one_step(writer.case_folder)
                        _run_script(writer.case_folder, "Allrun")

                        fccPrint("Solved {} with {} in {:.1f} s".format(
                            case_name, foam_name, time.time() - started))
                    except Exception as err:
                        failures.append((foam_name, case_name, str(err)))
                    finally:
                        _close_documents()
        finally:
            FreeCAD.ParamGet(prefs).SetString("InstallationPath", original_installation_path)
            FreeCAD.ParamGet(prefs).SetString("DefaultOutputPath", original_output_path)
            FreeCAD.ParamGet(prefs).SetBool("AppendDocNameToOutputPath", original_append_setting)
            shutil.rmtree(output_root, ignore_errors=True)

        if failures:
            self.fail("Solve smoke failures: {}".format(failures))


if __name__ == "__main__":
    unittest.main()
