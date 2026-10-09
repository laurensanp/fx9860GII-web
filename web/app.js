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

let toastTimer = null;
function toast(text) {
  const el = $('toast');
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2500);
}

let lastOff = null;
function updateStatus() {
  const off = !!fx.fx_is_off();
  if (off === lastOff) return;
  lastOff = off;
  const el = $('lcdmsg');
  el.textContent = off ? 'Ausgeschaltet – AC/ON tippen' : '';
  el.classList.toggle('show', off);
}

// ---------------- layout and input ----------------

function place(el, x, y, w, h) {
  el.style.left = x + 'px'; el.style.top = y + 'px';
  el.style.width = w + 'px'; el.style.height = h + 'px';
}

// Which part of the skin to show. Phones are tall and narrow, so there the
// brand row and the bottom margin are left out and the keys fill the width.
function crops() {
  const bottom = Math.max(...layout.keys.map((k) => k[5])) + 12;
  return [
    [6, 4, layout.w - 6, bottom],      // whole calculator face with the CASIO row
    [10, 60, layout.w - 10, bottom],   // from the display panel down
  ];
}

function fit() {
  const stage = $('stage');
  const cs = getComputedStyle(stage);
  const w = stage.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const h = stage.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
  const [full, panel] = crops().map(([x0, y0, x1, y1]) => ({ x0, y0, cw: x1 - x0, ch: y1 - y0 }));
  const scaleOf = (c) => Math.min(w / c.cw, h / c.ch);
  // Keep the CASIO row unless dropping it makes the calculator clearly bigger.
  const c = scaleOf(panel) > scaleOf(full) * 1.04 ? panel : full;
  const s = scaleOf(c);
  const view = $('view');
  view.style.width = c.cw * s + 'px';
  view.style.height = c.ch * s + 'px';
  view.style.borderRadius = c === panel ? 30 * s + 'px' : 34 * s + 'px';
  $('calc').style.transform = `scale(${s}) translate(${-c.x0}px, ${-c.y0}px)`;
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
  place($('lcdmsg'), ...layout.lcd);

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

  const mb = $('menubtn');
  mb.addEventListener('pointerdown', (e) => { e.preventDefault(); mb.classList.add('press'); });
  mb.addEventListener('pointercancel', () => mb.classList.remove('press'));
  mb.addEventListener('pointerup', () => {
    mb.classList.remove('press');
    if (running) $('menu').classList.add('show');
  });

  fit();
  window.addEventListener('resize', fit);
  if (window.visualViewport) window.visualViewport.addEventListener('resize', fit);
}

function setTurbo(on) {
  turbo = on;
  $('turbobadge').classList.toggle('show', on);
  $('m-turbo').textContent = on ? 'Turbo ausschalten' : 'Turbo einschalten';
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
  toast('Screenshot gespeichert');
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

$('m-restart').onclick = () => { $('menu').classList.remove('show'); fx.fx_reset(); toast('Neustart'); };
$('m-turbo').onclick = () => { setTurbo(!turbo); $('menu').classList.remove('show'); };
$('m-shot').onclick = async () => { $('menu').classList.remove('show'); await screenshot(); };
$('m-close').onclick = () => $('menu').classList.remove('show');
$('m-wipe').onclick = async () => {
  if (!confirm('Firmware, gespeicherte Dateien und Zustand wirklich von diesem Gerät löschen?')) return;
  running = false;
  await dbClear();
  location.reload();
};

// ---------------- start ----------------

if ('serviceWorker' in navigator) {
  // When a new version takes over, save and reload once so it is used right away.
  const hadController = !!navigator.serviceWorker.controller;
  let reloading = false;
  navigator.serviceWorker.addEventListener('controllerchange', async () => {
    if (!hadController || reloading) return;
    reloading = true;
    if (running) await saveState();
    location.reload();
  });
  navigator.serviceWorker.register('sw.js').then((reg) => reg.update());
}

(async () => {
  await buildUi();
  await loadCore();
  await boot();
})();
