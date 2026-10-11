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
  const lit = !!fx.fx_backlight();
  if (lit !== backlight) { setBacklight(lit); changed = 1; }
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
let backlight = false;

// The backlight (SHIFT + OPTN) turns the grey-green display blue.
function setBacklight(lit) {
  backlight = lit;
  onRGB = hexRGB(lit ? layout.lcd_on_lit : layout.lcd_on);
  offRGB = hexRGB(lit ? layout.lcd_off_lit : layout.lcd_off);
  $('glass').style.background = lit ? layout.lcd_off_lit : layout.lcd_off;
  $('calc').classList.toggle('lit', lit);
}

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

// The whole calculator is shown, scaled to fit the screen.
function fit() {
  const stage = $('stage');
  const cs = getComputedStyle(stage);
  const w = stage.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const h = stage.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
  const s = Math.min(w / layout.w, h / layout.h);
  const view = $('view');
  view.style.width = layout.w * s + 'px';
  view.style.height = layout.h * s + 'px';
  $('calc').style.transform = `scale(${s})`;
}

function press(el, code, down) {
  if (!running) return;
  el.classList.toggle('on', down);
  fx.fx_key(code, down ? 1 : 0);
}

async function buildUi() {
  layout = await (await fetch('layout.json')).json();
  place($('glass'), ...layout.glass);
  setBacklight(false);
  const calc = $('calc');
  calc.style.width = $('skin').style.width = layout.w + 'px';
  calc.style.height = $('skin').style.height = layout.h + 'px';
  place(lcd, ...layout.lcd);
  place($('lcdmsg'), ...layout.lcd);
  place($('menubtn'), ...layout.menu);
  $('turbobadge').style.left = layout.badge[0] + 'px';
  $('turbobadge').style.top = layout.badge[1] + 'px';
  $('pop').style.left = layout.pop[0] + 'px';
  $('pop').style.top = layout.pop[1] + 'px';
  $('pop').style.width = layout.pop[2] + 'px';

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
    if (running) $('pop').classList.toggle('show');
  });

  fit();
  window.addEventListener('resize', fit);
  if (window.visualViewport) window.visualViewport.addEventListener('resize', fit);
}

function setTurbo(on) {
  turbo = on;
  $('turbobadge').classList.toggle('show', on);
  $('m-turbo').classList.toggle('on', on);
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

// Pop-up entries behave like calculator keys: pressed look, action on release.
function closePop() { $('pop').classList.remove('show'); }
const popActions = {
  'm-turbo': () => { setTurbo(!turbo); closePop(); },
  'm-shot': async () => { closePop(); await screenshot(); },
  'm-restart': () => { closePop(); fx.fx_reset(); toast('Neustart'); },
  'm-wipe': () => { closePop(); wipe(); },
};
for (const [id, action] of Object.entries(popActions)) {
  const el = $(id);
  el.addEventListener('pointerdown', (e) => { e.preventDefault(); e.stopPropagation(); el.classList.add('press'); });
  el.addEventListener('pointercancel', () => el.classList.remove('press'));
  el.addEventListener('pointerup', () => { el.classList.remove('press'); action(); });
}
// While the pop-up is open, a tap anywhere else only closes it (no key press).
document.addEventListener('pointerdown', (e) => {
  if ($('pop').classList.contains('show') && !$('pop').contains(e.target) && !$('menubtn').contains(e.target)) {
    e.preventDefault();
    e.stopPropagation();
    closePop();
  }
}, true);
async function wipe() {
  if (!confirm('Firmware, gespeicherte Dateien und Zustand wirklich von diesem Gerät löschen?')) return;
  running = false;
  await dbClear();
  location.reload();
}

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
