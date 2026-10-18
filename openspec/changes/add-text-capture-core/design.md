# Design

## Context

The repository has no code yet (see proposal.md for motivation). The design is shaped by the target platform, checked on the development machine:

- **Ubuntu 24.04 LTS, GNOME Shell 46.** Ubuntu offers both an Xorg and a Wayland session (Wayland is the default), so either may be running.
- **No global-shortcut API on Wayland.** `xdg-desktop-portal-gnome` 46.2 implements the Screenshot portal but not GlobalShortcuts, which arrived in a later GNOME release. On Wayland, an app cannot grab a key itself.
- **No direct screen grabbing on Wayland.** Wayland clients cannot read other windows' pixels. Under Wayland, `QScreen::grabWindow` returns nothing, and an XWayland grab shows native Wayland windows as black.
- **Tray icons need the AppIndicators extension.** Ubuntu enables `ubuntu-appindicators@ubuntu.com` by default, and it hosts StatusNotifierItem icons. Stock GNOME has no tray.
- **Everything installs from apt** in 24.04: `python3-pyqt6` 6.6.1 (Qt 6.4.2, with QtDBus, QtNetwork, QtWidgets and QtTest), `qt6-wayland`, `tesseract-ocr` 5.3.4 with language packs, and `python3-pytest`.
- **Users may already have custom shortcuts.** The dev machine has two: `<Control>1` (Flameshot) and `<Control>q` (NormCap OCR).
- **Shell extensions hold shortcuts too.** Stock Ubuntu 24.04's Ubuntu Dock binds `<Super>q` (`org.gnome.shell.extensions.dash-to-dock shortcut`), so Capture2Text's `Win+Q` equivalent is not available. The default is `<Control>q`, chosen by the project owner.

## Goals / Non-Goals

**Goals:**
- One code path for the hotkey on X11 and Wayland, and the smallest possible session-specific code for screen grabbing.
- Every dependency comes from the Ubuntu 24.04 archive, with no pip, compiler or network fetches at install time.
- OCR runs outside the UI process, so a slow or crashing recognition can be killed without affecting the app or the desktop.
- Pressing the shortcut leads to a visible overlay within 500 ms when the app is running (see `capture-hotkey` spec).

**Non-Goals:**
- Desktops other than GNOME. `text-capture --capture` can be bound by hand elsewhere, but it is not tested.
- The GlobalShortcuts and ScreenCast portals. They can be added later for GNOME 48+ without changing the specs.
- Packaging as .deb, Snap or Flatpak. A per-user install script is enough for now.
- Configurable OCR engine parameters in the UI.

## Decisions

### D1. Python 3.12 + PyQt6 from apt
Qt provides the tray icon (`QSystemTrayIcon`, which uses StatusNotifierItem over D-Bus), full-screen overlays per monitor, the clipboard, D-Bus and local sockets in one toolkit, with native Wayland support through `qt6-wayland`. Python keeps iteration fast, and apt installs all of it.
- *C++/Qt6* (the original Capture2Text's stack) would be faster and lighter, but needs a build toolchain and slows development. It can be revisited if Python's idle memory is a problem.
- *GTK4 + PyGObject* has no tray API, so it would need GTK3 plus libayatana-appindicator for the icon. That means two toolkits.
- *Electron/Tauri* would blow the idle memory budget and add a non-apt runtime.

### D2. The hotkey is a GNOME custom keyboard shortcut that runs `text-capture --capture`
On first run the app adds an entry to `org.gnome.settings-daemon.plugins.media-keys custom-keybindings`, with name "Text Capture", command `<absolute path>/text-capture --capture` and binding `<Control>q`. GNOME's own settings daemon handles the key in both X11 and Wayland. The entry shows up in Settings › Keyboard › Custom Shortcuts, which meets the "user can change it" requirement with no hotkey UI of our own.
- **Ownership:** the entry lives at a dedicated dconf path, `…/custom-keybindings/text-capture/`, not a `customN` slot. The app can therefore find, update and remove only its own entry. *Spike (task 3.1), X11:* `gsd-media-keys` loads and fires an entry at this path. When the key was already held (`<Super>q` by Ubuntu Dock), it only logged `Failed to grab accelerator`, so the app cannot detect a missed grab and must rely on the conflict check. The `custom-keybindings` list is read, our path appended if missing, and written back, so other entries are never touched.
- **Conflict check:** before binding, read every binding in `org.gnome.desktop.wm.keybindings`, `org.gnome.shell.keybindings`, `org.gnome.mutter.keybindings`, `org.gnome.mutter.wayland.keybindings`, `org.gnome.settings-daemon.plugins.media-keys`, every installed `org.gnome.shell.extensions.*` schema, and all existing custom keybindings. Normalize case, modifier aliases and modifier order (`<Primary>Q` equals `<control>q`). If the combination is taken, create the entry with an empty binding, so it still appears in Settings, and notify the user.
- **Register once:** a `hotkey/registered` flag in settings means the entry is only created on first run. If the user later deletes or rebinds it, the app respects that.
- **How:** call the `gsettings` CLI with `subprocess`. It is always present on Ubuntu GNOME, and PyQt has no GSettings bindings.
- *Alternatives:* an X11 `XGrabKey` (works on X11 only); the GlobalShortcuts portal (not available on GNOME 46); reading `/dev/input` (needs root or the `input` group, which is a security problem).

### D3. One instance per session, with a launch path that doesn't load Qt
The running app listens on a `QLocalServer` at `$XDG_RUNTIME_DIR/text-capture.sock`. The entry point first tries a plain stdlib `socket.AF_UNIX` connection. If that succeeds, it sends one line (`capture`, `quit` or `show`) and exits without importing Qt, which keeps `--capture` well under 100 ms of the 500 ms budget. If nothing is listening, it removes any stale socket, imports Qt and becomes the server. If two launches race, the loser's `listen()` fails and it falls back to connecting as a client.
- *Alternative:* a D-Bus well-known name. It is more idiomatic on GNOME, but every client would have to load a D-Bus library, which costs startup time, and D-Bus activation isn't needed.

### D4. Screen grabbing: choose the grabber by session type, not by Qt platform
Use `XDG_SESSION_TYPE` (with `WAYLAND_DISPLAY` as a fallback) to pick the grabber. Even if Qt falls back to XWayland because `qt6-wayland` is missing, the portal must still be used.
- **X11:** `QScreen.grabWindow(0)` for each screen. It is synchronous and fast.
- **Wayland:** call the `org.freedesktop.portal.Screenshot.Screenshot` method with `interactive=false` through QtDBus, wait for the `Request.Response` signal, load the PNG from the returned URI into memory, then **delete that exact file**. Delete it only if it is the URI returned for this request and was modified after the trigger. Some GNOME versions write portal screenshots into `~/Pictures/Screenshots`, and the `region-capture` spec forbids leftovers.
- **App identity (verified on the dev machine):** the portal identifies an unsandboxed app by its systemd scope name. Run from a VS Code terminal, a request was attributed to `org.chromium.Chromium`; run in a scope named `app-io.github.CreditStar0117.TextCapture-<n>.scope`, it was attributed to `io.github.CreditStar0117.TextCapture`. The instance that becomes the server therefore re-executes itself once under `systemd-run --user --scope --unit=app-io.github.CreditStar0117.TextCapture-<pid>.scope`, unless its cgroup already names that ID (as it does when GNOME starts it from the app grid or autostart, whose desktop files are named after the ID). An environment guard prevents loops, and the step is skipped when `systemd-run` is missing.
- **Permission (verified on the dev machine):** with no stored permission, a non-interactive request makes the portal call `AccessDialog`. GNOME Shell refuses that unless the caller is the focused app ("Only the focused app is allowed to show a system access dialog"), and the portal answers with response 2. A background app triggered by a hotkey is never focused, so the flow is:
  1. On response 2, look up table `screenshot`, id `screenshot` in `org.freedesktop.impl.portal.PermissionStore`. If our ID has "yes", report a capture error. Otherwise (no entry or "no"), show a small focused permission window explaining why, with Continue and Cancel.
  2. Continue first deletes a stored "no" for our ID (only on that explicit click), then repeats the request while the window still has focus, so GNOME shows its Allow/Deny dialog.
  3. Allowed: the returned image contains our window, so it is discarded and its file deleted. The window closes and the capture overlay opens 300 ms later.
  4. Denied: notify that capture needs screenshot permission and that triggering a capture again asks again.
- **Asking before the overlay:** each grabber reports whether a grab is known to work without asking (`allowed()`: always on X11; on Wayland only when the store holds "yes" for our ID). If not, the controller makes one check grab before opening the overlay and discards its image. A permission failure therefore opens the permission window before the user has selected anything, and an app that the portal identifies under another ID still works, at the cost of that extra grab. If permission is withdrawn later, the grab after the selection fails the same way, and the overlay closes before the permission window opens.
- **When to grab:** the desktop is grabbed once, after the user releases the mouse button, while the overlay is still open (D5). The overlay is fully transparent over the selection, so the crop holds only the screen's own pixels. *Verified on the dev machine's Xorg session:* a grab through the transparent area matched the screen pixel for pixel, while the dimmed area came out darker. The controller waits 80 ms after the release so the compositor has shown the final selection without its size label. When the capture comes from the tray menu, the overlay opens 250 ms later so the menu has closed first.
- *Alternatives:* the ScreenCast portal + PipeWire (shows a monitor-picker dialog and needs GStreamer/PipeWire bindings); `org.gnome.Shell.Screenshot` called directly (restricted to allow-listed callers since GNOME 41); grabbing through XWayland (Wayland windows come out black).

### D5. One see-through overlay window per monitor
For each `QScreen`, create a frameless, always-on-top, translucent window and show it full-screen on that screen. Wayland has no global window positioning, so one window spanning all monitors isn't possible. The windows show no screenshot: they dim the live screen, so videos and animations keep moving underneath during a capture. The selection is a fully transparent hole with a 2-pixel clear margin, so the rounded edges of the crop stay clear too. Its border and W × H label are drawn outside the hole. Selections are clamped to the monitor where the drag started, as the spec requires. The windows handle `Esc`, right-click, the 4-pixel minimum drag and a 60-second auto-cancel timer. Once a drag ends, every window ignores mouse input and hides the label until the grab is done, then shows "Recognizing…".
- *Replaced:* the first version grabbed the desktop at the trigger and painted that still image in the overlay. Apps kept running underneath, but the screen looked frozen until the capture ended, and users found that disruptive (a playing video appeared to stop).
- **Mapping logical to physical pixels:** the crop rectangle is the selection scaled by the grabbed screen image's size over the screen's logical size. On X11 that is `screen.devicePixelRatio()`. For portal images, each screen's part of the desktop image is found first by comparing the image size with the logical layout of all screens. This is checked against the combined geometry, and falls back to a uniform proportional scale when they disagree.
- **Focus return:** the app never activates other windows. When the overlay windows close, Mutter gives focus back to the window that was on top before, which is the previously focused one, in both sessions.

### D6. OCR with the Tesseract 5 CLI in a niced subprocess
Run `nice -n 10 tesseract stdin stdout -l <lang> --psm 6 --dpi 300` through `QProcess`, with `OMP_THREAD_LIMIT=1`. The preprocessed PNG goes in through stdin, so no image touches disk. `QProcess` is asynchronous, so the UI never blocks, and it can be killed when the user cancels or the 15-second timeout hits.
- **Preprocessing** (in Qt, before OCR): convert to grayscale; invert if the mean brightness is below 50%, because Tesseract's LSTM model does poorly on light-on-dark text; upscale with smooth scaling so the effective scale is about 3× at 100% display scale and 1.5× at 200%; add a 10-pixel border in the background colour. Exact factors and the PSM are tuned against the reference test set, not hard-coded from guesses. *Tuned (task 6.6):* upscale **2× at 100%** (so 1× at 200%) with **PSM 6** gave 100% character accuracy on the 26-image set (1,493 characters). 3× gave 99.7%, and 1× with PSM 3 gave 99.4%. A 1000 × 300 region takes about 0.6 s.
- **Languages:** `tesseract --list-langs`, excluding `osd`, with a small table from code to display name (`eng` → English, `deu` → German, `chi_sim` → Chinese (Simplified), …) and the raw code as a fallback.
- **Line breaks:** Tesseract separates lines with `\n` and paragraphs with a blank line. Normalization trims the text and collapses blank lines. With "Keep line breaks" off, lines within a paragraph are joined with single spaces. This is a pure function, so it is unit-tested directly.
- *Alternatives:* pytesseract or tesserocr in-process (a hang can't be killed and a crash takes down the app; tesserocr isn't in apt); EasyOCR or PaddleOCR (PyTorch-sized dependencies, slow cold start, and they break the memory budget).

### D7. Set the clipboard while the overlay still has focus
On Wayland, a client can only set the selection using the serial of a recent input event while it has keyboard focus. Setting it after the overlay closes, when OCR is done but the app is unfocused, would fail silently. So the overlay stays open with a "Recognizing…" indicator until OCR finishes. Then `QClipboard.setText()` runs, and only then does the overlay close. Ownership is confirmed with `QClipboard.ownsClipboard()`. If that check fails and `wl-copy` is installed, it is used as a fallback. Otherwise the failure is reported. The app is long-running, so it keeps serving the clipboard after the overlay closes. On X11 the same order is used, so behaviour is the same in both sessions.

### D8. Notifications through `org.freedesktop.Notifications`
Call `Notify` directly instead of `QSystemTrayIcon.showMessage`, so notifications still work when there is no tray. *Implementation note:* PyQt6's QtDBus marshals Python ints as `i` and lists as `av`, so it cannot produce the `u` and `as` arguments `Notify` requires (verified). The call is therefore made with `gdbus call` in an asynchronous `QProcess`, whose GVariant text format states the exact types. `gdbus` ships with GLib on every GNOME desktop. The body is HTML-escaped because GNOME renders notification bodies as markup. Hints: `transient=true` (not kept in the message tray), `urgency=low` for results and `normal` for errors. `replaces_id` is reused, so rapid captures replace each other instead of stacking. GNOME banners never take keyboard focus.

### D9. Settings and the autostart file
`QSettings` in INI format at `~/.config/text-capture/text-capture.conf` holds `ocr/language`, `output/keep_line_breaks`, `output/notify`, `app/autostart` and `hotkey/registered`. Each change is written immediately with `sync()`. Turning "Start at login" on writes `~/.config/autostart/io.github.CreditStar0117.TextCapture.desktop` with `Exec=<absolute path> --background`. The file name carries the app ID so the autostarted instance runs in a correctly named scope (D4). Turning it off deletes that file.

### D10. Idle behaviour is event-driven only
While idle, nothing runs except the local-socket listener and the tray icon, with no timers and no polling. Overlay windows are created per capture and destroyed afterwards, so their image memory is freed. A top-level exception handler, plus a `try/finally` around each capture, always closes the overlays and notifies, which meets the `tray-service` "failures never leave the desktop blocked" requirement. Logs go to `$XDG_STATE_HOME/text-capture/text-capture.log`, capped at 1 MB with one backup.

### D11. Code layout and install
```
text_capture/
  __main__.py     # arg parsing; stdlib-only client path (D3)
  ipc.py          # QLocalServer + stdlib client
  app.py          # QApplication, tray menu, capture controller
  gnome_hotkey.py # gsettings register/conflict check/remove (D2)
  grab.py         # X11Grabber, PortalGrabber (D4)
  overlay.py      # per-screen overlay windows (D5)
  ocr.py          # preprocessing, tesseract QProcess, languages, text normalization (D6)
  output.py       # clipboard + notifications (D7, D8)
  settings.py     # QSettings wrapper + autostart file (D9)
scripts/install.sh  # apt deps, copy to ~/.local/share/text-capture,
                    # launcher in ~/.local/bin, app-grid .desktop + icon
                    # (both named io.github.CreditStar0117.TextCapture); --uninstall
tests/            # pytest; tests/data/ holds reference images + expected text
```
`install.sh` runs `sudo apt install` only for missing packages and asks first. The GNOME shortcut and autostart entry use the launcher's absolute path, so they don't depend on `PATH`.

## Risks / Trade-offs

- **[Risk] GNOME's screenshot permission needs a focused app (confirmed, see D4).** → Handled by the one-time permission window. If a future GNOME changes the response codes or the store layout, the flow falls back to reporting a capture error rather than looping.
- **[Risk] GNOME's portal screenshot may flash the screen or play a shutter sound.** → The app can't control this; it is accepted as cosmetic. If it is too disruptive, the ScreenCast portal (D4 alternative) is the follow-up.
- **[Risk] Portal screenshots add latency (~150–400 ms) between the release and the start of recognition.** → The overlay itself opens without waiting for a grab. The latency counts towards the 2-second recognition target and is measured in task 4.4.
- **[Risk] The see-through overlay needs a compositor, or its transparent parts would not show the screen.** → GNOME always composites, in both sessions. Other desktops are a non-goal.
- **[Trade-off] The selection is read when the mouse button is released, not when the capture starts.** Fast-changing content such as subtitles is captured as it looks at the release, which is what the user sees while selecting.
- **[Risk] Mixed-scale multi-monitor (e.g. 100% + 200%) and fractional scaling under Wayland can map portal image regions incorrectly.** → The mapping is a pure function and is unit-tested against the known GNOME layouts. It is also covered by the manual test matrix: 1×, 2×, 125% fractional, two monitors with mixed scales.
- **[Risk] A dedicated dconf path (`…/custom-keybindings/text-capture/`) might not be listed by GNOME Settings, which expects `customN`.** → It fires on X11 (task 3.1). Listing in Settings and firing on Wayland still need a check by hand. If it isn't listed, use the first free `customN` slot and identify our entry by its command path.
- **[Trade-off] `Ctrl+Q` is the usual "Quit" shortcut in many apps (Firefox, VS Code, LibreOffice, Text Editor).** While GNOME holds it as a global shortcut, apps no longer receive it, so users must quit those apps another way. → Accepted by the project owner; the README states it, and the key can be changed in Settings.
- **[Trade-off] Starting a Tesseract process for each capture costs ~100–200 ms to start and load the model.** → This is accepted for crash isolation and cancellation, and stays well inside the 2-second spec target.
- **[Trade-off] Python + Qt idle memory (~70–100 MB) is heavier than C++.** → It is within the 150 MB spec limit and measured in testing. C++ remains the escape route.
- **[Trade-off] With no tray (AppIndicators disabled), the only controls are the shortcut and the CLI.** → This is reported to the user once, per the spec.

## Migration Plan

This is a new project, so there is nothing to migrate. To deploy, run `scripts/install.sh`, then start Text Capture from the app grid. The first run registers the shortcut and the autostart entry. To roll back, run `text-capture --uninstall`, which removes the shortcut and autostart entry, then `scripts/install.sh --uninstall`, which removes the files. Settings in `~/.config/text-capture/` are kept unless the user deletes them.

## Open Questions

- What are the best upscale factor and PSM (6 vs. 3) for real screen text? These are tuned against the reference set during implementation (D6) without affecting any spec.
