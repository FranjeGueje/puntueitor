# Puntueitor – Agent Guide

## Running the App

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the Textual TUI app
python -m puntueitor.tui.app
```

Or directly:
```bash
python -c "from puntueitor.tui.app import PuntueitorApp; app = PuntueitorApp(); app.run()"
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
`puntueitor/gui3d/`, fully separate from `puntueitor/tui/`.

It is NOT read-only any more: it writes user flags, resolves unknown games,
refreshes and regenerates the library, and takes backups. Everything it does
beyond drawing goes through `core/services/`, which is the layer both
frontends share — see `arquitectura.md`. Anything long-running lives in a
worker with its own daemon thread and a `queue.Queue` drained per frame
(`covers.py`, `refresh.py`, `enrichment.py`, `unknowns.py`); never a
`ThreadPoolExecutor`, whose non-daemon threads and `atexit` hook block the
window from closing.

Keyboard and gamepad cover the same gestures; the full table is in the
README. Gamepad support (hot-plug aware) is in `gamepad_input.py`.

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
`tui/widgets/game_detail.py`, minus the cover URL (a clickable link there,
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
│   ├── providers/  # Store APIs → raw games (+ offline cache)
│   ├── auth/       # Store OAuth sessions and token storage
│   ├── resolvers/  # Steam, Epic, GOG, IGDB resolvers
│   ├── mappers/    # Raw → Game transformation
│   ├── pipeline/   # Orchestration pipelines
│   └── repository/ # Library persistence
└── tui/            # Textual TUI
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

1. **Providers** fetch each store's library from its own API and cache it
2. **Resolvers** identify each raw game against IGDB
3. **Mappers** transform raw data → canonical `Game` model
4. **Filters**, **Scoring**, **Enrichers** process the library
5. **Selectors** choose the best game from candidates
6. **Repository** persists the library to disk

Key concepts documented in Spanish in `arquitectura.md`.

## Testing

```bash
.venv/bin/python -m pytest -q
```

440 tests (pytest), tracked in the repo and run in CI
(`.github/workflows/tests.yml`).

They never touch the network or the real `$HOME`: `tests/conftest.py` mounts a
sandbox (XDG_* plus `Path.home`) BEFORE importing anything from `puntueitor`,
and `pytest_configure` refuses to run if that isolation is not in place. Both
halves matter — patching only the XDG variables leaves the legacy-path sources
pointing at the real home, which is how the user's files got moved into a temp
directory once.

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
  (`tui/screens/scoring.py`, `sorting.py`, `filtering.py`).

Item kinds are `action`, `check` (toggles in place) and `header` (a section
label that `move_focus` skips — its loop is bounded to one full pass so a
menu of nothing but headers can't spin forever).

Input bindings, all four main menus opening from the carousel: Select/Esc →
Options, Start/Tab → scoring, X/`x` → filter+sort, A/Enter → game menu.
Pressing the button that *opened* a menu again closes the **whole stack** back
to the carousel, not one level (`_toggle_root_menu` + `_menu_opener`). Each
button only closes its own menu — X inside the scoring menu configures the
focused system rather than closing it. The game menu is deliberately excluded:
it opens with A, and A inside a menu means "choose", so it can't also mean
"close" without ticking a checkbox on the way out. `_menu_opener` must be
cleared whenever the stack empties, or the *previous* menu's button would close
the next one.
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

## Two databases: extras (cache) vs user status (not cache)

User flags — `finished`, `hidden`, `backlog`, `favorite` — do **not** live
where the rest of a `Game`'s data lives. There are two stores and picking the
wrong one fails *silently*:

| Data | Store | Written via |
|---|---|---|
| duration, steam/steamdb scores, review counts (`_EXTRA_FIELDS`) | `puntueitor.db`, table `extras` | `LibraryRepository.save_game()` |
| `finished`/`hidden`/`backlog`/`favorite` | `library.sqlite`, table `user_games` | `LibraryCacher.set_status()` |

They're split on purpose: extras are a regenerable network cache, user flags
are not, so wiping the cache must never lose your favourites. `LibraryRepository`
holds both (`.extras_cacher`, `.library_cacher`) and `load()` merges them.

The gui3d game menu first "saved" via `save_game()`, which persisted nothing at
all — `_extras_row()` only reads `_EXTRA_FIELDS`, so the flags were dropped
without any error. Use `repo.library_cacher.set_status(...)`, same as
`tui/app.py:_toggle_game_flag`.

**`set_status` is a whole-row UPSERT.** Pass all four flags every time; sending
only the one that changed silently resets the other three to `False`.

`LibraryRepository(cache_dir=...)` used to honour that argument for only three
of its five cachers: `library_cacher` and `unknown_cacher` were constructed
with no path, so they went to the *real* user files regardless. The test suite
passes `tmp_path` and still wrote a made-up game (`igdb_id 1001`) into the real
`library.sqlite` on every run. All five now derive from `cache_dir`; production
paths are unchanged because `cache_dir` already defaults to `paths.data_dir()`.
If you add a cacher here, route it through `cache_dir` too.

Testing this must never touch the real DB. `paths.py` reads `XDG_DATA_HOME` on
every call, so setting it sandboxes everything — but *verify the redirect
before writing*:
```python
assert '/home/deck/.local' not in str(paths.library_db())
```
Note `library.sqlite` is in WAL mode: **its md5 does not change when rows do**
(writes land in `library.sqlite-wal`). Comparing checksums to prove "I didn't
touch it" is worthless here — query the rows. Learned the hard way: a smoke
script stubbed `save_game`, the code moved to `set_status`, and the stub
silently stopped covering the write path. Stub the method actually used *and*
make the real one raise.

## Carousel filtering (hidden games)

The carousel builds one `CarouselBox` per game up front — 1266 boxes cost ~1.2 s
and ~270 MB — so filtering must never rebuild them. Instead there's a level of
indirection: `_order` is the list of box indices currently walkable, in walk
order, and `_selected_pos` indexes *into `_order`*, not into `_boxes`. Filtering
is `set_visible_keys(keys)`, which rebuilds `_order` from the full entry list, so
a game that reappears lands **in its correct place**, never appended at the end.
The same mechanism is what sorting will use when it gets wired up.

Consequences worth knowing:

- "Neighbouring" entries are neighbours *in the visible order*. Cover preloading
  must ask the carousel (`neighbour_entries`, `is_near_selection`) rather than
  doing modular arithmetic on the full `entries` list, or with games filtered out
  it preloads covers for boxes the user can't reach.
- **An empty carousel is a valid state** (`Carousel.is_empty`, and `selected`
  returns `None`): regenerating the library empties it, and a filter can match
  nothing. It didn't use to be — `set_order` refused empty orders — but that made
  the screen lie: filters set and the whole library still on show. Everything
  that paints from the selection (ficha, background, menu accent, game menu)
  checks for `None`.
- If the selected game is the one being filtered out, selection falls to the next
  still-visible game *at or after* it, so it stays near where the user was
  looking instead of jumping to the top of the library.
- Toggling "Oculto" from the game menu defers the re-filter until that menu
  closes (`_hidden_filter_dirty`). Applying it immediately yanks the box out from
  under the open menu and shifts the selection while you're still editing it.

## Game menu: ESTADOS y AVANZADO (enriquecer / desconocer)

El menú de un juego (A sobre el carrusel) tiene dos secciones: **ESTADOS**, las
cuatro casillas que se guardan al momento (ver la sección de las dos bases de
datos), y **AVANZADO**, con dos acciones que **preguntan antes**: una tarda y va
a la red, la otra saca el juego de la biblioteca.

La lógica de las dos vive en **`core/services/game_actions.py`**, compartida con
la TUI, que antes la tenía escrita a mano dentro de `tui/app.py`:

- `enrich_game(repo, game) -> EnrichResult`. **Bloquea** (hace red) y **nunca
  lanza**: devuelve los tres desenlaces —datos / sin datos / error— en el
  resultado. Son tres y hay que distinguirlos: "no se encontró nada" es normal,
  un error es un fallo que el usuario querrá ver. Y no lanza porque quien la
  llama está siempre dentro de un hilo, donde una excepción se pierde sin dejar
  rastro. Va con `overwrite=True`: se ha pedido a mano sobre ese juego, así que
  rehace la búsqueda aunque ya hubiera datos o ya se hubiera buscado sin éxito
  (`extras.hltb_checked`), al revés que el pipeline.
- `forget_game(repo, game) -> {tienda: id}`. Borra la relación en `resolvers`
  (la fuente de verdad de qué está en la biblioteca) y apunta cada id de tienda
  en `unknown_games` para que el siguiente escaneo no lo vuelva a resolver al
  mismo juego. Hay que LEER las tiendas antes de borrar la relación. La ficha en
  la caché de IGDB se queda: es una caché global de todo lo consultado y no
  representa posesión.

En gui3d, enriquecer va por **`gui3d/enrichment.py`** (`EnrichWorker`), calcado
de `covers.CoverLoader` y por el mismo motivo: hilo propio `daemon=True`, nunca
`ThreadPoolExecutor`. Un solo hilo (esto se pide a mano, no en ráfagas), colas
`_pending`/`_done`, y `poll()` drenado desde `_update`. `request()` devuelve
False si ese juego ya está en vuelo: enriquecer tarda varios segundos sin que el
carrusel dé señal de estar haciendo nada, y volver a entrar y pulsar otra vez es
lo natural.

Al aplicar el resultado, `_on_enrich_done` **copia los campos sobre el `Game`
que ya está en la entrada** (`EXTRA_FIELDS` del repositorio) en vez de sustituir
la entrada: `CarouselEntry` es `frozen` y el carrusel guarda sus propias
referencias, así que cambiarla dejaría a `carousel.selected.game` y a
`self.entries` enseñando datos distintos. Y busca la entrada **por `key`**: entre
la petición y la respuesta el juego puede haber desaparecido.

Desconocer es síncrono: `forget_game`, quitar la entrada de `self.entries` y
`_apply_order()`. No se destruye ninguna caja — `set_order` esconde lo que no
esté en el orden. Caso límite: si era el último visible, `set_order` ignora un
orden vacío y la caja se quedaría en pantalla, así que se detecta antes y se
avisa en vez de reordenar.

### El menú de confirmación

`confirm_menu` es **uno solo para todas las preguntas de sí/no**: título e items
se rehacen en cada apertura (`_ask_confirm`), y lo que se recuerda es el
callback ya atado a su juego, no el juego. El de salir se queda aparte porque es
fijo y no va sobre nada.

- La pregunta va en **rótulos de sección, uno por línea** (`build_confirm_items`),
  no en el título: un rótulo no admite saltos de línea (su alto está fijado en
  `HEADER_HEIGHT`) y el título se dibuja a `TITLE_SCALE`, donde una frase entera
  se pasa de `PANEL_MAX_HALF_WIDTH`. El título lleva el nombre del juego.
- El **"No" va primero**: `set_items` deja el foco en la primera fila enfocable,
  así que la opción marcada de serie es la que no hace nada. Mismo criterio que
  `QUIT_ITEMS`.
- `confirm_yes` olvida el callback **antes** de ejecutarlo (es lo que impide que
  una segunda pulsación repita la acción) y hace `_close_all_menus()` antes de
  actuar: las dos acciones avisan por el notificador y cambian el carrusel, y
  dejar menús encima taparía justo el resultado.
- Salir con B no pasa por `_activate`, así que `_pop_menu` limpia
  `_confirm_action` cuando el menú cerrado es `confirm_menu`.

## The store registry is the only list of stores

`core/stores/` holds one `StoreSpec` per store — label, colour, config flag,
provider, resolver, session, paste hint — and everything else reads it: both
UIs' menus, the carousel colours, the log, the pipeline's resolver table, the
session service.

It exists because that same fact used to live in **eleven files**, hand-synced,
and it broke twice: the CUENTAS rows rendered fine but the dispatcher did not
route them, and `sessions_summary()` walked the whole enum and dragged Steam
into a list it had no business being in.

**Do not write another list of stores.** Two tests enforce it
(`tests/test_stores_registry.py`): one greps the source for lines naming two or
more stores outside `core/stores/`, the other for `for store in Stores`. If you
need "all the stores", ask `stores.all_stores()` — it also carries the right
order, which drives both menu order and colour priority.

Per-store facts belong in the spec, not in a constant elsewhere. `session=None`
is how Steam says it has no OAuth; `resolvable_by_id=False` is how Amazon says
its games can only be found by title. Both used to be separate tuples.

Adding a store still costs two lines outside its module — the `Stores` member
and the `Config` flag — because the enum is the database key and the config is
typed. The registry tests catch both omissions, in both directions.

## Store providers: the cache is the safety net, not an optimisation

Three of the four store APIs (GOG, Epic, Amazon) are undocumented — they are
the ones gogdl, Legendary and Nile use, and they can change without notice.
`LibraryProvider.fetch()` therefore **never returns empty when it has cached
data**: no network, expired session, or a store answering with zero games all
fall back to the last good library and say so in the log. Only a refresh that
comes back with games rewrites the cache.

That last case is the non-obvious one. A store replying "you own nothing" is
almost always a fault on their side, not a sold account, so `save_games()`
keeps the previous copy when handed an empty list. Without it, one bad answer
would wipe a library and the next startup would look like the user's fault.

`fetch()` also **never raises**. `load_library` walks the four stores in one
loop, and one store blowing up would take the ones behind it with it.

A network failure while *renewing* a token is not an expired session
(`OAuthSession.access_token`). If it were treated as one, a few minutes
offline would force the user to log in again on all three stores.

Providers emit the store's **raw dict**, with the keys the matching resolver
already reads (`app_name`/`appid`, `title`, `store_url` on Epic). Do not
"normalise" them into a common shape: the resolvers are what interpret them,
and they would all break at once for nothing.

## Pasting into the 3D text prompt

Panda3D has no clipboard API — `panda3d.core` has only `ClipPlaneAttrib`, and
`DirectGui` never mentions paste. So `core/services/clipboard.py` asks the
system, trying several ways in order and taking the first that answers.

Two things that look like the obvious answer and are not, documented so
nobody "fixes" this into them later:

- **`tkinter`** (`Tk().clipboard_get()`) is stdlib but needs the system `tk`
  package. On the machine this was written on, importing it fails outright:
  `libtk8.6.so: cannot open shared object file`.
- **`pyperclip`** reads nothing itself on Linux — it shells out to
  `xclip`/`xsel`/`wl-clipboard` or uses Qt/GTK bindings. It would be one more
  dependency failing in exactly the same places.

What makes it work with **nothing installed** on KDE is Klipper over D-Bus
(`qdbus6`, or `gdbus` from glib2). `gdbus` returns GVariant — `('text',)` —
parsed with `ast.literal_eval` (not `eval`: it executes nothing), with a
manual unwrap as backup.

Gamescope (Deck game mode) has neither Klipper nor `wl-paste`. That case is
reported to the user, not swallowed.

`read_clipboard()` catches **every** exception per source, deliberately: it
runs on the frame-drawing thread, and no system tool misbehaving should take
the app down over a failed paste.

**`Ctrl+V` is bound inside `_open_text_prompt`, not in `self._shortcuts`** —
that table is exactly what `_release_shortcuts` drops when the prompt opens,
and this is the one binding that must be live *while* typing. Panda3D emits
`"control-v"` because `ShowBase` registers Control as a ButtonThrower
modifier (`ShowBase.py:1722-1727`).

**Gamepad X pastes when the prompt is open.** No free button was left, and
none was needed: pad input never goes through the keyboard, so X already
reached `_on_filter_key` while typing and just returned on `self._typing`.
Context-dependent meaning is how A and B already work.

Control characters are stripped **on accept** as well as on paste
(`strip_control`). If `DirectEntry` ever inserted the 0x16 of Ctrl-V itself,
it would sit invisibly inside the URL and the store would reject the code
with nothing to see.

## OAuth: why the three logins are copy-paste (and why Steam has none)

GOG, Epic and Amazon pin their `redirect_uri` to a domain of their own — we
use their official clients' credentials and cannot register `localhost`. The
browser never comes back to us, so short of embedding a whole browser, pasting
is the only way.

**Steam has no login at all.** It briefly had one (OpenID, to fill in the
SteamID), and it was removed: Steam grants third parties no library access, so
the API key stayed mandatory and the "login" only saved typing 17 digits — at
the cost of a whole flow and of pretending Steam works like the others. It is
configured with its key and ID, as plain fields in Cuentas.

`auth/paste.py` takes the whole URL, the JSON Epic displays, or a bare code.
If the text is a URL or JSON that does *not* contain the code, it returns ""
rather than passing the URL along as if it were one — that only earns a 400
and makes the user think they picked the wrong account.

## Las tiendas marcadas deciden DOS cosas

El ajuste "TIENDAS A CARGAR" (Opciones → Tiendas) gobierna:

1. **De qué tiendas se escanea** — `pipeline.load_library.load_library`
   construye su lista de tiendas desde la config y salta las desmarcadas. Ya
   funcionaba.
2. **Qué juegos se enseñan** — esto faltaba: los juegos de una tienda
   desmarcada seguían en el carrusel y en la lista de la TUI.

Lo segundo lo resuelven `library_ops.active_stores()` e
`is_in_active_stores(game, activas)`, que aplican **las dos interfaces al
pintar**: `gui3d._visible_entries` (junto a los ocultos y los filtros) y
`tui.widgets.game_list.populate_games` (junto a los ocultos).

**No se filtra dentro de `repo.load()`** a propósito. Esa función es la Regla de
Oro —`resolvers` es la única fuente de verdad de qué está en la biblioteca— y
hacerla mentir según un ajuste de presentación rompería a quien la usa para
decidir qué escribir o qué enriquecer. Filtrando al pintar, además, volver a
marcar la tienda devuelve los juegos al instante y en su sitio del orden, sin
releer el disco.

Reglas del filtro:

- Basta con que **una** de las tiendas del juego esté marcada: hay 82 juegos en
  más de una en la biblioteca real, y desmarcar Epic no debe llevarse el juego
  que también tienes en Steam.
- Un juego **sin ninguna tienda conocida se enseña siempre**: no pertenece a
  ninguna desmarcada, así que esconderlo sería inventarse un criterio.
- Desmarcarlas todas deja el carrusel vacío, que es un estado válido.

**Aviso**: con una tienda desmarcada, **Regenerar todo borra sus juegos de la
base de datos** — se vacía entera y solo se repuebla lo marcado. Actualizar no,
porque no borra nada. Es la diferencia entre "no lo veo" y "ya no lo tengo".

## Vaciar una base de datos: NUNCA borrando el fichero

`BaseCacher` mantiene **una conexión abierta por hilo** (`_connect`). En cuanto
hay una abierta, `unlink()` solo quita el nombre del directorio: las conexiones
siguen leyendo y escribiendo en el inodo huérfano, así que la base "borrada"
sigue contestando con los datos viejos y todo lo que se reconstruya después
acaba en un fichero fantasma que se pierde al cerrar la aplicación.

Es lo que hacía `tui/app.py` con su `os.remove(paths.main_db())` al regenerar,
y se destapó al escribir el primer test que lo comprobaba **por los cachers ya
abiertos** en vez de mirando el disco.

Para vaciar de verdad: `BaseCacher.clear_tables()`, que hace `DELETE FROM` de
cada tabla declarada en `SCHEMA` (los nombres se sacan del propio `SCHEMA`, así
que añadir una tabla no obliga a acordarse de nada).

## Operaciones gordas: Opciones → Avanzado

El menú va en dos secciones (`kind="header"`, que no recibe foco): **DATOS**
y **COPIA DE SEGURIDAD**. Las de DATOS tardan minutos y las que tiran algo
preguntan antes:

- **Enriquecer todo** (`update_extras`): vuelve a preguntar duración y notas
  y las escribe ENCIMA, sin vaciar nada. Los enrichers van con
  `overwrite=True`, que es lo que sustituye al borrado — sin él se saltarían
  todo juego que ya tiene valor. Es la primera de la lista porque es la que
  casi siempre se quiere: interrumpirla no cuesta nada.
- **Enriquecer todo DESTRUCTIVO** (`enrich_all`, la `E` de la TUI): vacía los
  extras y vuelve a buscar duración y notas de toda la biblioteca. Los juegos
  se **releen del repositorio después de vaciar**: los que tuviera en memoria
  quien llama conservan sus duraciones, y con `overwrite=False` el enricher se
  saltaría justo lo que se acaba de pedir rehacer. Cortarla a la mitad deja
  sin datos a los juegos que no llegó a procesar, y por eso ya no es la
  entrada por defecto.
- **Restaurar Puntueitor MUY DESTRUCTIVO** (`regenerate_library`, la `R` de la
  TUI; la clave interna sigue siendo `REGENERATE_KEY`): vacía `puntueitor.db`
  entero —`resolvers`, caché de IGDB, extras **y desconocidos**— y lo
  reconstruye. Solo sobrevive `library.sqlite` (terminado, oculto, pendiente,
  favorito), que está en otro fichero justamente por esto: es lo único que no
  se puede volver a pedir a ninguna API.

Las cuatro operaciones son funciones con **nombre propio** en
`core/services/library_refresh.py`, no una sola con banderas: en el sitio de la
llamada tiene que leerse qué se va a perder. `RefreshWorker.start(mode)` elige
cuál, y todas mandan los mismos mensajes, así que el drenaje del carrusel no
distingue: un juego que llega es "este juego, con más datos".

`regenerate_library` vacía **la base del repositorio que recibe**
(`repo.cache_dir`), no `paths.main_db()`: son la misma en producción, pero un
repositorio apuntado a un temporal —los tests hacen justo eso— habría borrado
el fichero de verdad del usuario.

En el carrusel, regenerar invalida además el carrusel de desconocidos: su tabla
estaba en la base que se acaba de vaciar.

### Regenerar vacía el carrusel y lo va llenando

Al confirmar, `_clear_carousel()` destruye TODAS las cajas en el acto
(`Carousel.clear`) y los juegos van reapareciendo por el camino de siempre
(`_add_game_entry`) según los resuelve el pipeline. Al terminar no hay nada
especial que hacer: partiendo de cero no puede haber cajas fantasma de juegos
que ya no existen ni el mismo juego dos veces, que es lo que pasaba antes —
regenerar rehace la identificación y un `igdb_id` puede pasar a ser otro.

El primer intento fue rehacer el carrusel **al terminar**, y estaba mal: durante
los minutos que dura seguías viendo la biblioteca anterior entera. La pantalla
tiene que contar la verdad mientras tanto, y la verdad es que no hay nada.

Destruir de verdad (no esconder) importa: son ~270 MB con la biblioteca real.

### El aviso

`build_confirm_items(..., warning=N)` pinta en rojo (`WARNING_COLOR`) las N
primeras líneas, las que dicen qué se pierde. Solo funciona en rótulos de
sección: en las filas enfocables, `Menu._refresh_focus` reasigna el color al
mover el foco y lo machacaría.

El título es `¡IMPORTANTE!` y no lleva el símbolo ⚠ porque `HussarPrintA.otf`
**no trae el glifo U+26A0** — saldría un hueco, como pasó con los emoji de la
ficha.

## Actualizar la biblioteca (R2 / tecla "r")

Es la variante **suave** de la TUI (su tecla `r`) y **solo esa**: vuelve a
preguntar a las tiendas y añade lo que falte, sin borrar nada. La otra (`R`,
"Regenerar TODO") hace `os.remove(paths.main_db())` —se lleva por delante
`resolvers`, la caché de IGDB, los extras y los desconocidos— y son cientos de
peticiones; no está en el carrusel a propósito.

`core/services/library_refresh.py:refresh_library(repo, ...)` es lo que
comparten las dos interfaces. Los dos parámetros que no son intercambiables:

- `refresh=False` — no se vuelve a pedir a IGDB nada ya cacheado, así que una
  biblioteca resuelta apenas toca la red y solo se resuelve lo nuevo.
- `force_store_refresh=True` — el listado de propiedad de Steam **sí** se pide
  siempre; es justamente lo que hace que aparezcan los juegos comprados desde
  la última vez.

El **borrado destructivo se queda en `tui/app.py:do_reload`**, no detrás de un
parámetro de la función compartida: es la única parte irreversible y tiene que
estar a la vista de quien la ofrece.

Los tres callbacks (`on_game`, `on_progress`, `on_enriched`) se llaman **desde
hilos que no son el de la interfaz** — `on_enriched` viene del pool de cuatro
del pipeline —, así que solo pueden encolar. En gui3d lo hace
`refresh.RefreshWorker`, del mismo molde que los otros tres trabajadores (hilo
propio daemon, `poll()` desde `_update`, `shutdown()` en `destroy()`), con los
tres tipos de mensaje **en la misma cola** para que lleguen en orden: si el
"he terminado" adelantara al último juego, se escondería el progreso antes de
meter la última caja.

En el carrusel, además:

- Las cajas nuevas entran según llegan, pero `_apply_order()` se llama **una
  vez por frame** aunque hayan llegado varias: recoloca las 1266 cajas.
- La selección **se conserva** (sin `reset_selection`), al contrario que la
  TUI, que salta al primero.
- Un juego que ya tiene caja no se duplica: se le copian los `EXTRA_FIELDS` y
  se repintan sus etiquetas, que es como llegan los enriquecidos.
- Los juegos que ya no estén en las tiendas **no se quitan**, igual que en la
  TUI: la suave solo añade.
- Queda inerte escribiendo y en modo desconocidos, y una segunda pulsación no
  lanza otra actualización (`RefreshWorker.start()` devuelve False).

El progreso es un `OnscreenText` propio bajo el avisador, no el `Notifier`:
ese es de usar y tirar (entra, aguanta dos segundos y se va) y esto tiene que
quedarse los minutos que dure.

Los iconos `ICON_GAMEPAD_R2` (`0x21B3`, continúa la serie L1/R1/L2) e
`ICON_KEYBOARD_R` (`0xFF32`) se verificaron contra `PromptFont.otf` antes de
usarlos, como pide la nota de `fonts.py`: un codepoint inventado no avisa,
dibuja el glifo equivocado en silencio.

## Modo desconocidos (arriba sobre el carrusel)

Los juegos de `unknown_games` (los que no se pudieron casar con IGDB) tienen su
propio carrusel: **arriba** entra, **abajo** o **B** vuelve. Cajas negras
(`UNKNOWN_BODY_COLOR`) con el título escrito encima, porque sin ficha de IGDB no
hay carátula y una caja negra sin nada no se distingue de la de al lado.

La lógica vive en **`core/services/unknown_actions.py`**, compartida con la TUI
(mismo contrato que `game_actions.py`: sin UI, imports de red dentro de la
función, nunca lanza). Lo delicado, que costó descubrir la primera vez:

- `resolve_by_store` **quita el desconocido de la tabla antes** de resolver,
  porque `BaseResolver.resolve` se salta lo ya marcado y si no devolvería vacío
  sin intentarlo. Como consecuencia, **los tres caminos de fallo tienen que
  volver a apuntarlo** (tienda no soportada, sin resultados, excepción): si se
  pierde ahí, el juego desaparece de las dos listas y no hay forma de volver a
  él. Hay un test por camino.
- `adopt_result` escribe `resolvers` **antes** de quitar de `unknown_games`: al
  revés, un fallo en medio dejaría el juego fuera de las dos.
- `AdoptResult.unsupported` no es un error: esa tienda (Amazon) no tiene
  resolver propio y lo que hay que decir es "búscalo por título".

### El carrusel secundario

`Carousel` toma `body_color` y `cover_caption` — dos parámetros, no una
subclase, porque es lo único que cambia. Con `cover_caption` la caja lleva
`case_labels.build_cover_caption` (un `TextNode` blanco) **en vez de** las
pegatinas de estado: un desconocido no está en la biblioteca y no tiene estados.
El texto no se pinta en la textura porque `make_placeholder_texture` genera un
color plano de 2×2 cacheado **por color**, y meterle texto obligaría a una
textura por juego.

Se construye **perezosamente** al entrar (48 cajas ≈ 50 ms) y **no se entra si
no hay ninguno**: `Carousel` lanza `ValueError` con lista vacía. Lo mismo al
adoptar el último: se sale del modo y se desmonta antes de que `remove_entry` lo
deje vacío. `_invalidate_unknown_carousel()` lo tira cuando la tabla cambia por
detrás (al desconocer un juego), en vez de mantenerlo sincronizado a mano.

Las claves son la tupla `(store, id)`, que no puede chocar con los `igdb_id`
enteros del carrusel principal.

**`Carousel` copia la lista de entradas** (`list(entries)`). Antes la compartía
con `app.entries`, y al adoptar un juego el `append` de App dejaba una entrada
sin caja: `_layout` se salía de `_boxes` por el final con un `IndexError`.
`add_entry` solo hace *append* por la misma razón que `_order` guarda índices:
insertar en medio los invalidaría todos.

### El modo en `app.py`

`active_carousel` (propiedad) es lo que evita bifurcar veinte métodos. Sustituye
a `self.carousel` **solo** en lo que sigue a lo que se ve: navegar, la ficha, el
fondo, el acento de los menús y el `update(dt)`. Las carátulas
(`_request_nearby_covers`, `_on_cover_ready`, `_backfill_covers`) y todo lo que
ordena o filtra siguen apuntando **al principal**: con `active_carousel`
machacarían los placeholders negros.

El flanco de arriba/abajo se **sondea** en `_update_mode_switch` (como
`_update_menu_cycle`) en vez de escucharse como evento: el stick no emite
eventos, solo se puede leer su posición, y así teclado y mando siguen el mismo
camino. Devuelve 0 con un menú abierto —allí el eje vertical es del menú— y
`_reset_navigation` limpia `_mode_v_direction`, o al cerrar un cuadro de texto
con el stick a medio soltar se cambiaría de modo solo.

Filtros, orden, scoring, etiquetas, ocultos y saltos de grupo quedan inertes
(`_blocked_in_unknown_mode`), avisando en vez de callando: pulsar y que no pase
nada parece un cuelgue. Opciones sigue disponible — hay que poder salir.

La franja de abajo es un `unknown_frame` hermano, como `scoring_frame`, con
Tienda / ID / "N de M" y **su propia barra de ayuda**: así no hay que hacer
variable `help_text`, que es `mayChange=False` porque no cambia nunca.

### La búsqueda

Va en un hilo (`gui3d/unknowns.py`, `UnknownWorker`, mismo patrón que
`EnrichWorker`): la TUI puede permitirse bloquear su hilo mientras IGDB
contesta, pero aquí serían segundos a 0 fps con las cajas paradas a media
animación. Al encolar se cierran los menús y se avisa. El trabajo recuerda
**sobre qué desconocido** se pidió, así que navegar mientras tanto no rompe nada
—los resultados se abren para el original, como `_game_menu_entry`—; si se ha
salido del modo, se descarta.

## Puntueitor3D menu (Opciones → Puntueitor3D) y `gui3d.json`

Dos ajustes propios del frontend 3D, en `state.Preferences`, persistidos en
`gui3d.json` bajo la clave `"preferences"` (los filtros van bajo `"filters"`;
`save_*` conserva las claves ajenas, así que ambos conviven):

- **Puntuación mostrada** — cuál de las tres notas se pinta en la estrella de
  la caja. El valor guardado es `"steamdb"`/`"user"`/`"critic"`, y
  `case_labels.score_field()` lo traduce al campo de `Game`; a propósito no se
  guarda el nombre del campo, para que renombrarlo en el modelo no invalide
  los ficheros ya escritos. `load_preferences` valida contra `SCORE_SOURCES`
  porque el fichero es editable a mano.
- **Cargar filtros al inicio** (`Preferences.remember_filters`) — en `No` los
  filtros **no se borran**, solo se dejan de leer al arrancar y de escribir.
  Reactivarlo recupera los de la última vez. El rótulo nombra la mitad que se
  nota; el campo nombra las dos, porque gobierna también `_persist_filters`.

Como los menús de Cuentas y Tiendas, se edita sobre una **copia**
(`_gui3d_prefs = dataclasses.replace(self.prefs)`) y solo se aplica al pulsar
"Guardar", así que salir con B descarta. Antes se guardaba en el acto y era el
único menú que se comportaba así.

El repintado de las cajas va en el Guardar, no al cambiar el valor:
`Carousel.set_score_source` recorre **todas** las cajas, no solo las visibles
—una caja fuera del radio acabará entrando al navegar y se vería con la nota
anterior, el mismo motivo que documenta `set_labels_visible`— y hasta el
Guardar la copia es solo intención, no hay nada que pintar. Además
`set_score_source` corta en seco si la nota no ha cambiado, así que guardar sin
haber tocado esa opción no cuesta el recorrido.

`tools/entorno-prueba.sh <dir>` monta un entorno aislado y arranca la app en
él (`--3d`, `--shell`, `--copiar-config`, o `-- comando`). Úsalo para
cualquier prueba manual en vez de lanzar la app a pelo.

Al probar gui3d, **aislar con `HOME`, no enumerando variables `XDG_*`**. Ya
pasó: un lote de pruebas sandboxeó `XDG_DATA_HOME`/`CONFIG`/`CACHE` pero se
dejó `XDG_STATE_HOME`, y como `gui3d.json` vive en `state_dir()` acabó escrito
en el directorio real del usuario. `HOME` cubre las cuatro de una vez.

## Sample data is display-only, and must be purged on first real game

`build_sample_entries()` (six fake games) is shown when `build_real_entries()`
returns None — empty library, or no game with a cover. **Nothing about it is
ever persisted**; it is dicts in memory.

The trap: the real/sample decision happens once, in `__init__`
(`app.py:488`), and a SOFT refresh does not clear the carousel — correctly so,
since with a real library you do not want a blank screen for the minutes a
refresh takes. So real games used to pile up on top of the six fakes, which
survived until restart. `self._sample_mode` records which branch was taken,
and `_on_game_refreshed` clears the carousel on the first real game.

Two details that are load-bearing:

- The purge runs **before** the `igdb_id` dedup lookup. Sample entries use ids
  0-5, which IGDB also issues for real; purging afterwards would let a real
  game with such an id overwrite a dummy instead of getting its own box.
- It fires on the **first arriving game**, not at job start, so a refresh that
  yields nothing leaves the samples rather than an empty carousel.

`_persist_flags` also refuses to write in sample mode — those flags would land
in `library.sqlite`, the one database that cannot be regenerated.

## Config menus (Opciones → Cuentas / Tiendas)

There are **two** menus over the same config, and Cuentas comes first in
Opciones — nothing loads without credentials, so everything else in that menu
operates on games that do not exist yet.

- **Cuentas** (`build_accounts_items`): IGDB id/secret, Steam user id/API key,
  and login rows for GOG/Epic/Amazon.
- **Tiendas** (`build_settings_items`): the four store checkboxes.

Each mirrors the matching TUI screen (`tui/screens/accounts.py`,
`tui/screens/configuration.py`).

**Steam is a text field, not a login row, and that is deliberate.** Steam has
no third-party OAuth: its OpenID only says who you are and hands over no
token, so the API key is needed either way. Showing it like GOG implied that
going through the browser finished the job. `SETTINGS_ACCOUNTS` and
`accounts.CON_SESION` both exclude it; `sessions_summary()` iterates
`CON_SESION` and not `Stores` for the same reason.

**Every "Opciones → X" string in a user-facing message must name a menu that
exists, and the right one.** When credentials moved to Cuentas, half a dozen
warnings kept pointing at Configuración through an entire refactor — and those
are precisely the lines someone reads when nothing works.
`tests/test_indicaciones.py` greps the source for them and fails on both
mistakes: a menu that no longer exists, and credentials pointed at Tiendas.

Both menus share `self._settings` and `_save_settings` (`_open_config_form`).
One copy per menu would mean saving in one clobbers what was edited in the
other. `_refresh_settings_menu` repaints via the remembered `_settings_builder`
rather than assuming which menu is on screen.

The accounts rows are **not** edited on the copy like everything else here.
Logging in takes effect the moment the token comes back, so backing out with B
cannot undo it — they read their state from `accounts.sessions_summary()` and
the builders take it as a separate `sessions` argument for exactly that
reason. Mixing it into `values` would have told the user "B cancels this",
which would have been a lie.

`igdb_client_secret` and `steam_api_key` are **masked in the list** (`••••••••`)
but shown in clear **while editing**: you can't fix a one-character typo in a
key you can't see, and opening the editor is already a deliberate act. If that
trade-off is ever revisited, `DirectEntry` has an `obscured` option.

Everything is edited on a **copy** and only written on "Guardar", so backing out
with B leaves the config untouched. That matters more here than in the scoring
forms — these are the credentials, and losing them to a stray button press is a
different class of mistake. `ConfigManager.save()` also preserves unknown
on-disk keys, so saving can't drop anything it doesn't model.

Anything that covers a menu must **hide it first**: `Menu.hide()`/`show()`
preserve focus, unlike `open()` which resets it to the first row. The text
prompt is smaller than a menu, so drawn on top the menu's rows showed around
and under it and you read both at once. The same pair is what makes returning
from a submenu land on the row you left from rather than the first one — using
`open()` there silently sent focus back to the top.

**`MAX_VISIBLE_ITEMS` is 16, not 10.** The first version used 10 and quietly
made the *filter* menu scroll — it has 15 rows and used to fit. Both real long
menus (filters and settings) are 15 rows; the genre list at 26 still scrolls.
Above ~18 rows a panel fills the screen top to bottom (18 rows measure 1.77 of
the 2.0 available), so that's the ceiling.

## Scoring menu (scoring_info.py, scoring_config.py)

Mirrors the TUI's `tui/screens/scoring.py` + `scoring_config.py`: the four
systems listed, the focused one's description in a bar along the bottom, A
applies it, X opens its config form.

Applying goes through `LibraryService.score()` — the exact call the TUI makes —
and the returned `scores_map` becomes a throwaway sort criterion
(`sorting.scorer_criterion`). That's what guarantees both frontends rank
identically with the same config; the test asserts the gui3d order equals
`LibraryService`'s directly rather than trusting it.

The descriptions are **copied** from the TUI, not imported: that module is
Textual, and importing it would drag the whole TUI into the 3D app for five
strings. Edit both if they change. The *keys* (`mixed`/`weighted`/`time`/
`genre`) must stay identical — `LibraryService.score` dispatches on them.

Config forms come in three shapes (`Scorer.config`): `weights` (three
percentages that must total 100), `hours`, `genres`. Numbers are adjusted with
**left/right, ±1 per step** (held down they repeat, faster than list
navigation — 40→60 is twenty steps); A does nothing on them, so there's only
one way to change a value. Weights and hours are edited on a **copy** and only
written on "Guardar": distributing three percentages means passing through
invalid totals on the way (you lower one to raise another), so validating per
change would make them uneditable. Percentages are shown 0-100 but stored as
fractions, same as the TUI.

Refreshing such a form must **not** call `set_items` — that resets focus to the
first row, so holding left on "Usuarios" moved it one step and then silently
kept decrementing "Críticos". Mutate the existing items' `value`/`label` and
call `Menu.refresh_values()`, which only rewrites the text.

The gamepad's X must be wired to `_on_filter_key`, not `_open_filter_menu`:
the former is what knows X means "configure" inside the scoring menu. Bound to
the latter, only the keyboard `x` could open a config form.

Scoring settings live in their **own file**, `scoring.json`
(`paths.scoring_file()`), read/written by `load_scoring()`/`save_scoring()` —
used by both frontends *and* `LibraryService`, so they can't diverge.
`config.json` keeps only credentials, store toggles and paths. The split is
deliberate: the scoring values are rewritten every time you nudge a weight,
and that file used to also hold `steam_api_key` and `igdb_client_secret`.
Field names keep the `scoring_` prefix even though it's redundant there, so
readers didn't have to change and migration is a literal key copy.

`load_scoring()` **migrates on first run**: if `config.json` still carries
`scoring_*` keys they're copied out and then stripped. Order matters — the new
file is written *first*, so an interruption leaves the values duplicated
(harmless, `Config` ignores unknown keys) rather than lost. `ConfigManager.save()`
also preserves on-disk keys it doesn't know about, so a half-migrated file
can't be truncated by an unrelated save.

Both files are written with `write_json_atomic` (temp + `os.replace`). The old
`open(path, "w")` truncates *immediately*: any failure mid-dump left a
half-written `config.json`, i.e. no API keys. Same reasoning as the cover
downloads in `gui3d/covers.py`.

`ConfigManager` is a process-wide **singleton that writes the user's real
config file**, and it caches its directory on first instantiation.
`tests/conftest.py` now has an **autouse** fixture isolating every test
(deletes the `XDG_*` vars, patches `Path.home`, resets the singleton) — per-test
isolation kept failing by omission. Two traps it does not protect you from:

- **`monkeypatch.undo()` inside a test undoes the fixture too**, putting the
  rest of that test back on the real files. It happened: a test of atomic
  writes called `undo()` and migrated the real config. Use
  `with monkeypatch.context() as m:` to revert one patch.
- Don't point the `XDG_*` vars at the temp dir instead of deleting them:
  `paths.py` prefers them over `Path.home()`, so tests that hand-write into
  `tmp_path/".config"` would read a different directory than the code writes.

Two layout consequences this feature forced:

- **The description bar reuses the ficha's strip** (same `FICHA_BAR_TOP_Z`),
  which is free because the ficha is animated away whenever a menu is open. The
  scoring menu itself is raised (`Menu.set_center_z`) or its centred panel
  overlaps that strip.
- **`Menu` scrolls past `MAX_VISIBLE_ITEMS`.** The genre list has 23 entries and
  a full-height panel ran off both ends of the screen, title out of frame and
  "Restaurar" cut off. The window follows focus and sticks at the ends; panel
  height is *fixed* while scrolling (rather than measured from the visible rows)
  so it doesn't jump as shorter header rows scroll through, and all row texts
  are still created — only the off-window ones hidden — so the measured panel
  width can't change as you scroll.

## Filters (filters.py, text_prompt.py)

`Filters` holds name / max duration / finished / favorite / backlog, and
`matches()` is the single place that decides whether a game gets in.
`app._visible_entries()` combines it with the hidden-games switch, so filtering
and sorting compose through the same path as everything else.

The three state filters are **tri-state**, not boolean: unset / only-yes /
only-no. A bool can't express "don't care", which is what they are almost
always. Left/right cycles them, edge-triggered rather than hold-repeat — with
only three values a slightly long press would wrap past the one you wanted.
The edge is detected by polling in `_update_menu_cycle` so keyboard and pad go
through one path.

A game with **unknown duration fails** the max-duration filter. The filter says
"lasts at most X" and we don't know that it does; letting it through would
assert something not on record.

**A filter that matches nothing now applies anyway** and leaves the carousel
empty, with a "Ningún juego coincide" notice. It used to be refused because the
carousel couldn't be empty, which left filters set and the whole library on
screen — three things disagreeing at once. The empty carousel is the honest
answer.

The **text prompt is the dangerous part**. A focused `DirectEntry` does *not*
stop Panda3D dispatching key events through the messenger — verified — so
typing "o" would still toggle hidden games and "x" would open a menu on top.
`app` therefore drops its shortcuts while the prompt is open
(`_release_shortcuts`) and re-binds on close, with two deliberate exceptions:
`escape` stays bound (it can't be typed, and it's how you cancel) and `enter`
is released (the `DirectEntry`'s own `command` handles it — leaving it bound
fires both and applies the text twice).

**The re-bind must be deferred one frame** (`_close_text_prompt` schedules
`_rebind_shortcuts_task`). Pressing Enter queues *two* events in the same batch:
the `DirectEntry`'s `accept`, and right behind it the raw `"enter"` from the
ButtonThrower, which having focus in the entry does not suppress. Re-binding
inside the first handler meant the second one found `_on_confirm` listening
again, and since menu focus was still on "Nombre" it reopened the prompt
instantly. The symptom looked like "Enter does nothing" — the filter *was* being
applied, the box just reappeared. Diagnosed by driving real X keystrokes into a
real window with XTEST (python-xlib); `accept_text()` called directly from a
test never goes near this path and passes happily. Gamepad buttons don't go through the
keyboard at all, so every pad-reachable action checks `self._typing`, including
navigation: otherwise the stick would keep scrolling the carousel behind the
prompt.

Menu rows can carry a `value` rendered as `Label  <value>`. Changing one calls
`Menu.refresh_values()`, which only rewrites the label text — rebuilding the
menu would send focus back to the first row on every keypress, and the panel is
deliberately *not* re-measured so a longer value can't make the menu jump width
mid-use.

## Sorting and the L1/R1 group jump (sorting.py)

`sorting.py` owns the sort criteria (`title`, `user_score`, `critic_score`,
`steamdb`, `duration` — the TUI's keys except `steamdb`, which it doesn't
offer). Each defines the value it sorts by, the direction, the **group** that
value falls in, and how that group is named on screen. Default directions match
the TUI's: name and duration ascending, scores descending.

Group labels are per-criterion for a reason. Scores name *which* score they are
("Usuarios: 95", "Crítica: 90", "SteamDB: 85") — the notification doesn't say
which sort you came from, so a bare "Puntuación: 95" wouldn't tell you. They
show only the low end, not a range: scores top out at 100, so the last bucket
came out as `100-104`, an interval that can't exist and holds exactly one value.
Durations *do* show the range ("Duración: 5-9 h") because hours have no ceiling.
Names say "Letra: A", falling back to "Inicial: 1" for titles starting with a
digit ("112 Operator"), which form their own group and aren't a letter.

An earlier `mixed` criterion computed the score through `MixedScore` +
`ConfigManager`, mirroring `LibraryService.sort`. It was replaced by SteamDB's
score: it's a plain stored field, it drops the config dependency, and it sorts
by the very number already printed on each box's sticker. Note the sticker
*rounds* (`94.95` → "95") while the bucket *floors* (→ the 90 group), so a box
can read 95 while the jump says "Puntuación: 90". That's display rounding, not a
mis-sorted entry.

`order_entries()` returns `(keys, groups)` *together*, and that pairing is the
whole design. The group is always derived from the same value the sort used, so
the jump can't land somewhere that disagrees with what's on screen. The carousel
stores the group boundaries once (`_group_starts`) and `jump_to_group` is then a
`bisect` — no walking 1266 entries per button press.

Jump semantics, per the spec: R1 goes to the **first** entry of the next group,
L1 to the **first** entry of the previous group (not the last, and not the start
of the current one), wrapping at both ends. "No games with that letter" needs no
special handling — walking the boundaries of the *actual* sorted list skips
absent groups for free (verified: 3 → 6 → 8 with no 4, 5 or 7 in the library).

Two things that follow from the grouping, not from taste:

- Name sort uses `title.lower()`, **not** `title_normalized`. The latter strips
  punctuation for IGDB matching, so grouping by its initial would put games in
  letters that don't match what's printed on screen. `real_data`'s
  `title_normalized` sort is now only the stable-sort tiebreak.
- Games with **no value** (no score, unknown duration) go last in their own
  group, whichever the direction. Treating them as zero would float them to the
  top of an ascending sort, and a game with no score is not a bad game.

`mixed` reuses `MixedScore` with `ConfigManager`, exactly like
`LibraryService.sort`, so both frontends rank identically. `ConfigManager` is
imported lazily inside the value factory — it reads from disk and is pointless
if you never sort by that criterion. The strategy is built once per sort, not
per game.

L1/R1 are real buttons (`lshoulder`/`rshoulder`), unlike the triggers — they
arrive as events with no polling.

Transient messages go through `notifications.Notifier` (top-right, at the
title's height): fade in 1 s, hold 2 s, fade out 1 s, driven by one `Sequence`.
One message at a time and a new one replaces whatever is showing — these are
"you just did this" acknowledgements, so the newest is the only one worth
reading. Two details that matter: the text node needs
`TransparencyAttrib.M_alpha` or the alpha in `set_color_scale` does nothing,
and a replacing message must `finish()` the running sequence first, otherwise
its `startColorScale` fights a still-live interval on the same node. `TEXT_Z`
duplicates `app.TITLE_TEXT_Y` deliberately — importing it would make the
dependency circular, so moving the title means moving this too.

L2 is **not a button**: on an Xbox pad it's `Axis.left_trigger`, and Panda3D
doesn't even report the equivalent button as known. It's polled per frame in
`GamepadInput.update()` with two thresholds (press 0.6 / release 0.35). The
hysteresis is not optional — analog triggers don't reliably rest at 0, and with a
single threshold a trigger hovering near it re-fires the toggle every frame.

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

## Copias de seguridad (`core/services/backup.py`)

Toda la instalación a un zip y de vuelta, desde las dos interfaces. Cuatro
cosas que costaron y que no se deducen leyendo el código:

**El zip guarda por PREFIJOS, no por rutas reales** (`config/`, `data/`,
`cache/`, `state/`). Una copia hecha en una máquina tiene que restaurarse en
otra donde el usuario se llame distinto o las XDG_* apunten a otro sitio.

**Las bases SQLite se copian con `Connection.backup`, no con `shutil`.** Van
en modo WAL y ABIERTAS por la aplicación que hace la copia, así que copiarlas
por bytes deja fuera lo último que hizo el usuario. Y el origen se abre en
lectura-escritura, no con `mode=ro`: para leer el `-wal` hace falta el índice
`-shm`, que una conexión de solo lectura no siempre puede abrir.

**Al restaurar se escribe en un fichero NUEVO y se pone en su sitio con
`os.replace`.** Con `open(destino, "wb")` se trunca el fichero existente
—mismo inodo que SQLite tiene abierto— y las conexiones vivas vuelcan su
estado encima al cerrarse: la base restaurada se quedaba con el esquema y
cero filas, y el carrusel enseñaba los juegos de muestra
(`build_real_entries() or build_sample_entries()`). Es la trampa de "vaciar
una base de datos" de más arriba, pero al revés. Además se borran los
`-wal`/`-shm` que hubiera al lado: un WAL de la base anterior revierte o
corrompe lo recién restaurado.

**Después de restaurar se sale con `os._exit(0)`**, no con el cierre normal:
un cierre ordenado escribe por su cuenta (gui3d guarda sus filtros encima del
`gui3d.json` recién restaurado).

Y la restauración **rechaza** entradas del zip con `..`, con ruta absoluta o
fuera de los cuatro prefijos: el destino son carpetas reales del `$HOME`, así
que sin eso un zip preparado escribe donde quiera (zip-slip).

## El log (`core/logging_setup.py`, `core/diagnostics.py`)

`setup_logging(frontend)` lo llaman los dos puntos de entrada **después** de
`paths.migrate_legacy_paths()`. No se configura al importar: gui3d hacía un
`basicConfig` sin fichero al importar su módulo, así que lanzado desde Steam
no dejaba ni una línea en ninguna parte.

`describe_error(error, servicio)` es el único sitio que traduce una excepción
a una frase accionable, y la distinción que importa es **no confundir "no hay
internet" con "tus credenciales no valen"**: mandar a revisar unas claves que
estaban bien hace perder el rato e invita a romperlas. Se mira el tipo y el
`response.status_code`; nunca se hace una petición para "comprobar si hay
internet".

Regla dura: **en el log nunca entra el VALOR de una credencial**, solo su
nombre. El log se comparte para pedir ayuda. Hay tests que lo fijan, y la URL
de Steam se registra sin sus `params` porque la API key viaja ahí.

## Editor Rápido (R3 / tecla "e")

Marca los cuatro estados con el stick derecho sin abrir menús. La tabla de
gestos vive en `menus.EDITOR_FLAGS` / `EDITOR_KEYS` —dato, no comportamiento—
para poder probarla sin ventana.

- El stick se lee **por flanco** (`_update_editor`) y con **histéresis** en
  `gamepad_input.right_stick()`: se cuenta al pasar de 0.7 y no se vuelve a
  contar hasta bajar de 0.3. Con un solo umbral, un empujón real dejaba en el
  log el estado marcado y desmarcado cuatro veces — el eje tiembla y al
  soltarlo rebota. Aquí cada empujón ESCRIBE en la base de datos.
- **Un solo eje**: en diagonal gana el de mayor valor absoluto. Marcar dos
  estados de una sacudida es lo que haría desconfiar del modo.
- `hidden` se aplica **al salir** del modo (`_hidden_filter_dirty`), como en
  el menú de juego: re-filtrar en caliente quita de debajo la caja que estás
  marcando.
- La persistencia es `_persist_flags`, compartida con el menú de juego, y
  manda LOS CUATRO estados porque `set_status` reescribe la fila entera.
- El modo bloquea con aviso todo lo que abra algo encima (menú de juego,
  filtros, Puntueitor, Opciones, actualizar y el cambio a desconocidos) y deja
  pasar navegar, etiquetas y ocultos.

## Environment

- Python 3.13 y 3.14 (el `.venv` local es 3.14; la CI prueba las dos)
- Virtual environment: `.venv/`