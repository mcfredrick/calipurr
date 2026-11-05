"""Drives the real viewer in Chrome with real mouse events. Run: uv run --group e2e pytest tests/e2e"""

import json
import threading

import pytest
import trimesh

playwright_api = pytest.importorskip("playwright.sync_api")

from calipurr import profiles  # noqa: E402
from calipurr.project import Project  # noqa: E402
from calipurr.server import make_server  # noqa: E402

CHROME_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as pw:
        instance = pw.chromium.launch(channel="chrome", headless=True, args=CHROME_ARGS)
        yield instance
        instance.close()


@pytest.fixture
def app(browser, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    root = tmp_path / "part"
    root.mkdir()
    block = trimesh.creation.box(extents=(60, 40, 20))
    block.apply_translation((0, 0, 10))
    block.export(root / "block.stl")
    project = Project(root)
    server = make_server(project)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    page = browser.new_page(viewport={"width": 1400, "height": 1000})
    problems = []
    page.on("pageerror", lambda err: problems.append(str(err)))
    # Chrome logs the mismatch warning's 409 response, which the page handles on purpose.
    page.on("console", lambda m: problems.append(m.text) if m.type == "error" and "409" not in m.text else None)
    page.goto(f"http://127.0.0.1:{server.server_address[1]}/")
    page.wait_for_function("window.__calipurrLoaded === 'block.stl'")
    yield page, project
    page.close()
    server.shutdown()
    server.server_close()
    assert problems == []


def canvas_center(page):
    box = page.locator("#view").bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def test_dots_land_on_the_model_follow_it_and_can_be_removed(app):
    page, project = app
    x, y = canvas_center(page)
    page.click("#point")

    page.mouse.click(x, y)
    page.wait_for_selector("#comments input")
    dot = project.dots()[0]
    px, py, pz = dot["position"]
    # The click hit the block's surface.
    assert -30.01 <= px <= 30.01 and -20.01 <= py <= 20.01 and -0.01 <= pz <= 20.01

    page.locator("#comments input").first.fill("chamfer this")
    page.locator("#comments input").first.press("Tab")
    page.wait_for_function("document.querySelector('.pin').title.includes('chamfer')")
    assert project.dots()[0]["text"] == "chamfer this"

    # A click off the model places nothing.
    box = page.locator("#view").bounding_box()
    page.mouse.click(box["x"] + 8, box["y"] + 8)
    assert len(project.dots()) == 1

    before = page.locator(".pin").bounding_box()
    page.click("#spin")
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 150, y + 40, steps=6)
    page.mouse.up()
    page.wait_for_timeout(600)
    after = page.locator(".pin").bounding_box()
    assert abs(after["x"] - before["x"]) + abs(after["y"] - before["y"]) > 5
    assert project.dots()[0]["position"] == dot["position"]

    # Rotating never removes a dot, even if the drag starts on one.
    page.click("#point")
    page.mouse.click(x, y)
    page.wait_for_function("document.querySelectorAll('.pin').length === 2")
    page.locator("#comments button").first.click()
    page.wait_for_function("document.querySelectorAll('.pin').length === 1")
    assert [d["id"] for d in project.dots()] == [2]
    assert page.locator("#comments b").first.inner_text() == "Dot 1."

    page.locator(".pin").click()
    page.wait_for_function("document.querySelectorAll('.pin').length === 0")
    assert project.dots() == []


def test_full_gauge_loop_with_step_picked_on_the_model(app):
    page, project = app
    project.meow("D1", "Tube inside diameter", "Measure at two spots with calipers")
    page.wait_for_selector("#f-D1")
    assert "1 more value" in page.inner_text("#bowlmsg")

    page.locator(".field details summary").first.click()
    form = page.locator(".field details")
    form.locator('input[aria-label="Smallest size"]').fill("20.3")
    form.locator('input[aria-label="Largest size"]').fill("21.1")
    form.locator("button.primary").click()
    page.wait_for_function("window.__calipurrLoaded.startsWith('kittens/')")
    page.wait_for_selector("#report:not([hidden])")
    assert page.get_attribute("#paw", "aria-pressed") == "true"
    page.wait_for_function("!document.getElementById('problems').textContent.includes('Checking')")
    assert page.inner_text("#problems") == "None found."
    assert "null" not in page.inner_text("#report")
    # The plug stands tip-up, so A belongs at the top of the screen.
    labels = page.locator(".steplabel")
    assert labels.all_inner_texts() == list("ABCDE")
    heights = [labels.nth(i).bounding_box()["y"] for i in range(5)]
    assert heights == sorted(heights)

    # Sweep the tall gauge from top to bottom to find a step by hovering, then click it.
    box = page.locator("#view").bounding_box()
    x = box["x"] + box["width"] / 2
    letters = []
    for i in range(10, 90, 4):
        y = box["y"] + box["height"] * i / 100
        page.mouse.move(x, y)
        page.wait_for_timeout(30)
        tip = page.locator(".steptip")
        if tip.is_visible():
            letters.append((tip.inner_text()[0], y))
    seen = [letter for letter, _ in letters]
    # The plug stands tip-up, so the sweep meets A at the top first.
    assert seen[0] == "A" and set("ABCDE") <= set(seen)
    assert seen == sorted(seen)

    target_y = next(y for letter, y in letters if letter == "D")
    page.mouse.click(x, target_y)
    page.wait_for_selector('.steps button[aria-pressed="true"]')
    assert page.locator('.steps button[aria-pressed="true"]').inner_text().startswith("D")

    measured = page.locator('input[aria-label^="Caliper"]')
    measured.fill("20.0")
    page.fill('input[aria-label="Material"]', "PLA")
    page.click("text=That step fit")
    page.wait_for_selector("text=Save it anyway")
    assert project.params()["D1"]["status"] == "needed"

    measured = page.locator('input[aria-label^="Caliper"]')
    measured.fill("20.75")
    page.click("text=That step fit")
    page.wait_for_selector("text=Result: step D fit")
    param = project.params()["D1"]
    assert param["value"] == 20.9 and param["status"] == "measured" and "PLA" in param["note"]
    assert "Bowl full" in page.inner_text("#bowlmsg")


def test_agent_edits_appear_without_reloading(app):
    page, project = app
    project.meow("H", "Height", "How much room is there?")
    page.wait_for_selector("#f-H")
    project.add_dot("block.stl", [0, 0, 20], "from the agent")
    page.wait_for_selector(".pin")
    trimesh.creation.box(extents=(10, 10, 80)).export(project.root / "block.stl")
    page.wait_for_function("document.querySelector('.dimlabel[data-axis=Z]').textContent.startsWith('Z 80')", timeout=8000)


def test_values_history_and_litter_box(app):
    page, project = app
    project.meow("D1", "Bore", "Measure it")
    page.wait_for_selector("#f-D1")
    page.fill("#f-D1", "10")
    page.press("#f-D1", "Tab")
    page.wait_for_function("document.querySelector('.badge').textContent === 'measured'")
    page.fill("#f-D1", "12")
    page.press("#f-D1", "Tab")
    page.wait_for_function("document.getElementById('f-D1').value === '12'")
    page.locator("#lives button").last.click()
    page.wait_for_function("document.getElementById('f-D1').value === '10'")
    assert project.params()["D1"]["value"] == 10

    page.click("text=Discard this file")
    page.wait_for_selector("#litter >> text=Rescue", timeout=4000)
    assert not (project.root / "block.stl").exists()
    page.click("#litter >> text=Rescue")
    page.wait_for_selector("text=Discard this file")
    page.wait_for_function("window.__calipurrLoaded === 'block.stl'")
    assert (project.root / "block.stl").exists()


def test_photo_can_be_marked_with_dots(app):
    page, project = app
    import base64

    png = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg=="
    photos = project.root / "photos"
    photos.mkdir()
    (photos / "machine.png").write_bytes(base64.b64decode(png))
    page.wait_for_selector('option[value="photos/machine.png"]', state="attached")
    page.select_option("#file", "photos/machine.png")
    page.wait_for_function("document.getElementById('photoimg').naturalWidth > 0")
    page.evaluate("document.getElementById('photoimg').style.width='300px'")
    page.click("#point")
    box = page.locator("#photoimg").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.25, box["y"] + box["height"] * 0.5)
    page.wait_for_selector(".pin")
    u, v = project.dots()[0]["position"]
    assert u == pytest.approx(0.25, abs=0.02) and v == pytest.approx(0.5, abs=0.02)
    pin = page.locator(".pin").bounding_box()
    assert pin["x"] + pin["width"] / 2 == pytest.approx(box["x"] + box["width"] * 0.25, abs=3)


def test_collar_tag_runs_machine_checks(app):
    page, project = app
    profiles.adopt("p1s", "printer")
    page.wait_for_selector('#machine option[value="p1s"]', state="attached")
    page.select_option("#machine", "p1s")
    page.wait_for_function("document.getElementById('fit').textContent.includes('still needs')")
    for key, value in [("build_x_mm", "256"), ("build_y_mm", "256"), ("build_z_mm", "256")]:
        page.fill(f'input[data-machine-field="{key}"]', value)
        page.press(f'input[data-machine-field="{key}"]', "Tab")
        page.wait_for_function(f"!document.querySelector('input[data-machine-field=\"{key}\"]')")
    page.wait_for_function("document.getElementById('fit').textContent.startsWith('If it fits, I sits.')")
    assert json.loads(json.dumps(profiles.load("p1s")))["fields"]["build_x_mm"]["value"] == 256
