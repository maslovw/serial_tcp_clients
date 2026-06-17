# Handoff: Serial → TCP Server — Port Manager GUI

## Overview
A desktop GUI for a **serial-to-TCP splitter** tool. The underlying program shares one serial
console across multiple TCP clients: the serial port opens when the first TCP client connects and
closes when the last disconnects; if the serial device is lost, all TCP clients stay connected while
the server attempts to reconnect.

Unlike the original CLI (one serial port per invocation), this GUI manages **multiple serial→TCP
mappings at once**. Each row is exactly one serial port bound to one TCP listen port, which can fan
out to several TCP clients:

```
clientA <-->\
             | <-----> TcpServer(:5000) <---> serial port (COM3)
clientB <-->/
```

The GUI is a **master–detail** layout: a list of port mappings on the left, and the selected port's
console, settings, throughput and live log on the right.

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes that show the
intended look and behavior. They are **not** production code to copy directly.

The task is to **recreate these designs in the target environment**. The reference CLI is a Python
program (`serial-tcp-server.exe`), and the user's stated target is a **Python Tkinter** desktop
app — so these HTML mockups should be reimplemented with Tkinter/ttk (e.g. `ttk` widgets, a themed
style, `tkinter.scrolledtext` for the console, threads for the serial/TCP I/O). If a different
framework is later chosen (PySide/Qt, etc.), apply the same layout and visual spec using that
toolkit's idioms. Treat the HTML purely as a visual + behavioral spec.

## Fidelity
**High-fidelity (hifi).** Colors, typography, spacing, and interaction states are intended to be
final. Recreate the UI faithfully. Because Tkinter's native widgets are limited, match the *layout,
hierarchy, and color intent* closely; pixel-identical rounded corners/shadows are not required where
the toolkit makes them impractical — prioritize the structure, the status color language, and the
monospace console.

## File to implement
- **`Port Manager.dc.html`** — the chosen design (this is what to build).
- `reference_all_variations.dc.html` — the earlier 3-way exploration (Classic ttk / Modern / Dark
  console). Reference only; the user selected the Modern direction, which became `Port Manager`.

---

## Window structure

A single resizable window, ~1040×730 px at rest. Top to bottom:

1. **Title bar** (custom-drawn in the mock; in Tkinter this is just the OS window chrome — the title
   text is `Serial TCP Server`).
2. **App bar** — app identity on the left, global controls on the right. Always visible.
3. **Body** — two columns: a fixed-width port list (master) and a flexible detail panel.

### App bar
- Height ~58 px, white background, 1px bottom border `#eef0f4`, horizontal padding 16 px.
- Left cluster: a 32×32 rounded-square icon (`#2a6fdb` fill, white glyph) + a two-line label:
  - Line 1: **Port Manager** — 16px/700, color `#1d2433`.
  - Line 2: **`4 mappings · 6 clients`** — 11.5px/400, color `#8a93a4` (live summary of the list).
- Right cluster (gap 8 px), all 36–38px tall:
  - **Start all** — solid green `#1f8a5b`, white text, left-pointing ▶ triangle, subtle shadow.
  - **Stop all** — light `#f3f5f8` fill, 1px `#e3e6ec` border, text `#4a5263`, ■ square glyph.
  - vertical divider `#e6e9ef`.
  - **＋** button — 36×36, 1px `#e3e6ec` border, text `#6b7385` (add new port mapping).
  - **⚙** button — 36×36, same styling (global settings).

---

## Master: port list (left column)

- Fixed width **340 px**, background `#f6f8fb`, 1px right border `#eaedf2`, padding 14 px,
  vertical stack with 10 px gaps. Scrolls vertically if the list is long.
- One **card per port mapping**. At the bottom, a dashed **`＋ Add serial → TCP port`** button
  (1.5px dashed `#d3d9e2`, radius 10, text `#8a93a4`).

### Port card (compact)
White, radius 10, padding 13×14 px. Border + shadow depend on selection (see States):
- **Header row** (flex, centered):
  - Port/device name — 14px/700, `#1d2433` (e.g. `COM3`, `COM4`, `ttyUSB0`, `COM7`).
  - TCP port — 11.5px/500 **monospace**, `#8a93a4`, formatted `→ :5000`.
  - **Status pill** (pushed right): rounded 20px, dot + label, 10.5px/600. See status colors.
  - **`›` chevron** — 15px/700, color `#c2cad6` unselected / `#2a6fdb` selected.
- **Stats row** (flex, items bottom-aligned, top margin 11 px):
  - Two stat columns, gap 24 px: **`▲ OUT`** and **`▼ IN`**. Label 9px/600 `#9aa3b2`
    letter-spacing .04em; value 12px/600 **monospace** `#3b4252` (e.g. `4.2 KB/s`, `18 KB/s`).
    When the port isn't actively transferring, value is `—` in `#bcc3cf`.
  - Pushed right: **`CLIENTS`** label (same small style) over the count — 13px/700.
    Count color `#2a6fdb` when clients>0, `#4a5263` for a single client on a degraded port,
    `#9aa3b2` when 0.

---

## Detail panel (right column)

- Flexible width (fills remainder), padding 18×20 px, background continues `#f6f8fb`, scrolls
  vertically. Shows the **currently selected** port. There is also an **empty state** for when no
  port is selected.

### Empty state (no selection)
Centered column: a 46×46 rounded `#eef2fb` tile with a `#2a6fdb` `›` glyph, then
**Select a port** (14px/600 `#4a5263`), then helper text (12px/400 `#9aa3b2`, max-width 240):
"Click the › on any port to open its console, settings and live log here."

### Detail — running port (e.g. COM3, COM7)
1. **Header row**:
   - Name 19px/700 `#1d2433` + `→ 0.0.0.0:5000` in 13px/500 monospace `#8a93a4`.
   - Sub-line (margin-top 7): status dot + **`Running · uptime 03:12:44`** 11.5px/600 `#1f7a48`.
   - Right buttons: **Stop** (white, 1px `#e3e6ec`, red text `#b23b3b`, ■ glyph) and **Edit**
     (white, 1px `#e3e6ec`, text `#4a5263`). 9px padding, radius 8.
2. **Stat tiles** — 4-up CSS grid, gap 10, margin-top 16. Each tile: white, 1px `#eaedf2`, radius 9,
   padding 12. Label 10px/600 `#9aa3b2` letter-spacing .04em; value 20px/700 `#1d2433` (unit suffix
   11px/600 `#9aa3b2`). Tiles: **TCP CLIENTS**, **TX TOTAL**, **RX TOTAL**, **BAUD**.
3. **Settings chips** — a `SERIAL` caption (11px/600 `#8a93a4`) followed by pill chips, gap 8,
   margin-top 16. Two chip styles:
   - *active/value* chips: `#eef2fb` bg, text `#2a5bb0` (e.g. `8N1`, `parity N`).
   - *muted/off* chips: `#f3f5f8` bg, text `#6b7385` (e.g. `xon/xoff off`, `char-mode off`,
     `echo-wait 0s`). All chips 11.5px/500 **monospace**, radius 6, padding 5×10.
4. **Console** — margin-top 16, dark `#11151c`, radius 9, padding 13×15, fixed height (~236 px on
   the primary view), `overflow:hidden` (scrollable in real impl). Monospace 11.5px, line-height 1.9.
   - Header line: `CONSOLE — COM3` 10px/600 `#6b7588` letter-spacing .06em, and a right-aligned
     **`● live`** indicator in `#4d8f6b`.
   - Log lines: timestamp `[12:05:11]` in `#6b7588`, then the payload. Payload color encodes type:
     - client connect/disconnect events → `#7fb4ff`
     - RX (data received from serial) → `#c7cedb`
     - TX (data sent to serial) → `#e6c07b`
     - status/throughput notices → `#9bdca0`
   - A blinking cursor block (`#9bdca0`, ~7×14) trails the last line on live ports.

### Detail — reconnecting port (e.g. COM4)
Same skeleton, plus:
- Status sub-line uses amber: dot `#e0a020`, text `#9a6b00`, label `Reconnecting · attempt 4`.
- An **amber banner** under the header (margin-top 16): bg `#fdf6e8`, 1px `#f4e2b8`, radius 9,
  dot `#e0a020`, text 12px/500 `#8a6a1a`: "Serial device lost — TCP client kept connected,
  retrying every 2s."
- TX/RX tiles show `—` (`#bcc3cf`) since no serial data flows.
- Console header indicator is **`● retrying`** (`#c9923a`); log lines are retry attempts in
  `#e6c07b` / `#e6a87b`.

### Detail — stopped port (e.g. ttyUSB0)
- Status sub-line gray: dot `#aab1bf`, text `#7a8294`, label `Stopped`.
- Header buttons become **Start** (solid green `#1f8a5b`, white, ▶), **Edit**, **Remove**
  (white, 1px `#f0d2d2`, red text `#b23b3b`).
- No tiles/console. Instead a **dashed empty panel** (1.5px dashed `#d8dde6`, radius 9, padding
  40×24, centered): a 40×40 `#eef0f4` tile with a `#aab1bf` square, then **Port stopped**
  (13px/600 `#7a8294`) and helper text (12px/400 `#9aa3b2`, max-width 340): "Press Start to begin
  listening on :5002. The serial port opens when the first TCP client connects and closes when the
  last disconnects."

---

## Interactions & Behavior
- **Select a port**: clicking anywhere on a port card (or its `›`) selects it. The selected card
  gets a `#2a6fdb` border + soft blue shadow `0 4px 14px rgba(42,111,219,0.14)` and its chevron
  turns blue; the detail panel swaps to that port. Default selection on launch: the first port.
- **Start / Stop (per port)**: toggles that port's server. Stopping closes the TCP listener and
  serial port; the card status pill and detail update accordingly.
- **Start all / Stop all**: applies to every mapping.
- **＋ Add serial → TCP port** (app bar button and the dashed list footer): opens an add/edit dialog
  to choose a serial device, baudrate, parity (`N E O S M`), flow control (`--xonxoff`), char-mode
  (`-cm`), char-delay (`-cd`), wait-echo (`-we`), and the TCP listen port.
- **Edit**: same dialog, prefilled, for the selected port.
- **Remove**: deletes a stopped mapping.
- **Console input** (recommended to add): a send line at the bottom of the console to transmit to
  the serial port, with CR/LF and local-echo toggles (mirrors `-we`/echo behavior).
- **Reconnect**: automatic when the serial device drops; clients are retained; banner + retrying
  state shown until reconnected.
- **Chevron rotation** in the mock (accordion variant) is not used in this master-detail version;
  the chevron is purely a selection affordance here.

### Live values to wire up
- App-bar summary `N mappings · M clients`.
- Per-card OUT/IN throughput (KB/s), CLIENTS count, status.
- Detail tiles: client count, cumulative TX/RX totals, baud, uptime.
- Console stream (append-only, color-coded, autoscroll).

## State Management
- `ports: List[PortMapping]` — each has: `device`, `tcp_port`, `baudrate`, `parity`, `xonxoff`,
  `char_mode`, `char_delay`, `wait_echo`, plus runtime: `status` (`running|reconnecting|stopped`),
  `clients: List[ClientConn]`, `tx_total`, `rx_total`, `tx_rate`, `rx_rate`, `uptime`,
  `log: List[LogLine]`, `reconnect_attempt`.
- `selected_port_id: Optional[str]` — drives the detail panel (null → empty state).
- Each running mapping owns a TCP listener thread + a serial read/write thread; UI updates marshalled
  back to the Tk main loop (e.g. via a queue + `after()`).

## Design Tokens

### Colors
| Role | Hex |
|---|---|
| Accent (primary/blue) | `#2a6fdb` |
| Accent text-on-light | `#2a5bb0` |
| Chip blue bg | `#eef2fb` |
| Success / running | `#1f8a5b` (dot), `#1f7a48` (text), `#e7f6ee` (pill bg) |
| Warning / reconnecting | `#e0a020` (dot), `#9a6b00` (text), `#fdf3e0` (pill bg), banner `#fdf6e8`/`#f4e2b8`/`#8a6a1a` |
| Stopped / muted | `#aab1bf` (dot), `#7a8294` (text), `#eef0f4` (pill bg) |
| Danger | `#b23b3b` (text/glyph), border `#f0d2d2` |
| Text strong | `#1d2433` |
| Text medium | `#3b4252` / `#4a5263` |
| Text muted | `#8a93a4` / `#9aa3b2` |
| Disabled value | `#bcc3cf` |
| Window / body bg | `#ffffff` (chrome), `#f6f8fb` (panels) |
| Borders | `#eef0f4`, `#eaedf2`, `#e6e9ef`, `#e3e6ec`; dashed `#d3d9e2` / `#d8dde6` |
| Console bg | `#11151c` |
| Console text | ts `#6b7588`, rx `#c7cedb`, tx `#e6c07b`, conn `#7fb4ff`, status `#9bdca0`, retry `#e6c07b`/`#e6a87b` |

### Typography
- UI font: system UI stack (`system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`).
  In Tkinter use the platform default (Segoe UI / SF / DejaVu Sans).
- Monospace (port numbers, chips, console): **JetBrains Mono** (mock loads it from Google Fonts);
  fall back to Consolas / Menlo / DejaVu Sans Mono.
- Scale: 9–11px micro-labels (uppercase, letter-spacing .04–.06em), 11.5–13px body,
  14–16px card/app titles, 19px detail title, 20px tile values. Weights 400/500/600/700.

### Spacing & shape
- Card/tile radius 9–10 px; pills 20 px; chips/buttons 6–8 px.
- Padding: cards 13–14, detail 18–20, tiles 12, chips 5×10.
- Gaps: list 10, tile grid 10, chip row 8, button row 8.
- Selected card shadow: `0 4px 14px rgba(42,111,219,0.14)`. Window shadow (mock only): n/a in Tk.

## Assets
- No raster assets. Icons are simple glyphs/CSS shapes (▶ triangle, ■ square, `›` chevron, `⇄`, `⚙`,
  `＋`). Reproduce with Tk text/canvas or a small icon set of your choice.
- JetBrains Mono font (Google Fonts) for monospace — bundle the TTF with the app or use a local
  monospace fallback.

## Files
- `Port Manager.dc.html` — the design to implement (master-detail, the selected direction).
- `reference_all_variations.dc.html` — earlier exploration of three styles (Classic ttk / Modern /
  Dark console), for context on alternatives.
