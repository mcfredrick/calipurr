import json

import pytest

from calipurr import profiles
from calipurr.cli import main


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    return tmp_path


def needed(capsys, name):
    capsys.readouterr()
    code = main(["hungry", name, "--json"])
    return code, json.loads(capsys.readouterr().out)["needed"]


def test_new_machine_has_no_defaults_and_hungry_blocks_until_fed(capsys):
    main(["adopt", "laser1", "--kind", "laser"])
    code, missing = needed(capsys, "laser1")
    assert code == 1
    assert set(missing) == {f.key for f in profiles.KINDS["laser"]}
    assert all("value" not in e for e in profiles.load("laser1")["fields"].values())

    for key, value in [("source", "diode"), ("bed_x_mm", "400"), ("bed_y_mm", "400"), ("power_w", "10")]:
        main(["feed", "laser1", key, value])
    main(["feed", "laser1", "kerf_mm", "0.12", "--assumed"])

    code, missing = needed(capsys, "laser1")
    assert (code, missing) == (0, {})


def test_feed_records_provenance_and_survives_reload():
    profiles.adopt("mpcnc", "cnc")
    profiles.feed("mpcnc", "travel_z_mm", "90.5", profiles.MEASURED, "with router installed")
    entry = profiles.load("mpcnc")["fields"]["travel_z_mm"]
    assert entry["value"] == 90.5
    assert entry["status"] == "measured"
    assert entry["note"] == "with router installed"
    assert entry["date"]


@pytest.mark.parametrize(
    "argv",
    [
        ["feed", "mpcnc", "travel_z_mm", "tall"],
        ["feed", "mpcnc", "travel_z_mm", "-5"],
        ["feed", "mpcnc", "travel_z_mm", "nan"],
        ["feed", "mpcnc", "travel_z_mm", "inf"],
        ["feed", "mpcnc", "kerf_mm", "0.1"],
        ["feed", "ghost", "travel_z_mm", "5"],
        ["adopt", "mpcnc", "--kind", "cnc"],
        ["adopt", "../escape", "--kind", "cnc"],
    ],
)
def test_bad_input_is_rejected_without_changing_the_profile(argv, capsys):
    profiles.adopt("mpcnc", "cnc")
    before = profiles.load("mpcnc")
    assert main(argv) == 2
    assert "calipurr:" in capsys.readouterr().err
    assert profiles.load("mpcnc") == before
    assert profiles.litter() == ["mpcnc"]


def test_interview_retries_bad_values_skips_blanks_and_survives_ctrl_d(monkeypatch):
    answers = iter(["plasma", "co2", "n", "400", "", ""])

    def fake_input(_prompt):
        try:
            return next(answers)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    assert main(["adopt", "shop-laser", "--kind", "laser"]) == 0

    fields = profiles.load("shop-laser")["fields"]
    assert (fields["source"]["value"], fields["source"]["status"]) == ("co2", "assumed")
    assert (fields["bed_x_mm"]["value"], fields["bed_x_mm"]["status"]) == (400.0, "measured")
    assert fields["kerf_mm"]["status"] == "needed"


def test_pun_commands_and_plain_aliases_do_the_same_thing(capsys):
    main(["add", "bambu", "--kind", "printer"])
    main(["set", "bambu", "nozzle_mm", "0.4"])
    capsys.readouterr()
    main(["list", "--json"])
    listed = json.loads(capsys.readouterr().out)
    assert listed["bambu"]["kind"] == "printer"
    assert "nozzle_mm" not in listed["bambu"]["needed"]


def test_tags_keep_facts_in_words_and_survive_feeding(capsys):
    main(["adopt", "router", "--kind", "cnc"])
    assert main(["tag", "router", "home_corner", "Front-left"]) == 0
    main(["feed", "router", "travel_x_mm", "440"])
    capsys.readouterr()
    main(["vet", "router"])
    shown = capsys.readouterr().out
    assert "home_corner: Front-left" in shown and "travel_x_mm: 440.0" in shown
    # A tag is never a question, so it can't make a machine hungry or fill a required value.
    assert "home_corner" not in needed(capsys, "router")[1] and "travel_y_mm" in needed(capsys, "router")[1]
    assert main(["tag", "router", "home_corner", "--remove"]) == 0
    assert "notes" not in profiles.load("router") or not profiles.load("router")["notes"]


@pytest.mark.parametrize(
    "argv",
    [
        ["tag", "router", "Bad Name", "text"],
        ["tag", "router", "home", "   "],
        ["tag", "router", "home"],
        ["tag", "router", "home", "text", "--remove"],
        ["tag", "router", "missing", "--remove"],
    ],
)
def test_unclear_tags_are_refused(argv, capsys):
    main(["adopt", "router", "--kind", "cnc"])
    assert main(argv) != 0
    assert not profiles.load("router").get("notes")
