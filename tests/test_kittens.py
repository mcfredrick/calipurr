import json

import numpy as np
import pytest
import trimesh

from calipurr import kitten, profiles, purrflight
from calipurr.cli import main
from calipurr.errors import Hiss, NeedsConfirmation
from calipurr.project import Project


@pytest.fixture
def project(tmp_path):
    return Project(tmp_path)


def diameter_at(mesh, z):
    section = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    points = section.vertices
    return float(np.hypot(points[:, 0], points[:, 1]).max() * 2)


def inner_diameter_at(mesh, z):
    section = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    points = section.vertices
    return float(np.hypot(points[:, 0], points[:, 1]).min() * 2)


def test_plug_gauge_steps_match_their_metadata(project):
    record = kitten.make_gauge(project, 20.3, 21.1, 0.2)
    mesh = trimesh.load_mesh(project.root / record["file"])
    assert mesh.is_volume and mesh.body_count == 1
    assert [s["letter"] for s in record["steps"]] == list("ABCDE")
    assert [s["size_mm"] for s in record["steps"]] == [20.3, 20.5, 20.7, 20.9, 21.1]
    # A is the tip, so a plug narrows toward the top and prints without overhangs.
    assert record["steps"][0]["z0"] > record["steps"][-1]["z0"]
    for step in record["steps"]:
        # Sampled clear of the recessed letter's height range.
        assert diameter_at(mesh, step["z0"] + 0.2) == pytest.approx(step["size_mm"], abs=0.02)


def test_socket_gauge_steps_match_their_metadata(project):
    record = kitten.make_gauge(project, 23.5, 24.1, 0.2, kind="socket")
    mesh = trimesh.load_mesh(project.root / record["file"])
    assert mesh.is_volume and mesh.body_count == 1
    by_letter = {s["letter"]: s for s in record["steps"]}
    assert by_letter["A"]["size_mm"] == 24.1 and by_letter["A"]["z1"] == pytest.approx(mesh.bounds[1][2])
    for step in record["steps"]:
        assert inner_diameter_at(mesh, step["z0"] + 0.2) == pytest.approx(step["size_mm"], abs=0.02)


def test_labels_are_recessed_and_never_widen_a_step(project):
    plain = kitten.make_gauge(project, 20.3, 21.1, 0.2, labels=False, name="plain")
    labeled = kitten.make_gauge(project, 20.3, 21.1, 0.2, name="labeled")
    plain_mesh = trimesh.load_mesh(project.root / plain["file"])
    labeled_mesh = trimesh.load_mesh(project.root / labeled["file"])
    assert labeled_mesh.volume < plain_mesh.volume
    assert np.allclose(labeled_mesh.bounds, plain_mesh.bounds, atol=0.01)
    assert labeled_mesh.body_count == 1


def test_labels_face_the_side_the_viewer_opens_on(project):
    plain = trimesh.load_mesh(project.root / kitten.make_gauge(project, 20.3, 20.7, 0.2, labels=False, name="p")["file"])
    labeled = trimesh.load_mesh(project.root / kitten.make_gauge(project, 20.3, 20.7, 0.2, name="l")["file"])
    new = labeled.vertices[~np.isin(labeled.vertices.round(4).view("f8,f8,f8"), plain.vertices.round(4).view("f8,f8,f8")).ravel()]
    assert (new[:, 1] < 0).all()


def test_each_letter_makes_its_own_mark():
    shapes = {letter: tuple(map(tuple, kitten.STROKES[letter])) for letter in kitten.LETTERS}
    assert len(set(shapes.values())) == len(kitten.LETTERS)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"start": 21, "stop": 20, "step": 0.2}, "larger"),
        ({"start": 20, "stop": 21, "step": 0.01}, "steps"),
        ({"start": 20, "stop": 21, "step": -0.2}, "greater than zero"),
        ({"start": 20, "stop": 21, "step": 0.2, "step_height": 3}, "tall"),
        ({"start": 3, "stop": 3.4, "step": 0.2}, "curves too sharply"),
        ({"start": 20, "stop": 21, "step": 0.2, "kind": "cone"}, "kinds"),
        ({"start": 20, "stop": 21, "step": 0.2, "target": "ghost"}, "ghost"),
    ],
)
def test_bad_gauges_are_refused_with_a_reason(project, kwargs, message):
    with pytest.raises(Hiss, match=message):
        kitten.make_gauge(project, **kwargs)
    assert kitten.kittens(project) == []


def test_small_gauge_can_skip_labels(project):
    record = kitten.make_gauge(project, 3, 3.4, 0.2, labels=False)
    assert trimesh.load_mesh(project.root / record["file"]).is_volume


def test_existing_kitten_needs_force(project):
    kitten.make_gauge(project, 20, 20.4, 0.2, name="k")
    with pytest.raises(Hiss, match="already exists"):
        kitten.make_gauge(project, 20, 20.4, 0.2, name="k")
    assert kitten.make_gauge(project, 20, 20.6, 0.2, name="k", force=True)["steps"][-1]["size_mm"] == 20.6


def test_report_uses_modeled_size_and_records_printed_offset(project):
    # A real result: the step modeled at 20.9 printed at 20.75 and fit, so 20.9 goes in the model.
    project.meow("plug_od", "Plug diameter", "What fits the tube?")
    record = kitten.make_gauge(project, 20.3, 21.1, 0.2, target="plug_od", name="g")
    kitten.report(project, "g", "d", 20.75, material="PLA", machine="p1s")

    param = project.params()["plug_od"]
    assert param["value"] == 20.9 and param["status"] == "measured"
    assert "20.75" in param["note"] and "PLA" in param["note"]
    result = kitten.load_kitten(project, "g")["report"]
    assert result["offset_mm"] == -0.15 and result["letter"] == "D"
    assert record["for"] == "plug_od"


def test_report_catches_a_misread_step_until_confirmed(project):
    project.meow("plug_od", "Plug diameter", "What fits the tube?")
    kitten.make_gauge(project, 20.3, 21.1, 0.2, target="plug_od", name="g")
    with pytest.raises(NeedsConfirmation, match="right step"):
        kitten.report(project, "g", "D", 20.4)
    assert project.params()["plug_od"]["status"] == "needed"
    assert kitten.load_kitten(project, "g")["report"] is None
    kitten.report(project, "g", "D", 20.4, confirm=True)
    assert project.params()["plug_od"]["value"] == 20.9


def test_report_rejects_unknown_step(project):
    kitten.make_gauge(project, 20, 20.4, 0.2, name="g")
    with pytest.raises(Hiss, match="no step Z"):
        kitten.report(project, "g", "Z", 20)


def box_at(x=0, y=0, z=0, size=(20, 20, 20)):
    mesh = trimesh.creation.box(extents=size)
    mesh.apply_translation(np.array([x, y, z]) + np.array(size) / 2)
    return mesh


def test_cut_keeps_original_geometry_and_rests_on_the_bed(project):
    source = trimesh.creation.cylinder(radius=10, height=30, sections=64)
    source.apply_translation([5, -3, 15])
    source.export(project.root / "part.stl")
    record = kitten.make_cut(project, "part.stl", keep_above=20)
    piece = trimesh.load_mesh(project.root / record["file"])
    assert piece.is_volume
    assert piece.bounds[0][2] == pytest.approx(0)
    assert piece.extents[2] == pytest.approx(10)
    assert piece.volume == pytest.approx(source.volume / 3, rel=0.001)
    assert piece.centroid[0] == pytest.approx(5, abs=0.01)


def test_cut_explains_an_empty_range(project):
    box_at().export(project.root / "part.stl")
    with pytest.raises(Hiss, match="spans Z 0 to 20"):
        kitten.make_cut(project, "part.stl", keep_above=50)


def statuses(tmp_path, mesh, machine=None, profile=None):
    path = tmp_path / "m.stl"
    mesh.export(path)
    return {c["id"]: c["status"] for c in purrflight.run(path, machine, profile)["checks"]}


def test_purrflight_passes_a_simple_block(tmp_path):
    result = statuses(tmp_path, box_at())
    assert result["solid"] == result["bed"] == result["overhang"] == "pass"
    assert result["fit"] == "unknown"


def test_purrflight_flags_a_part_starting_in_midair(tmp_path):
    # An upside-down T's opposite: a wide top on a thin post has unsupported undersides.
    post = box_at(40, 40, 0, (20, 20, 30))
    top = box_at(0, 0, 30, (100, 100, 10))
    mesh = trimesh.boolean.union([post, top], engine="manifold")
    assert statuses(tmp_path, mesh)["overhang"] == "warn"


def test_purrflight_accepts_a_pocket_floor(tmp_path):
    pocket = trimesh.boolean.difference([box_at(size=(40, 40, 20)), box_at(10, 10, 5, (20, 20, 20))], engine="manifold")
    assert statuses(tmp_path, pocket)["overhang"] == "pass"


@pytest.mark.parametrize("kind", ["plug", "socket"])
def test_purrflight_passes_our_own_gauges(project, kind):
    record = kitten.make_gauge(project, 20.3, 21.1, 0.2, kind=kind)
    checks = {c["id"]: c["status"] for c in purrflight.run(project.root / record["file"])["checks"]}
    assert checks["solid"] == checks["bed"] == checks["overhang"] == "pass"


def test_purrflight_flags_a_part_with_no_flat_base(tmp_path):
    ball = trimesh.creation.icosphere(subdivisions=3, radius=10)
    assert statuses(tmp_path, ball)["bed"] == "fail"


def test_purrflight_flags_an_open_mesh(tmp_path):
    mesh = box_at()
    mesh.update_faces(np.arange(len(mesh.faces)) != 0)
    assert statuses(tmp_path, mesh)["solid"] == "fail"


@pytest.fixture
def printer(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    profiles.adopt("p", "printer")
    return "p"


def test_purrflight_refuses_to_guess_at_unknown_machine_limits(tmp_path, printer):
    result = statuses(tmp_path, box_at(), printer, profiles.load(printer))
    assert result["fit"] == "unknown"


def test_purrflight_checks_fit_and_suggests_rotation(tmp_path, printer):
    for key, value in [("build_x_mm", 100), ("build_y_mm", 200), ("build_z_mm", 50)]:
        profiles.feed(printer, key, str(value), "measured")
    profile = profiles.load(printer)
    assert statuses(tmp_path, box_at(size=(90, 150, 40)), printer, profile)["fit"] == "pass"

    path = tmp_path / "wide.stl"
    box_at(size=(150, 90, 40)).export(path)
    fit = next(c for c in purrflight.run(path, printer, profile)["checks"] if c["id"] == "fit")
    assert fit["status"] == "fail" and "rotated" in fit["detail"]


def test_purrflight_says_when_a_fit_rests_on_assumptions(tmp_path, printer):
    for key in ("build_x_mm", "build_y_mm"):
        profiles.feed(printer, key, "200", "measured")
    profiles.feed(printer, "build_z_mm", "200", "assumed")
    path = tmp_path / "m.stl"
    box_at().export(path)
    fit = next(c for c in purrflight.run(path, printer, profiles.load(printer))["checks"] if c["id"] == "fit")
    assert fit["status"] == "pass" and "build_z_mm" in fit["detail"]


def test_cli_gauge_report_and_preflight_flow(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    root = str(tmp_path)
    assert main(["ask", "od", "--name", "Plug", "--ask", "Fit the tube", "--project", root]) == 0
    assert main(["bowl", "--project", root]) == 1
    assert main(["test-piece", "gauge", "--from", "20", "--to", "20.4", "--for", "od", "--name", "g", "--project", root]) == 0
    assert main(["kitten", "report", "g", "--step", "B", "--measured", "20.1", "--project", root]) == 0
    capsys.readouterr()
    assert main(["params", "--json", "--project", root]) == 0
    assert json.loads(capsys.readouterr().out)["params"]["od"]["value"] == 20.2
    assert main(["purrflight", "kittens/g.stl", "--json", "--project", root]) == 0
    assert json.loads(capsys.readouterr().out)["overall"] == "unknown"
    assert main(["kitten", "report", "g", "--step", "B", "--measured", "19", "--project", root]) == 2
    assert "--confirm" in capsys.readouterr().err
