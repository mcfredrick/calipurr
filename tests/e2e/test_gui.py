"""Drives the real viewer in Chrome with real mouse events. Run: uv run --group e2e pytest tests/e2e"""

import json
import struct
import threading
import zlib

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


def blank_png(width, height):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    rows = (b"\0" + b"\xcc" * width) * height
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


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
    page.wait_for_selector("#q-D1")
    assert "1 required answer" in page.inner_text("#bowlmsg")

    page.locator("#question details summary").click()
    form = page.locator("#question details")
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
    page.wait_for_selector("#q-H")
    project.add_dot("block.stl", [0, 0, 20], "from the agent")
    page.wait_for_selector(".pin")
    trimesh.creation.box(extents=(10, 10, 80)).export(project.root / "block.stl")
    page.wait_for_function("document.querySelector('.dimlabel[data-axis=Z]').textContent.startsWith('Z 80')", timeout=8000)


def test_values_history_and_litter_box(app):
    page, project = app
    project.meow("D1", "Bore", "Measure it")
    page.wait_for_selector("#q-D1")
    page.fill("#q-D1", "10")
    page.press("#q-D1", "Enter")
    page.wait_for_function("document.querySelector('.qhead .badge').textContent === 'measured'")
    page.fill("#q-D1", "12")
    page.press("#q-D1", "Enter")
    page.wait_for_function("document.querySelector('.chip').title === 'Bore: 12 mm'")
    page.locator("#lives button").last.click()
    page.wait_for_function("document.getElementById('q-D1').value === '10'")
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


def current(page):
    return page.locator("#question h2").inner_text()


def wait_for_question(page, name):
    page.wait_for_function("name => document.querySelector('#question h2')?.textContent === name", arg=name)


def test_carousel_walks_through_questions_until_the_agents_turn(app):
    page, project = app
    assert "no questions" in page.inner_text("#next")
    assert not page.locator("#carousel").is_visible()

    project.meow("use", "Where it lives", "Where does it go?", kind="choice", choices=["Indoors", "Outdoors"])
    project.meow("why", "Reason", "Why replace it?", kind="text")
    project.meow("bore", "Bore", "Measure the bore", unit="mm", show="block.stl")
    project.meow("color", "Color", "Any color?", kind="text", required=False)
    wait_for_question(page, "Where it lives")
    assert "3 questions left" in page.inner_text("#next")
    assert "1 of 4" in page.inner_text("#question")

    # Saving with nothing entered holds on the same question.
    page.click("#question .primary")
    page.wait_for_selector("#toast:not([hidden])")
    assert project.params()["use"]["status"] == "needed"

    page.click("#question label:has-text('Outdoors')")
    page.click("#question .primary")
    wait_for_question(page, "Reason")
    assert project.params()["use"]["value"] == "Outdoors"
    assert page.get_attribute(".chip:nth-child(1)", "title") == "Where it lives: Outdoors"

    # Leaving a question keeps what was typed but saves nothing.
    page.fill("#question textarea", "It is str")
    page.click("button[aria-label='Next question']")
    wait_for_question(page, "Bore")
    page.click("button[aria-label='Previous question']")
    wait_for_question(page, "Reason")
    assert page.input_value("#question textarea") == "It is str"
    assert project.params()["why"]["status"] == "needed"

    page.fill("#question textarea", "It is stripped")
    page.click("#question .primary")
    wait_for_question(page, "Bore")
    page.fill("#question input[type=number]", "12.5")
    page.select_option("#question select", "assumed")
    page.click("#question .primary")

    # Saving skips ahead to what's still open, and optional questions don't hold anything up.
    wait_for_question(page, "Color")
    page.wait_for_function("document.querySelector('#next h2').textContent.includes('Tell your agent')")
    assert "1 optional question" in page.inner_text("#next")
    assert project.hungry() == {}

    # A chip reopens an answer to change or clear it.
    page.click(".chip:has-text('Bore')")
    wait_for_question(page, "Bore")
    assert page.input_value("#question input[type=number]") == "12.5"
    assert page.input_value("#question select") == "assumed"
    page.click("button:has-text('Clear answer')")
    page.wait_for_function("document.querySelector('#next h2').textContent.includes('1 question left')")
    assert project.params()["bore"]["status"] == "needed"
    page.fill("#question input[type=number]", "13")
    page.click("#question .primary")
    page.wait_for_function("document.querySelector('#next h2').textContent.includes('Tell your agent')")

    project.nudge("Print the gauge")
    page.wait_for_function("document.querySelector('#next h2').textContent === 'Print the gauge'")

    # A new question after everything was answered comes straight up.
    project.meow("more", "One more", "Sorry, another", kind="text")
    wait_for_question(page, "One more")


def test_polling_keeps_a_half_typed_answer_and_still_shows_agent_changes(app):
    page, project = app
    project.meow("bore", "Bore", "Measure the bore")
    page.wait_for_selector("#q-bore")
    page.fill("#q-bore", "7")
    project.add_dot("block.stl", [0, 0, 20], "something changed")
    page.wait_for_selector(".pin")
    assert page.input_value("#q-bore") == "7"
    assert page.evaluate("document.activeElement.id") == "q-bore"


def test_questions_mark_their_dimension_and_bring_up_the_picture(app):
    page, project = app
    (project.root / "photos").mkdir()
    (project.root / "photos" / "side.png").write_bytes(blank_png(200, 100))
    project.meow("width", "Width", "Measure it", show="photos/side.png", at=[[0.25, 0.5], [0.75, 0.5]])
    project.meow("across", "Across", "Measure it", show="photos/side.png", at=[[0.25, 0.5], [0.75, 0.5]])
    project.meow("top", "Top", "On the block", show="block.stl", at=[[0, 0, 20]])

    page.wait_for_selector('.mark.active[data-key="width"]')
    assert page.input_value("#file") == "photos/side.png"
    page.wait_for_function("document.getElementById('photoimg').naturalWidth === 200")
    image = page.locator("#photoimg").bounding_box()
    stage = page.locator("#stage").bounding_box()
    line = page.locator('.mark[data-key="width"] .span')
    x1, x2 = (float(line.get_attribute(a)) for a in ("x1", "x2"))
    assert x1 == pytest.approx(image["x"] - stage["x"] + image["width"] * 0.25, abs=1)
    assert x2 == pytest.approx(image["x"] - stage["x"] + image["width"] * 0.75, abs=1)

    # Labels of marks that end in the same place stay readable.
    def glyph_box(key):
        return page.locator(f'.mark[data-key="{key}"] text').evaluate(
            "(n) => { const b = n.getBBox(); return [b.y, b.y + b.height]; }"
        )

    (top_a, bottom_a), (top_b, bottom_b) = glyph_box("width"), glyph_box("across")
    assert bottom_a <= top_b or bottom_b <= top_a

    # Marks on other pictures stay off this one.
    assert page.locator('.mark[data-key="top"]').count() == 0

    # The highlight follows the question within one picture, and across to the next.
    page.fill("#question input[type=number]", "30")
    page.click("#question .primary")
    page.wait_for_selector('.mark.active[data-key="across"]')
    assert page.locator(".mark.active").count() == 1
    page.click("button[aria-label='Next question']")
    page.wait_for_selector('.mark.active[data-key="top"]')
    assert page.input_value("#file") == "block.stl"

    # Clicking a label on the picture goes to its question, and the mark shows the answer.
    page.click(".chip:has-text('Width')")
    page.wait_for_selector('.mark.active[data-key="width"]')
    assert page.text_content('.mark[data-key="width"] text') == "Width: 30 mm"
    page.wait_for_function("(i => i.complete && i.getBoundingClientRect().width > 0)(document.getElementById('photoimg'))")
    page.wait_for_timeout(100)
    page.locator('.mark[data-key="across"] text').click(force=True)
    wait_for_question(page, "Across")


def test_picture_and_question_stay_in_view_with_many_questions(app):
    page, project = app
    for number in range(40):
        project.meow(f"q{number}", f"Question {number}", "Measure it", show="block.stl", at=[[number, 0, 20]])
    page.wait_for_function("document.querySelectorAll('.chip').length === 40")

    assert page.evaluate("document.documentElement.scrollHeight <= window.innerHeight")
    stage = page.locator("#stage").bounding_box()
    last_chip = page.locator(".chip").last.bounding_box()
    save = page.locator("#question .answer .primary").bounding_box()
    assert stage["height"] >= 260
    assert save["y"] + save["height"] <= 1000 and last_chip["y"] + last_chip["height"] <= 1000
