# Puntueitor – Agent Guide

## Running the App

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the Textual TUI app
python -m puntueitor.gui.app
```

Or directly:
```bash
python -c "from puntueitor.gui.app import PuntueitorApp; app = PuntueitorApp(); app.run()"
```

## Dependencies

Install from `requirements.txt`:
```bash
pip install -r requirements.txt
```

Required packages: `igdbpy`, `howlongtobeatpy`, `textual`, `rich`, `panda3d`

## 3D frontend (gui3d/)

```bash
python -m puntueitor.gui3d.app
```

A Panda3D frontend alongside the TUI, not a replacement. Lives in
`puntueitor/gui3d/`, fully separate from `gui/`; neither `core/` nor `gui/`
were touched to build it. Read-only: it never runs the pipeline or queries
IGDB, and the only network traffic is fetching missing cover JPGs.
Keyboard: arrows navigate, Enter confirms, Esc/Start opens the options
submenu, Q quits. Gamepad: d-pad + face_a/face_b + start, same gestures, via
`gamepad_input.py` (hot-plug aware).

Data: `real_data.py` loads the **whole** library through
`LibraryRepository.load()` — the same loader the TUI uses. Going through the
repository is what makes duration and the Steam/SteamDB scores available at
all (they are not in the IGDB cache; they live in the extras table and only
the repository joins them in), and it means the "Golden Rule" no longer has
to be restated here. Falls back to `sample_data.py`'s synthetic entries if
the library is empty or missing; those are real `Game` objects, some with
deliberate gaps, so the ficha can be exercised without a database.

There used to be a 60-game cap left over from prototype days. It silently
dropped 95% of a 1273-game library while the log cheerfully reported all
1273 loaded. Measured before removing it: 1266 boxes cost 1.2 s and ~270 MB
to build, and navigation runs at 0.5 ms per move, so nothing justified the
cap — and box virtualisation/recycling is not needed either.

**Covers are loaded lazily, and this dominates startup time.** Turning a
cached JPG into a texture costs ~3.4 ms; doing that for all 1266 games at
startup cost 4.3 s of black window to display nine boxes. The symptom was
backwards from what you would guess: startup got *slower* as the cover cache
got *more complete*, because a missing cover was a cheap 2x2 placeholder and
a present one was a JPEG decode. `build_real_entries` now loads no textures
at all — every entry starts on a shared per-store placeholder — and the same
proximity window that drives downloads also drives texture creation. Startup
went 5.9 s -> 1.5 s, live textures 1266 -> 21.

Three pieces make that work, and they are easy to accidentally undo:
- `make_placeholder_texture` caches by colour. The palette has five entries,
  so without the cache a 1266-game library allocated 1266 GPU textures to
  paint five flat colours.
- `CoverLoader.poll()` returns **paths, not textures**. If it returned
  textures, the backfill downloading the whole library would recreate all
  1266 textures as they landed, quietly restoring the cost that was just
  removed. `App._on_cover_ready` only builds the texture if the box is near
  the selection; otherwise the file simply sits on disk until approached.
- `CoverLoader._download` checks the disk before downloading, so a file
  already fetched (by an earlier session, or by the TUI, which shares the
  directory) skips the network entirely.

Measured after the change: 21 covers live at startup, one more per
navigation step, 277 MB after traversing 204 positions.

The remaining startup cost is `Carousel` building all 1266 boxes eagerly
(~1.16 s, 7684 GeomNodes for the nine that are visible). Building them on
demand as they enter `VISIBLE_RADIUS` would amortise it to ~0.9 ms per
navigation step; it needs `set_texture` to buffer textures for boxes that do
not exist yet, since `COVER_PRELOAD_RADIUS` (10) reaches further than
`VISIBLE_RADIUS` (4).

The download side is in two tiers, and both matter:
- `App._request_nearby_covers` asks for everything within
  `COVER_PRELOAD_RADIUS` of the selection, on every move. This is what makes
  the box you are looking at get its art first.
- `App._backfill_covers` then works through the rest of the library
  whenever fewer than `COVER_BACKFILL_INFLIGHT` downloads are outstanding,
  so covers do eventually all arrive rather than only the ones you happen
  to visit. The cap is the whole point: dumping 1200 requests into the pool
  at once would put a freshly-navigated-to cover behind all of them.

**Two independent bugs produced "Texture exists but cannot be read" /
"carátula corrupta o ilegible" for a handful of covers per session**, and
fixing only one of them looked like a fix but wasn't:

1. `download_cover` used to write straight to the final `{igdb_id}.jpg`
   path via `urlretrieve`. While a download was in flight, the file was on
   disk and `path.exists()` was already True — but the bytes were only
   partial. `App._request_nearby_covers` and `_on_cover_ready` read
   straight from disk on the main thread (bypassing `CoverLoader` entirely
   when the file looks present), so a fast-enough navigation could catch a
   cover mid-download and get a truncated JPEG. Fixed by downloading to a
   `{igdb_id}.jpg.<thread-id>.tmp` sibling and `os.replace`-ing it into
   place: `path.exists()` is now False until the file is fully written,
   with no partial-visibility window, because rename is atomic at the
   filesystem level.

2. Fixing (1) alone did not fix the symptom, and the reason is worth
   knowing before touching this file again: `_load_texture` used
   `TexturePool.load_texture(filename)`. **Verified empirically**
   (`Texture` object identity compared before/after replacing the file's
   content at the same path): TexturePool caches by filename string and
   does not re-read from disk on a second call for the same path, even
   after the underlying content changes completely. Since every `igdb_id`
   always maps to the same filename for the life of the process (by
   design, to share the cache with the TUI), a single bad read — however it
   happened — poisoned that cover for the rest of the session; deleting the
   file on failure (to allow a retry) did nothing, because the problem was
   never on disk, it was in Panda3D's pool. Switched to a fresh `Texture()`
   + `.read(Filename)` per call, which always re-reads from disk and has no
   such cache.

Confirmed the combined fix under stress: a harness that downloads via a
throttled `urlretrieve` stand-in while the main thread polls
`load_cover_texture(allow_download=False)` in a tight loop, counting only
reads where the file was already present at the moment of the call (get
this check wrong — checking existence *after* the call instead of before —
and the harness reports false failures purely from its own TOCTOU gap, as
one early version of it did). 800 downloads, 47 caught mid-flight, 0 real
failures.

`CoverLoader.request` ignores keys already asked for (consecutive windows
overlap almost entirely) and keeps an `inflight` count, decremented in a
`finally` — a failed download that leaked the count would stall the backfill
permanently. Downloads run on background threads and live-swap the texture
in when ready (`Carousel.set_texture`, polled each frame in `App._update`);
startup never blocks, and a game whose download fails just keeps its
per-store colour placeholder.

**The d-pad is not buttons.** On Xbox-style pads the kernel exposes it as
the hat axis ABS_HAT0X/ABS_HAT0Y, and Panda3D does not map those to any
named `Axis` — they show up as `Axis.none`. Meanwhile, because the device
declares itself a gamepad, Panda3D *does* advertise `dpad_left` etc. as
existing buttons: `find_button(GamepadButton.dpad_left()).known` is True.
They simply never fire. That combination is a trap — everything looks
supported and nothing happens — and it is why the d-pad never worked, in
either the event-based or the polled version. Confirmed against the kernel:
`/proc/bus/input/devices` reports `B: ABS=3003f` for this pad, whose bits 16
and 17 are HAT0X and HAT0Y.

`GamepadInput.direction()` therefore checks three sources and ORs them: the
unmapped hat axis (`_find_hat_axis` takes the first `Axis.none` axis, since
evdev orders HAT0X before HAT0Y), the held state rebuilt from d-pad
press/release events, and the button state. Each works on a different class
of controller and none works everywhere. `_find_hat_axis` is a heuristic; if
some pad ever scrolls the carousel when pressing *up*, its two hat axes are
in the opposite order.

Navigation repeats while a direction is *held*, and this is deliberately
built on polled state rather than key events. Panda3D does emit
`arrow_left-repeat`, but its cadence is the desktop's key-repeat setting,
which has nothing to do with what a carousel wants; and a gamepad d-pad has
no repeat event at all. So `App._held_direction` reads keyboard held-flags
(`arrow_left` / `arrow_left-up`) and `GamepadInput.direction()`, which polls
the d-pad buttons *and* the left stick axis and returns -1/0/+1. The stick
used to be edge-detected inside `GamepadInput`, which is exactly why holding
it did nothing until you re-centred it.

`App._update_navigation` owns the timing: fire immediately, wait
`NAV_REPEAT_DELAY`, then repeat on an interval that accelerates from
`NAV_REPEAT_INTERVAL` to `NAV_REPEAT_MIN_INTERVAL` — measured at 204
positions in 10 s held down, which is what makes a 1266-game library
traversable. `NAV_MAX_STEPS_PER_FRAME` caps a long frame from teleporting
the selection, and the leftover debt is dropped rather than carried, or the
carousel keeps coasting after release.

The background is deliberately *not* updated on selection change — only
after `BACKGROUND_SETTLE_DELAY` of no movement (`App._update_background`).
Regenerating the blur costs ~9 ms, so at full scroll speed it would hitch
every frame; measured over a 10 s held scroll, deferring it cut 204 blur
regenerations down to 2. Title and ficha still update instantly, being just
text. Note it compares the texture as well as the key, so a cover that
finishes downloading for the already-selected game still lands as the
background.

Default order is alphabetical. It used to be "games with a cached cover
first", which made the prototype open on real art but left the library in an
order that depended on which JPGs happened to be on disk. Wiring the
"Ordenar" submenu is still pending.

The carousel only lays out `VISIBLE_RADIUS` boxes on each side of the
selection (`carousel.py`); the rest stay hidden and get positioned only when
they enter that window, so the arc doesn't wrap around itself with large
libraries.

The case body (`game_case.py`) has rounded corners — a real 3D rounded-rect
extrusion (`_rounded_rect_outline` → front cap, back cap, side belt), not a
flat box or a texture trick. `CORNER_RADIUS`/`CORNER_SEGMENTS` control the
look. The cover card is built from the same outline (not `CardMaker`) so it's
clipped to the case's rounded silhouette instead of overhanging square past
the curved corners. Outline winding is CCW as traced on paper (X right, Z
up) starting from the bottom-right corner's arc — verified empirically by
rendering front/back/angled views, not derived by hand, after the reflection
and radius-sign mistakes earlier in this file's history.

Store badges (`case_banner.py`) are embedded geometry at the top of each
box's cover, full width (no side margin — same width as the cover itself) —
not a floating 2D panel — so they move/rotate with the case for free as a
child node. No real Steam/Epic/GOG/Amazon logo assets in the repo (trademark
concerns for unofficial material); badges are colored text chips instead,
same palette as the cover placeholders.

The carousel's vertical framing is controlled by `CAROUSEL_RAISE` in
`app.py` (translates `carousel_root` in world Z), not by tilting the
camera — near-camera objects move a lot on screen per world-unit of camera
pitch, which made the gap-to-title tuning very twitchy. Apparent carousel
size/spread is controlled by camera distance (`_setup_camera`) and
`ARC_RADIUS`, not by scaling the boxes themselves — that keeps the selected
box correctly bigger than its neighbors (see the radius-sign note in
`carousel.py`) instead of just shrinking everything uniformly.

Each box's reflection (`game_case.py:build_case_reflection`) mirrors the
*whole* case — body and cover, not just the cover — by rebuilding the same
rounded-rect geometry (`_build_case_body`/`_build_cover`, both take an
`alpha_for_z` callback) with per-vertex alpha fading to 0 with distance from
the case (no shader needed, GPU interpolates vertex color across the
triangle), then mirroring that copy locally: `scale(1,1,-1)` + `set_z(-height)`
under the box's own root — not a mirrored instance of the whole scene. An
earlier version instanced the entire `carousel_root` through a
`scale(1,1,-1)` node at world Z=0; once `CAROUSEL_RAISE` moved the carousel
up, that mirror plane no longer lined up with the boxes' actual bottom edge,
so the "reflection" floated disconnected below them and read as a bouncing
shadow rather than something attached to the case. Mirroring per-box in
local space sidesteps that class of bug entirely.

Side boxes tilt to face the *selected* box (`carousel.py:BOX_TILT_DEG`), not
outward — the sign is unintuitive and was wrong in an earlier pass: for a box
to the right (offset>0), a *positive* heading turns it further outward
(+X), not inward. Verified by transforming the rest-pose front normal
`(0,-1,0)` through `NodePath.get_quat().xform(...)` and checking its sign,
not by eyeballing renders — a pixel-comparison attempt at this exact
question was inconclusive/misleading.

Arc spacing (`carousel.py`) is intentionally non-uniform:
`SELECTED_GAP_DEG` is the angle from the selected box to its immediate
neighbors, `SIDE_GAP_DEG` (smaller) is the angle between side boxes
thereafter — `_cumulative_angle` sums these — so side boxes cluster tightly
while the gap around the selected box stays wide:
`|||||||||  |  |||||||||`.

"The cases are invisible, I only see the covers" had a much simpler cause
than the spine-thickness theory first recorded here (that theory — that the
inward tilt plus tight clustering swallowed a thin spine, fixed by raising
`CASE_DEPTH` from 0.08 to 0.13 — was wrong, or at best a minor contributor;
the complaint survived it unchanged): **the cover was exactly the same size
as the case**, so head-on it covered 100% of the front face and the only
case pixels on screen were a few of spine. Fixed with `COVER_INSET` in
`game_case.py` — the cover is scaled down inside the case so the body shows
as a frame around it. The inset is a *fraction* of the case size applied to
width, height and corner radius alike, not a fixed offset: a fixed offset
would change the cover's aspect ratio (0.9/1.23 instead of 1.0/1.33) and
visibly stretch the art.

That frame is also what finally made the per-store case color
(`store_colors.py`, priority Steam > GOG > Epic > Amazon > neutral gray)
actually visible — before the inset, the body color existed but had nowhere
to show.

Real lesson from this one: the earlier "verified the geometry is there,
bounds are correct, it renders in isolation" check was true and still
useless, because it never asked *what is in front of it*. Confirming a node
exists is not confirming it is visible.

The front of a case is laid out as three non-overlapping bands, and
`CASE_HEIGHT` is **derived, not chosen**, to make them fit exactly:

    outer margin (COVER_INSET)   <- store-coloured frame, uniform all round
      banner strip (BANNER_HEIGHT)
      cover art (exactly COVER_ASPECT)
    outer margin

`game_case.inner_size()` gives the area inside the frame; `cover_geometry()`
gives the cover's band below the banner, including its z centre — which is
*not* 0, since the banner pushes the art down. `case_banner.py` takes its
width, top edge and corner radius from `inner_size()`.

Three constraints — a uniform frame, a banner that does not overlap the art,
and art at its true aspect ratio — cannot all hold unless the case is taller
than the art, so CASE_HEIGHT falls out of the other constants rather than
being tuned by hand. It lands at 1:1.45, near a real DVD keep case (1:1.41);
the old hand-set 1:1.33 was the aspect of the *artwork*, which is what
forced the banner to overlap it. Don't "simplify" CASE_HEIGHT back to a
literal: it silently reintroduces either the overlap or stretched art.

Earlier iterations got both wrong in turn — first the banner sat flush
against the outer border at full case width, eating the frame along the top
and sides; then it respected the frame but still sat on top of the art.
Reference for the intended look is `caja.png` in the repo root (continuous
frame, banner as a strip inside it, art starting below it).

The cover's outline has rounded BOTTOM corners and square TOP corners
(`_rounded_rect_outline(..., top_radius=0.0)`): its bottom follows the
case's curve, while its top has to meet the banner's straight bottom edge.
Rounding it there would show two notches of case colour under the banner's
ends.

Its background (`_build_banner_background`) has rounded TOP corners only —
the bottom stays square, being an internal edge with no silhouette to
conflict with. A plain rectangular banner poked its square corners past the
curved silhouette it sits in, since near the top edge the rounded
cross-section is narrower than the nominal width — visible as spikes.

Antialiasing is MSAA and needs BOTH halves, which is why it silently did
nothing for a while:
1. `framebuffer-multisample 1` / `multisamples 4` via `load_prc_file_data`
   at *module import time*, before `ShowBase` creates the window (setting it
   afterwards has no effect), and
2. `render.set_antialias(AntialiasAttrib.M_multisample)` — Panda3D leaves
   multisampling switched off in the pipe until some node asks for it via
   `AntialiasAttrib`, no matter what the framebuffer supports.

With only (1), edges were still perfectly hard. **Do not use
`win.get_fb_properties().get_multisamples()` to check whether AA is on** —
it reported 8 both with `multisamples 4` and with `multisamples 0`, because
it describes the framebuffer's capability, not whether anything is using it.
The check that actually works: render a white case on a black background and
sweep a scanline across its edge. Without AA the transition is 0.00 -> 1.00
with zero intermediate pixels; with AA there are hundreds.

Separately, cover textures need mipmaps (`covers.py:_load_texture` sets
`FT_linear_mipmap_linear` + anisotropic 16). Covers are almost always
*minified* in the carousel (~264 px of texture into ~110 px on screen, less
on the angled side boxes) and Panda3D's default filter has no mipmaps, so
the art shimmered while navigating. That looks like missing AA but is
texture aliasing — MSAA smooths geometry edges only, never face interiors,
so no amount of MSAA would have fixed it. `textures-power-2 none` is set for
the same reason: the default `down` was rescaling every 264x374 cover to
256x256 on load, squashing a 3:4 image into a square and then stretching it
back at draw time.

Case body color now follows the game's primary store
(`store_colors.py:primary_store_color`, priority Steam > GOG > Epic > Amazon
> default dark gray) instead of a single fixed dark navy for every case.
`game_case.py`'s `build_game_case`/`build_case_reflection` take a
`body_color` param threaded from `carousel.py`'s `CarouselBox.__init__`, so
the case and its mirrored reflection always share the same store color. It
only became visible at all once `COVER_INSET` gave the body a frame to show
in (see above). `store_colors.py`
centralizes the palette so the case body, the store banner chips
(`case_banner.py`), and the placeholder cover shown before a real cover
downloads (`real_data.py`) never drift out of sync with each other.

Background (`background.py`) is the selected game's cover with
`background-size: cover`-style UV cropping (fills the screen edge-to-edge
without distorting), downscaled + gaussian-blurred, and darkened.

Darkening is `set_color_scale(1 - DARKEN, ...)` on the card itself, NOT a
black semi-transparent card in front of it. It used to be the latter and it
never drew a single pixel: the overlay was created at *exactly* the same
position and scale as the image card, and Panda3D's default depth test is
`less`, not `less_equal`, so two coplanar surfaces at an identical depth
value mean the second one loses and is discarded entirely. That's why
raising the alpha did nothing at all. The color-scale version is
mathematically identical — compositing black at alpha `a` gives
`img*(1-a) + 0*a` = `img*(1-a)`, which is what multiplying by `1-a` does —
with no dependence on draw order.

The blur is back (it had been removed earlier as "a separate future pass")
because it is what fixes the pixelation: an IGDB cover is ~264 px wide and
gets stretched ~7x to fill the screen. It is done by downscaling to
`BLUR_WIDTH` and gaussian-blurring *there*, then letting the GPU magnify it
back with linear filtering — the magnification is part of the blur, and
blurring at reduced size costs a fraction of blurring at full size, which
matters because the background is regenerated on every carousel move.
Results are cached per source texture (bounded, FIFO), keyed by `id()` with
the source texture kept alive in the value so the id can't be recycled.

Card size is recomputed on every `window-event`, not just once at startup:
Panda3D auto-adjusts the camera lens's horizontal FOV to match the window's
aspect ratio on resize (confirmed in runtime — vertical FOV stays fixed), so
a size computed once at a narrower startup aspect leaves black bars at the
sides after maximizing to a wider one. `ficha_frame` in `app.py`
had the identical bug (its `-aspect, aspect` frameSize was only computed
once, at construction) and is fixed the same way, via its own
`window-event` handler.

Triangle winding caused two separate bugs here, in opposite directions, and
they masked each other. Winding decides which way a face points, and
Panda3D backface-culls by default.

1. `_add_belt` wound the case's side band inwards: for the right-hand side
   the geometric normal came out as -X instead of +X. The near spine was
   culled, so a tilted case showed only the flat front frame and read as a
   sheet of card rather than a box.
2. `build_case_reflection` mirrors with `set_scale(1, 1, -1)`, and a
   mirror reverses winding for everything under it. That *re-reversed* the
   already-wrong belt back to correct, so the spine was visible in the
   reflection while missing on the case above it — the reported symptom.
   The same mirror culled the reflected cover outright (a single-sided flat
   fan has no second face to fall back on), which is why the cover did not
   reflect at all.

Fixed at the source: `_add_belt` now winds outwards, and the reflection
pre-inverts its geometry with `_flipped()` (`Geom.reverse_in_place`) so the
mirror's reversal cancels out. Do not "fix" the reflection with
`set_two_sided(True)` instead — on the semi-transparent body that blends
front and back faces on top of each other and darkens it.

The check that settles this kind of question in one shot: scan a horizontal
line of pixels across the edge of a tilted case and compare it against the
same line across its reflection. Before, the case's silhouette started 28 px
inside the reflection's; a mirror must have exactly the same silhouette
width, so that mismatch alone localises the bug. Afterwards both start at
the same x, and the spine reads at the value predicted by
`ambient + directional * max(0, N·L)`.

Note this invalidates the earlier reasoning that raised `CASE_DEPTH` from
0.08 to 0.13 "because the spine was only about a pixel wide". The spine was
never thin — it was not being drawn. 0.13 is now a deliberately chunky
spine, roughly double a real case at scale, and could be taken back down.

`REFLECTION_MAX_ALPHA` was lowered 0.22 -> 0.16 at the same time: 0.22 had
been tuned while the reflection was showing nothing but flat body colour, so
once real cover art appeared the same alpha read far stronger on screen.

Two Panda3D API traps hit repeatedly while debugging the above, both of
which produced confidently wrong conclusions:
- `NodePath.node()` and `NodePath.get_children()` return **fresh Python
  wrappers each call**, so `child.node() is target.node()` and
  `child is target` are always False. Use `==`, or keep positional indices.
  An "isolate this node by hiding its siblings" check silently hid the node
  under test instead.
- Verify visual bugs by *looking at the rendered image*, not only by
  reducing it to a pixel statistic. A "does the reflection show art?"
  variance metric was sampling a screen region that did not contain the
  reflection, and reported the fix as ineffective; the saved PNG showed
  immediately that it worked.

The bottom panel ("ficha") shows the same fields as the TUI's
`gui/widgets/game_detail.py`, minus the cover URL (a clickable link there,
useless here, and the cover is already on screen at size). The game's title
is not repeated either — it is already the largest thing on screen above the
carousel.

Those fields are why `real_data.py` now goes through
`LibraryRepository.load()` instead of joining `resolvers` and `games` by
hand: duration, Steam and SteamDB scores are not in the IGDB cache at all,
they live in the extras table and only the repository joins them in. It also
means the "Golden Rule" no longer has to be restated in `gui3d`.

UI font (`fonts.py`) is Hussar Print (Robert Jablonski, SIL OFL 1.1),
shipped in `gui3d/assets/fonts/`, loaded once via `ui_font()` and applied to
every text widget: title, ficha, store banner chips, submenu. `ui_font()`
returns None if the file is missing so callers fall back to Panda3D's
default rather than crashing — `case_banner.py` checks for that explicitly
since `TextNode.set_font` doesn't accept None. `build3d.sh` needs
`--add-data "puntueitor/gui3d/assets:puntueitor/gui3d/assets"` for
PyInstaller to bundle the file; without it the dev run works (loads
straight from the source tree) and the packaged binary silently falls back
to the default font, which is easy to not notice until someone runs the
built binary specifically.

No emoji in the labels, unlike the TUI: neither Panda3D's default font nor
Hussar Print has those glyphs, and both render them as empty boxes (warns on
stderr, "No definition in for character U+1f3ae"). Accents and ñ are fine in
both. Cyrillic titles in a few library entries still don't render — Hussar
Print is Latin-only — and fixing that would need a second, wider-coverage
font as fallback, not just swapping this one.

Layout notes, each of which came from something that broke:
- One `OnscreenText` per row, not one multi-line text per column. Line
  spacing comes from the font and there is no per-node setter — only
  `TextFont.set_line_height`, which is shared with the whole HUD — so
  custom spacing needs separate nodes anyway.
- Row heights are measured, not assumed: values wrap
  (`textNode.get_num_rows()` after setting the text) and rows are stacked by
  their real height. With a fixed step, a game with nine genres had the next
  rows drawn on top of it.
- The description is truncated (`MAX_DESCRIPTION_CHARS`, in `ficha.py`).
  The TUI can skip this because its panel scrolls; this one does not.

`MAX_DESCRIPTION_CHARS` is coupled to `DESCRIPTION_TEXT_SCALE` in `app.py`
and NOT an independent constant, and this bit once: raising the ficha's
text scale (0.036 -> 0.040) while leaving the character budget at 480 pushed
the worst-case description (a 0.700 measured height) past the taller
panel's own available height (0.690) — bigger text means fewer characters
fit per line at the same wrap width, so the same character count needs more
lines, and total height grows faster than the scale itself. Had to drop the
budget to 420 to bring it back under. Whenever either constant changes,
re-measure the worst case over the WHOLE library, not whatever game happens
to be selected — the peak for fields and the peak for the description come
from different games, so eyeballing one game in the running app proves
nothing about the other column or about entries you didn't happen to visit.
Current worst case: fields 0.432, description 0.650, against 0.690
available (`FICHA_BAR_TOP_Z = -0.16`, up from -0.36 — the ceiling on how
much higher this can go is where it starts eating the selected box itself
instead of just its already-fading reflection, checked by rendering, not
by eyeballing the constant).

Careful with `Lens.project()` when checking for distortion by hand: it
returns raw NDC coordinates normalized independently per axis (x by
tan(HFOV/2), y by tan(VFOV/2)), *not* the aspect2d convention
(`-aspect..+aspect` on x). Comparing raw NDC width/height directly looks
like squashing that isn't there — verified in this project by projecting the
same box's corners at two aspect ratios and finding a ~26% raw-NDC-ratio
difference that vanished (0.766 vs 0.752, matching `CASE_WIDTH/CASE_HEIGHT`)
once converted to actual screen pixels (`ndc * window_size/2` per axis).

Real (confirmed, reproduced locally) distortion bug and its fix: request a
1920x1080 window under a WM that reserves space for its own taskbar/panel,
and it gets clamped to something like 1920x1008 — but the aspect ratio Panda
uses stays at the *originally requested* 1.778 instead of the actual 1.905.
Panda's own automatic correction (`ShowBase.windowEvent` →
`adjustWindowAspectRatio`) only fires on a detected *change* to the window's
properties; if the WM's clamp happens before Panda's baseline "previous
properties" snapshot is taken, no change is ever detected and no
`window-event` fires — confirmed by tracing: `_on_window_event` never got
called across 40+ frames even though `win.get_x_size()/get_y_size()` already
reflected the clamped size from frame 0. Fixed with a per-frame self-healing
check (`App._check_lens_aspect_ratio`, called from `_update`) that
compares `get_aspect_ratio()` against `camLens.get_aspect_ratio()` and
re-syncs on any mismatch — a plain float comparison, not worth trying to
catch via events given the above. `window-event` handling is kept too, as
the fast path for genuine live resizes.

`_sync_lens_aspect_ratio` calls `self.adjustWindowAspectRatio(...)`, not
`camLens.set_aspect_ratio(...)` directly — the first version of this fix did
the latter, which only corrects the 3D lens. `aspect2d` (title, description
bar, submenu — everything 2D) has its *own* independent scale
(`aspect2d.set_scale(1/aspect_ratio, 1, 1)`) that only `adjustWindowAspectRatio`
touches; skipping it left the 2D HUD still misproportioned even after the 3D
boxes were already rendering correctly.

Reflection opacity lives in `carousel.py:REFLECTION_MAX_ALPHA` — keep it low
(subtle) rather than a strong duplicate; a high value reads as a second solid
box floating below rather than a reflection.

## Configuration

The app requires API keys stored at `~/.config/puntueitor/config.json`:
- `steam_api_key`
- `steam_user_id`
- `igdb_client_id`
- `igdb_client_secret`
- others...

The app prompts for configuration if missing (press `c` in the TUI).

## Project Structure

```
puntueitor/
├── core/           # Domain logic
│   ├── models/     # Game, Library, ScoredGame
│   ├── filters/    # NameFilter, GenreFilter, DurationFilter
│   ├── scoring/    # MixedScore, WeightedScore
│   ├── selector/   # Game selection logic
│   ├── cachers/    # SQLite, todos sobre BaseCacher
│   ├── enrichers/  # HLTB + Steam score
│   ├── resolvers/  # Steam, Epic, GOG, IGDB resolvers
│   ├── mappers/    # Raw → Game transformation
│   ├── pipeline/   # Orchestration pipelines
│   └── repository/ # Library persistence
└── gui/            # Textual TUI
    ├── app.py      # Main app entry
    ├── screens/    # TUI screens
    └── widgets/    # Reusable widgets
```

## Conventions

**Missing data.** Two different rules, do not mix them:

- `duration_hours`: `None` is the *only* "unknown" value. Never write `0` to
  mean "HLTB found nothing" — the scorers read it as a real zero-hour game and
  rank it at the top. A failed HLTB lookup is recorded in `extras.hltb_checked`
  so it is not retried on every startup.
- Ratings (`critic_score`, `user_score`, `steamdb_score`): use
  `models/util.py:is_missing()`. External sources return `0` for both "no data"
  and "zero score", and a real 0/100 rating does not occur in practice.

Sorters put missing values last in *both* directions — partition the list, do
not smuggle a `±inf` into the sort key.

## Architecture Flow

1. **Resolvers** fetch raw data from external APIs (Steam, Epic, GOG, HLTB)
2. **Mappers** transform raw data → canonical `Game` model
3. **Filters**, **Scoring**, **Enrichers** process the library
4. **Selectors** choose the best game from candidates
5. **Repository** persists the library to disk

Key concepts documented in Spanish in `LEEME.txt` and `arquitectura.md`.

## Testing

```bash
.venv/bin/python -m pytest tests/ -q
```

238 tests (pytest). The `tests/` directory is gitignored, so test changes do not
show up in `git status` — run the suite explicitly after touching the core.

## Linting / Type Checking

No configured tooling. Project uses standard Python 3.14 without ruff, mypy, or pre-commit hooks.

## File locations (XDG)

Every path lives in `core/paths.py` and nowhere else:

| Where | What | Why |
|---|---|---|
| `~/.config/puntueitor/` | `config.json` | hand-editable settings |
| `~/.local/share/puntueitor/` | `puntueitor.db`, `library.sqlite` | user data and expensive derived data |
| `~/.cache/puntueitor/` | `covers/`, `igdb_token.json`, `<steamid>.sqlite` | genuinely re-downloadable |
| `~/.local/state/puntueitor/` | `puntueitor.log` | not config, not cache, not worth backing up |

`puntueitor.db` used to live in `~/.cache`, which was wrong in a way that
could lose data: it holds `resolvers` — by the project's own Golden Rule the
only source of truth for what is in the library — plus `extras` (HLTB hours,
Steam scores), which are rebuildable only via thousands of API calls. The
contract of `~/.cache` is that anything in it may be deleted at any moment,
and it is routinely excluded from backups. `library.sqlite` was in
`~/.config`, which was semantically wrong but harmless (it is user data, not
settings). The `games` table stays inside `puntueitor.db` even though it is
pure IGDB cache: splitting it would force every cacher to juggle two
connections to save about a megabyte.

`migrate_legacy_paths()` moves the old files on first run and is called at
import of `core/paths.py`. That timing is deliberate — anything that opens a
database must ask this module for the path first, so migration cannot be
beaten to the punch by a cacher creating an empty database at the
destination, which would make the migration skip and leave the real data
orphaned. It never overwrites and never deletes, and it moves SQLite's
`-wal`/`-shm` sidecars along with the database (WAL is enabled, so a `-wal`
left behind can hold unflushed transactions).

**Paths are functions, not module constants, and this is not a style
choice.** They resolve `Path.home()` / `XDG_*_HOME` on every call so that
patching either actually redirects the app. The first version of this module
used constants evaluated at import; the config tests kept monkeypatching
`Path.home` believing they were isolated, and running the suite overwrote
the real `~/.config/puntueitor/config.json`, wiping the user's API keys.
Same reasoning applies to `BaseCacher.default_path()` being a method rather
than a `DEFAULT_PATH` attribute. When touching this module, verify isolation
under a patched `Path.home` *before* running the suite.

Case labels (`case_labels.py`) are four fixed sticker slots on the case
front: favorite top-left, finished-OR-backlog top-right (they share the slot
and finished wins when both are set), duration bottom-centre, score
bottom-right. Each only built if its data is truthy
(`favorite`/`finished`/`backlog`) or present (`steamdb_score`,
`duration_hours > 0`; `0` means "no data", same convention as `ficha.py`).
Never on the reflection, matching the store banner. Built once per box at
`CarouselBox.__init__`, baked from `entry.game` — not rebuilt on selection
change, since these are per-game facts that don't change while the box
exists.

Space / gamepad Y toggles them all (`App._toggle_labels` →
`Carousel.set_labels_visible`). It walks **every** box, not just the visible
ones: a box outside `VISIBLE_RADIUS` will scroll into view later and would
otherwise arrive with its labels still showing after they were hidden.

Careful when testing that visibility: `NodePath.is_hidden()` reports True if
the node *or any ancestor* is hidden, and off-screen boxes already have
their root hidden by the carousel's own virtualisation — so counting
`labels_np.is_hidden()` across all boxes says "1266 hidden" even right after
showing them. Use `get_hidden_ancestor() == labels_np` to ask about the
node's own state.

Reported once as "favorite/finished/backlog don't show at all" when the code
was in fact correct — the real library only had 2 favorites and 15 backlog
entries out of 1266 (1 in 633 and 1 in 84 boxes), so browsing simply never
landed on one. Before debugging a "label never appears" report, count how
many games actually carry that flag; forcing the flag on every game and
rendering is the fastest way to separate a rendering bug from a data
frequency artifact.

Score/duration text scale and offsets are expressed as a **fraction of
`BOTTOM_LABEL_SIZE`**, not in absolute units, so resizing the sticker
rescales the number and its placement with it instead of needing four
constants recalibrated by hand.

Three-digit values get shrunk automatically (`_THREE_DIGIT_SCALE`): duration
in the real 1266-game library reaches 169h (7 games are 3-digit) and score
can be 100. At a size that looks right for "42" inside a round icon, "169"
spilled straight off the clock face. Shrinking only that case keeps the
number large on the ~99% of boxes that show two digits. Anyone resizing
these must re-check with a 3-digit value, not just whatever game happens to
be selected while testing.

A faked-bold variant (`DynamicTextFont.set_outline`, a separate font
instance since `FontPool.load_font` caches by path and would have emboldened
the title/ficha/banner too) was tried and dropped — asked for plain weight
again once seen rendered. `ui_font_bold()` no longer exists; if bold ever
comes back, the separate-instance requirement is the part worth
remembering, same cache-by-name trap that forced the move away from
`TexturePool` for covers.

The top badges are deliberately oversized relative to `BANNER_HEIGHT`
(0.22 vs 0.11) and positioned to slightly overhang the case's own outer
edge, not sit flush inside it — asked for explicitly as a "sticker" look
rather than a badge neatly inset in the frame. `TOP_LABEL_TOP_MARGIN` keeps
a sliver of margin from the physical top edge (a sticker flush with the
edge reads as an render artifact, like it's been cut off, not intentional
overhang).

## Button icons (fonts.py: icon_font, ICON_*)

The bottom help bar used to spell out key/button names as text ("Enter/A",
"Esc/Start"). It's icons now, via PromptFont (Yukari "Shinmera" Hafner, SIL
OFL — `assets/buttons/PromptFont-OFL.txt`), extracted from the zip the user
provides as `promptfont-all.zip` — only `promptfont.otf` and the license
text are committed, not the ~1 MB zip itself (same treatment as
`hussar-print.zip` for Hussar Print: keep the source archive out of the
repo, commit only what's actually used). **Don't delete or `git add -A`
that zip** — it's the user's file, not a build artifact.

PromptFont is a normal OTF, not a texture atlas: every key/button is a
glyph at a specific Unicode codepoint (mostly the "Control Pictures" block
and repurposed math-symbol ranges), so it's used exactly like Hussar
Print — loaded with `DynamicTextFont`, sent as regular text. `icon_font()`
mirrors `ui_font()`'s pattern and registers `ICON_PROPERTY`, a `TextProperties`
that swaps `set_font` to PromptFont for whatever text sits inside
`icon_markup(...)` — reusing the exact `\x01name\x01...\x02` structure
escape already established for `SUPERSCRIPT_PROPERTY`. `icon_markup()`
exists specifically so nobody hand-types those control characters at each
call site; a stray or missing `\x02` doesn't error, it just silently
renders wrong.

The `ICON_*` constants are built with `chr(0x....)`, not typed as literal
characters. A hand-typed exotic Unicode glyph is one accidental
mis-transcription away from silently becoming a *different* glyph with no
error — `chr()` keeps the codepoint visible and searchable next to the
comment naming which PromptFont glyph it is. Every codepoint used was
checked against PromptFont's own `glyphs.json` before use; the font ships
~900 glyphs under non-obvious names and nothing in the `.otf` itself
documents which codepoint is which.

Not every plausible glyph reads correctly at HUD size. `xbox-dpad-left`,
`xbox-dpad-right` and `xbox-dpad-left-right` all render as the exact same
plain cross in flat single-colour text — whatever distinguishes them (the
"active" arm) is conveyed by a colour/shade variant in PromptFont's own
multi-colour rendering that a plain `TextNode` fill doesn't reproduce.
Confirmed by rendering all four dpad variants side by side. Ended up using
`analog-left-right` (a stick icon flanked by two arrows) instead, which
reads unambiguously *and* is more accurate — this app's navigation accepts
the d-pad and the analog stick interchangeably, so a generic "directional
input" icon fits better than a dpad-specific one anyway. Before wiring up
any new icon from this font, render it in isolation and at the actual
target size first — don't assume the name matches what it looks like
flattened to one colour.

`icon_font()`'s `TextProperties` needs its own `set_text_scale`/
`set_glyph_shift` tuned against Hussar Print, because the two fonts don't
share metrics — untuned, PromptFont's glyphs sat smaller and higher than
the surrounding text. There's no way to compute this from font metrics;
it's calibrated by rendering the help bar and reading it at the size it
actually ships at, the same as every other layout constant in this
codebase.

## Menu system (menu.py, menus.py, rounded_panel.py)

Replaced the old single `submenu.py`, which was one fixed options panel
navigated **left/right** — a leftover from when the only thing on screen was
the horizontal carousel. Menus are vertical lists now and they **stack**:
`app.App._menu_stack` holds them, `_push_menu`/`_pop_menu` move through it,
and `active_menu` (top of stack, or None) is what decides who owns input.

Three modules, split by what they know about:

- `rounded_panel.py` — pure drawing primitive, knows nothing about menus.
  Panda3D has no rounded rect (`DirectFrame` is square-cornered at every
  relief), and the usual 9-slice texture route would need one PNG per panel
  colour, so it generates a triangle-fan geometry instead.
- `menu.py` — the widget: panel, title, rows, focus highlight. Knows
  nothing about games or scoring.
- `menus.py` — just the *contents* (which rows, which keys). `MenuItem.key`
  is the contract with `app.py`, and the keys deliberately match the TUI's
  (`gui/screens/scoring.py`, `sorting.py`, `filtering.py`).

Item kinds are `action`, `check` (toggles in place) and `header` (a section
label that `move_focus` skips — its loop is bounded to one full pass so a
menu of nothing but headers can't spin forever).

Input bindings, all four main menus opening from the carousel: Select/Esc →
Options, Start/Tab → scoring, X/`x` → filter+sort, A/Enter → game menu.
B and Esc both go back, but they are **not** the same handler: Esc doubles as
"open Options" on the main screen (the keyboard has no comfortable Select),
while B on the main screen deliberately does nothing, because it means
"back" and there's nowhere to go back to. `x` is context-sensitive — inside
the scoring menu it configures the focused system instead of opening filters.

Things that were found by rendering, not by reasoning:

- **Stacked menus must hide the one underneath.** Leaving it visible (so you
  could see where you came from) sounds nice, but every menu draws centred at
  the same spot, so the two panels landed on top of each other and the text
  overlapped letter-on-letter. Screenshot it if you ever want to re-try this.
- **Unfocused rows have to be dim, not white.** The focus highlight uses the
  selected game's store colour (`store_colors.as_text_color`, which brightens
  the chip colours — they're designed as dark backgrounds with white text on
  top, unreadable as text themselves). Epic's is a near-black grey that
  brightens to off-white, so against white rows its highlight was *invisible*.
  Dimming the unfocused rows makes the highlight work for any store hue.
- **Panel width is measured, not fixed.** The scoring menu's hint has one
  extra key ("configurar") and overflowed a fixed-width panel, while the quit
  confirmation had half a panel of empty space. `_half_width()` measures the
  composed `TextNode`s (`get_width() * scale`) — you can't estimate this by
  counting characters, especially with icon glyphs mixed in. This forces the
  panel to be built *after* the texts, hence `set_bin("background", 0)` so it
  doesn't cover them.
- **The hint gap must exceed the other margins.** Row baselines sit at 0.62
  of their slot, so only a fraction of a row is left under the last one; a
  normal-sized gap put the hint on top of the last item.

Menu titles use plain `ui_font()`, not a bold variant — bold was tried
(`ui_font_bold()`, same faked-outline approach documented above for the case
labels) and dropped again once seen rendered: the outline blurred the title
at menu scale. `ui_font_bold()` was deleted outright rather than left unused,
same call as the case-labels bold removal — see the note above if it needs
reviving.

## `messenger.accept` overwrites silently — one handler per (object, event)

Closing the window used to leave the process running forever (the window
vanished, the task loop kept spinning, only Ctrl+C got out). Three separate
bugs stacked on top of each other; the first is the one that will bite again:

**1. Handlers clobbering each other.** Panda3D's messenger keys handlers by
`(object, event)`, and registering a second one for the same pair *replaces*
the first — no error, no warning at default notify level. Three places were
registering `window-event`:

- `ShowBase.__init__` → `self.windowEvent` (this is the one that notices the
  window closed and calls `userExit()`)
- `App.__init__` → `self._on_window_event`
- `background.py` → **`base.accept("window-event", ...)`**

That last one is the trap: `Background` wasn't a `DirectObject`, so it called
`base.accept(...)`, meaning *"the App accepts this event"*. Same object key as
the App's own handler, so it silently replaced it — which had already replaced
ShowBase's. Only Background's survived, so nothing ever called `userExit()`.
Fix: `Background` now inherits `DirectObject` and uses `self.accept(...)`, so
it has its own messenger identity. `App._on_window_event` explicitly chains
`ShowBase.windowEvent(self, window)` (guarded by `hasattr(window,
"getProperties")`, absent in offscreen/test mode where `self.win` is a
`GraphicsBuffer`).

Verify with:
```python
messenger._Messenger__callbacks['window-event']   # expect one entry per object
```

**2. Nothing called `App.destroy()`.** `userExit()` goes straight to
`sys.exit()`. `ShowBase` exposes `self.exitFunc` precisely as the pre-exit
hook — set it rather than reimplementing the close path.

**3. Non-daemon download threads blocked interpreter exit.**
`ThreadPoolExecutor`'s workers are non-daemon *and* `concurrent.futures`
registers an atexit hook that joins them all, so the process waited on
in-flight covers. `shutdown(wait=False, cancel_futures=True)` does **not**
help — it cancels *queued* work, never interrupts a running download. Plus
`DOWNLOAD_TIMEOUT` was declared but never wired up (`urlretrieve` accepts no
timeout), so a stalled server hung forever. `CoverLoader` now runs its own
`daemon=True` threads and downloads via `urlopen(..., timeout=...)`. Abandoning
a download mid-flight is safe because covers are written to a temp file and
`os.replace`d only when complete.

Reproducing a real close needs an actual `WM_DELETE_WINDOW` — a programmatic
`request_properties(open=False)` does *not* generate the same event. Use
python-xlib to send the ClientMessage, then assert the process is gone; and
dump `faulthandler.dump_traceback()` on a stuck run to see which thread is
stuck where, rather than guessing.

## Environment

- Python 3.14 (from `.venv`)
- Virtual environment: `.venv/`