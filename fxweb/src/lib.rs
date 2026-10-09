//! fx-9860GII-2 emulator core for the browser. Uses the emulator modules of
//! `fxemu` from the neighbouring folder `fx9860-emulator` unchanged and
//! exports a small C-style interface to JavaScript (see web/app.js).
//! No dependencies, no wasm-bindgen.

#![allow(dead_code)]

#[path = "../../../fx9860-emulator/fxemu/src/bus.rs"]
mod bus;
#[path = "../../../fx9860-emulator/fxemu/src/cpu.rs"]
mod cpu;
#[path = "../../../fx9860-emulator/fxemu/src/flash.rs"]
mod flash;
#[path = "../../../fx9860-emulator/fxemu/src/keys.rs"]
mod keys;
#[path = "../../../fx9860-emulator/fxemu/src/lcd.rs"]
mod lcd;
#[path = "../../../fx9860-emulator/fxemu/src/state.rs"]
mod state;
#[path = "../../../fx9860-emulator/fxemu/src/timers.rs"]
mod timers;

use std::collections::VecDeque;

use bus::Bus;
use cpu::Cpu;
use flash::Flash;
use state::Snap;
use timers::{Rtc, CPU_HZ};

struct Emu {
    cpu: Cpu,
    key_events: VecDeque<(u8, bool)>,
    key_matrix: [u8; 12],
    key_changed_at: u64,
    frame: Vec<u8>,
    out: Vec<u8>,
}

static mut EMU: Option<Emu> = None;

fn emu() -> &'static mut Emu {
    // Single-threaded: JavaScript calls in one at a time.
    unsafe { (*std::ptr::addr_of_mut!(EMU)).as_mut().expect("fx_init not called") }
}

/// Reserve `len` bytes for JavaScript to fill (ROM, flash, snapshot).
#[no_mangle]
pub extern "C" fn fx_alloc(len: usize) -> *mut u8 {
    let mut v = vec![0u8; len];
    let p = v.as_mut_ptr();
    std::mem::forget(v);
    p
}

#[no_mangle]
pub extern "C" fn fx_free(ptr: *mut u8, len: usize) {
    unsafe { drop(Vec::from_raw_parts(ptr, len, len)) }
}

/// Start a machine from a flash image (the ROM dump, or the saved flash).
#[no_mangle]
pub extern "C" fn fx_init(flash_ptr: *const u8, flash_len: usize, unix_time: f64) {
    let image = unsafe { std::slice::from_raw_parts(flash_ptr, flash_len) }.to_vec();
    let mut bus = Bus::new(Flash::new(image));
    bus.rtc = Rtc::from_unix(unix_time as u64);
    let cpu = Cpu::new(bus);
    let frame = cpu.bus.lcd.frame();
    unsafe {
        *std::ptr::addr_of_mut!(EMU) = Some(Emu {
            key_changed_at: cpu.cycles,
            cpu,
            key_events: VecDeque::new(),
            key_matrix: [0; 12],
            frame,
            out: Vec::new(),
        });
    }
}

/// Resume from a snapshot. `elapsed` = seconds since it was taken (the real
/// clock keeps running while the calculator is off). Returns 1 on success.
#[no_mangle]
pub extern "C" fn fx_load_state(ptr: *const u8, len: usize, elapsed: f64) -> i32 {
    let data = unsafe { std::slice::from_raw_parts(ptr, len) };
    if data.len() < 8 || &data[..8] != state::MAGIC {
        return 0;
    }
    let e = emu();
    if e.cpu.load(&mut state::R::new(&data[8..])).is_err() {
        return 0;
    }
    e.cpu.bus.rtc.add_seconds(elapsed.max(0.0) as u64);
    e.cpu.bus.set_keys([0; 12]);
    e.key_matrix = [0; 12];
    e.key_changed_at = e.cpu.cycles;
    e.frame = e.cpu.bus.lcd.frame();
    1
}

/// Build a snapshot; returns its length, read it at `fx_out_ptr`.
#[no_mangle]
pub extern "C" fn fx_save_state() -> usize {
    let e = emu();
    let mut w = state::W::default();
    w.0.extend_from_slice(state::MAGIC);
    e.cpu.save(&mut w);
    e.out = w.0;
    e.out.len()
}

#[no_mangle]
pub extern "C" fn fx_out_ptr() -> *const u8 {
    emu().out.as_ptr()
}

#[no_mangle]
pub extern "C" fn fx_flash_ptr() -> *const u8 {
    emu().cpu.bus.flash.data.as_ptr()
}

#[no_mangle]
pub extern "C" fn fx_flash_len() -> usize {
    emu().cpu.bus.flash.data.len()
}

/// 1 if the flash changed since the last call (files or settings saved).
#[no_mangle]
pub extern "C" fn fx_flash_take_dirty() -> i32 {
    let f = &mut emu().cpu.bus.flash;
    let d = f.dirty;
    f.dirty = false;
    d as i32
}

/// Queue a key press or release (key code as in keys.rs).
#[no_mangle]
pub extern "C" fn fx_key(code: u32, down: i32) {
    emu().key_events.push_back((code as u8, down != 0));
}

#[no_mangle]
pub extern "C" fn fx_reset() {
    emu().cpu.reset();
}

/// Run for about `cycles` CPU cycles (29.49 MHz). Returns 1 if the display changed.
#[no_mangle]
pub extern "C" fn fx_run(cycles: f64) -> i32 {
    let e = emu();
    let slice = CPU_HZ / 250; // 4 ms, as in the desktop version
    let key_gap = CPU_HZ / 20;
    let key_timeout = CPU_HZ / 2;
    let end = e.cpu.cycles + cycles.max(0.0) as u64;
    while e.cpu.cycles < end {
        let target = (e.cpu.cycles + slice).min(end);
        while e.cpu.cycles < target {
            e.cpu.cycles += e.cpu.step() as u64;
            if e.cpu.cycles >= e.cpu.bus.next_tick {
                e.cpu.bus.tick(e.cpu.cycles);
            }
        }
        // Apply key events one at a time, each only after the OS has read the
        // previous change, so fast typing never merges two keys.
        let since = e.cpu.cycles - e.key_changed_at;
        if since >= key_gap && (e.cpu.bus.keys_seen || since >= key_timeout) {
            if let Some((code, down)) = e.key_events.pop_front() {
                keys::set_matrix(&mut e.key_matrix, code, down);
                e.cpu.bus.set_keys(e.key_matrix);
                e.key_changed_at = e.cpu.cycles;
            }
        }
    }
    let frame = e.cpu.bus.lcd.frame();
    let changed = frame != e.frame;
    e.frame = frame;
    changed as i32
}

/// The 128x64 display, 16 bytes per row, MSB = leftmost pixel.
#[no_mangle]
pub extern "C" fn fx_lcd_ptr() -> *const u8 {
    emu().frame.as_ptr()
}

/// 1 when the calculator is switched off (blank screen, CPU asleep).
#[no_mangle]
pub extern "C" fn fx_is_off() -> i32 {
    let e = emu();
    (e.cpu.sleeping && e.frame.iter().all(|&b| b == 0)) as i32
}

/// 1 while the CPU is idle (waiting for a key), so the page can save power.
#[no_mangle]
pub extern "C" fn fx_is_idle() -> i32 {
    emu().cpu.sleeping as i32
}

/// Let the calculator's clock catch up after the page was in the background.
#[no_mangle]
pub extern "C" fn fx_advance_clock(secs: f64) {
    emu().cpu.bus.rtc.add_seconds(secs.max(0.0) as u64);
}

#[no_mangle]
pub extern "C" fn fx_cpu_hz() -> f64 {
    CPU_HZ as f64
}
