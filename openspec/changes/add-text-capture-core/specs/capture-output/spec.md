# Spec Delta

## Purpose

Delivers recognized text to the user: places it on the clipboard so it can be pasted anywhere, and gives brief, non-intrusive feedback about the result.

## ADDED Requirements

### Requirement: Recognized text is copied to the clipboard
When recognition produces non-empty text, the system SHALL place it on the standard clipboard (the one used by `Ctrl+V`) as plain UTF-8 text. It SHALL be pasteable into any app after the overlay closes, in both X11 and Wayland sessions, for as long as the app is running and nothing else replaces the clipboard.

#### Scenario: Paste into another app
- **WHEN** the user captures the text "Invoice 2026-104" and then presses `Ctrl+V` in a text editor
- **THEN** "Invoice 2026-104" is pasted

#### Scenario: Paste into a native Wayland app
- **WHEN** in a Wayland session the user captures text and pastes it into a native Wayland app
- **THEN** the captured text is pasted

#### Scenario: Non-Latin text
- **WHEN** the recognized text contains non-ASCII characters such as "naïve café"
- **THEN** the pasted text contains exactly those characters

### Requirement: Empty results leave the clipboard unchanged
If recognition finds no text, the system SHALL NOT change the clipboard, and SHALL tell the user that no text was found.

#### Scenario: Region contains no text
- **WHEN** the clipboard holds "previous" and the user captures a region containing only an image with no text
- **THEN** the clipboard still holds "previous"
- **AND** the user is told "No text found"

### Requirement: Result notification is shown without taking focus
When "Show notifications" is on (the default), each successful capture SHALL show a desktop notification with up to the first 100 characters of the text. It SHALL disappear by itself and SHALL NOT take focus. When the setting is off, successful captures SHALL show no notification. Errors SHALL always be reported.

#### Scenario: Notification on success
- **WHEN** notifications are on and a capture succeeds
- **THEN** a notification shows the start of the recognized text and disappears without user action

#### Scenario: Notifications turned off
- **WHEN** notifications are off and a capture succeeds
- **THEN** no notification is shown

#### Scenario: Notification does not interrupt typing
- **WHEN** the user is typing in another app at the moment a result notification appears
- **THEN** every keystroke continues to go to that app

### Requirement: Clipboard failures are reported
If the text cannot be placed on the clipboard, the system SHALL tell the user that copying failed, whatever the notification setting is.

#### Scenario: Clipboard unavailable
- **WHEN** recognition succeeds but the clipboard cannot be set
- **THEN** the user gets a notification that the text could not be copied
