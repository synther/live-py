## devices

A device provides controls, addressing by a number.

1. "Launchpad Pro"

   Stock device. Controls are well known.

2. "LaunchControl"
3. "Keyboard1"
4. "Synth1"
5. "DIY1". Custom MIDI knobs

   - control 1 - CC30
   - control 2 - CC31
   - control 3 - CC32

## layout/controls mapping to devices

TODO reactive programming?
TODO xaml like, one-way, two-way binding
instead of events

- global objects
  - tempo
    - bpm

- List `clips-to-copy`
- Sequencer `sequencer`
- TODO MIDI tracks routing? Monitoring?
- Page `page-tempo-buttons`
  - Button `tempo_minus`
    - Device: "Launchpad Pro"
    - Position: 7
    - Event `pressed`:
      - `global.tempo = global.tempo + 5`
    - OR bind:
      - `global.tempo <- global.tempo + pressed_int * 5`
  - Button `tempo_plus`
    - Device "Launchpad Pro"
    - Position: 8
- Page `page-shuffle-buttons`
  - Button `shuffle_minus`
    - Device: "Launchpad Pro"
    - Position: 7 (`tempo_minus` button reused)
    - Event `pressed`:
      - `global.shuffle = global.shuffle - 5`
    - OR bind:
      - `global.shuffle <- global.shuffle - pressed_int * 5`
  - Button `shuffle_plus`
    - Device "Launchpad Pro"
    - Position: 8 (`tempo_plus` button reused)
    - Event `pressed`:
      - `global.shuffle = global.shuffle + 5`
    - OR bind:
      - `global.shuffle <- global.shuffle + pressed_int * dial_inc`
- Button `shuffle`
  - Device "Launchpad Pro"
  - Position: 9
  - Bind:
    - `page-shuffle-buttons.visible <- pressed_bool`
- Button `copy-clip`
  - Device "Launchpad Pro"
  - Position: 8
  - Event `pressed`:
    - set `clips-to-copy` -> `[]`
    - `clips` -> select mode active
  - Event `released`:
    - `clips.copy(from: clips-to-copy[0], to: clips-to-copy[1], allow overwrite)`
    - `clips` -> select mode deactivate
- Grid `clips_grid`
  - Device "Launchpad Pro"
  - Position: 2 (bottom left) -> 13 (top right)
  - Bind:
    - `self.selected = self.selected + select-next-track-launchpad.pressed_int`
    - `self.selected = self.selected + select-next-track-launchcontrol.pressed_int`
  - Event `pressed`:
    - `clips.trigger {{ pressed_x }}, {{ pressed_y }}`
- LCD `selected-track`:
  - Bind:
    - `self.text = clips_grid.selected`
- Button `select-next-track-launchpad`
  - Device "Launchpad Pro"
  - Position: 2
- Button `select-next-track-launchcontrol`
  - Device "Launchpad Pro"
  - Position: 2
- Clips `clips` (TODO extend Clips from Grid so no need for 2 components)
  - Device "Launchpad Pro"
  - Position: `clips_grid` (also possible to have "virtual" Clips, without grid on launchpad. Just clips able to record and play, maybe with other controls)
  - Event `clip-launched`:
    - `sequencer` play `{{ clip_name }}`
    - TODO quantization, feeback from `sequencer` when to lid grid green.
  - TODO record clips?
  - Event `clip-selected`:
    - add `{{ clip_selected }} -> `clips-to-copy`
- Page `master_fx_page`:
  - Button `flanger_on`
    - Device: "Launchpad Pro"
    - Position: 7 (reusing tempo button)
    - Event `pressed`:
      - Send CC: "Synth1", CC45 = 100
- Button `Master effects`
  - Device "LaunchControl"
  - Position: 1
  - Bind:
    - `master_fx_page.visible = pressed_bool`
- TODO Shift just for a single button?

## route

control `tempo_minus` -> decrease tempo
control `tempo_plus` -> increase tempo
