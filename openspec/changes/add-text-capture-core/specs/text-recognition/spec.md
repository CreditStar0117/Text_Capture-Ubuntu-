# Spec Delta

## Purpose

Turns the image of a selected screen region into accurate plain text, in the language the user chooses, entirely on the local machine and without slowing down the desktop.

## ADDED Requirements

### Requirement: Selected region is recognized as text in reading order
The system SHALL recognize the text in the captured image and return it as plain text in reading order: top to bottom, and left to right for horizontal scripts. It SHALL handle typical on-screen UI and document text, including small fonts at 100% display scale.

#### Scenario: Standard UI text
- **WHEN** the user captures a region showing one line of 11 pt sans-serif text at 100% display scale
- **THEN** the recognized text matches the displayed characters

#### Scenario: Multi-line paragraph
- **WHEN** the user captures a region showing a three-line paragraph
- **THEN** the recognized text contains the three lines in top-to-bottom order

#### Scenario: Reference accuracy
- **WHEN** the reference screen-text images in the project's test data are recognized in English
- **THEN** the character accuracy across the set is at least 98%

### Requirement: User chooses the OCR language
The user SHALL be able to choose the recognition language from the language packs installed on the system. The default SHALL be English. Only installed languages SHALL be offered, and the choice SHALL persist across restarts.

#### Scenario: Switching language
- **WHEN** the German language pack is installed, the user selects German and captures the word "Größe"
- **THEN** the recognized text is "Größe"

#### Scenario: Only installed languages are listed
- **WHEN** only the English and French language packs are installed
- **THEN** the language choice lists exactly English and French

#### Scenario: Selected language is removed
- **WHEN** the selected language pack is uninstalled and the user starts a capture
- **THEN** recognition falls back to English and the user is told once that the selected language is no longer available

### Requirement: Missing OCR engine is reported clearly
If the recognition engine or its English data is not installed, the app SHALL still start, and starting a capture SHALL tell the user which Ubuntu package to install instead of failing silently.

#### Scenario: Engine not installed
- **WHEN** the OCR engine package is not installed and the user presses the capture shortcut
- **THEN** the user gets a notification naming the package to install
- **AND** the app keeps running

### Requirement: Line breaks follow the user's setting
With "Keep line breaks" on (the default), each recognized line SHALL end with a newline. With it off, lines in the same paragraph SHALL be joined with single spaces. In both cases, leading and trailing whitespace SHALL be trimmed and repeated blank lines collapsed into one.

#### Scenario: Keep line breaks on
- **WHEN** "Keep line breaks" is on and the user captures two lines "Hello" and "world"
- **THEN** the result is `Hello\nworld`

#### Scenario: Keep line breaks off
- **WHEN** "Keep line breaks" is off and the user captures two lines "Hello" and "world"
- **THEN** the result is `Hello world`

### Requirement: Recognition never blocks the desktop
Recognition SHALL run without freezing the app or other apps, at reduced CPU priority. While it runs, the overlay SHALL show a "Recognizing…" indicator, and `Esc` SHALL cancel it. A region up to 1000 × 300 pixels SHALL finish within 2 seconds. Recognition taking over 15 seconds SHALL be abandoned and reported.

#### Scenario: Typical region is fast
- **WHEN** the user captures a 1000 × 300 pixel region of text on Ubuntu 24.04 desktop hardware
- **THEN** the result is ready within 2 seconds

#### Scenario: Cancel during recognition
- **WHEN** recognition is in progress and the user presses `Esc`
- **THEN** recognition stops, the overlay closes and the clipboard is unchanged

#### Scenario: Recognition takes too long
- **WHEN** recognition has run for 15 seconds without finishing
- **THEN** it is stopped, the overlay closes, the clipboard is unchanged and the user is told recognition timed out

### Requirement: Recognition is local only
Captured images and recognized text SHALL be processed only on the local machine and SHALL NOT be sent over the network.

#### Scenario: Offline use
- **WHEN** the computer has no network connection and the user captures text
- **THEN** recognition works as normal
