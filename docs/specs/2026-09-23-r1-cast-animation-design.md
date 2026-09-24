# R1 cast animation

Date: 2026-09-23

Tito and Paco replace the record circle with a living pixel character. The same layers draw the 512 icon and the 192 screen bust. The grid is 96, drawn at that size. Nothing is scaled up from 64.

## States

| State | Enters | Leaves |
| --- | --- | --- |
| idle | boot, 4 s after the reply finishes typing, error | PTT hold |
| listen | `longPressStart` | `sttEnded` |
| think | transcript sent | reply or error |
| speak | reply text | typing done, then 4 s |

Shared motion, 12 fps, canvas smoothing off:

- Breath lifts every `head` layer 1 px for half of a 3.8 s cycle. `cast.attach` says which layers ride with the head. The body stays put.
- Blink every 3 s in three frames (half, shut, half). Every fourth blink is a double. Blink swaps only the eye layer. Glasses stay on.
- Think, listen, and speak each spend two frames arriving, then hold the pose.
- Each layer is baked once into an offscreen canvas and composited with `drawImage`.
- Mouth follows the character being typed. `A/А` open, `O/О/U/У` round, `E/И/I` wide, `M/М/B/Б/P/П` closed lips, other consonants half, space shut. A change of shape shows `mouth_mid` for one frame. Vowels lift `mustache_open`.
- Type rate is one constant: 14 Cyrillic characters per second, 16 Latin. Comma adds 250 ms. Period, `!`, and `?` add 450 ms.

## Screen (240x282)

- Name row stays.
- `#stage` is a 192×192 canvas (96×96 grid, scale 2), centered.
- The wheel scrolls one dialog line (16 px). Autoscroll stays pinned to the bottom until the wheel moves. Idle keeps the reply on screen until the next PTT.
- Peek hides the stage. The task list uses the full height. Status and the event log stay one line.
- `#dialog` sits on the chest, full width, 3 lines at 13 px, pixel border `#FE5000`.
- Listen shows the transcript in gray once `sttEnded` arrives. Think shows three dots. Speak types the reply. The wheel scrolls the typed lines.
- No `#rec`. No CSS animation on the stage. No WebGL.

## Acting

Tito, charro majordomo: black vest, orange embroidery, moño charro, mustache, dark glasses, calendar with a papel picado strip.

- Idle: fixes the bow, glances at the calendar.
- Listen: leans in 1 px, brow up, slow nod, lens glint.
- Think: `glasses_low` sits under the eyes, `eyes_up` looks over the frame, calendar plays `cal_0`, `cal_1`, `cal_2`.
- Speak: free hand ticks on comma and period.
- `action: "task"`: one day on the calendar lights for 2 s.

Paco, notes clerk: straw work hat (not a festival sombrero), red bandana, thick drooping mustache, no glasses, guayabera, pencil, tooled notebook.

- Idle: spins the pencil behind the ear.
- Listen: writes. Notebook lines appear one by one.
- Think: `hat_back` opens the forehead, `pencil_bite` at the mouth, `brows_knit`, `eyes_up`, three dots to the right of the head.
- Speak: holds the notebook, marks a tick on each period.
- `action: "saved"`: a check appears in the notebook for 2 s.

Culture is costume and tools. Face proportions stay ordinary. Palette: `#111` ground, skin unchanged, `#FE5000` plus teal `#1A9B96` and pink `#E25B8A` only in trim.

## Build

`rabbit/cast/build.py` is the only drawing source.

- Emits `cast.js` (`window.CAST`) into both creations, including `order`, `attach`, and `idle`.
- Face layers are separate: `eyes_open`, `eyes_half`, `eyes_shut`, `eyes_up`, `eyes_side_l`, `eyes_side_r`, three brow poses, two mustache poses, seven mouths. Tito also has `glasses` and `glasses_low`. Paco has no glasses. His mustache is a thick drooping horseshoe, and `fringe` shows only with `hat_back`. Tito's hair is a side part, not a cap.
- Tito props: `bow`, `hand_bow`, `hand_tick`, `cal_0`, `cal_1`, `cal_2`, `cal_lit`, `glint`.
- Paco props: `hat_crown`, `hat_band`, `hat_brim`, `hat_back`, `pencil_ear`, `pencil_touch`, `pencil_bite`, `pencil_write_0` through `pencil_write_2`, notebook lines, `mark_0` through `mark_2`.
- Renders idle portraits to `tito.png`, `icon.png`, and `paco.png` at 512×512.
- Copies `rabbit/cast/stage.js` so both creations carry the same bytes.
- Mirrors `rabbit/assistant` and `rabbit/paco` into `services/assistant/static/`.
- `rabbit/cast/preview.html` is a local frame sheet. `?freeze=<ms>` holds the clock. It is not copied to the dyno.

`stage.js` reads `CAST[who]`, composites layers, and owns the typewriter. `createStage(canvas, dialog, who, { clock })` takes an optional clock. The creations omit it and use `performance.now`.

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
