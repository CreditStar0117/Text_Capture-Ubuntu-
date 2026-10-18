# Spec Delta

## Purpose

Lets the user mark the exact area of the screen whose text they want, and turns that area into an image for recognition, on any monitor and display scale, in both X11 and Wayland sessions.

## ADDED Requirements

### Requirement: Capture shows a frozen image of the screen
When a capture starts, the system SHALL cover every monitor with a still image of what that monitor showed at the moment of the trigger, with the whole image slightly dimmed. Other apps SHALL keep running underneath. The overlay only shows a still image and SHALL NOT pause any app.

#### Scenario: Overlay shows the screen as it was
- **WHEN** the user triggers a capture
- **THEN** each monitor shows a dimmed still image of its contents at the moment of the trigger

#### Scenario: Apps keep running during capture
- **WHEN** a video is playing and the user triggers a capture, waits five seconds, then cancels
- **THEN** the video has kept playing for those five seconds and was not paused

### Requirement: User selects a rectangle by dragging
The user SHALL select a region by pressing the left mouse button and dragging. While dragging, the selected rectangle SHALL be shown undimmed with a visible border and its size in pixels. Releasing the button SHALL complete the selection.

#### Scenario: Drag and release
- **WHEN** the user drags from one corner of a paragraph to the opposite corner and releases
- **THEN** the overlay shows the rectangle undimmed while dragging
- **AND** releasing the button sends exactly that rectangle to recognition

#### Scenario: Accidental click or tiny drag
- **WHEN** the user clicks without dragging, or drags less than 4 pixels in either direction
- **THEN** no recognition happens and the overlay stays open for another attempt

### Requirement: Capture can always be cancelled
Pressing `Esc` or clicking the right mouse button SHALL close the overlay without recognizing anything and without changing the clipboard. If the user makes no selection within 60 seconds, the overlay SHALL close by itself the same way.

#### Scenario: Cancel with Esc
- **WHEN** the overlay is open and the user presses `Esc`
- **THEN** the overlay closes, no recognition runs and the clipboard is unchanged

#### Scenario: Cancel with right-click
- **WHEN** the overlay is open and the user right-clicks
- **THEN** the overlay closes, no recognition runs and the clipboard is unchanged

#### Scenario: Abandoned overlay closes itself
- **WHEN** the overlay has been open for 60 seconds without a selection
- **THEN** the overlay closes as if cancelled

### Requirement: Focus returns to the previous window
After the overlay closes for any reason, keyboard focus SHALL return to the window that had focus before the capture started.

#### Scenario: Continue typing after capture
- **WHEN** the user is typing in a text editor, triggers a capture, completes a selection, and then keeps typing without clicking
- **THEN** the keystrokes go to the text editor

### Requirement: Captured pixels match the selection on any monitor and scale
The captured image SHALL contain exactly the screen pixels under the selected rectangle, at the monitor's native resolution, whatever the display scale (including fractional scales such as 125%) and whichever monitor the selection is on. A selection SHALL stay within the monitor where the drag started. Dragging past that monitor's edge SHALL clamp the selection to the edge.

#### Scenario: HiDPI monitor at 200% scale
- **WHEN** the user selects a 100 × 50 logical-pixel area on a monitor at 200% scale
- **THEN** the captured image is 200 × 100 pixels and shows the selected content at full sharpness

#### Scenario: Selection on a secondary monitor
- **WHEN** the user selects text on the second of two monitors
- **THEN** the captured image shows that text, not content from the first monitor

#### Scenario: Dragging past the monitor edge
- **WHEN** the user starts a drag on the left monitor and moves the pointer onto the right monitor
- **THEN** the selection stops at the left monitor's right edge

### Requirement: Capture works in X11 and Wayland sessions
Region capture SHALL work in both Ubuntu on Xorg and Ubuntu on Wayland sessions, and the captured image SHALL include the content of native Wayland apps. If the desktop asks for permission to take screenshots, the user SHALL be asked no more than once. If permission is refused, the user SHALL be told that capture is unavailable and how to allow it.

#### Scenario: Native Wayland app content is captured
- **WHEN** in a Wayland session the user selects text shown in a native Wayland app
- **THEN** the captured image shows that text (not a black or empty area)

#### Scenario: Screenshot permission refused
- **WHEN** the desktop asks whether Text Capture may take screenshots and the user refuses
- **THEN** no overlay is shown and the user gets a notification explaining that capture needs screenshot permission and how to grant it

### Requirement: Screenshots are not kept on disk
Screen images taken for a capture SHALL NOT remain on disk after the capture ends, and SHALL NOT be added to the user's Pictures folder or screenshot history.

#### Scenario: No image files left behind
- **WHEN** the user completes or cancels a capture
- **THEN** no new image file from that capture exists in the Pictures folder, the temporary directory or the app's data directories
