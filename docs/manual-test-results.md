# Manual test results

Results of the manual checks for the `add-text-capture-core` change (tasks 10.1–10.4). The dev machine runs Ubuntu 24.04.2, GNOME Shell 46, with two 1920×1080 monitors at 100% scale.

Status values: **Pass**, **Fail** (with a note), **To do**, or **Not testable** (with the reason).

## 10.1 Capture flow

| Spec scenario | Xorg | Wayland | Notes |
|---|---|---|---|
| Shortcut starts a capture (capture-hotkey) | To do | To do | Needs a free key. On the dev machine `Ctrl+Q` belongs to NormCap, so the entry was created unbound, as specified. |
| `text-capture --capture` starts a capture | Pass | To do | 2026-10-18: the overlay opened on both monitors. |
| Overlay shows the frozen screen on every monitor | Pass | To do | 2026-10-18: one full-screen window per monitor, at (0,0) and (1920,0). |
| Drag selects; the text reaches the clipboard | Pass | To do | 2026-10-18: drag → OCR → clipboard ran end to end. The test text was covered by other windows, so the visible text was read instead. Repeat by hand with visible text. |
| Click or tiny drag is ignored | Pass (automated) | To do | `tests/test_overlay.py` |
| `Esc` cancels; clipboard unchanged | Pass | To do | 2026-10-18: clipboard stayed `before-cancel`; no overlay windows left. |
| Right-click cancels | Pass (automated) | To do | `tests/test_overlay.py` |
| Focus returns to the previous window | Pass | To do | 2026-10-18: text typed after a capture and after an `Esc` cancel reached the test window (`ok1ok2`). |
| A video keeps playing during a capture | To do | To do | |
| Second launch from the app grid gives no second tray icon | To do | To do | Covered by `tests/test_ipc.py` and `tests/test_main.py`. Check the top bar by hand. |
| Capture from the tray menu does not capture the menu | To do | To do | |
| Ten relaunches leave one shortcut entry | Pass (automated) | n/a | `tests/test_gnome_hotkey.py::test_register_is_idempotent` |
| Wayland: first capture shows the permission window and GNOME's dialog | n/a | To do | |
| Wayland: after Allow, later captures don't ask | n/a | To do | |
| Wayland: after Deny, the next capture asks again | n/a | To do | |
| Wayland: native Wayland app content is captured (not black) | n/a | To do | |
| No screenshot files left in `~/Pictures/Screenshots` or `/tmp` | Pass (X11 grabs to memory) | To do | |

## 10.2 Idle impact

| Measurement | Result | Limit | Status |
|---|---|---|---|
| Average CPU over one hour (09:15–10:15, normal desktop use, one capture in between) | 0.08% of one core (`pidstat -u -r -p <pid> 60 60`; busiest minute 3.55%, during the capture) | < 1% of one core | Pass |
| Resident memory (RSS) | 107.7 MB average, 108 MB at the end, 131 MB peak (`VmHWM`) | < 150 MB | Pass |

## 10.3 Monitors and scaling

| Setup | Result | Status |
|---|---|---|
| Two monitors at 100%, selection on each | The X11 grab returns both monitors (1920×1080 each). OCR of a label at (200,200) on DP-1 was exact. | Pass (DP-1); DP-2 to do |
| HiDPI or fractional scale | Not available on the dev machine. Covered by geometry unit tests. | Not testable |

## 10.4 Start at login

| Check | Status |
|---|---|
| "Start at login" on → the app runs after logging back in, no window | To do |
| "Start at login" off → the app does not run after logging back in | To do |
