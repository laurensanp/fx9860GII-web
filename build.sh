#!/usr/bin/env bash
# Builds the web app into web/: the WebAssembly core and the skin.
# Needs the emulator in the neighbouring folder ../fx9860-emulator, Rust with
# the wasm32-unknown-unknown target, Python 3 with Pillow, and the DejaVu fonts.
set -e
cd "$(dirname "$0")"
EMU=../fx9860-emulator
FONTS=${FONTS:-/usr/share/fonts/truetype/dejavu}

rustup target list --installed | grep -q wasm32-unknown-unknown || rustup target add wasm32-unknown-unknown
(cd fxweb && cargo build --release --target wasm32-unknown-unknown)
cp fxweb/target/wasm32-unknown-unknown/release/fxweb.wasm web/fxweb.wasm

python3 make_skin.py web "$FONTS"
ls -l web/fxweb.wasm web/skin@3x.png web/layout.json
