# Tasks

## 1. Project setup

- [x] 1.1 Create the `text_capture/` package with the module files from design D11, plus `tests/` with a `conftest.py` that sets `QT_QPA_PLATFORM=offscreen` and provides a session-wide `QApplication` fixture, a `pyproject.toml` (project metadata, pytest config) and a `.gitignore`. Verify that `python3 -m text_capture --help` prints usage and `python3 -m pytest` runs (0 tests, exit code 5 or 0).
- [x] 1.2 Add a dependency step to `scripts/install.sh` (`--check-deps`) that lists the missing apt packages (`python3-pyqt6`, `qt6-wayland`, `tesseract-ocr`, `tesseract-ocr-eng`, `python3-pytest`) and offers to `sudo apt install` them after asking. Verify that `scripts/install.sh --check-deps` reports every package present on the dev machine after installing.

## 2. Settings, single instance and command line

- [x] 2.1 Implement `settings.py` (QSettings INI at `~/.config/text-capture/text-capture.conf`, keys and defaults from design D9, `sync()` on each change). Verify with unit tests, using a temporary `XDG_CONFIG_HOME`, that the defaults are correct and values survive a reload.
- [x] 2.2 Implement `ipc.py`: a `QLocalServer` at `$XDG_RUNTIME_DIR/text-capture.sock` and a stdlib-only `AF_UNIX` client, with stale-socket cleanup and recovery when two launches race (design D3). Verify with tests that a second "instance" forwards `capture`/`quit` to the first, that a stale socket file is replaced, and that two simultaneous starts leave exactly one server.
- [x] 2.3 Implement argument parsing in `__main__.py` for `--capture`, `--quit`, `--background` and `--uninstall`, where the client path never imports PyQt6. Verify that a test asserts `PyQt6` is absent from `sys.modules` on the client path, and that `--capture` against a running server returns in under 100 ms (timed in a test).

## 3. GNOME capture hotkey

- [ ] 3.1 Spike: by hand, create a custom keybinding at the dedicated dconf path `…/custom-keybindings/text-capture/` and confirm it is listed and editable in Settings › Keyboard › Custom Shortcuts and fires in both X11 and Wayland sessions. Then remove it. Verify by recording the outcome in design.md D2, switching D2 to "first free `customN` slot, identified by command path" if the dedicated path is not listed.
- [x] 3.2 Implement conflict detection in `gnome_hotkey.py`: collect bindings from the schemas listed in D2 plus all existing custom keybindings, and normalize accelerators. Verify with unit tests against recorded `gsettings` output fixtures, covering case/modifier-order normalization, a taken `<Super>q`, and a free `<Super>q`.
- [x] 3.3 Implement registration: append only our path to `custom-keybindings`, set name, absolute command and binding (empty on conflict), set the `hotkey/registered` flag, and never re-create the entry after the user deletes it. Verify with unit tests using a fake `gsettings` runner that existing entries are byte-identical after registration, that 10 registrations give one entry, and that a user-changed binding is preserved.
- [ ] 3.4 Implement removal for `--uninstall`, which drops only our path and its keys. Verify with a unit test (fake runner) that other entries survive, and by hand on the dev machine that `<Control>1` and `<Control>q` still work after install and then uninstall.
- [ ] 3.5 Add a "Capture shortcut" section to README.md covering the default key, how to change it in Settings, and what happens on a conflict. Verify that following the README steps on the dev machine rebinds the shortcut.

## 4. Screen grabbing

- [x] 4.1 Implement session detection (`XDG_SESSION_TYPE`, then `WAYLAND_DISPLAY`) and grabber selection in `grab.py`, independent of the Qt platform (design D4). Verify with unit tests for the env combinations x11, wayland, Wayland with Qt on xcb, and unset.
- [x] 4.2 Implement the X11 grabber (`QScreen.grabWindow(0)` for each screen into one desktop image). Verify by hand in an Xorg session that a debug command (`python3 -m text_capture.grab --save /tmp/…`) writes a correct full-desktop image.
- [ ] 4.3 Implement the portal grabber with QtDBus: call `Screenshot` with `interactive=false`, handle `Request.Response`, load the URI into memory, and delete the returned file under the D4 conditions. A refused or cancelled response code becomes a "permission refused" result. Verify by hand in a Wayland session that the debug command captures native Wayland windows (not black) and that `~/Pictures/Screenshots` and `/tmp` have no new files afterwards.
- [ ] 4.4 Measure the portal grab latency (10 runs) and record whether a permission dialog appeared on the dev machine. Verify by writing the numbers into design.md Risks and resolving the permission open question. If the median latency exceeds 350 ms, implement the "capturing" placeholder overlay from the Risks mitigation.
- [x] 4.5 Implement the pure geometry function that maps a selection on a screen (logical rect, screen geometry, device pixel ratio, full image size) to a physical crop rect, with the proportional fallback. Verify with unit tests for 1×, 2×, 125% fractional, two monitors at the same scale, two monitors with mixed scales, and a negative-offset monitor layout.
- [ ] 4.6 Run the server instance under the stable app ID (design D4): re-execute once under `systemd-run --user --scope` unless the cgroup already names `io.github.CreditStar0117.TextCapture`, and set Qt's desktop file name to that ID. Verify with unit tests of the cgroup check and loop guard, and by hand that a portal request from the running instance carries that app ID (`dbus-monitor`).
- [ ] 4.7 Implement the one-time permission window and flow from design D4 (response 2 → permission-store lookup → focused window → Continue repeats the request → discard that image → real capture; Deny → notification; Cancel → nothing). Verify with unit tests of the decision logic using fake store and portal results, and by hand in a Wayland session: the first capture shows the window and GNOME's dialog, Allow makes later captures silent, and after Deny the next capture asks again.

## 5. Capture overlay

- [x] 5.1 Implement `overlay.py`: one frameless, always-on-top, full-screen window per `QScreen`, painting its slice of the frozen image dimmed, with a crosshair cursor. Verify with an offscreen QTest that one window per screen is created and painted pixels are darker than the source.
- [x] 5.2 Add drag selection with an undimmed rect, border and `W × H` label, the 4-px minimum and clamping to the starting monitor. Emit the selection as a physical crop rect using 4.5. Verify with QTest mouse-event tests for a normal drag, a click without drag (no emit), a 3-px drag (no emit) and dragging past the edge (clamped).
- [x] 5.3 Add cancellation (`Esc`, right-click, 60 s inactivity timer) and a "Recognizing…" state that keeps the overlay open until told to close. Verify with QTest tests for each cancel path (timer shortened by a test hook), and that `Esc` during "Recognizing…" emits cancel.
- [ ] 5.4 Verify focus return by hand in both sessions: type in gedit, capture, then keep typing. The keystrokes land in gedit after both a completed and a cancelled capture.

## 6. Text recognition

- [x] 6.1 Build the reference test set in `tests/data/`: at least 20 PNGs (Qt-rendered UI text at several sizes and scales, light and dark themes, plus at least 5 real screenshots from the dev machine), each with an expected `.txt`. Verify that the files exist and a test helper loads every pair.
- [x] 6.2 Implement language discovery (`tesseract --list-langs`, excluding `osd`) and code → display-name mapping. Verify with unit tests on recorded command output, and that a missing selected language falls back to `eng` with a one-time warning flag.
- [x] 6.3 Implement preprocessing (grayscale, invert on dark backgrounds, upscale by display scale, padding) per D6. Verify with unit tests on synthetic images covering output size, inversion of a dark image, and no inversion of a light image.
- [x] 6.4 Implement the Tesseract `QProcess` runner (`nice -n 10`, `OMP_THREAD_LIMIT=1`, PNG via stdin, text via stdout, cancel, 15 s timeout, "engine not installed" detection). Verify with tests that a real run on a reference image returns text, that cancel kills the process, that a fake slow `tesseract` on `PATH` triggers the timeout, and that a `PATH` without `tesseract` yields the missing-engine error naming `tesseract-ocr`.
- [x] 6.5 Implement text normalization (trim, collapse blank lines, keep line breaks or join lines within a paragraph). Verify with unit tests for `Hello\nworld` in both modes, paragraph separation, and whitespace-only input giving an empty result.
- [x] 6.6 Add the accuracy test (character accuracy across the 6.1 set, in English) and tune the upscale factors and PSM 6 vs. 3. Verify that the test passes at ≥ 98%, record the chosen parameters in design.md D6, and confirm a 1000 × 300 region completes in under 2 s (timed test).
- [ ] 6.7 Add an "OCR languages" section to README.md (installing `tesseract-ocr-<lang>` and choosing it from the tray). Verify by installing `tesseract-ocr-deu` on the dev machine and confirming German appears after an app restart.

## 7. Clipboard and notifications

- [x] 7.1 Implement clipboard delivery in `output.py`: `setText` while the overlay is focused, an `ownsClipboard()` check, the `wl-copy` fallback, and an error result (design D7). Verify with an offscreen test that the text round-trips through `QClipboard`, and a unit test (fakes) for the fallback/error decision order.
- [x] 7.2 Implement notifications through `org.freedesktop.Notifications` (transient, urgency, `replaces_id`, 100-character preview with an ellipsis, success notifications suppressed when the setting is off, errors always shown). Verify with unit tests on the message builder (truncation, hints) and a fake D-Bus sender for the on/off/error matrix.
- [x] 7.3 Implement the empty-result rule (no clipboard write, "No text found" notification). Verify with a unit test that the clipboard fake is never called for an empty or whitespace-only result.

## 8. Tray app and capture controller

- [x] 8.1 Implement the capture controller in `app.py`: the grab → overlay → OCR → output → close sequence, ignoring triggers while a capture is active, and a `try/finally` that always closes the overlays and notifies on error. Verify with tests using fake grabber and OCR: a second trigger during a capture is ignored, an exception raised mid-capture closes every overlay and the next trigger works.
- [ ] 8.2 Implement the tray icon and menu (Capture with a 250 ms delay, OCR Language submenu, toggles showing check state, Quit), plus a one-time notice with no tray (`QSystemTrayIcon.isSystemTrayAvailable()` false). Add symbolic and full-colour SVG icons. Verify with offscreen tests of menu structure and toggle → settings wiring, and by hand that the icon appears in the Ubuntu top bar.
- [x] 8.3 Implement the "Start at login" toggle (write/delete `~/.config/autostart/io.github.CreditStar0117.TextCapture.desktop` with `--background`), on by default at first run. Verify with unit tests using a temporary `XDG_CONFIG_HOME` that the file appears and disappears with the toggle, and that its `Exec` uses the absolute launcher path.
- [x] 8.4 Wire first-run setup (hotkey registration, autostart), `--uninstall` (stop the running instance, remove the hotkey entry and autostart file) and logging to `$XDG_STATE_HOME/text-capture/` with a 1 MB cap. Verify with a test, using a fake runner and temporary XDG dirs, that first run creates both and `--uninstall` removes only ours.
- [x] 8.5 Add a "Tray menu" section to README.md describing each item. Verify that every menu item listed in the README matches the running app's menu.

## 9. Install script and launcher

- [x] 9.1 Complete `scripts/install.sh`: copy the package to `~/.local/share/text-capture`, write the `~/.local/bin/text-capture` launcher, and install the app-grid `.desktop` file and icon to `~/.local/share/applications` and `~/.local/share/icons`. Add `--uninstall`, which runs `text-capture --uninstall` and then removes those files. Verify on the dev machine that after install "Text Capture" is in the app grid and `text-capture --help` works from a new terminal, and that after uninstall none of those files remain.
- [x] 9.2 Add "Install", "Uninstall" and "Troubleshooting" sections to README.md (Wayland screenshot permission, AppIndicators extension disabled, missing OCR engine). Verify by doing a fresh install on the dev machine using only the README.

## 10. Integration verification

- [ ] 10.1 Run the manual test matrix in both Ubuntu on Xorg and Ubuntu on Wayland: hotkey → select → paste; Esc and right-click cancel; focus return; a video keeps playing during capture; second launch from the app grid gives no second icon; Capture from the tray menu does not capture the menu; ten relaunches give one shortcut entry. Verify by recording pass/fail for each spec scenario in `docs/manual-test-results.md`.
- [ ] 10.2 Measure idle impact: one hour idle while working normally, sampling with `pidstat -p <pid> 60`, plus resident memory from `/proc/<pid>/status`. Verify that the recorded average CPU is under 1% and RSS under 150 MB in `docs/manual-test-results.md`.
- [ ] 10.3 If a second monitor or a HiDPI/fractional setting is available, verify that a selection on each monitor and scale captures the right pixels. Record the results, or "not testable on this hardware", in `docs/manual-test-results.md`.
- [ ] 10.4 Log out and back in with "Start at login" on and then off. Verify that the app is running only in the first case, and record this in `docs/manual-test-results.md`.
- [ ] 10.5 Run `python3 -m pytest` and `openspec validate add-text-capture-core --strict`. Verify that both pass.

## Workflow follow-up

- Archive the change with `/opsx:archive` once the tasks are done and reviewed, which copies these specs into `openspec/specs/`.
- After archiving, check that `openspec list --specs` shows the five capabilities.
