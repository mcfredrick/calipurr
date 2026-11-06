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
const WALKTHROUGH_NOTE = 'Nothing is left to prepare. Follow the walkthrough at the machine.';

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

async function sendPhotos(files) {
  const key = ui.currentQuestion;
  const asked = key && (ui.state.params[key].name || key);
  for (const file of files) {
    const query = new URLSearchParams({ name: file.name });
    if (key) query.set('key', key);
    try {
      const response = await fetch(`/api/photo?${query}`, { method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      toast(asked ? `Photo added to ${asked}.` : 'Photo added.', true);
      await refresh(true);
      selectFile(data.result.file);
    } catch (error) {
      toast(`${file.name}: ${error.message}`);
    }
  }
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
  answerDrafts: new Map(),
  noteDrafts: new Map(),
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

// The current question's dimension. It belongs to the question, unlike dots, which are comments.

const SVG_NS = 'http://www.w3.org/2000/svg';
const marksLayer = overlay.appendChild(document.createElementNS(SVG_NS, 'svg'));
marksLayer.id = 'marks';
let mark = null;

function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

function valueLabel(entry) {
  return typeof entry.value === 'number' ? `${entry.value} ${entry.unit || 'mm'}` : entry.value;
}

function markLabel(key, entry) {
  const name = entry.name || key;
  return entry.value === undefined ? name : `${name}: ${valueLabel(entry)}`;
}

function syncMark() {
  const key = ui.currentQuestion;
  const entry = key && ui.state.params[key];
  if (!entry?.at || entry.show !== ui.file) {
    mark = null;
    marksLayer.replaceChildren();
    return;
  }
  const group = svg('g', { class: 'mark', 'data-key': key });
  const halo = svg('line', { class: 'halo' });
  const line = svg('line', { class: 'span' });
  const ends = entry.at.map(() => svg('circle', { r: 4.5 }));
  const text = svg('text');
  text.textContent = markLabel(key, entry);
  group.append(halo, line, ...ends, text);
  marksLayer.replaceChildren(group);
  mark = { entry, halo, line, ends, text };
}

function placeMark(locate, width) {
  if (!mark) return;
  const [a, b = a] = mark.entry.at.map(locate);
  for (const line of [mark.halo, mark.line]) {
    line.setAttribute('x1', a.x);
    line.setAttribute('y1', a.y);
    line.setAttribute('x2', b.x);
    line.setAttribute('y2', b.y);
  }
  [a, b].slice(0, mark.ends.length).forEach((point, index) => {
    mark.ends[index].setAttribute('cx', point.x);
    mark.ends[index].setAttribute('cy', point.y);
  });
  // The label continues past the line's end so it doesn't cover what's being measured.
  const length = Math.hypot(b.x - a.x, b.y - a.y);
  const along = length ? { x: (b.x - a.x) / length, y: (b.y - a.y) / length } : { x: 1, y: 0 };
  const roomRight = b.x + 12 * along.x < width - 190;
  mark.text.setAttribute('x', b.x + 12 * along.x);
  mark.text.setAttribute('y', b.y + 12 * along.y + 4);
  mark.text.setAttribute('text-anchor', along.x >= 0 && roomRight ? 'start' : 'end');
}

function placeOverlay() {
  const photo = isPhoto();
  const image = $('photoimg').getBoundingClientRect();
  const frame = stage.getBoundingClientRect();
  const locate = (p) => (photo
    ? { x: image.left - frame.left + p[0] * image.width, y: image.top - frame.top + p[1] * image.height }
    : toScreen(p));
  placeMark(locate, frame.width);
  for (const node of pins.values()) {
    const at = locate(node.__position);
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

const hasFiles = (event) => event.dataTransfer?.types.includes('Files');
window.addEventListener('dragover', (event) => {
  if (!hasFiles(event)) return;
  // Without this the browser opens the dropped file in place of the page.
  event.preventDefault();
  document.body.classList.add('dropping');
});
window.addEventListener('dragleave', (event) => {
  if (!event.relatedTarget) document.body.classList.remove('dropping');
});
window.addEventListener('drop', (event) => {
  document.body.classList.remove('dropping');
  if (!hasFiles(event)) return;
  event.preventDefault();
  sendPhotos([...event.dataTransfer.files]);
});

function renderBowl() {
  const params = Object.entries(ui.state.params);
  const required = params.filter(([, e]) => e.required !== false);
  const missing = required.filter(([, e]) => e.status === 'needed').length;
  const fed = required.length - missing;
  const height = required.length ? 32 * fed / required.length : 0;
  $('kibble').setAttribute('y', 48 - height);
  $('kibble').setAttribute('height', height);
  $('bowlmsg').textContent = !params.length
    ? 'Nothing asked yet.'
    : missing ? `${missing} required answer${missing > 1 ? 's' : ''} to go.` : 'Bowl full. Emily is purring.';

  const build = ui.state.build;
  const buildNode = $('buildstatus');
  buildNode.hidden = !build.configured;
  if (build.configured) {
    const text = build.running ? 'Rebuilding the model...' : build.ok === null ? 'The model rebuilds when a value changes.' : build.ok ? 'Model rebuilt.' : 'The last rebuild failed.';
    buildNode.replaceChildren(h('b', {}, 'Rebuild'), h('div', {}, text));
    if (build.ok === false) buildNode.append(h('pre', { class: 'buildlog' }, build.output));
  }
}

function answerInput(key, entry, id) {
  if (entry.kind === 'choice') {
    return h('div', { class: 'choices', role: 'radiogroup', 'aria-label': entry.name || key }, ...entry.choices.map((choice) => h('label', {},
      h('input', { type: 'radio', name: `${id}-${key}`, value: choice, ...(entry.value === choice ? { checked: '' } : {}) }), choice)));
  }
  if (entry.kind === 'text') return h('textarea', { id, rows: 2, 'aria-label': entry.name || key, value: entry.value ?? '' });
  return null;
}

function answerValue(node) {
  const picked = node.querySelector?.('input:checked');
  return picked ? picked.value : node.value ?? '';
}

function photoList(entry) {
  const known = new Map(ui.state.files.photos.map((f) => [f.name, f]));
  const thumbs = (entry.photos || []).filter((name) => known.has(name)).map((name) => h('button', { type: 'button', 'aria-label': `Show ${name}`, title: name, onclick: () => selectFile(name) },
    h('img', { src: fileUrl(known.get(name)), alt: '' })));
  const input = h('input', { type: 'file', accept: 'image/*', multiple: '', 'aria-label': 'Add a photo to this question' });
  input.addEventListener('change', () => sendPhotos([...input.files]));
  return h('div', { class: 'photos' }, ...thumbs, h('label', { class: 'addphoto' }, input, 'Add a photo (or drop one anywhere)'));
}

function noteBox(key, entry) {
  const box = h('textarea', { rows: 2, class: 'qnote', 'aria-label': 'Note for your agent', placeholder: 'Note for your agent (optional). Explain a photo, or anything else.', value: ui.noteDrafts.get(key) ?? entry.comment ?? '' });
  box.addEventListener('input', () => ui.noteDrafts.set(key, box.value));
  box.addEventListener('change', async () => {
    const text = box.value;
    try {
      await post('/api/params/comment', { key, text });
      if (ui.noteDrafts.get(key) === text) ui.noteDrafts.delete(key);
      await refresh(true);
    } catch (error) {
      toast(error.message);
    }
  });
  return box;
}

function badge(entry) {
  const optional = entry.status === 'needed' && entry.required === false;
  return h('span', { class: `badge ${optional ? 'optional' : entry.status}` }, optional ? 'optional' : entry.status);
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

function nextUnanswered(afterKey) {
  const params = Object.entries(ui.state.params);
  const start = params.findIndex(([key]) => key === afterKey) + 1;
  const open = [...params.slice(start), ...params.slice(0, start)].filter(([, e]) => e.status === 'needed');
  return (open.find(([, e]) => e.required !== false) || open[0])?.[0] ?? null;
}

function goToQuestion(key) {
  ui.currentQuestion = key;
  renderCarousel();
  syncMark();
}

function questionNode(key, entry, position, total) {
  const id = `q-${key}`;
  const keys = Object.keys(ui.state.params);
  const step = (by) => goToQuestion(keys[(position - 1 + by + total) % total]);
  let control = answerInput(key, entry, id);
  let status = null;
  let unitPick = null;
  if (!control) {
    const unit = entry.unit || 'mm';
    control = h('input', { id, type: 'text', inputmode: 'decimal', autocomplete: 'off', 'aria-label': entry.name || key, value: entry.value ?? '' });
    if (unit === 'mm' || unit === 'in') {
      unitPick = h('select', { 'aria-label': 'Unit' }, h('option', { value: 'mm' }, 'mm'), h('option', { value: 'in' }, 'in'));
      // A saved value is stored in the question's unit, so show it in that unit.
      unitPick.value = entry.value === undefined ? ui.lengthUnit || unit : unit;
      unitPick.addEventListener('change', () => { ui.lengthUnit = unitPick.value; });
    }
    status = h('select', { 'aria-label': 'How you know this' }, h('option', { value: 'measured' }, 'Measured'), h('option', { value: 'assumed' }, 'Just a guess'));
    if (entry.status === 'assumed') status.value = 'assumed';
  }
  if (control.matches('input, textarea')) {
    if (ui.answerDrafts.has(key)) control.value = ui.answerDrafts.get(key);
    control.addEventListener('input', () => ui.answerDrafts.set(key, control.value));
  }
  const save = async () => {
    const typed = answerValue(control);
    const value = unitPick && unitPick.value !== entry.unit && typed ? `${typed} ${unitPick.value}` : typed;
    if (!value) {
      toast(entry.status === 'needed' ? 'Enter an answer, or use the arrows to come back to this later.' : 'Enter an answer, or use Clear answer.');
      return;
    }
    if (String(entry.value ?? '') !== value || (status && entry.status !== status.value)) {
      const saved = await act('/api/params', { key, value, status: status ? status.value : undefined });
      if (!saved) return;
      ui.answerDrafts.delete(key);
    }
    const next = nextUnanswered(key);
    if (next) goToQuestion(next);
    document.querySelector('#question textarea, #question input:not([type=radio])')?.focus();
  };
  if (entry.kind !== 'text') control.addEventListener('keydown', (event) => { if (event.key === 'Enter') save(); });
  const answered = entry.status !== 'needed';
  const seePicture = entry.show ? h('button', { type: 'button', class: 'linkish', onclick: () => selectFile(entry.show) }, 'Show its picture') : null;
  const clear = answered ? h('button', { type: 'button', class: 'linkish', onclick: () => {
    ui.answerDrafts.delete(key);
    act('/api/params', { key, value: '' });
  } }, 'Clear answer') : null;
  return h('div', {},
    h('div', { class: 'qhead' },
      h('button', { type: 'button', class: 'arrow', 'aria-label': 'Previous question', onclick: () => step(-1) }, '‹'),
      h('h2', {}, entry.name || key),
      badge(entry),
      h('span', { class: 'count' }, `${position} of ${total}`),
      h('button', { type: 'button', class: 'arrow', 'aria-label': 'Next question', onclick: () => step(1) }, '›')),
    h('p', { class: 'ask' }, entry.ask || ''),
    entry.why ? h('p', { class: 'why' }, entry.why) : null,
    status && !entry.at ? h('p', { class: 'why' }, "This one isn't marked on a picture.") : null,
    entry.note ? h('p', { class: 'why' }, entry.note) : null,
    h('div', { class: 'answer' },
      control,
      unitPick ?? (status ? h('span', {}, entry.unit || 'mm') : null),
      status,
      h('button', { type: 'button', class: 'primary', onclick: save }, nextUnanswered(key) ? 'Save and next' : 'Save'),
      seePicture,
      clear),
    status ? gaugeForm(key, entry) : null,
    noteBox(key, entry),
    photoList(entry));
}

function chipNode(key, entry) {
  const label = entry.value === undefined ? `${entry.name || key}: not answered` : markLabel(key, entry);
  const optional = entry.status === 'needed' && entry.required === false;
  return h('button', {
    type: 'button',
    class: `chip ${optional ? 'optional' : entry.status}`,
    'aria-current': key === ui.currentQuestion ? 'true' : null,
    'aria-label': label,
    title: label,
    onclick: () => goToQuestion(key),
  }, entry.name || key);
}

function renderCarousel() {
  const params = Object.entries(ui.state.params);
  $('carousel').hidden = !params.length;
  if (!params.length) {
    ui.currentQuestion = null;
    ui.shownQuestion = null;
    return;
  }
  const open = nextUnanswered(null);
  const requiredOpen = params.some(([, e]) => e.status === 'needed' && e.required !== false);
  // An agent asking something new after everything was answered should bring it straight up.
  if (!ui.state.params[ui.currentQuestion] || (ui.finished && requiredOpen)) ui.currentQuestion = open ?? params[0][0];
  ui.finished = !requiredOpen;
  const key = ui.currentQuestion;
  const entry = ui.state.params[key];
  $('chips').replaceChildren(...params.map(([k, e]) => chipNode(k, e)));
  // Redrawing the same question would wipe a half-typed answer.
  // Saving a note must not redraw either: the click that moved focus off it would land on a replaced button.
  const shown = JSON.stringify([key, { ...entry, comment: undefined }, open]);
  if (ui.shownQuestion !== shown) {
    ui.shownQuestion = shown;
    $('question').replaceChildren(questionNode(key, entry, params.findIndex(([k]) => k === key) + 1, params.length));
  }
  if (ui.askedKey !== key) {
    ui.askedKey = key;
    if (entry.show && entry.show !== ui.file) selectFile(entry.show);
  }
}

function emilyCard(variant, kicker, title, ...rest) {
  return h('div', { class: `nextcard ${variant}` },
    h('img', { src: '/logo.svg', alt: '' }),
    h('span', { class: 'kicker' }, kicker),
    h('h2', {}, title),
    ...rest);
}

function renderNext() {
  const params = Object.values(ui.state.params);
  const needed = params.filter((e) => e.required !== false && e.status === 'needed').length;
  const optional = params.filter((e) => e.required === false && e.status === 'needed').length;
  const node = $('next');
  const copy = (opening, primary = true) => {
    const text = `${opening} Read my answers and comments with: calipurr bowl --json --project "${ui.state.root}" and calipurr dots --json --project "${ui.state.root}"`;
    return h('button', { type: 'button', class: primary ? 'primary' : '', onclick: async () => {
      await navigator.clipboard.writeText(text);
      toast('Copied. Paste it to your agent.', true);
    } }, 'Copy a message for your agent');
  };
  const bell = (label, primary = true) => h('button', { type: 'button', class: primary ? 'primary' : '', onclick: async () => {
    try {
      await post('/api/bell', {});
      toast('Sent to your agent.', true);
    } catch (err) {
      toast(err.message);
    }
    await refresh(true);
  } }, label);
  const handBack = (opening) => (ui.state.lurking ? bell('Dinner bell: send to agent') : copy(opening));
  if (ui.state.handed) {
    node.replaceChildren(emilyCard('waiting', 'SENT TO YOUR AGENT', 'Your agent has it. Nothing to do here for now.', copy('Here is my latest.', false)));
  } else if (needed) {
    const early = ui.state.lurking ? bell('Dinner bell: send what I have so far', false) : null;
    node.replaceChildren(emilyCard('', 'EMILY NEEDS YOU', `${needed} question${needed > 1 ? 's' : ''} left, just below the picture`, early));
  } else if (ui.state.next) {
    node.replaceChildren(emilyCard('', 'YOUR NEXT STEP', ui.state.next, handBack(`I finished this step: ${ui.state.next}`)));
  } else if (params.length) {
    const extra = optional ? h('span', { class: 'why' }, `${optional} optional question${optional > 1 ? 's' : ''} left, if you have time.`) : null;
    const title = ui.state.lurking ? 'Your turn is done. Send it to your agent.' : 'Your turn is done. Tell your agent you finished.';
    node.replaceChildren(emilyCard('done', "THAT'S EVERYTHING FOR NOW", title, extra, handBack("I answered Emily's questions.")));
  } else {
    node.replaceChildren(emilyCard('waiting', 'NOTHING NEEDED', 'Emily has no questions right now.'));
  }
  // It sits here as well as in the side panel, because that panel drops below the page in a narrow window.
  if (!ui.walkthrough) {
    const list = ui.state.walkthroughs;
    node.firstChild.append(...list.map((w) => h('button', { type: 'button', class: 'primary', onclick: () => openWalkthrough(w.name) }, list.length === 1 ? 'Open walkthrough' : `Open ${w.title}`)));
  }
}

function openWalkthrough(name) {
  ui.walkthrough = name;
  renderWalkthroughs();
  renderNext();
}

function renderWalkthroughs() {
  const list = ui.state.walkthroughs;
  $('catwalk').hidden = !list.length;
  const shown = list.find((w) => w.name === ui.walkthrough);
  $('walklist').replaceChildren(...list.map((w) => h('button', { type: 'button', 'aria-current': w === shown ? 'true' : 'false', onclick: () => openWalkthrough(w.name) }, w.title)));
  const wasHidden = $('workcard').hidden;
  $('walkpanel').hidden = !shown;
  $('workcard').hidden = !!shown;
  if (shown) {
    const url = `/walkthroughs/${encodeURIComponent(shown.name)}`;
    const versioned = `${url}?v=${shown.mtime}`;
    $('walktitle').textContent = shown.title;
    $('walkopen').href = url;
    // Setting the same address again would throw away the reader's place on every poll.
    if ($('walkframe').getAttribute('src') !== versioned) $('walkframe').src = versioned;
  } else if (wasHidden) {
    ui.walkthrough = null;
    resize();
  }
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
    panel.replaceChildren(h('b', {}, 'Machine'), h('p', {}, Object.keys(machines).length ? 'Choose one from the collar tag to see its specs and check fit.' : 'Add one with calipurr adopt NAME --kind printer, cnc or laser.'));
    return;
  }
  const needed = Object.entries(machine.fields).filter(([, f]) => f.status === 'needed');
  const known = Object.entries(machine.fields).filter(([, f]) => f.status !== 'needed');
  const spec = (label, value, detail, title) => h('div', { class: 'spec', title },
    h('dt', {}, label),
    h('dd', {}, String(value), detail ? h('small', {}, ` ${detail}`) : null));
  const tagName = (key) => key.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase());
  panel.replaceChildren(
    h('b', {}, `${ui.machine} (${machine.kind})`),
    h('dl', { class: 'specs' },
      ...known.map(([, f]) => spec(f.ask, f.value, f.status, [f.note, f.date].filter(Boolean).join(', '))),
      ...Object.entries(machine.notes).map(([key, n]) => spec(tagName(key), n.value, null, n.date))),
    needed.length ? h('p', {}, 'Emily needs these to check fit.') : null,
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
  if (params.some((e) => e.status === 'needed' && e.required !== false)) return 0;
  // A job with no STL, like one cut from G-code, is ready once its walkthrough exists.
  if (!ui.state.files.models.length) return ui.state.walkthroughs.length ? 3 : 1;
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
  $('stagenote').textContent = shown === 3 && !ui.state.files.models.length ? WALKTHROUGH_NOTE : STAGE_NOTES[shown];
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
  renderNext();
  renderCarousel();
  renderBowl();
  renderLives();
  renderWalkthroughs();
  renderComments();
  renderReport();
  renderLitter();
  renderChecks();
  renderStage();
  syncMark();
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
  // The question's own fields are exempt: it only redraws if the question itself changes.
  const typing = !force && document.activeElement?.matches('input, select, textarea') && !$('question').contains(document.activeElement);
  if (typing) return;
  const state = JSON.parse(text);
  if (ui.state && state.ui_build !== ui.state.ui_build) {
    // The server now has newer page code. Wait for anything typed but unsaved, because a reload would lose it.
    const unsaved = [...ui.answerDrafts.values(), ...ui.noteDrafts.values()].some(Boolean) || document.activeElement?.matches('input, textarea');
    if (!unsaved) location.reload();
    return;
  }
  ui.stateText = text;
  ui.state = state;
  renderAll();
  runCheck();
}

setMode('spin');
resize();
await refresh(true);
if (currentGauge()) setMode('paw');
animate();
setInterval(() => refresh().catch(() => toast('Lost contact with Calipurr. Is it still running?')), 1500);

$('walkclose').addEventListener('click', () => openWalkthrough(null));
