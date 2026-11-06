import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import trimesh

from calipurr import profiles
from calipurr.errors import Hiss
from calipurr.project import MAX_LIVES, Project, length_value
from calipurr.server import make_server


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    root = tmp_path / "part"
    root.mkdir()
    trimesh.creation.box(extents=(10, 10, 10)).export(root / "part.stl")
    return Project(root)


def test_values_track_where_they_came_from_and_can_be_forgotten(project):
    project.meow("D1", "Bore", "Measure it")
    assert project.hungry() == {"D1": "Measure it"}
    project.answer("D1", "26.7", "assumed", "from a catalog")
    entry = project.params()["D1"]
    assert (entry["value"], entry["status"], entry["note"]) == (26.7, "assumed", "from a catalog")
    # Rewording a question must not throw away its answer.
    project.meow("D1", "Bore", "Measure it twice")
    assert project.params()["D1"]["value"] == 26.7
    project.forget("D1")
    assert "value" not in project.params()["D1"] and project.params()["D1"]["status"] == "needed"


@pytest.mark.parametrize("raw", ["wide", "-1", "0", "nan", "inf", None])
def test_bad_values_are_refused(project, raw):
    project.meow("D1", "Bore", "Measure it")
    with pytest.raises(Hiss):
        project.answer("D1", raw)
    assert project.params()["D1"]["status"] == "needed"


def test_nine_lives_keeps_history_and_restores(project):
    project.meow("D1", "Bore", "Measure it")
    for value in range(1, 16):
        project.answer("D1", value)
    lives = project.lives()
    assert len(lives) == MAX_LIVES - 1
    assert lives[-1]["values"]["D1"] == 14
    project.restore_life(lives[-1]["id"])
    assert project.params()["D1"]["value"] == 14
    # Restoring is itself reversible.
    assert project.lives()[-1]["values"]["D1"] == 15


def test_dots_keep_stable_ids_and_validate_position(project):
    first = project.add_dot("part.stl", [1, 2, 3], "here")
    second = project.add_dot("part.stl", [4, 5, 6])
    project.remove_dot(first["id"])
    third = project.add_dot("part.stl", [7, 8, 9])
    assert [d["id"] for d in project.dots()] == [second["id"], third["id"]]
    assert third["id"] > second["id"]
    for bad in ([1, 2], [1, 2, float("inf")], ["a", 2, 3]):
        with pytest.raises(Hiss):
            project.add_dot("part.stl", bad)


def test_photo_dots_use_two_coordinates(project):
    (project.root / "machine.jpg").write_bytes(b"not really an image")
    assert project.add_dot("machine.jpg", [0.25, 0.5], "this clamp")["position"] == [0.25, 0.5]


def test_litter_box_round_trip(project):
    assert project.discard("part.stl") == "litter/part.stl"
    assert project.files()["models"] == []
    assert project.rescue("litter/part.stl") == "part.stl"
    assert [f["name"] for f in project.files()["models"]] == ["part.stl"]


@pytest.mark.parametrize("name", ["../secret.stl", "/etc/passwd", "../../x.jpg", "params.toml", ".calipurr/lives/1.toml"])
def test_only_project_models_and_photos_can_be_opened(project, name):
    (project.root.parent / "secret.stl").write_text("outside")
    project.meow("D1", "Bore", "Measure it")
    with pytest.raises(Hiss):
        project.resolve_file(name)


@pytest.fixture
def served(project):
    def start(build=None):
        server = make_server(project, build=build)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        return f"127.0.0.1:{server.server_address[1]}"

    servers = []
    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def call(host, route, body=None, **headers):
    data = None if body is None else json.dumps(body).encode()
    all_headers = {"Host": host}
    if body is not None:
        all_headers |= {"Origin": f"http://{host}", "Content-Type": "application/json"}
    all_headers |= {k.replace("_", "-"): v for k, v in headers.items()}
    request = urllib.request.Request(f"http://{host}{route}", data=data, headers=all_headers)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def test_server_serves_the_viewer_and_project_files(project, served):
    host = served()
    assert call(host, "/")[0] == 200
    assert call(host, "/vendor/three.module.min.js")[0] == 200
    status, body = call(host, "/file/part.stl")
    assert status == 200 and len(body) > 100
    state = json.loads(call(host, "/api/state")[1])
    assert state["files"]["models"][0]["name"] == "part.stl"


@pytest.mark.parametrize("route", ["/file/../params.toml", "/file/%2e%2e/%2e%2e/etc/passwd", "/../server.py", "/.hidden"])
def test_server_blocks_paths_outside_its_files(project, served, route):
    assert call(served(), route)[0] == 404


def test_server_rejects_foreign_sites(project, served):
    host = served()
    # DNS rebinding arrives with another site's name in Host.
    assert call(host, "/api/state", Host="evil.example")[0] == 403
    # A cross-site form or fetch can't name Calipurr as its origin.
    body = {"file": "part.stl", "position": [0, 0, 0]}
    assert call(host, "/api/dots", body, Origin="https://evil.example")[0] == 403
    assert project.dots() == []
    request = urllib.request.Request(f"http://{host}/api/dots", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(request)
    assert err.value.code == 403
    assert call(host, "/api/dots", body, Content_Type="text/plain")[0] == 415


def test_server_full_gauge_loop(project, served):
    host = served()
    project.meow("D1", "Bore", "Measure it")
    made = json.loads(call(host, "/api/kitten/gauge", {"from": 20, "to": 20.4, "step": 0.2, "for": "D1"})[1])["result"]
    report = {"name": made["name"], "letter": "B", "measured": 19}
    status, body = call(host, "/api/kitten/report", report)
    assert status == 409 and json.loads(body)["needs_confirmation"]
    assert call(host, "/api/kitten/report", report | {"measured": 20.1})[0] == 200
    state = json.loads(call(host, "/api/state")[1])
    assert state["params"]["D1"]["value"] == 20.2
    check = json.loads(call(host, f"/api/check?file={made['file']}")[1])
    assert {c["id"] for c in check["checks"]} >= {"solid", "bed", "overhang", "fit", "clearance"}


def test_server_reports_bad_requests_plainly(project, served):
    host = served()
    status, body = call(host, "/api/params", {"key": "ghost", "value": 1})
    assert status == 400 and "ghost" in json.loads(body)["error"]
    assert call(host, "/api/params", {"value": 1})[0] == 400


def wait_for_build(host):
    for _ in range(100):
        build = json.loads(call(host, "/api/state")[1])["build"]
        if not build["running"] and build["ok"] is not None:
            return build
        time.sleep(0.05)
    raise AssertionError("build never finished")


def test_rebuild_runs_after_a_value_changes_and_reports_failure(project, served):
    project.meow("D1", "Bore", "Measure it")
    host = served(f'{sys.executable} -c "import pathlib;pathlib.Path(\'built.txt\').write_text(\'yes\')"')
    assert call(host, "/api/params", {"key": "D1", "value": 5})[0] == 200
    assert wait_for_build(host)["ok"] is True
    assert (project.root / "built.txt").read_text() == "yes"

    failing = served(f'{sys.executable} -c "raise SystemExit(\'boom\')"')
    call(failing, "/api/params", {"key": "D1", "value": 6})
    build = wait_for_build(failing)
    assert build["ok"] is False and "boom" in build["output"]


def test_machine_values_can_be_fed_through_the_server(project, served):
    profiles.adopt("p", "printer")
    host = served()
    assert call(host, "/api/machine/feed", {"name": "p", "key": "build_x_mm", "value": 256, "status": "measured"})[0] == 200
    assert profiles.load("p")["fields"]["build_x_mm"]["value"] == 256


def test_choice_and_text_questions_validate_their_answers(project):
    project.meow("use", "Use", "Where?", kind="choice", choices=["Indoors", "Outdoors"])
    project.meow("why", "Why", "Why?", kind="text", required=False)
    assert set(project.hungry()) == {"use"}

    with pytest.raises(Hiss, match="one of"):
        project.answer("use", "Moon")
    with pytest.raises(Hiss, match="needs an answer"):
        project.answer("why", "   ")

    assert project.answer("use", "Outdoors")["status"] == "answered"
    assert project.hungry() == {}
    assert project.answer("why", "It broke")["value"] == "It broke"


def test_asking_again_keeps_an_answer_only_if_it_still_fits(project):
    project.meow("use", "Use", "Where?", kind="choice", choices=["Indoors", "Outdoors"])
    project.answer("use", "Outdoors")

    project.meow("use", "Use", "Where does it live?", kind="choice", choices=["Indoors", "Outdoors"])
    assert project.params()["use"]["value"] == "Outdoors"

    project.meow("use", "Use", "Where?", kind="choice", choices=["Wet", "Dry"])
    assert project.params()["use"]["status"] == "needed"
    assert "value" not in project.params()["use"]

    project.meow("bore", "Bore", "Measure")
    project.answer("bore", 5)
    project.meow("bore", "Bore", "Describe it", kind="text")
    assert project.params()["bore"]["status"] == "needed"


@pytest.mark.parametrize("kwargs", [{"kind": "choice"}, {"choices": ["a"]}, {"kind": "essay"}, {"show": "nope.jpg"}])
def test_malformed_questions_are_refused(project, kwargs):
    with pytest.raises(Hiss):
        project.meow("q", "Q", "?", **kwargs)


def test_bowl_and_nudge_tell_an_agent_where_things_stand(project, capsys):
    from calipurr.cli import main

    args = ["--json", "--project", str(project.root)]
    project.meow("use", "Use", "Where?", kind="text")
    assert main(["bowl", *args]) == 1
    assert json.loads(capsys.readouterr().out)["ready"] is False

    project.answer("use", "Outdoors")
    assert main(["nudge", "Print the gauge", *args]) == 0
    capsys.readouterr()
    assert main(["bowl", *args]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ready"] is True and out["next"] == "Print the gauge"
    assert out["params"]["use"]["value"] == "Outdoors"

    assert main(["nudge", "--clear", *args]) == 0
    assert project.next_step() == ""


class Lurker:
    """Runs lurk on a thread, the way an agent's background command would."""

    def __init__(self, project, timeout=20):
        self.project = project
        self.reason = None
        self.thread = threading.Thread(target=self._run, args=(timeout,), daemon=True)
        self.thread.start()
        while not project.lurking():
            time.sleep(0.01)

    def _run(self, timeout):
        self.reason = self.project.lurk(timeout)

    def result(self):
        self.thread.join(10)
        return self.reason


def test_lurk_returns_when_the_last_open_question_is_answered(project):
    project.meow("bore", "Bore", "How wide?")
    project.meow("color", "Color", "What color?", kind="text", required=False)
    lurker = Lurker(project)

    # An open optional question still leaves the user something to do.
    project.answer("bore", 12.5)
    time.sleep(1.2)
    assert lurker.thread.is_alive()

    project.answer("color", "Red")
    assert lurker.result() == "answered"
    assert project.handed() and not project.lurking()


def test_lurk_waits_for_the_bell_while_the_user_does_a_physical_step(project):
    project.meow("use", "Use", "Where?", kind="text")
    project.answer("use", "Outdoors")
    project.nudge("Print the gauge")
    lurker = Lurker(project)
    time.sleep(1.2)
    assert lurker.thread.is_alive()

    project.ring()
    assert lurker.result() == "sent"
    assert project.handed()

    # The agent replying clears the "your agent has it" state.
    project.nudge("Now measure it")
    assert not project.handed()


def test_answers_during_a_physical_step_do_not_end_the_wait_early(project):
    project.nudge("Print the gauge")
    project.meow("use", "Use", "Where?", kind="text")
    lurker = Lurker(project)
    time.sleep(0.7)
    project.answer("use", "Outdoors")
    time.sleep(1.2)
    assert lurker.thread.is_alive()
    project.ring()
    assert lurker.result() == "sent"


def test_lurk_times_out_and_cli_reports_it(project, capsys):
    from calipurr.cli import main

    project.meow("bore", "Bore", "How wide?")
    assert main(["lurk", "--timeout", "0", "--json", "--project", str(project.root)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["reason"] == "timeout" and out["needed"] == ["bore"] and out["dots"] == []
    assert not project.lurking() and not project.handed()


def test_bell_needs_a_waiting_agent_and_a_killed_one_stops_counting(project, served):
    host = served()
    status, body = call(host, "/api/bell", {})
    assert status == 400 and b"No agent is waiting" in body

    project.lurk_path.parent.mkdir(parents=True, exist_ok=True)
    project.lurk_path.touch()
    assert json.loads(call(host, "/api/state")[1])["lurking"] is True
    os.utime(project.lurk_path, (time.time() - 60, time.time() - 60))
    assert json.loads(call(host, "/api/state")[1])["lurking"] is False


@pytest.mark.parametrize(
    "at",
    [
        [[0.5]],
        [[0.5, 1.5]],
        [[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]],
    ],
)
def test_marks_must_fit_their_picture(project, at):
    (project.root / "side.jpg").write_bytes(b"x")
    with pytest.raises(Hiss):
        project.meow("q", "Q", "?", show="side.jpg", at=at)


def test_marks_survive_answers_and_need_a_picture(project, capsys):
    from calipurr.cli import main

    (project.root / "side.jpg").write_bytes(b"x")
    with pytest.raises(Hiss, match="picture"):
        project.meow("q", "Q", "?", at=[[0.1, 0.1]])

    args = ["--project", str(project.root), "--name", "Q", "--ask", "?", "--show", "side.jpg"]
    assert main(["meow", "q", *args, "--at", "0.1,0.2", "--at", "0.3,0.4"]) == 0
    assert project.answer("q", 5)["at"] == [[0.1, 0.2], [0.3, 0.4]]
    assert project.forget("q")["at"] == [[0.1, 0.2], [0.3, 0.4]]


@pytest.mark.parametrize("manifest", [".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "gemini-extension.json"])
def test_plugin_manifests_match_the_package_version(manifest):
    from calipurr import __version__

    root = Path(__file__).parent.parent
    assert json.loads((root / manifest).read_text())["version"] == __version__


@pytest.mark.parametrize(
    "raw, unit, expected, entered",
    [
        ("406", "mm", 406.0, None),
        ("406 mm", "mm", 406.0, None),
        ("16 in", "mm", 406.4, "16 in"),
        ('16"', "mm", 406.4, "16 in"),
        ("16 1/2 inches", "mm", 419.1, "16 1/2 in"),
        ("16-1/2in", "mm", 419.1, "16-1/2 in"),
        ("5/8 in", "mm", 15.875, "5/8 in"),
        ("25.4 mm", "in", 1.0, "25.4 mm"),
        ("5/8 in", "in", 0.625, None),
    ],
)
def test_lengths_convert_to_the_questions_unit(raw, unit, expected, entered):
    assert length_value("D1", raw, unit) == (pytest.approx(expected), entered)


@pytest.mark.parametrize("raw, unit", [("1/0 in", "mm"), ("5/8", "mm"), ("in", "mm"), ("-2 in", "mm"), ("2 in", "rpm")])
def test_unclear_lengths_are_refused(raw, unit):
    with pytest.raises(Hiss):
        length_value("D1", raw, unit)


PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16


def test_photos_stay_with_their_question_through_answers_and_rewording(project):
    project.meow("back", "Back", "What does it look like?", kind="text")
    name = project.add_photo("../../evil.txt", PNG, "back")
    assert name == "photos/evil.png" and (project.root / name).read_bytes() == PNG
    assert project.add_photo("evil.png", PNG, "back") == "photos/evil-2.png"
    project.answer("back", "Grooved")
    project.meow("back", "Back", "Reworded", kind="text")
    project.forget("back")
    assert project.params()["back"]["photos"] == [name, "photos/evil-2.png"]
    project.discard(name)
    assert project.params()["back"]["photos"] == ["photos/evil-2.png"]


@pytest.mark.parametrize("data", [b"<svg></svg>", b"\0\0\0 ftypheic"])
def test_files_that_are_not_viewable_photos_are_refused(project, data):
    with pytest.raises(Hiss):
        project.add_photo("x.png", data)
    assert project.files()["photos"] == []


def test_photo_upload_needs_calipurrs_own_page(project):
    server = make_server(project)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = f"127.0.0.1:{server.server_address[1]}"

    def upload(origin):
        request = urllib.request.Request(f"http://{host}/api/photo?name=a.png", data=PNG, headers={"Origin": origin, "Content-Type": "image/png"})
        try:
            return urllib.request.urlopen(request).status
        except urllib.error.HTTPError as err:
            return err.code

    try:
        assert upload("https://evil.example") == 403
        assert upload(f"http://{host}") == 200
        assert (project.root / "photos" / "a.png").exists()
    finally:
        server.shutdown()
        server.server_close()
