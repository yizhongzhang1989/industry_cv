# Button battery regression data

Small real-camera samples from the 2026-11-26 LR41 case. All images use 1920×1080 pixels;
the black board is the labeled picking region. Use the ROI in
`examples/button_battery/configs/vision.json` (paths here are relative to the repo root).

| File | Expected count | Condition |
|---|---:|---|
| button_cells_100.jpg | 100 | Initial lighting, touching pairs |
| button_cells_edge_marking.jpg | 100 | Inscription damages the thresholded rim |
| button_cells_98.jpg | 98 | Two bottom-right parts removed |
| button_cells_side_light.jpg | 100 | Side illumination and shadow, parts replaced |
| button_cells_shadow_flicker.jpg | 100 | Later side-light frame with reflection changes |

`button_cells_100.json` contains algorithm-assisted, visually reviewed approximate centers.
These are development regression labels, not independent physical metrology. Initial-image
association tolerance is 3 px; side-light images allow 12 px to account for camera/part shifts.
The latter tests correspondence and count, not 12 px localization accuracy.

Evidence and limitations: `knowledge/cases/2026-11-26-button-battery/README.md`.
Keep full videos and customer production data in the parent site project. Add only minimal
necessary samples here, record their provenance and conditions, and avoid growing binary
history with repetitive frames. This dataset is development material and is not in the wheel.
