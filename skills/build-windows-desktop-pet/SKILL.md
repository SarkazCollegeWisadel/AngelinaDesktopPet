---
name: build-windows-desktop-pet
description: Build, customize, test, and package a transparent PySide6 Windows desktop pet from user-provided PNG/GIF character art, with dragging, directional movement, physics, idle animation, speech bubbles, nearby chat, office keyboard reactions, selectable destinations and leash anchors, optional OpenAI-compatible text/vision AI, and privacy-safe local settings. Use when Codex is asked to create, reproduce, reskin, extend, or package an interactive Windows desktop pet from character images.
---

# Build a Windows desktop pet

Create a working, tested Windows desktop pet from the public AngelinaDesktopPet template while keeping user secrets out of source control.

## Start with exactly two inputs

In the first reply, ask for these two items before modifying files:

1. **Required images:** Ask for the character image paths or attachments. Request at least one transparent idle PNG; for the complete experience request matching PNG/GIF scene pairs plus an office PNG showing the character with a desk, keyboard, and mouse. Ask whether green-screen GIF backgrounds may be removed.
2. **Experimental API Key:** Ask for the provider, Base URL, model, and a short-lived test key, or let the user explicitly choose offline-only mode. State that the key will only be used for a connection test and runtime configuration, never written into source files, logs, tests, commits, or the Skill.

If the user already supplied either item in the current conversation, acknowledge it instead of asking them to repeat it. Do not expose a full key in responses or tool output. Do not start implementation until the user answers both items, including an explicit “no key/offline” answer.

## Build workflow

1. Inspect the image set visually and map scene names before editing. Read [references/assets-and-persona.md](references/assets-and-persona.md).
2. Create a new project with `scripts/scaffold_project.py`. Prefer `--source` when a local AngelinaDesktopPet checkout is available; otherwise let the script fetch the public template. Never overwrite a non-empty directory.
3. Use `--clean-assets` for a new character. Copy the approved images into `assets/source/PNG`, `assets/source/GIF`, and `assets/source/generated/office.png`. Keep PNG/GIF stems identical for matching scenes.
4. Update `angelina_pet/constants.py`, visible labels, tray text, package identifiers, and `angelina_pet/persona.py` for the requested character. Set source-facing direction for every locomotion scene so moving and dragging always mirror correctly.
5. Preserve the behavior and privacy requirements in [references/feature-contract.md](references/feature-contract.md). Adapt the implementation instead of deleting a feature merely because an asset is missing.
6. Configure and test optional AI according to [references/api-and-privacy.md](references/api-and-privacy.md). Put the test key only into the running app's local encrypted settings. Prefer a mocked API test in the committed test suite.
7. Run the asset pipeline, unit tests, smoke test, and package build. Fix failures before handoff.
8. Report the EXE/ZIP paths, tested features, limitations, and exact test results. Never echo the key. Publish or change external repositories only when the user explicitly requests it.

## Scaffold commands

From this Skill directory:

```powershell
python scripts/scaffold_project.py --output C:\work\MyDesktopPet
```

From an existing local template checkout:

```powershell
python scripts/scaffold_project.py --source C:\path\AngelinaDesktopPet --output C:\work\MyDesktopPet --clean-assets
```

The script copies only project inputs and excludes `.git`, virtual environments, build output, settings, secrets, and this Skill itself.

## Required validation

Run in the generated project:

```powershell
python tools\prepare_assets.py
python -m unittest discover -s tests -v
python tools\smoke_controller.py
.\build.ps1
```

Also launch the packaged EXE briefly and confirm transparent rendering, drag/throw, wheel scaling, right-click destination and leash-anchor selection, office key feedback, chat topmost behavior, and clean shutdown.
