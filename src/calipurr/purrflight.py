"""Pre-flight checks on a model, each reported in plain words.

Thresholds here flag things to look at. They can't promise a print will work.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from .profiles import NEEDED

BED_TOLERANCE_MM = 0.05
SMALL_BED_CONTACT_MM2 = 25.0
OVERHANG_NORMAL_Z = -np.cos(np.radians(45))
STANDOFF_MM = 0.2
# Ledges this small span too little to sag, like the ceiling of a recessed letter.
SMALL_LEDGE_MM2 = 4.0

PASS, WARN, FAIL, UNKNOWN = "pass", "warn", "fail", "unknown"

SIZE_KEYS = {
    "printer": ("build_x_mm", "build_y_mm", "build_z_mm"),
    "cnc": ("travel_x_mm", "travel_y_mm", "travel_z_mm"),
}


def _check(check_id: str, label: str, status: str, detail: str) -> dict:
    return {"id": check_id, "label": label, "status": status, "detail": detail}


def _solid(mesh: trimesh.Trimesh) -> dict:
    if not mesh.is_volume:
        return _check("solid", "Closed solid", FAIL, "The mesh has holes or bad faces, so slicers and CAM may misread it.")
    bodies = mesh.body_count
    if bodies > 1:
        return _check("solid", "Closed solid", WARN, f"Closed, but it has {bodies} separate bodies.")
    return _check("solid", "Closed solid", PASS, f"Closed solid, {mesh.volume / 1000:.1f} cm3.")


def _bed_contact(mesh: trimesh.Trimesh) -> dict:
    z_min = mesh.bounds[0][2]
    flat = (mesh.face_normals[:, 2] < -0.99) & (mesh.triangles[:, :, 2].max(axis=1) < z_min + BED_TOLERANCE_MM)
    area = float(mesh.area_faces[flat].sum())
    if area == 0:
        return _check("bed", "Bed contact", FAIL, "Nothing flat touches the bed, so it would start on a point or edge.")
    if area < SMALL_BED_CONTACT_MM2:
        return _check("bed", "Bed contact", WARN, f"Only {area:.0f} mm2 touches the bed, so it may come loose. Consider a brim.")
    return _check("bed", "Bed contact", PASS, f"{area:.0f} mm2 touches the bed.")


def _significant_overhangs(mesh: trimesh.Trimesh) -> np.ndarray:
    """Faces in overhanging areas big enough to matter."""
    z_min = mesh.bounds[0][2]
    lowest = mesh.triangles[:, :, 2].min(axis=1)
    steep = np.where((mesh.face_normals[:, 2] < OVERHANG_NORMAL_Z) & (lowest > z_min + STANDOFF_MM))[0]
    groups = trimesh.graph.connected_components(mesh.face_adjacency, nodes=steep)
    big = [g for g in groups if mesh.area_faces[g].sum() >= SMALL_LEDGE_MM2]
    return np.concatenate(big) if big else np.array([], dtype=int)


def _midair_starts(mesh: trimesh.Trimesh, faces: np.ndarray) -> np.ndarray:
    """Vertices of the given overhanging faces with nothing beneath them to print on."""
    z = mesh.vertices[:, 2]
    # Any upward-facing neighbor means this is a pocket floor, which has support below.
    has_up_face = np.zeros(len(z), dtype=bool)
    np.logical_or.at(has_up_face, mesh.faces.ravel(), np.repeat(mesh.face_normals[:, 2] > 1e-6, 3))
    edges = mesh.edges_unique
    has_lower_neighbor = np.zeros(len(z), dtype=bool)
    a, b = edges[:, 0], edges[:, 1]
    np.logical_or.at(has_lower_neighbor, a, z[b] < z[a] - 1e-6)
    np.logical_or.at(has_lower_neighbor, b, z[a] < z[b] - 1e-6)
    candidates = np.unique(mesh.faces[faces])
    return candidates[~has_lower_neighbor[candidates] & ~has_up_face[candidates]]


def _overhangs(mesh: trimesh.Trimesh) -> dict:
    faces = _significant_overhangs(mesh)
    if not len(faces):
        return _check("overhang", "Overhangs", PASS, "No overhangs past 45 degrees that need support.")
    area = float(mesh.area_faces[faces].sum())
    starts = _midair_starts(mesh, faces)
    if len(starts):
        where = mesh.vertices[starts[np.argmin(mesh.vertices[starts, 2])]]
        spot = f"The lowest is near X {where[0]:.1f}, Y {where[1]:.1f}, Z {where[2]:.1f}."
        return _check("overhang", "Overhangs", WARN, f"Part of this may start in mid-air, across {area:.0f} mm2 of overhang. Check it in your slicer, because it may need supports or a new orientation. {spot}")
    return _check("overhang", "Overhangs", WARN, f"{area:.0f} mm2 overhangs past 45 degrees. Check it in your slicer, because it may need supports.")


def _machine_size(mesh: trimesh.Trimesh, machine_name: str, profile: dict) -> list[dict]:
    keys = SIZE_KEYS.get(profile["kind"])
    if keys is None:
        return [_check("fit", "Fits the machine", UNKNOWN, f"Size checks for STL files don't apply to a {profile['kind']}.")]
    fields = profile["fields"]
    missing = [k for k in keys if fields[k]["status"] == NEEDED]
    if missing:
        detail = f"{machine_name} still needs {', '.join(missing)}, so this can't be checked yet."
        return [
            _check("fit", "Fits the machine", UNKNOWN, detail),
            _check("clearance", "Room to spare", UNKNOWN, detail),
        ]
    limits = np.array([fields[k]["value"] for k in keys])
    margins = limits - mesh.extents
    size = " x ".join(f"{v:.1f}" for v in mesh.extents)
    room = " x ".join(f"{v:g}" for v in limits)
    assumed = [k for k in keys if fields[k]["status"] != "measured"]
    caveat = f" This relies on assumed values: {', '.join(assumed)}." if assumed else ""
    if (margins < 0).any():
        axis = "XYZ"[int(np.argmin(margins))]
        footprint, bed = np.sort(mesh.extents[:2]), np.sort(limits[:2])
        turned = mesh.extents[2] <= limits[2] and (footprint <= bed).all()
        hint = " It would fit if rotated on the bed." if turned else ""
        return [
            _check("fit", "Fits the machine", FAIL, f"{size} mm doesn't fit {room} mm. {axis} is over by {-margins.min():.1f} mm.{hint}{caveat}"),
            _check("clearance", "Room to spare", FAIL, "No room to spare."),
        ]
    tightest = "XYZ"[int(np.argmin(margins))]
    return [
        _check("fit", "Fits the machine", PASS, f"{size} mm fits {room} mm.{caveat}"),
        _check("clearance", "Room to spare", PASS, f"Tightest margin is {margins.min():.1f} mm in {tightest}."),
    ]


def run(path: Path, machine_name: str | None = None, profile: dict | None = None) -> dict:
    mesh = trimesh.load_mesh(path)
    checks = [_solid(mesh)]
    size = " x ".join(f"{v:.2f}" for v in mesh.extents)
    process = profile["kind"] if profile else None
    # Bed contact and overhangs only matter for parts built up in layers.
    if process in (None, "printer"):
        checks += [_bed_contact(mesh), _overhangs(mesh)]
    if profile:
        checks += _machine_size(mesh, machine_name or "This machine", profile)
    else:
        unknown = "Choose a machine to check this."
        checks += [
            _check("fit", "Fits the machine", UNKNOWN, unknown),
            _check("clearance", "Room to spare", UNKNOWN, unknown),
        ]
    statuses = {c["status"] for c in checks}
    overall = FAIL if FAIL in statuses else WARN if WARN in statuses else UNKNOWN if UNKNOWN in statuses else PASS
    return {"file": path.name, "size_mm": size, "machine": machine_name, "overall": overall, "checks": checks}
