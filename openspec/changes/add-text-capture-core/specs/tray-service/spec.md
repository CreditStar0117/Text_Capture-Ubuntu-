# Spec Delta

## Purpose

Keeps Text Capture available all the time as a quiet background app with a tray icon, so captures are always one keystroke away, without ever getting in the way of the user's other apps or the system.

## ADDED Requirements

### Requirement: Tray icon with app menu
While running, the app SHALL show an icon in the top-bar tray area. Clicking it SHALL open a menu with: Capture, OCR Language (a submenu of installed languages), Keep line breaks, Show notifications, Start at login, and Quit. Toggle items SHALL show their current state.

#### Scenario: Menu contents
- **WHEN** the user clicks the tray icon
- **THEN** the menu shows Capture, OCR Language, Keep line breaks, Show notifications, Start at login, and Quit
- **AND** each toggle shows a check mark when it is on

#### Scenario: Capture from the menu
- **WHEN** the user chooses Capture in the tray menu
- **THEN** the menu closes and a capture starts, and the menu has closed before the overlay opens

#### Scenario: Tray area not available
- **WHEN** the desktop has no tray area (for example, the AppIndicators extension is disabled)
- **THEN** the app keeps running and the capture shortcut still works
- **AND** the user is told once that the tray icon cannot be shown and that `text-capture --quit` stops the app

### Requirement: Only one instance runs
Only one instance of the app SHALL run per user session. Launching the app while it is already running SHALL pass the launch's request (for example `--capture` or `--quit`) to the running instance and then exit, without showing a second tray icon.

#### Scenario: Second launch
- **WHEN** the app is running and the user launches it again from the app grid
- **THEN** no second tray icon appears and only one app process remains

#### Scenario: Request forwarded to the running instance
- **WHEN** the app is running and the user runs `text-capture --quit`
- **THEN** the running instance exits

### Requirement: App starts at login
"Start at login" SHALL be on by default after first run. When on, the app SHALL start automatically in the background at login without opening any window. When the user turns it off, the app SHALL NOT start at the next login.

#### Scenario: Default autostart
- **WHEN** the user runs the app for the first time and then logs out and back in
- **THEN** the app is running with its tray icon and no window has opened

#### Scenario: Autostart turned off
- **WHEN** the user turns off "Start at login" and logs out and back in
- **THEN** the app is not running

### Requirement: Settings persist across restarts
The OCR language, Keep line breaks, Show notifications and Start at login settings SHALL be saved in the user's configuration directory as soon as they change, and SHALL be restored when the app starts.

#### Scenario: Settings survive restart
- **WHEN** the user selects French and turns off notifications, then quits and starts the app
- **THEN** French is selected and notifications are off

### Requirement: Idle app does not interfere with the system
When no capture is in progress, the app SHALL NOT show windows, take focus, make sounds or do periodic work. Averaged over one minute of idling it SHALL use under 1% of one CPU core, and it SHALL use under 150 MB of memory.

#### Scenario: Working alongside the idle app
- **WHEN** the app has been idle in the background for an hour while the user works in other apps
- **THEN** no window from the app appeared, focus never moved to it, and its average CPU use stayed under 1% of one core

### Requirement: Failures never leave the desktop blocked
If a capture fails unexpectedly, the app SHALL close any overlay it opened, report the error, and keep running so the next capture works. No failure SHALL leave a full-screen overlay covering the desktop.

#### Scenario: Internal error during capture
- **WHEN** an unexpected error occurs while the overlay is open
- **THEN** the overlay closes, the user is told the capture failed, and the next shortcut press starts a new capture normally

### Requirement: App can be quit and its desktop integration removed
Choosing Quit, or running `text-capture --quit`, SHALL stop the app. Running `text-capture --uninstall` SHALL stop the app and remove the shortcut and autostart entry the app created, leaving every other shortcut and autostart entry untouched.

#### Scenario: Quit from the tray
- **WHEN** the user chooses Quit in the tray menu
- **THEN** the app process exits and the tray icon disappears

#### Scenario: Uninstall desktop integration
- **WHEN** the user runs `text-capture --uninstall`
- **THEN** the app stops, the "Text Capture" shortcut and its autostart entry are removed, and all other custom shortcuts still work
