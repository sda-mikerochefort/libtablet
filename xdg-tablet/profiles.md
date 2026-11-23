# XDG Tablet Profile Specification

Status: **Draft, schema-version 1**. Not yet ratified.

This document specifies a desktop-neutral file format for user configuration of
pen tablets, pen displays and tablet pads ("remotes"). It covers stylus
pressure curves, active area, output mapping, button/ring/strip/dial bindings,
radial menus, OLED labels and per-application overrides.

The goal is that an artist's configuration survives a change of desktop
environment or compositor (GNOME, KDE Plasma, Cosmic, Sway, …) and can be
edited by any settings tool, including a compositor-agnostic CLI.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are to be interpreted
as described in RFC 2119.

A JSON Schema for the parsed document is provided in
[`profile.schema.json`](profile.schema.json) and a complete example in
[`example-profiles.toml`](example-profiles.toml).

## 1. Files and precedence

The format is [TOML 1.0](https://toml.io/en/v1.0.0). Files are UTF-8.

| Layer | Location | Purpose | Written by |
|-------|----------|---------|-----------|
| 1 (lowest) | `$XDG_DATA_DIRS/xdg-tablet/profiles.d/*.toml` | vendor/distribution defaults (e.g. `/usr/share/xdg-tablet/profiles.d/`) | packages |
| 2 | `$XDG_CONFIG_DIRS/xdg-tablet/profiles.d/*.toml` | site/administrator defaults (e.g. `/etc/xdg/xdg-tablet/profiles.d/`) | administrator |
| 3 (highest) | `$XDG_CONFIG_HOME/xdg-tablet/profiles.toml` | user configuration | settings tools, compositor |

Within a layer, files in a `profiles.d/` directory are applied in
lexicographic (byte-wise) order of their file names. For each of
`$XDG_DATA_DIRS` and `$XDG_CONFIG_DIRS`, directories listed **earlier** in the
variable take precedence, i.e. they are applied **later**. If a file with the
same name exists in several directories of the same variable, only the
highest-precedence one is used (the usual XDG "shadowing" rule).

Defaults when the variables are unset or empty follow the XDG Base Directory
Specification (`~/.config`, `/etc/xdg`, `/usr/local/share:/usr/share`).

Implementations MUST only ever write layer 3.

### 1.1 Merge rules

The effective configuration is computed by merging the layers in order:

1. Tables are merged key by key, recursively. A key in a later layer replaces
   the same key from an earlier layer.
2. `[[device]]` entries are identified by their `id`. A device entry in a
   later layer is merged into the earlier entry with the same `id`, using rule 1.
   Entries with new `id`s are appended.
3. `[[app]]` entries are identified by the pair (`app-id`, `device`) and merged
   in the same way. If `app-id` is an array, the identity is the
   sorted, de-duplicated array.
4. `[[device.tool]]` entries are identified by their `match` table (compared as
   values) and merged in the same way.
5. All other arrays (including arrays of tables such as ring/strip/dial
   `modes`) are **replaced** wholesale, never concatenated.
6. A device entry with `disabled = true` in any layer removes the
   device's configuration (and all `[[app]]` entries referring to it) from
   the effective result unless a later layer sets `disabled = false`.

## 2. Document structure overview

```toml
schema-version = 1

[[device]]           # one entry per physical tablet / remote
id = "…"
match = ["…"]
[device.mapping]     # output mapping, area, rotation
[device.touch]       # touch arbitration (pen displays with touch)
[[device.tool]]      # per-stylus settings (pressure, stylus buttons)
[device.pad]         # pad buttons, rings, strips, dials, mode groups
[device.oled]        # auxiliary displays on the pad

[radial-menu.<name>] # named radial menus usable from any action

[[app]]              # per-application overrides
```

## 3. Versioning and extensibility

* `schema-version` (integer, REQUIRED) – the major version of this
  specification the file was written against. This document defines version
  `1`.
* A reader encountering a **higher** `schema-version` than it implements
  SHOULD apply the keys it understands, MUST NOT fail hard, and MUST NOT write
  the file back (to avoid destroying data it does not understand). It SHOULD
  tell the user that the file was written by a newer tool.
* New optional keys may be added in a minor revision of this specification
  without bumping `schema-version`. Readers MUST ignore keys they do not
  understand.
* Writers MUST preserve keys they do not understand when rewriting the file
  (read-modify-write of the whole document, not regeneration from internal
  state). Writers SHOULD preserve comments and key ordering where the TOML
  library allows.
* Implementation-specific keys MUST be prefixed with `x-` followed by a
  reverse-DNS or project name, e.g. `x-org.kde.kwin-foo`. Keys without
  this prefix are reserved for this specification. The JSON Schema accepts
  `x-*` keys in every table and rejects other unknown keys, so that typos are
  caught by validators while runtime readers remain lenient.
* Readers MUST treat an action string they cannot parse (section 9) as
  `none` and SHOULD log a warning; they MUST NOT discard the rest of the file.

## 4. Device selection

```toml
[[device]]
id = "kamvas-pro-16"
name = "Huion Kamvas Pro 16 (2.5K)"   # informative only
match = ["usb|256c|2009||HUION_T21j", "usb|256c|2009|HUION Kamvas Pro 16"]
```

* `id` (string, REQUIRED) – stable identifier, unique within the merged
  document, matching `^[a-z0-9][a-z0-9._-]*$`. Used as the merge key and by
  `[[app]]` entries. Tools SHOULD derive it from the libtablet device name when
  creating new entries.
* `name` (string, optional) – human-readable label for settings UIs.
* `match` (array of strings, REQUIRED, at least one) – the device applies if
  **any** of the strings matches. Each string uses the libtablet (libwacom)
  `DeviceMatch` syntax:

  ```
  bus|vid|pid[|name[|uniq]]
  ```

  * `bus`: one of `usb`, `bluetooth`, `serial`, `i2c`;
  * `vid`, `pid`: 4 hexadecimal digits (case-insensitive);
  * `name`: optional kernel device name; if present and non-empty it must
    match the kernel name exactly (after stripping the ` Pen`, ` Pad`,
    ` Finger`, ` Touch` suffixes the way libwacom does);
  * `uniq`: optional; matched as a **prefix** of the kernel `uniq` string
    (`hdev->uniq`, which HID-BPF programs may populate with a firmware
    identifier such as `HUION_T21j_221221`). An empty `name` with a non-empty
    `uniq` (`usb|256c|2009||HUION_T21j`) matches on bus/vid/pid/uniq only.

  If several device entries match one physical device, the entry whose
  matching string is most specific wins: a `uniq` match beats a `name` match,
  which beats a bare `bus|vid|pid` match. Ties are resolved by document order
  (later wins).

* `disabled` (bool, optional, default `false`) – see section 1.1.

A device entry applies to all kernel nodes (stylus, pad, touch) that
libinput groups into one physical device (`LIBINPUT_DEVICE_GROUP`).

Multiple identical physical devices (same match) share one entry. Per-unit
configuration is out of scope for schema-version 1 (see open questions).

## 5. Output mapping, area, orientation

```toml
[device.mapping]
mode = "absolute"              # "absolute" | "relative"
target = "edid"                # "auto" | "edid" | "connector" | "desktop"
edid = { vendor = "HUI", product = "Kamvas Pro 16", serial = "0000001" }
connector = "DP-2"             # fallback when target = "connector" or EDID not found
keep-aspect = true
area = [0.0, 0.0, 1.0, 1.0]    # x1, y1, x2, y2, normalized
rotation = 0                   # 0 | 90 | 180 | 270, clockwise
left-handed = false
cycle = ["target", "desktop", "next-output"]
```

* `mode` – `absolute` (default) maps the active area to the target;
  `relative` makes the stylus behave like a mouse. Only meaningful for
  opaque tablets; compositors MAY ignore `relative` for pen displays.
* `target`:
  * `auto` (default) – the compositor decides. For pen displays this SHOULD
    use libtablet's EDID metadata for the device, then built-in panel
    heuristics, then an interactive "tap the screen" identification.
  * `edid` – map to the output whose EDID matches `edid`. `vendor` is the
    three-letter PNP ID, `product` the monitor name descriptor (or the
    decimal product code if no name descriptor exists), `serial` the
    serial-number descriptor (or the decimal serial number). Empty or
    absent members are wildcards. This is the same triple GNOME stores in
    `org.gnome.desktop.peripherals.tablet output`.
  * `connector` – map to the output with this connector name (e.g. `DP-2`,
    `eDP-1`). Fragile across hardware changes; SHOULD only be used when the
    output has no usable EDID.
  * `desktop` – map to the bounding box of all outputs ("Virtual Tablet
    Mode").

  If the target output is not present, the compositor MUST fall back to
  `connector` (when set and present), then to `auto`.
* `keep-aspect` (bool, default `true` for opaque tablets, ignored for pen
  displays) – shrink the effective area so that the area's aspect ratio
  matches the target's.
* `area` – active area as `[x1, y1, x2, y2]` in normalized device
  coordinates, origin top-left in the device's **native** orientation
  (before `rotation` and `left-handed`), with `0 <= x1 < x2 <= 1` and
  `0 <= y1 < y2 <= 1`. This is exactly libinput's
  `struct libinput_config_area_rectangle`. Default `[0, 0, 1, 1]`.
  GNOME's `area` key stores margins in percent `[left, right, top, bottom]`;
  the conversion is `x1 = left/100, x2 = 1 - right/100, y1 = top/100,
  y2 = 1 - bottom/100`.
* `rotation` – physical rotation of the device in degrees clockwise.
* `left-handed` – equivalent to libinput's left-handed configuration (180°
  rotation for most tablets, plus ring/strip direction inversion). If both
  `left-handed = true` and `rotation` are set, the rotations add up.
* `cycle` – the sequence stepped through by the `display-toggle` action
  (section 9). Elements: `target` (the configured target above), `desktop`,
  `next-output` (each output in compositor order, one at a time), or an
  explicit `{ edid = {…} }` / `{ connector = "…" }` table. Default
  `["target", "desktop"]`. The cycle position is session state and MUST NOT be
  written to the file.

Coordinate transforms SHOULD be performed in the compositor's floating-point
logical coordinate space so that fractional output scales do not reduce
precision.

## 6. Touch

```toml
[device.touch]
enabled = true
arbitration = "handedness-palm-zone"
```

* `enabled` (bool, default `true`).
* `arbitration` – how touch is handled while a stylus is in proximity:
  * `strict-proximity` – all touches are suppressed while any tool is in
    proximity (classic libinput behaviour);
  * `handedness-palm-zone` (default) – touches in the palm zone (derived from
    `left-handed`, tool position and tilt) are suppressed, touches elsewhere
    are delivered;
  * `off` – no arbitration.

Touch follows the device's output mapping.

## 7. Tools (styli)

```toml
[[device.tool]]
match = { type = "pen" }                    # applies to all pens on this device
pressure-curve = [0.25, 0.10, 0.75, 0.90]
pressure-range = [0.02, 1.0]
eraser-mode = "default"
buttons = { primary = "button:middle", secondary = "button:right", tertiary = "radial-menu:main" }

[[device.tool]]
match = { type = "pen", tool-id = 0x862, serial = 0x2a3f0c1 }   # one specific pen
pressure-curve = [0.0, 0.0, 1.0, 1.0]
```

### 7.1 Matching

`match` (table, REQUIRED):

* `type` – `pen`, `eraser`, `brush`, `pencil`, `airbrush`, `mouse`, `lens`,
  or `any`. These correspond to `enum libinput_tablet_tool_type`.
* `tool-id` (integer, optional) – `libinput_tablet_tool_get_tool_id()`.
* `serial` (integer, optional) – `libinput_tablet_tool_get_serial()`. For
  devices without hardware serials, libinput's synthetic per-device tool
  identity yields serial `0`; `serial = 0` therefore means "the pen that has
  no serial".

The most specific matching entry wins (serial > tool-id > type > `any`).
Entries are merged in that order, so a per-serial entry only needs to list the
keys it changes.

### 7.2 Pressure

* `pressure-range = [min, max]`, `0 <= min < max <= 1`, default `[0, 1]`.
  Maps hardware pressure `min` to logical 0 and `max` to logical 1. This is
  exactly `libinput_tablet_tool_config_pressure_range_set()`. GNOME's
  `pressure-range` stores percentages: divide by 100.
* `pressure-curve = [x1, y1, x2, y2]` – the control points P1 = (x1, y1) and
  P2 = (x2, y2) of a cubic Bézier curve whose end points are fixed at
  P0 = (0, 0) and P3 = (1, 1). All four values MUST be in `[0, 1]`, which
  guarantees that the curve is a function of x on [0, 1]. Default
  `[0, 0, 1, 1]`. The curve maps the logical pressure produced by
  `pressure-range` (x) to the pressure delivered to clients (y). GNOME's
  `pressure-curve` stores the same four numbers in 0..100: divide by 100.
* A curve is the **identity** iff `x1 == y1` and `x2 == y2`.
* `eraser-pressure-curve`, `eraser-pressure-range` – the same, applied while
  the tool is in eraser mode (the eraser end, or the eraser button in
  `button` mode of section 7.3). Default: same as the non-eraser values.

**Reporting obligation.** A compositor that applies a non-identity
`pressure-curve` (or a non-default `pressure-range`) to pressure it sends via
`zwp_tablet_tool_v2.pressure` MUST announce this to clients that bound
`zwp_tablet_manager_v2` at version 3 or later by sending the
`zwp_tablet_tool_v2.pressure_curve` event with the value `custom` (and
`linear` otherwise), so that applications do not apply a second curve.

### 7.3 Stylus buttons

* `buttons` (table) – keys `primary`, `secondary`, `tertiary` (the
  `BTN_STYLUS`, `BTN_STYLUS2`, `BTN_STYLUS3` buttons). Values are actions
  (section 9). Default: `passthrough` for all three.
* `eraser-mode` – how an eraser **button** (a button that firmware reports as
  a switch to the eraser tool) behaves: `default` (the tool becomes an eraser),
  `button` (it behaves like a button bound to `eraser-button`).
* `eraser-button` – action for the eraser button in `button` mode.

## 8. Pad

```toml
[device.pad]
unbound = "passthrough"
buttons = { A = "mode-switch", B = { action = "Ctrl+z", label = "Undo" } }

[[device.pad.ring]]
modes = [
  { cw = "bracketright", ccw = "bracketleft", label = "Brush size" },
  { cw = "Ctrl+plus", ccw = "Ctrl+minus", label = "Zoom" },
]

[[device.pad.strip]]
modes = [{ up = "Page_Up", down = "Page_Down", label = "Scroll" }]

[[device.pad.dial]]
modes = [{ cw = "Ctrl+bracketright", ccw = "Ctrl+bracketleft", label = "Rotate", step = 1 }]

[[device.pad.mode-override]]
group = 0
mode = 1
buttons = { B = { action = "Ctrl+Shift+z", label = "Redo" } }
```

* `unbound` – what happens to pad controls without a binding: `passthrough`
  (default; events are sent to the focused client through
  `zwp_tablet_pad_v2`) or `none`.
* `buttons` – keyed by libtablet button letter (`A` … `Z`, as returned by
  the libwacom button API, which names buttons with a single `char`).
  Letters are independent of evdev codes. The value is an action.
* `ring`, `strip`, `dial` – arrays in libtablet/libinput index order (ring 0,
  ring 1, …). Each entry has `modes`, an array with one element per mode of
  the control's mode group (index 0 = mode 0). If the device has more modes
  than array elements, the remaining modes use `unbound`.
  * Ring and dial directions: `cw`, `ccw`. Strip directions: `up`, `down`.
    Values are actions, applied once per **step**.
  * `step` (integer >= 1, default 1) – the control distance that triggers one
    action. For dials, the unit is a full detent (120 `value120` units). For
    rings and strips, it is the hardware's logical increment.
  * `label` (string) – what the control does in this mode. Shown by OSDs and
    sent to OLEDs. If the whole control is `passthrough`, compositors SHOULD
    use the label the client provided via `set_feedback` instead.
* `mode-override` – per-mode button bindings for buttons that belong to a
  mode group: `group` (integer, mode group index), `mode` (integer),
  `buttons` (as above). Applied on top of `buttons` while that mode is
  active.

## 9. Actions

An action is either a string or a table `{ action = "<string>", label = "<text>" }`.
The optional `label` is used by on-screen displays and OLEDs; if absent the
implementation derives one (e.g. the key combination).

Action strings:

| Syntax | Meaning |
|--------|---------|
| `none` | Do nothing; the event is consumed. |
| `passthrough` | Deliver the event to the focused client unmodified (stylus buttons as `zwp_tablet_tool_v2.button`, pad controls as `zwp_tablet_pad_v2` events). |
| `<keycombo>` | Synthesize a key combination: zero or more modifiers followed by one xkb keysym name, joined by `+`. Modifiers: `Ctrl`, `Shift`, `Alt`, `Super`, `Meta`, `Hyper`, `AltGr`. Keysym names are those of `xkb_keysym_from_name()` (case-sensitive, e.g. `z`, `Z`, `bracketleft`, `F5`, `KP_Add`). Examples: `Ctrl+Shift+z`, `F5`. A combination may also consist of modifiers only (`Ctrl`, `Shift+Alt`): those modifiers are held for as long as the control is held. The key combination is pressed when the control is pressed and released when it is released; for rings, strips and dials it is pressed and released once per step. |
| `button:<b>` | Emit a pointer button: `left`, `middle`, `right`, `back`, `forward`, or a number 1–32 (`1` = left). |
| `scroll:<dir>` | Emit one discrete scroll step: `up`, `down`, `left`, `right`. |
| `display-toggle` | Advance this device's mapping one step through `mapping.cycle`. |
| `mode-switch` | Advance the mode of the mode group the control belongs to. |
| `mode-set:<n>` | Set that mode group to mode `n`. |
| `osd` | Show the compositor's pad overlay (help) for this device. |
| `radial-menu:<name>` | Open the radial menu `<name>` (section 10) at the stylus position, or centred on the device's output for pad controls. |
| `eraser` | Stylus buttons only: while held, the tool is reported as an eraser (`zwp_tablet_tool_v2` proximity-out then proximity-in as eraser). |

Arbitrary command execution is intentionally **not** an action. See the open
questions.

Built-in action names are reserved words. A keysym that happens to collide
with one (none currently do) can be written as `keys:<keycombo>`, which is
also valid for every key combination.

## 10. Radial menus

```toml
[radial-menu.main]
items = [
  { label = "Undo", action = "Ctrl+z" },
  { label = "Redo", action = "Ctrl+Shift+z" },
  { label = "Brushes", action = "radial-menu:brushes" },
]
```

* Menu names match `^[a-z0-9][a-z0-9._-]*$`.
* `items` – 1 to 12 items, laid out clockwise starting at 12 o'clock. Each item
  has a `label` (REQUIRED), an `action` (REQUIRED; may open another radial
  menu, max nesting depth 4) and an optional `icon` (a freedesktop icon name).
* Radial menus are global and can be overridden per application.

## 11. OLED and auxiliary displays

```toml
[device.oled]
enabled = true
brightness = 70          # percent
timeout = 300            # seconds of inactivity before blanking, 0 = never
rotation = 0             # 0 | 90 | 180 | 270
content = "labels"       # "labels" | "app-name" | "off"
labels = { A = "Undo" }  # per-button label override
```

The compositor renders the labels of the active bindings for the focused
application (section 12) and current mode. The precedence is: `oled.labels`,
then the action's `label`, then the client's `set_feedback` string (for
`passthrough` controls), then a derived label. Display geometry and encoding
come from libtablet's `[OLED]` device metadata, not from this file.

## 12. Per-application overrides

```toml
[[app]]
app-id = "org.kde.krita"
device = "kamvas-pro-16"        # a device id, or "*" for all devices
[app.pad]
buttons = { B = { action = "Ctrl+z", label = "Undo" } }
[[app.tool]]
match = { type = "pen" }
buttons = { tertiary = "radial-menu:krita" }
[app.radial-menu.krita]
items = [{ label = "Brush presets", action = "F6" }]
```

* `app-id` (string or array of strings, REQUIRED) – compared exactly with the
  `xdg_toplevel.app_id` of the focused toplevel (for X11 clients, the
  `WM_CLASS` class as mapped by the compositor).
* `device` (string, default `"*"`).
* Overridable sub-tables: `pad`, `tool` (array, same matching as
  `[[device.tool]]`), `oled`, `radial-menu`. `mapping` and `touch` are
  **not** overridable per application, because changing the mapped area on
  focus change disorients users.
* Inheritance: the effective configuration for a device while an app has
  focus is the device configuration, merged with the matching `[[app]]`
  entries in order: `device = "*"` entries first, then entries naming the
  device. The section 1.1 rules apply unchanged; in particular an app's
  `ring`, `strip` or `dial` array replaces the device's array as a whole.
* The compositor switches profiles when keyboard focus moves to a toplevel
  with a different `app_id`. While no toplevel has focus, the device
  configuration is used. On switch it SHOULD update mode LEDs and OLED
  labels.

## 13. Reading, writing and live reload

### 13.1 Readers (compositors)

* Readers MUST watch the user file's directory (e.g. inotify
  `IN_CLOSE_WRITE | IN_MOVED_TO | IN_DELETE`) and the layer 1/2
  `profiles.d` directories, and reload when they change. They SHOULD debounce
  by at least 100 ms.
* A file that fails to parse MUST NOT be applied. The reader MUST keep the
  last successfully applied configuration and SHOULD report the error.
* Changes MUST take effect without restarting the session. Changes to a tool's
  pressure configuration MAY be deferred until the tool next enters proximity.

### 13.2 Writers (settings tools, the compositor)

To avoid lost updates between several writers (for example a settings app and
a compositor storing an interactively calibrated output mapping):

1. Take an exclusive advisory lock with `flock(LOCK_EX)` on
   `$XDG_CONFIG_HOME/xdg-tablet/profiles.toml.lock` (create it with mode 0600
   if needed). Do not lock `profiles.toml` itself, because it is replaced by
   rename.
2. Re-read `profiles.toml` while holding the lock and apply the change to the
   freshly read document (read-modify-write).
3. Write the result to a temporary file in the **same directory**
   (`profiles.toml.XXXXXX`), `fsync()` it, then `rename()` it over
   `profiles.toml`, then `fsync()` the directory.
4. Release the lock.

Readers do not take the lock. `rename()` makes every observed state complete.
Writers MUST NOT hold the lock for longer than the read-modify-write cycle and
MUST NOT block on user interaction while holding it.

The file SHOULD be created with mode 0644 and the directory with 0755.

## 14. Relation to other components

* **libinput** implements `area`, `left-handed`, `rotation`,
  `pressure-range`, touch arbitration modes and synthetic tool serials. The
  compositor translates this file into libinput configuration calls.
* **libtablet** provides device metadata: button letters, mode groups,
  ring/strip/dial counts, OLED geometry and EDID hints for pen displays.
  Validators SHOULD check button letters and control indices against it.
* **tablet-v2** (Wayland) carries `passthrough` events and `set_feedback`
  labels, and (version 3) the pressure-curve announcement.

## 15. Open questions

1. Pads with more than 26 buttons (the libwacom API names buttons with a
   single letter).
2. Per-unit configuration for several identical devices (match on the HID
   `phys` path or serial number?).
3. Whether to allow a restricted, user-confirmed `exec:` action.
4. Key **sequences** (`Ctrl+c Ctrl+v`) and text-input actions.
5. Whether `app-id` should support globs, and how Flatpak or X11 app IDs are
   normalised.
6. Whether the compositor should be allowed to write the file at all, or
   whether it should use a separate state file (`$XDG_STATE_HOME`) for
   calibration results.
7. Migration tooling from GNOME gsettings and the KDE `kcminputrc` tablet
   sections.
