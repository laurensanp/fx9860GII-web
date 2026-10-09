// fx-9860GII-2 web app: runs the WebAssembly emulator core (fxweb.wasm),
// draws the skin and the LCD, and keeps firmware, flash and machine state
// in this device's IndexedDB. Nothing is uploaded anywhere.
'use strict';

const FLASH_SIZE = 4 << 20;
const $ = (id) => document.getElementById(id);

// ---------------- storage (IndexedDB) ----------------

const db = new Promise((resolve, reject) => {
  const req = indexedDB.open('fxemu', 1);
  req.onupgradeneeded = () => req.result.createObjectStore('files');
  req.onsuccess = () => resolve(req.result);
  req.onerror = () => reject(req.error);
});

async function dbGet(key) {
  const d = await db;
  return new Promise((resolve, reject) => {
    const r = d.transaction('files').objectStore('files').get(key);
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

async function dbPut(key, value) {
  const d = await db;
  return new Promise((resolve, reject) => {
    const tx = d.transaction('files', 'readwrite');
    tx.objectStore('files').put(value, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function dbClear() {
  const d = await db;
  return new Promise((resolve) => {
    const tx = d.transaction('files', 'readwrite');
    tx.objectStore('files').clear();
    tx.oncomplete = () => resolve();
  });
}

// Ask the browser not to evict our data under storage pressure.
if (navigator.storage && navigator.storage.persist) navigator.storage.persist();

// ---------------- emulator core ----------------

let fx = null;      // wasm exports
let running = false;
let turbo = false;
let layout = null;

function mem() { return new Uint8Array(fx.memory.buffer); }

function copyIn(bytes) {
  const ptr = fx.fx_alloc(bytes.length);
  mem().set(bytes, ptr);
  return ptr;
}

async function loadCore() {
  const resp = await fetch('fxweb.wasm');
  const { instance } = await WebAssembly.instantiate(await resp.arrayBuffer(), {});
  fx = instance.exports;
}

function isFirmware(bytes) {
  if (bytes.length !== FLASH_SIZE) return false;
  const sig = String.fromCharCode(...bytes.subarray(0x10000, 0x10008));
  return sig === 'CASIOWIN';
}

async function boot() {
  const rom = await dbGet('rom');
  if (!rom) { $('setup').classList.add('show'); return; }
  const flash = (await dbGet('flash')) || rom;
  const now = Date.now() / 1000;
  const ptr = copyIn(flash);
  fx.fx_init(ptr, flash.length, now);
  fx.fx_free(ptr, flash.length);
  const state = await dbGet('state');
  const savedAt = (await dbGet('stateTime')) || now;
  if (state) {
    const sp = copyIn(state);
    fx.fx_load_state(sp, state.length, now - savedAt);
    fx.fx_free(sp, state.length);
  }
  drawLcd();
  running = true;
  lastFrame = performance.now();
  requestAnimationFrame(frame);
}

// ---------------- saving ----------------

let flashSaveTimer = null;

async function saveFlash() {
  if (!running) return;
  const len = fx.fx_flash_len();
  const data = mem().slice(fx.fx_flash_ptr(), fx.fx_flash_ptr() + len);
  await dbPut('flash', data);
}

async function saveState() {
  if (!running) return;
  const len = fx.fx_save_state();
  const data = mem().slice(fx.fx_out_ptr(), fx.fx_out_ptr() + len);
  await dbPut('state', data);
  await dbPut('stateTime', Date.now() / 1000);
}

function saveAll() {
  if (!running) return;
  saveState();
  if (flashSaveTimer) { clearTimeout(flashSaveTimer); flashSaveTimer = null; saveFlash(); }
}

// iOS may suspend or close the app at any time once it is in the background.
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    saveAll();
    hiddenAt = Date.now();
  } else if (running) {
    // The calculator's clock keeps running while the app is in the background.
    if (hiddenAt) fx.fx_advance_clock((Date.now() - hiddenAt) / 1000);
    hiddenAt = 0;
    lastFrame = performance.now();
  }
});
window.addEventListener('pagehide', saveAll);
setInterval(() => { if (running) saveState(); }, 30000);
let hiddenAt = 0;

// ---------------- main loop ----------------

let lastFrame = 0;

function frame(now) {
  if (!running) return;
  const dt = Math.min(now - lastFrame, 100);
  lastFrame = now;
  const hz = fx.fx_cpu_hz();
  let changed = 0;
  if (turbo) {
    const until = performance.now() + 12;
    do { changed |= fx.fx_run(hz / 100); } while (performance.now() < until);
  } else {
    changed = fx.fx_run(hz * dt / 1000);
  }
  if (changed) drawLcd();
  if (fx.fx_flash_take_dirty() && !flashSaveTimer) {
    flashSaveTimer = setTimeout(() => { flashSaveTimer = null; saveFlash(); }, 2000);
  }
  updateStatus();
  requestAnimationFrame(frame);
}

// ---------------- display ----------------

const lcd = $('lcd');
const lctx = lcd.getContext('2d');
const img = lctx.createImageData(128, 64);
let onRGB = [42, 46, 40], offRGB = [183, 191, 168];

function hexRGB(h) { return [1, 3, 5].map((i) => parseInt(h.substr(i, 2), 16)); }

function drawLcd() {
  const p = fx.fx_lcd_ptr();
  const m = mem();
  for (let y = 0; y < 64; y++) {
    for (let x = 0; x < 128; x++) {
      const on = (m[p + y * 16 + (x >> 3)] >> (7 - (x & 7))) & 1;
      const c = on ? onRGB : offRGB;
      const i = (y * 128 + x) * 4;
      img.data[i] = c[0]; img.data[i + 1] = c[1]; img.data[i + 2] = c[2]; img.data[i + 3] = 255;
    }
  }
  lctx.putImageData(img, 0, 0);
}

let statusMsg = '', statusUntil = 0, statusClass = '';
function flashStatus(text, cls, ms) { statusMsg = text; statusClass = cls; statusUntil = Date.now() + ms; }

function updateStatus() {
  const el = $('status');
  let text = '', cls = '';
  if (Date.now() < statusUntil) { text = statusMsg; cls = statusClass; }
  else if (fx.fx_is_off()) { text = 'Ausgeschaltet – AC/ON tippen zum Einschalten'; cls = 'warn'; }
  else if (turbo) { text = 'Turbo: volle Geschwindigkeit'; cls = 'warn'; }
  if (el.textContent !== text) el.textContent = text;
  if (el.className !== cls) el.className = cls;
}

// ---------------- layout and input ----------------

function place(el, x, y, w, h) {
  el.style.left = x + 'px'; el.style.top = y + 'px';
  el.style.width = w + 'px'; el.style.height = h + 'px';
}

function fit() {
  const calc = $('calc');
  const stage = $('stage');
  const cs = getComputedStyle(stage);
  const w = stage.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const h = stage.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
  const s = Math.min(w / layout.w, h / layout.h);
  calc.style.transform = `scale(${s})`;
}

function press(el, code, down) {
  if (!running) return;
  el.classList.toggle('on', down);
  fx.fx_key(code, down ? 1 : 0);
}

async function buildUi() {
  layout = await (await fetch('layout.json')).json();
  onRGB = hexRGB(layout.lcd_on); offRGB = hexRGB(layout.lcd_off);
  const calc = $('calc');
  place(lcd, ...layout.lcd);
  place($('status'), ...layout.status);

  for (const [code, name, x0, y0, x1, y1] of layout.keys) {
    const el = document.createElement('div');
    el.className = 'hit' + (['UP', 'DOWN', 'LEFT', 'RIGHT'].includes(name) ? ' pad' : '');
    place(el, x0, y0, x1 - x0, y1 - y0);
    let pointer = null;
    el.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      pointer = e.pointerId;
      try { el.setPointerCapture(e.pointerId); } catch (_) {}
      press(el, code, true);
    });
    const up = (e) => { if (pointer === e.pointerId) { pointer = null; press(el, code, false); } };
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
    calc.appendChild(el);
  }

  for (const [name, x0, y0, x1, y1] of layout.tools) {
    const el = document.createElement('div');
    el.className = 'tool';
    el.textContent = { turbo: 'Turbo', shot: 'Screenshot', restart: 'Restart' }[name];
    place(el, x0, y0, x1 - x0, y1 - y0);
    el.addEventListener('pointerdown', (e) => { e.preventDefault(); el.classList.add('press'); });
    el.addEventListener('pointerup', () => { el.classList.remove('press'); tool(name, el); });
    el.addEventListener('pointercancel', () => el.classList.remove('press'));
    calc.appendChild(el);
  }

  fit();
  window.addEventListener('resize', fit);
  if (window.visualViewport) window.visualViewport.addEventListener('resize', fit);
}

async function tool(name, el) {
  if (!running) return;
  if (name === 'turbo') {
    turbo = !turbo;
    el.classList.toggle('on', turbo);
  } else if (name === 'shot') {
    await screenshot();
  } else if (name === 'restart') {
    $('menu').classList.add('show');
  }
}

async function screenshot() {
  const c = document.createElement('canvas');
  c.width = 512; c.height = 256;
  const x = c.getContext('2d');
  x.imageSmoothingEnabled = false;
  x.drawImage(lcd, 0, 0, 512, 256);
  const blob = await new Promise((r) => c.toBlob(r, 'image/png'));
  const file = new File([blob], `fx9860-${Date.now()}.png`, { type: 'image/png' });
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file] }); return; } catch (_) { return; }
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = file.name;
  a.click();
  flashStatus('Screenshot gespeichert', 'ok', 3000);
}

// Hardware keyboard (iPad keyboard, desktop browsers): same keys as the desktop app.
const KEYMAP = {
  '0': 0x11, '1': 0x21, '2': 0x22, '3': 0x23, '4': 0x31, '5': 0x32, '6': 0x33, '7': 0x41, '8': 0x42, '9': 0x43,
  '.': 0x12, ',': 0x55, '+': 0x24, '-': 0x25, '*': 0x34, '/': 0x35, '(': 0x53, ')': 0x54, '^': 0x73,
  Enter: 0x15, Backspace: 0x44, Escape: 0x74, ArrowUp: 0x86, ArrowDown: 0x75, ArrowLeft: 0x85, ArrowRight: 0x76,
  F1: 0x91, F2: 0x92, F3: 0x93, F4: 0x94, F5: 0x95, F6: 0x96, m: 0x84, M: 0x84, Home: 0x07, Tab: 0x71,
};
const held = new Set();
addEventListener('keydown', (e) => {
  const code = KEYMAP[e.key];
  if (code === undefined || !running || e.ctrlKey || e.metaKey) return;
  e.preventDefault();
  if (held.has(e.key)) return;
  held.add(e.key);
  fx.fx_key(code, 1);
});
addEventListener('keyup', (e) => {
  const code = KEYMAP[e.key];
  if (code === undefined || !held.has(e.key)) return;
  held.delete(e.key);
  fx.fx_key(code, 0);
});

// ---------------- setup and menu ----------------

$('romfile').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (!isFirmware(bytes)) {
    $('error').textContent = 'Das ist kein vollständiger fx-9860GII-2-Dump (erwartet: 4 MiB mit "CASIOWIN" an 0x10000).';
    return;
  }
  await dbClear();
  await dbPut('rom', bytes);
  $('setup').classList.remove('show');
  boot();
});

$('m-restart').onclick = () => { $('menu').classList.remove('show'); fx.fx_reset(); };
$('m-close').onclick = () => $('menu').classList.remove('show');
$('m-wipe').onclick = async () => {
  if (!confirm('Firmware, gespeicherte Dateien und Zustand wirklich von diesem Gerät löschen?')) return;
  running = false;
  await dbClear();
  location.reload();
};

// ---------------- start ----------------

if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js');

(async () => {
  await buildUi();
  await loadCore();
  await boot();
})();
