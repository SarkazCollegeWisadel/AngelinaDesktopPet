# Assets and persona

## Image intake

Ask for paths or attachments and inspect every source image before editing it.

Minimum usable set:

- One transparent PNG for idle display.
- One office PNG containing the character, desk, keyboard, and mouse. If absent, create a clearly disclosed fallback and keep office reactions functional.

Recommended full set:

- Several transparent PNG poses.
- Matching animated GIFs using the same filename stems.
- At least one left- or right-facing locomotion scene.
- Optional UI references for speech bubbles and chat styling.

Use this source layout:

```text
assets/source/PNG/<scene>.png
assets/source/GIF/<scene>.gif
assets/source/generated/office.png
```

Run `tools/prepare_assets.py` after changing sources. It removes near-`#00ff00` GIF chroma backgrounds, crops transparent bounds, emits animation frames, creates the manifest, and generates the icon. Confirm transparent corners and visually inspect fine hair, props, and green costume details.

## Scene mapping

Update `angelina_pet/constants.py` rather than forcing another character into Angelina-specific names:

- `IDLE_SCENE`: neutral resting pose.
- `READING_SCENE`: stationary reading or calm pose.
- `OFFICE_SCENE`: generated office image.
- `ALL_CHARACTER_SCENES`: every selectable pose.
- `SCENE_SOURCE_FACING`: source direction for every locomotion scene (`-1` left, `1` right).

Keep matching PNG/GIF stems identical. Ensure walking, destination travel, dragging, and throwing all use `SCENE_SOURCE_FACING` for mirroring.

## Persona

Ask for the desktop pet's name and desired relationship after the two mandatory opening inputs if it cannot be inferred. When the character comes from an existing work, verify characterization from primary or official sources when internet access is available. Summarize traits; do not copy long copyrighted dialogue.

Keep dialogue brief, warm, situational, and varied. Define explicit anti-OOC boundaries. Always keep useful offline lines so the pet remains lively without an API.
