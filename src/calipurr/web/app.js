import * as THREE from 'three';
import { OrbitControls } from '/vendor/OrbitControls.js';
import { STLLoader } from '/vendor/STLLoader.js';

const $ = (id) => document.getElementById(id);
const PERCH_Y = [310, 220, 130, 40];
const STAGE_NOTES = [
  'Measure real things and answer the cat.',
  'Build the model from those numbers. It appears here when an STL lands in this folder.',
  'Look over the fit, clearance and problem cards, and print a test piece for anything risky.',
  'Nothing is blocking this file. Read any hairball warnings, then slice it or send it to CAM.',
];

function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key.startsWith('on') || key === 'value' || key === 'disabled' || key === 'hidden' || key === 'open') node[key] = value;
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  node.append(...children.filter((c) => c !== null && c !== undefined));
  return node;
}

async function post(route, body) {
  const response = await fetch(route, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error);
    error.needsConfirmation = data.needs_confirmation;
    throw error;
  }
  return data.result;
}

function toast(message, good = false) {
  const node = $('toast');
  node.textContent = message;
  node.className = good ? 'good' : '';
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, good ? 4000 : 9000);
}

async function act(route, body, success) {
  try {
    const result = await post(route, body);
    if (success) toast(success, true);
    await refresh(true);
    return result;
  } catch (error) {
    if (error.needsConfirmation) throw error;
    toast(error.message);
    return null;
  }
}

const ui = {
  state: null,
  stateText: '',
  file: null,
  machine: localStorage.getItem('calipurr-machine') || '',
  mode: 'spin',
  showDims: true,
  pickedStep: null,
  hoverStep: null,
  check: null,
  viewedStage: null,
  drafts: { measured: '', material: '', note: '' },
};

// 3D view

const canvas = $('view');
const stage = $('stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
const scene = new THREE.Scene();
scene.background = new THREE.Color('#f4f0e6');
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8577, 2.2));
const sun = new THREE.DirectionalLight(0xffffff, 2.0);
sun.position.set(1, -1.5, 2);
scene.add(sun);
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 20000);
camera.up.set(0, 0, 1);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
const loader = new STLLoader();
const ray = new THREE.Raycaster();

const view = { mesh: null, name: null, mtime: null, box: new THREE.Box3(), helpers: new THREE.Group(), band: null };
scene.add(view.helpers);

function clearModel() {
  if (view.mesh) {
    scene.remove(view.mesh);
    view.mesh.geometry.dispose();
    view.mesh = null;
  }
  view.helpers.clear();
  view.band = null;
}

function frameCamera() {
  const size = view.box.getSize(new THREE.Vector3());
  const center = view.box.getCenter(new THREE.Vector3());
  const distance = Math.max(size.length(), 1) * 1.9;
  camera.position.copy(center).add(new THREE.Vector3(0.3, -1, 0.55).normalize().multiplyScalar(distance));
  camera.near = distance / 200;
  camera.far = distance * 20;
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
}

function loadModel(file) {
  const reframing = view.name !== file.name;
  view.name = file.name;
  view.mtime = file.mtime;
  loader.load(fileUrl(file), (geometry) => {
    if (view.name !== file.name || view.mtime !== file.mtime) return;
    clearModel();
    geometry.computeBoundingBox();
    view.box.copy(geometry.boundingBox);
    view.mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0x9fb6c4, roughness: 0.65, metalness: 0.05 }));
    scene.add(view.mesh);
    const size = view.box.getSize(new THREE.Vector3());
    const center = view.box.getCenter(new THREE.Vector3());
    const grid = new THREE.GridHelper(Math.max(size.x, size.y) * 1.6, 16, 0xbdb5a2, 0xd8d1c0);
    grid.rotation.x = Math.PI / 2;
    grid.position.set(center.x, center.y, view.box.min.z);
    view.helpers.add(grid);
    const outline = new THREE.Box3Helper(view.box, 0x8a8577);
    outline.visible = ui.showDims;
    outline.name = 'outline';
    view.helpers.add(outline);
    if (reframing) frameCamera();
    updateBand();
    window.__calipurrLoaded = file.name;
  }, undefined, () => toast(`Couldn't load ${file.name}`));
}

function fileUrl(file) {
  return `/file/${file.name.split('/').map(encodeURIComponent).join('/')}?v=${file.mtime}`;
}

function resize() {
  const width = stage.clientWidth;
  const height = stage.clientHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(stage);

function toScreen(position) {
  const vector = new THREE.Vector3(...position).project(camera);
  return { x: (vector.x + 1) / 2 * stage.clientWidth, y: (1 - vector.y) / 2 * stage.clientHeight };
}

function currentGauge() {
  const kitten = ui.state?.kittens.find((k) => k.file === ui.file);
  return kitten?.type === 'gauge' ? kitten : null;
}

function updateBand() {
  if (view.band) {
    view.helpers.remove(view.band);
    view.band = null;
  }
  const gauge = currentGauge();
  const letter = ui.hoverStep || ui.pickedStep;
  if (!gauge || !letter || !view.mesh) return;
  const step = gauge.steps.find((s) => s.letter === letter);
  const largest = Math.max(view.box.max.x - view.box.min.x, view.box.max.y - view.box.min.y);
  const radius = (gauge.kind === 'socket' ? largest / 2 : step.size_mm / 2) + 0.12;
  const geometry = new THREE.CylinderGeometry(radius, radius, step.z1 - step.z0, 96, 1, true);
  geometry.rotateX(Math.PI / 2);
  view.band = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: 0xe9c74e, transparent: true, opacity: 0.62, side: THREE.DoubleSide, depthWrite: false }));
  view.band.position.set((view.box.min.x + view.box.max.x) / 2, (view.box.min.y + view.box.max.y) / 2, (step.z0 + step.z1) / 2);
  view.helpers.add(view.band);
}

function hitModel(event) {
  if (!view.mesh) return null;
  const rect = canvas.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2(
    (event.clientX - rect.left) / rect.width * 2 - 1,
    -(event.clientY - rect.top) / rect.height * 2 + 1,
  ), camera);
  return ray.intersectObject(view.mesh)[0] || null;
}

function stepAt(event) {
  const gauge = currentGauge();
  const hit = gauge && hitModel(event);
  if (!hit) return null;
  const step = gauge.steps.find((s) => hit.point.z >= s.z0 && hit.point.z < s.z1);
  return step ? step.letter : null;
}

let press = null;
canvas.addEventListener('pointerdown', (event) => { press = { x: event.clientX, y: event.clientY }; });
canvas.addEventListener('pointerup', async (event) => {
  if (!press || Math.hypot(event.clientX - press.x, event.clientY - press.y) > 5) return;
  press = null;
  if (ui.mode === 'point') {
    const hit = hitModel(event);
    if (!hit) {
      toast('Click on the model to place a dot.');
      return;
    }
    await placeDot([hit.point.x, hit.point.y, hit.point.z].map((v) => +v.toFixed(3)));
  } else if (ui.mode === 'paw') {
    const letter = stepAt(event);
    if (letter) {
      ui.pickedStep = letter;
      updateBand();
      renderReport();
    }
  }
});
canvas.addEventListener('pointermove', (event) => {
  if (ui.mode !== 'paw') return;
  const letter = stepAt(event);
  if (letter !== ui.hoverStep) {
    ui.hoverStep = letter;
    updateBand();
  }
  ui.tip = letter ? { x: event.clientX - canvas.getBoundingClientRect().left, y: event.clientY - canvas.getBoundingClientRect().top } : null;
});
canvas.addEventListener('pointerleave', () => {
  ui.hoverStep = null;
  ui.tip = null;
  updateBand();
});

async function placeDot(position) {
  const dot = await act('/api/dots', { file: ui.file, position });
  if (dot) document.querySelector(`#comments input[data-id="${dot.id}"]`)?.focus();
}

$('photoimg').addEventListener('click', (event) => {
  if (ui.mode !== 'point') {
    toast('Choose the laser dot tool to mark this photo.');
    return;
  }
  const rect = event.target.getBoundingClientRect();
  placeDot([(event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height].map((v) => +v.toFixed(4)));
});

function isPhoto() {
  return ui.state?.files.photos.some((f) => f.name === ui.file) || ui.state?.discarded.some((f) => f.name === ui.file && !f.name.toLowerCase().endsWith('.stl'));
}

// Overlay of dots, dimensions and the step tip, redrawn every frame because they follow the camera.

const overlay = $('overlay');
const pins = new Map();

function syncPins() {
  const dots = ui.state ? ui.state.dots.filter((d) => d.file === ui.file) : [];
  const live = new Set(dots.map((d) => d.id));
  for (const [id, node] of pins) {
    if (!live.has(id)) {
      node.remove();
      pins.delete(id);
    }
  }
  dots.forEach((dot, index) => {
    let node = pins.get(dot.id);
    if (!node) {
      node = h('button', {
        class: 'pin',
        type: 'button',
        onclick: () => { if (ui.mode === 'point') act('/api/dots/remove', { id: dot.id }); },
      });
      overlay.append(node);
      pins.set(dot.id, node);
    }
    node.textContent = index + 1;
    node.title = `Dot ${index + 1}${dot.text ? `: ${dot.text}` : ''}. Click with the laser dot tool to remove it.`;
    node.setAttribute('aria-label', `Remove dot ${index + 1}`);
    node.dataset.id = dot.id;
    node.__position = dot.position;
  });
}

function placeOverlay() {
  const photo = isPhoto();
  const image = $('photoimg').getBoundingClientRect();
  const frame = stage.getBoundingClientRect();
  for (const node of pins.values()) {
    const p = node.__position;
    const at = photo
      ? { x: image.left - frame.left + p[0] * image.width, y: image.top - frame.top + p[1] * image.height }
      : toScreen(p);
    node.style.left = `${at.x}px`;
    node.style.top = `${at.y}px`;
  }
  placeDimensions(photo);
  placeStepLabels(photo);
  const tip = overlay.querySelector('.steptip');
  const gauge = currentGauge();
  if (tip) {
    const step = gauge?.steps.find((s) => s.letter === ui.hoverStep);
    tip.hidden = !(step && ui.tip);
    if (step && ui.tip) {
      tip.textContent = `${step.letter}: ${step.size_mm} mm, ${stepPosition(gauge, step)}`;
      tip.style.left = `${ui.tip.x}px`;
      tip.style.top = `${ui.tip.y}px`;
    }
  }
}

function stepPosition(gauge, step) {
  const order = gauge.steps.indexOf(step) + 1;
  const end = gauge.kind === 'socket' ? 'mouth' : 'tip';
  return order === 1 ? `at the ${end}` : `number ${order} from the ${end}`;
}

const dimNodes = ['X', 'Y', 'Z'].map((axis) => {
  const node = h('div', { class: 'dimlabel' });
  node.dataset.axis = axis;
  overlay.append(node);
  return node;
});
overlay.append(h('div', { class: 'steptip', hidden: true }));

function placeDimensions(photo) {
  const show = ui.showDims && !photo && view.mesh;
  const { min, max } = view.box;
  const size = view.box.getSize(new THREE.Vector3());
  const spots = [
    [(min.x + max.x) / 2, min.y, min.z],
    [max.x, (min.y + max.y) / 2, min.z],
    [max.x, min.y, (min.z + max.z) / 2],
  ];
  const values = [size.x, size.y, size.z];
  dimNodes.forEach((node, i) => {
    node.hidden = !show;
    if (!show) return;
    const at = toScreen(spots[i]);
    node.textContent = `${node.dataset.axis} ${values[i].toFixed(2)} mm`;
    node.style.left = `${at.x}px`;
    node.style.top = `${at.y}px`;
  });
}

const stepNodes = new Map();

function placeStepLabels(photo) {
  const gauge = photo || !view.mesh ? null : currentGauge();
  const steps = gauge?.steps || [];
  const live = new Set(steps.map((s) => s.letter));
  for (const [letter, node] of stepNodes) {
    if (!live.has(letter)) {
      node.remove();
      stepNodes.delete(letter);
    }
  }
  if (!gauge) return;
  // Beside the model's right edge on screen, whichever way it's turned.
  const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
  const center = view.box.getCenter(new THREE.Vector3());
  const radius = Math.max(view.box.max.x - view.box.min.x, view.box.max.y - view.box.min.y) / 2 + 2;
  for (const step of steps) {
    let node = stepNodes.get(step.letter);
    if (!node) {
      node = h('div', { class: 'steplabel' }, step.letter);
      overlay.append(node);
      stepNodes.set(step.letter, node);
    }
    const at = toScreen([center.x + right.x * radius, center.y + right.y * radius, (step.z0 + step.z1) / 2]);
    node.style.left = `${at.x}px`;
    node.style.top = `${at.y}px`;
    node.classList.toggle('picked', step.letter === ui.pickedStep);
  }
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
  placeOverlay();
}

// Tools

function setMode(mode) {
  ui.mode = mode;
  $('spin').setAttribute('aria-pressed', mode === 'spin');
  $('point').setAttribute('aria-pressed', mode === 'point');
  $('paw').setAttribute('aria-pressed', mode === 'paw');
  canvas.className = { spin: 'spinning', point: 'pointing', paw: 'picking' }[mode];
  $('photo').className = mode === 'point' ? 'pointing' : '';
  stage.classList.toggle('pointing', mode === 'point');
  controls.enableRotate = mode === 'spin';
  controls.enablePan = mode === 'spin';
}
$('spin').onclick = () => setMode('spin');
$('point').onclick = () => setMode('point');
$('paw').onclick = () => setMode('paw');
$('dims').onclick = () => {
  ui.showDims = !ui.showDims;
  $('dims').setAttribute('aria-pressed', ui.showDims);
  const outline = view.helpers.getObjectByName('outline');
  if (outline) outline.visible = ui.showDims;
};
$('file').onchange = (event) => selectFile(event.target.value);
$('machine').onchange = (event) => {
  ui.machine = event.target.value;
  localStorage.setItem('calipurr-machine', ui.machine);
  ui.check = null;
  renderAll();
  runCheck();
};

function selectFile(name) {
  ui.file = name;
  ui.pickedStep = null;
  ui.hoverStep = null;
  ui.drafts = { measured: '', material: ui.drafts.material, note: '' };
  ui.check = null;
  const gauge = currentGauge();
  if (gauge) setMode('paw');
  else if (ui.mode === 'paw') setMode('spin');
  renderAll();
  runCheck();
}

// Panels

function allFiles() {
  return [...ui.state.files.models, ...ui.state.files.photos, ...ui.state.discarded];
}

function renderFiles() {
  const { models, photos } = ui.state.files;
  const select = $('file');
  select.replaceChildren();
  const group = (label, list) => {
    if (!list.length) return;
    const node = h('optgroup', { label });
    list.forEach((f) => node.append(h('option', { value: f.name }, f.name)));
    select.append(node);
  };
  group('Models', models);
  group('Photos', photos);
  group('Litter box', ui.state.discarded);
  const known = allFiles().some((f) => f.name === ui.file);
  if (!known) ui.file = models[0]?.name || photos[0]?.name || null;
  if (ui.file) select.value = ui.file;

  const file = allFiles().find((f) => f.name === ui.file);
  const photo = isPhoto();
  $('empty').hidden = !!file;
  canvas.hidden = !file || photo;
  $('photo').hidden = !file || !photo;
  $('paw').hidden = !currentGauge();
  if (!file || photo) {
    clearModel();
    view.name = null;
    view.mtime = null;
    if (file) {
      const url = fileUrl(file);
      if ($('photoimg').getAttribute('src') !== url) $('photoimg').src = url;
    }
  } else if (view.name !== file.name || view.mtime !== file.mtime) {
    loadModel(file);
    resize();
  }
  updateBand();
}

function renderBowl() {
  const params = Object.entries(ui.state.params);
  const missing = params.filter(([, e]) => e.status === 'needed').length;
  const fed = params.length - missing;
  const height = params.length ? 32 * fed / params.length : 0;
  $('kibble').setAttribute('y', 48 - height);
  $('kibble').setAttribute('height', height);
  $('bowlmsg').textContent = !params.length
    ? 'Nothing asked yet. Your agent can add questions with calipurr meow.'
    : missing ? `Emily needs ${missing} more value${missing > 1 ? 's' : ''}.` : 'Bowl full. Emily is purring.';

  $('fields').replaceChildren(...params.map(([key, entry]) => fieldNode(key, entry)));
  const build = ui.state.build;
  const buildNode = $('buildstatus');
  buildNode.hidden = !build.configured;
  if (build.configured) {
    const text = build.running ? 'Rebuilding the model...' : build.ok === null ? 'The model rebuilds when a value changes.' : build.ok ? 'Model rebuilt.' : 'The last rebuild failed.';
    buildNode.replaceChildren(h('b', {}, 'Rebuild'), h('div', {}, text));
    if (build.ok === false) buildNode.append(h('pre', { class: 'buildlog' }, build.output));
  }
}

function fieldNode(key, entry) {
  const input = h('input', { id: `f-${key}`, type: 'number', min: '0', step: 'any', value: entry.value ?? '', 'aria-label': `${entry.name || key} in ${entry.unit || 'mm'}` });
  const status = h('select', { 'aria-label': `How you know ${entry.name || key}` },
    h('option', { value: 'measured' }, 'Measured'), h('option', { value: 'assumed' }, 'Assumed'));
  if (entry.status === 'assumed') status.value = 'assumed';
  const commit = () => {
    const changedValue = String(entry.value ?? '') !== input.value;
    const changedStatus = entry.status !== 'needed' && entry.status !== status.value;
    if (changedValue || (changedStatus && input.value !== '')) {
      act('/api/params', { key, value: input.value, status: status.value });
    }
  };
  input.onchange = commit;
  status.onchange = commit;
  const note = entry.note ? h('p', {}, entry.note) : null;
  return h('div', { class: 'field' },
    h('label', { class: 'title', for: `f-${key}` }, `${key}, ${entry.name || ''}`, h('span', { class: `badge ${entry.status}` }, entry.status)),
    h('p', {}, entry.ask || ''),
    h('div', { class: 'row' }, input, h('span', {}, entry.unit || 'mm'), status),
    note,
    gaugeForm(key, entry),
  );
}

function gaugeForm(key, entry) {
  const center = entry.value;
  const from = h('input', { type: 'number', step: 'any', 'aria-label': 'Smallest size', value: center ? +(center - 0.4).toFixed(2) : '' });
  const to = h('input', { type: 'number', step: 'any', 'aria-label': 'Largest size', value: center ? +(center + 0.4).toFixed(2) : '' });
  const step = h('input', { type: 'number', step: 'any', 'aria-label': 'Step size', value: 0.2 });
  const kind = h('select', { 'aria-label': 'What the gauge does' },
    h('option', { value: 'plug' }, 'Plug, goes inside'), h('option', { value: 'socket' }, 'Socket, goes around'));
  const make = h('button', {
    class: 'primary',
    type: 'button',
    onclick: async () => {
      const made = await act('/api/kitten/gauge', { from: from.value, to: to.value, step: step.value, kind: kind.value, for: key }, 'Test piece made. Print it, then tell Emily which step fit.');
      if (made) selectFile(made.file);
    },
  }, 'Make a kitten');
  return h('details', {},
    h('summary', {}, 'Not sure? Make a test piece'),
    h('div', { class: 'row' }, 'From', from, 'to', to, 'by', step, 'mm'),
    h('div', { class: 'row' }, kind, make),
  );
}

function renderLives() {
  const lives = ui.state.lives;
  const nodes = lives.map((life, index) => h('button', {
    type: 'button',
    title: `Go back to ${life.saved}: ${Object.entries(life.values).map(([k, v]) => `${k} ${v ?? 'blank'}`).join(', ')}`,
    'aria-label': `Restore the version saved ${life.saved}`,
    onclick: () => act('/api/lives/restore', { id: life.id }, 'Restored that version. The one you had is saved too.'),
  }, '🐾'));
  nodes.push(h('span', { class: 'current', style: 'opacity:1', title: 'Current version' }, '🐾'));
  while (nodes.length < 9) nodes.push(h('span', {}, '🐾'));
  $('lives').replaceChildren(...nodes);
}

function renderComments() {
  const dots = ui.state.dots.filter((d) => d.file === ui.file);
  $('comments').replaceChildren(...dots.map((dot, index) => {
    const input = h('input', { placeholder: 'Tell Emily about this spot', value: dot.text, 'data-id': dot.id });
    input.onchange = () => act('/api/dots/edit', { id: dot.id, text: input.value });
    return h('li', {},
      h('label', {}, h('b', {}, `Dot ${index + 1}.`), ' ', input),
      h('button', {
        type: 'button',
        'aria-label': `Remove dot ${index + 1}`,
        title: `Remove dot ${index + 1}`,
        onclick: async () => {
          await act('/api/dots/remove', { id: dot.id });
          $('point').focus();
        },
      }, '×'));
  }));
  syncPins();
}

function renderReport() {
  const node = $('report');
  const gauge = currentGauge();
  node.hidden = !gauge;
  if (!gauge) return;
  const end = gauge.kind === 'socket' ? 'mouth' : 'tip';
  const steps = h('div', { class: 'steps', role: 'group', 'aria-label': 'Gauge steps' }, ...gauge.steps.map((step) => h('button', {
    type: 'button',
    'aria-pressed': ui.pickedStep === step.letter,
    onmouseenter: () => { ui.hoverStep = step.letter; updateBand(); },
    onmouseleave: () => { ui.hoverStep = null; updateBand(); },
    onclick: () => { ui.pickedStep = step.letter; updateBand(); renderReport(); },
  }, h('b', {}, step.letter), `${step.size_mm} mm`)));
  const measured = h('input', { type: 'number', step: 'any', placeholder: 'Caliper reading', 'aria-label': 'Caliper reading of the step in millimeters', value: ui.drafts.measured });
  const material = h('input', { placeholder: 'Material', 'aria-label': 'Material', value: ui.drafts.material });
  const note = h('input', { placeholder: 'How did it feel?', 'aria-label': 'How the fit felt', value: ui.drafts.note });
  measured.oninput = () => { ui.drafts.measured = measured.value; };
  material.oninput = () => { ui.drafts.material = material.value; };
  note.oninput = () => { ui.drafts.note = note.value; };
  const warning = h('div', { class: 'warn', role: 'alert', hidden: true });
  const send = async (confirm) => {
    if (!ui.pickedStep || !measured.value) {
      warning.textContent = 'Pick the step that fit, then enter what it measures with calipers.';
      warning.hidden = false;
      return;
    }
    try {
      await act('/api/kitten/report', {
        name: gauge.name,
        letter: ui.pickedStep,
        measured: measured.value,
        material: material.value,
        note: note.value,
        machine: ui.machine,
        confirm,
      }, gauge.for ? `Nom. ${gauge.for} is now measured.` : 'Nom. Result saved.');
    } catch (error) {
      warning.replaceChildren(error.message, ' ', h('button', { type: 'button', class: 'linkish', onclick: () => send(true) }, 'Save it anyway'));
      warning.hidden = false;
    }
  };
  const result = gauge.report
    ? h('p', { class: 'result' }, `Result: step ${gauge.report.letter} fit. Modeled ${gauge.report.modeled_mm} mm, measured ${gauge.report.measured_mm} mm, so it printed ${Math.abs(gauge.report.offset_mm)} mm ${gauge.report.offset_mm < 0 ? 'under' : 'over'}.`)
    : null;
  node.replaceChildren(
    h('h3', {}, `Report card: ${gauge.name}${gauge.for ? `, for ${gauge.for}` : ''}`),
    ...(result ? [result] : []),
    h('p', {}, `Step A is at the ${end}, so it's the first to fit. Click the step that fit on the model or below.`),
    steps,
    h('div', { class: 'row' }, measured, material, note, h('button', { type: 'button', class: 'primary', onclick: () => send(false) }, 'That step fit')),
    warning,
  );
}

function renderLitter() {
  const file = allFiles().find((f) => f.name === ui.file);
  const nodes = [];
  if (file && !file.name.startsWith('litter/')) {
    nodes.push(h('div', {}, h('button', { type: 'button', class: 'linkish', onclick: () => act('/api/litter/discard', { file: file.name }, `Moved ${file.name} to the litter box.`) }, 'Discard this file')));
  }
  if (!ui.state.discarded.length) nodes.push(h('div', {}, 'Nothing discarded.'));
  for (const item of ui.state.discarded) {
    nodes.push(h('div', {}, `${item.name.slice('litter/'.length)} `, h('button', {
      type: 'button',
      class: 'linkish',
      onclick: async () => {
        const moved = await act('/api/litter/rescue', { file: item.name }, 'Rescued from the litter box.');
        if (moved) selectFile(moved.file);
      },
    }, 'Rescue')));
  }
  $('litter').replaceChildren(...nodes);
}

function renderMachines() {
  const machines = ui.state.machines;
  const select = $('machine');
  select.replaceChildren(h('option', { value: '' }, 'None chosen'), ...Object.keys(machines).map((n) => h('option', { value: n }, n)));
  if (!machines[ui.machine]) ui.machine = '';
  select.value = ui.machine;
  const panel = $('machinepanel');
  const machine = machines[ui.machine];
  if (!machine) {
    panel.replaceChildren(h('b', {}, 'Machine'), h('p', {}, Object.keys(machines).length ? 'Choose one from the collar tag to check fit.' : 'Add one with calipurr adopt NAME --kind printer, cnc or laser.'));
    return;
  }
  const needed = Object.entries(machine.fields).filter(([, f]) => f.status === 'needed');
  panel.replaceChildren(
    h('b', {}, `${ui.machine} (${machine.kind})`),
    needed.length ? h('p', {}, 'Emily needs these to check fit.') : h('p', {}, 'All values on file.'),
    ...needed.map(([key, field]) => {
      const input = h('input', { 'aria-label': field.ask, 'data-machine-field': key });
      const status = h('select', { 'aria-label': `How you know: ${field.ask}` }, h('option', { value: 'measured' }, 'Measured'), h('option', { value: 'assumed' }, 'Assumed'));
      input.onchange = () => {
        if (input.value) act('/api/machine/feed', { name: ui.machine, key, value: input.value, status: status.value });
      };
      return h('div', { style: 'margin:6px 0' }, h('label', {}, field.ask), h('div', { class: 'row' }, input, status));
    }),
  );
}

function checkFor(id) {
  return ui.check?.checks.find((c) => c.id === id);
}

function renderChecks() {
  const set = (id, card, text, status) => {
    $(id).textContent = text;
    $(id).closest('.mini').className = `mini ${status || ''}`;
  };
  const model = ui.file && !isPhoto();
  if (!model) {
    for (const id of ['fit', 'whiskers', 'problems']) set(id, null, 'Choose a model to check.', '');
  } else if (!ui.check) {
    for (const id of ['fit', 'whiskers', 'problems']) set(id, null, 'Checking...', '');
  } else {
    const fit = checkFor('fit');
    const pre = fit.status === 'pass' ? 'If it fits, I sits. ' : '';
    set('fit', null, pre + fit.detail, fit.status);
    const room = checkFor('clearance');
    set('whiskers', null, room.detail, room.status);
    const bad = ui.check.checks.filter((c) => ['solid', 'bed', 'overhang'].includes(c.id) && ['warn', 'fail'].includes(c.status));
    set('problems', null, bad.length ? bad.map((c) => `${c.label}: ${c.detail}`).join(' ') : 'None found.', bad.some((c) => c.status === 'fail') ? 'fail' : bad.length ? 'warn' : 'pass');
  }
  if (ui.state.build.ok === false) {
    $('problems').textContent = 'The last rebuild failed. See the food bowl for details.';
    $('problems').closest('.mini').className = 'mini fail';
  }
}

function computedStage() {
  const params = Object.values(ui.state.params);
  if (params.some((e) => e.status === 'needed')) return 0;
  if (!ui.state.files.models.length) return 1;
  // Warnings ask for a look but don't block, because a person can judge them. Failures and unknowns hold here.
  if (!['pass', 'warn'].includes(ui.check?.overall)) return 2;
  return 3;
}

function renderStage() {
  const current = computedStage();
  const shown = ui.viewedStage ?? current;
  document.querySelectorAll('.perch').forEach((perch) => {
    perch.classList.toggle('on', +perch.dataset.i === current);
    perch.classList.toggle('viewing', +perch.dataset.i === shown && shown !== current);
  });
  $('stagecat').style.transform = `translateY(${PERCH_Y[current]}px)`;
  $('stagenote').textContent = STAGE_NOTES[shown];
}
document.querySelectorAll('.perch').forEach((perch) => {
  const choose = () => {
    ui.viewedStage = +perch.dataset.i === computedStage() ? null : +perch.dataset.i;
    renderStage();
  };
  perch.onclick = choose;
  perch.onkeydown = (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      choose();
    }
  };
});

function renderAll() {
  $('project').textContent = ui.state.project;
  renderMachines();
  renderFiles();
  renderBowl();
  renderLives();
  renderComments();
  renderReport();
  renderLitter();
  renderChecks();
  renderStage();
}

async function runCheck() {
  const file = ui.file;
  const machine = ui.machine;
  if (!file || isPhoto()) return;
  const query = new URLSearchParams({ file });
  if (machine) query.set('machine', machine);
  const response = await fetch(`/api/check?${query}`);
  const data = await response.json();
  if (ui.file !== file || ui.machine !== machine) return;
  if (!response.ok) {
    toast(data.error);
    return;
  }
  ui.check = data;
  renderChecks();
  renderStage();
}

// Agents edit the same files, so keep watching them. Skip redraws while the user is typing.

async function refresh(force = false) {
  const response = await fetch('/api/state');
  const text = await response.text();
  if (!force && text === ui.stateText) return;
  const typing = !force && document.activeElement?.matches('input, select, textarea');
  if (typing) return;
  ui.stateText = text;
  ui.state = JSON.parse(text);
  renderAll();
  runCheck();
}

setMode('spin');
resize();
await refresh(true);
if (currentGauge()) setMode('paw');
animate();
setInterval(() => refresh().catch(() => toast('Lost contact with Calipurr. Is it still running?')), 1500);
