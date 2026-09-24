# R1 cast animation

Date: 2026-09-23

Tito and Paco replace the record circle with a living pixel character. The same layers draw the 512 icon and the 128 screen bust.

## States

| State | Enters | Leaves |
| --- | --- | --- |
| idle | boot, 4 s after the reply finishes typing, error | PTT hold |
| listen | `longPressStart` | `sttEnded` |
| think | transcript sent | reply or error |
| speak | reply text | typing done, then 4 s |

Shared motion, 12 fps, canvas smoothing off:

- Breath lifts the head 1 px for half of a 3.8 s cycle.
- Blink every 2–6 s, closed for 2 frames, sometimes twice.
- Mouth follows the character being typed. `A/А` open, `O/О/U/У` round, `E/И/I` wide, `M/М/B/Б/P/П` closed lips, other consonants half, space shut.
- Type rate is one constant: 14 Cyrillic characters per second, 16 Latin. Comma adds 250 ms. Period, `!`, and `?` add 450 ms.

## Screen (240x282)

- Name row stays.
- `#stage` is a 128×128 canvas (64×64 grid, scale 2), centered.
- `#dialog` sits on the chest, full width, 3 lines at 13 px, pixel border `#FE5000`.
- Listen shows the transcript in gray once `sttEnded` arrives. Think shows three dots. Speak types the reply. The wheel scrolls the typed lines.
- Peek open shrinks the canvas to 64×64 in the top-right corner and hides the dialog.
- No `#rec`. No CSS animation on the stage. No WebGL.

## Acting

Tito, charro majordomo: black vest, orange embroidery, moño charro, mustache, dark glasses, calendar with a papel picado strip.

- Idle: fixes the bow, glances at the calendar.
- Listen: leans in 1 px, brow up, slow nod, lens glint.
- Think: glasses slide to the nose tip, calendar pages flip.
- Speak: free hand ticks on comma and period.
- `action: "task"`: one day on the calendar lights for 2 s.

Paco, notes clerk: straw work hat (not a festival sombrero), red bandana, mustache, round glasses, guayabera, pencil, tooled notebook.

- Idle: spins the pencil behind the ear.
- Listen: writes. Notebook lines appear one by one.
- Think: bites the pencil, hat slides back, three dots above the hat.
- Speak: holds the notebook, marks a tick on each period.
- `action: "saved"`: a check appears in the notebook for 2 s.

Culture is costume and tools. Face proportions stay ordinary. Palette: `#111` ground, skin unchanged, `#FE5000` plus teal `#1A9B96` and pink `#E25B8A` only in trim.

## Build

`rabbit/cast/build.py` is the only drawing source.

- Emits `cast.js` (`window.CAST`) into both creations.
- Renders idle portraits to `tito.png`, `icon.png`, and `paco.png` at 512×512.
- Copies `rabbit/cast/stage.js` so both creations carry the same bytes.
- Mirrors `rabbit/assistant` and `rabbit/paco` into `services/assistant/static/`.

`stage.js` reads `CAST[who]`, composites layers, and owns the typewriter.

## API

- `POST /api/text` adds `"action": "task"` when the turn used `todoist_add` or `plan_apply`. Otherwise `"action": ""`.
- `POST /api/paco/text` adds `"action": "saved"` only when a write returned `wrote`. `push_failed` and `token_expired` leave it empty.

## Later agents

Mexican given name, one trade tool, same palette and `rabbit/cast/` pipeline. No caricature. Recorded in `.cursor/rules/toy-lair-devices.mdc`.

## Tests

- Both indexes contain `canvas#stage` and `#dialog`, and do not contain `#rec`, `getUserMedia`, or `webgl`.
- Both still load `CreationVoiceHandler` and `wantsR1Response`.
- The two `stage.js` files are byte-identical. Static mirrors match `rabbit/`.
- Icons stay 512×512 PNG.
- Action fields behave as in API above.

Device check, not automated: type rate against the R1 speaker, and that 12 fps stays even on the Helio P35.
