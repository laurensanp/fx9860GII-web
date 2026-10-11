# fx-9860GII-2 – Web-App

Web-Version des [fx-9860GII-2-Emulators](https://github.com/laurensanp/fx9860GII) für das
iPhone und andere Browser. Der Emulator-Kern ist derselbe Rust-Code, als WebAssembly
übersetzt; er läuft vollständig im Browser, auch offline.

Die Firmware ist nicht enthalten. Beim ersten Start wird ein eigener 4-MiB-Dump
(`fx9860gii2_full_4MB.bin`) ausgewählt; er bleibt zusammen mit den gespeicherten Dateien
und dem Zustand ausschließlich im Speicher des Geräts (IndexedDB).

## Nutzung auf dem iPhone

1. Die Seite in Safari öffnen.
2. **Teilen → Zum Home-Bildschirm.** Die App startet danach im Vollbild und offline.
   Nur so bleiben die Daten dauerhaft erhalten; bei normalen Websites löscht Safari
   gespeicherte Daten nach 7 Tagen ohne Besuch.
3. Beim ersten Start die Dump-Datei auswählen, etwa aus der Dateien-App oder per AirDrop.

Der Zustand wird beim Wechsel in den Hintergrund und alle 30 Sekunden gesichert; beim
nächsten Öffnen geht es an derselben Stelle weiter. **Restart** öffnet ein Menü zum
Neustart oder zum Löschen von Firmware und Daten. **Screenshot** teilt das Display als PNG.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `fxweb/` | Rust-Crate, die den Emulator-Kern für WebAssembly exportiert |
| `web/` | die fertige Web-App: `index.html`, `app.js`, `fxweb.wasm`, Skin, Icons, Manifest, Service Worker |
| `build.sh` | baut `fxweb.wasm` und den Skin neu |
| `make_photo_skin.py`, `skin-photo.webp` | schneidet den Skin aus dem Foto des Rechners und legt die Tastenpositionen fest |

`fxweb` bindet die Quelldateien aus `../fx9860-emulator/fxemu/src` direkt ein; beide
Ordner müssen nebeneinander liegen.

## Bauen und testen

```bash
./build.sh
```

Voraussetzungen: Rust mit dem Ziel `wasm32-unknown-unknown`, Python 3 mit Pillow.
Zum lokalen Testen genügt ein einfacher Webserver im Ordner `web/`,
z. B. `python -m http.server`. Für das iPhone muss die Seite über HTTPS erreichbar sein,
etwa über GitHub Pages. Nach Änderungen an den Dateien in `web/` die Konstante `VERSION`
in `web/sw.js` erhöhen, damit installierte Apps die neue Fassung laden.

## Rechtliches

Die Firmware gehört CASIO und ist nicht Teil dieses Projekts. CASIO und fx-9860GII sind
Marken der CASIO Computer Co., Ltd.; dieses Projekt steht in keiner Verbindung zu CASIO.
