# Feature contract

Preserve these behaviors unless the user explicitly removes one:

## Window and input

- Transparent, frameless Windows tool window with optional always-on-top.
- Alpha-aware character rendering, left-drag repositioning, wheel scaling, and remembered size/position.
- Click cycle: jump, squash/rebound, and horizontal shake.
- Drag release physics with velocity, gravity, bounce, and screen bounds.

## Life and movement

- Random idle GIF/scene changes and unsolicited but rate-limited local dialogue.
- Free walking with direction-aware mirroring.
- Full-desktop destination picker with left-click selection and Esc/right-click cancellation.
- Reusable picker for a persistent leash anchor; show the tether and constrain activity radius.
- Reading/stationary mode and office mode.

## Office and chat

- Office character image containing a keyboard and mouse.
- Global key hook used only for local animation; blue key-name capsule, soft hand-side motion, mouse reaction, blinking, stretch, and visible star feedback.
- Opaque cream/coral/blue speech bubble that avoids the character, stays visible long enough, and opens chat when clicked.
- Always-on-top nearby mini chat showing only the most recent two rounds.

## AI and settings

- Useful offline dialogue at all times.
- Optional OpenAI-compatible text chat and optional vision understanding.
- Manual and opt-in periodic screen checks.
- DPAPI-protected local key storage, system tray, autostart option, and graceful shutdown.

## Acceptance

- Asset processor produces transparent frames and a valid manifest.
- Unit tests cover facing, physics, destination/leash selection, settings persistence, office feedback, chat history, and privacy boundaries.
- Smoke test creates and closes the controller without leaving a process behind.
- Packaged EXE cold-starts on Windows without a development environment.
