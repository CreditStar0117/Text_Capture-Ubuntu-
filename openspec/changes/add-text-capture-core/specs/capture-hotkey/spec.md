# Spec Delta

## Purpose

Lets the user start a screen-text capture from anywhere on the desktop with one keyboard shortcut, in both X11 and Wayland sessions, without disturbing the user's other shortcuts.

## ADDED Requirements

### Requirement: Default capture shortcut is registered on first run
On first run, the system SHALL register `Ctrl+Q` as a system-wide shortcut that starts a capture, provided no other desktop shortcut (including shortcuts of GNOME Shell extensions) already uses that key combination. The shortcut SHALL work in both X11 and Wayland sessions, whichever window has focus.

#### Scenario: First run with a free key combination
- **WHEN** the app runs for the first time and no desktop shortcut uses `Ctrl+Q`
- **THEN** a shortcut named "Text Capture" bound to `Ctrl+Q` is registered
- **AND** pressing `Ctrl+Q` in any application starts a capture

#### Scenario: Shortcut works in a Wayland session
- **WHEN** the user is logged into an Ubuntu on Wayland session and presses the capture shortcut while a native Wayland app has focus
- **THEN** a capture starts

#### Scenario: Shortcut works in an X11 session
- **WHEN** the user is logged into an Ubuntu on Xorg session and presses the capture shortcut
- **THEN** a capture starts

### Requirement: Existing shortcuts are never overridden or modified
The system SHALL NOT change, remove or take over any keyboard shortcut it did not create. If the default key combination is already in use, the system SHALL skip binding it and tell the user once how to choose another combination.

#### Scenario: Default key combination already taken
- **WHEN** the app runs for the first time and another shortcut already uses `Ctrl+Q`
- **THEN** that other shortcut keeps working unchanged
- **AND** the user gets a notification saying the capture shortcut was not bound and how to set one

#### Scenario: Other custom shortcuts are preserved
- **WHEN** the user already has custom shortcuts and the app registers its own
- **THEN** every previously existing custom shortcut keeps its name, command and key combination

### Requirement: Shortcut registration is idempotent
Launching the app again SHALL NOT create duplicate shortcut entries. If the user has changed the key combination of the app's shortcut, later launches SHALL keep the user's choice.

#### Scenario: Repeated launches
- **WHEN** the app is started ten times
- **THEN** exactly one "Text Capture" shortcut entry exists

#### Scenario: User-chosen key combination survives relaunch
- **WHEN** the user rebinds the "Text Capture" shortcut to `Ctrl+Alt+T` and the app restarts
- **THEN** the shortcut is still bound to `Ctrl+Alt+T`

### Requirement: User can change the shortcut in desktop settings
The app's shortcut SHALL appear in the desktop's keyboard settings under the name "Text Capture", where the user can rebind or disable it with the standard settings UI.

#### Scenario: Rebinding from Settings
- **WHEN** the user opens Settings › Keyboard › Custom Shortcuts and changes "Text Capture" to another key combination
- **THEN** the new combination starts a capture and the old one no longer does

### Requirement: Triggering starts a capture whether or not the app is running
Pressing the shortcut SHALL start a capture. If the app is running, the capture overlay SHALL appear within 500 ms. If the app is not running, it SHALL start and then begin a capture. Pressing the shortcut while a capture is already in progress SHALL NOT open a second overlay.

#### Scenario: App already running
- **WHEN** the app is running in the background and the user presses the shortcut
- **THEN** the capture overlay appears within 500 ms

#### Scenario: App not running
- **WHEN** the app has been quit and the user presses the shortcut
- **THEN** the app starts and the capture overlay appears

#### Scenario: Shortcut pressed during a capture
- **WHEN** the capture overlay is open and the user presses the shortcut again
- **THEN** no second overlay opens and the current capture continues

### Requirement: Capture can be triggered from the command line
Running `text-capture --capture` SHALL start a capture exactly as the shortcut does, so other tools and scripts can trigger it.

#### Scenario: Command-line trigger
- **WHEN** the user runs `text-capture --capture` in a terminal
- **THEN** the capture overlay appears
