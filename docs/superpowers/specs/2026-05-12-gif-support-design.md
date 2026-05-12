# Design: Animated GIF Support

**Date:** 2026-05-12
**Status:** Approved

## Context

The Ad Creative Resizer accepts `.gif` files but loses animation — Pillow's `Image.open()` loads only frame 0, and `resize_image_bytes()` outputs a static single-frame GIF. The team uploads animated GIF ad creatives and gets back broken static versions.

**Goal:** Preserve full animation (all frames, timing, loop count) when resizing GIF files, with zero changes to how static images (PNG, JPG, WebP, static GIF) are processed.

**Constraints:**
- Pure Pillow — no new dependencies
- GIF in, GIF out (no format conversion)
- Single upload flow — no workflow change for the team
- Surgical changes only — existing static resize path must be untouched

---

## Design

### What changes in `app.py`

**1. New `resize_gif_bytes(img, target_w, target_h)` function**

Placed immediately after `resize_image_bytes()`. Responsible for animated GIF resizing:

- Iterates all frames via `ImageSequence.Iterator(img)`
- Resizes each frame to `(target_w, target_h)` using `LANCZOS`
- Reads original per-frame durations from `img.info.get("duration", 100)`
- Each frame is converted to `RGBA` before resize (handles palette/transparency safely)
- First frame is saved with `save_all=True, append_images=remaining_frames, duration=durations, loop=img.info.get("loop", 0)` as `format="GIF"`
- Returns `BytesIO` buffer

**2. Routing change in `analyze_assets()`**

At the call site for `resize_image_bytes()`, add a check:

```python
if ext == "gif" and getattr(img, "n_frames", 1) > 1:
    resized_bytes = resize_gif_bytes(img, target_w, target_h)
else:
    resized_bytes = resize_image_bytes(img, target_w, target_h)
```

**3. No other changes**

`find_nearest_size()`, `find_ratio_match()`, `build_zip()`, `build_csv()`, and all UI code are untouched.

### Edge Cases

| Case | Behavior |
|------|----------|
| Single-frame GIF | `n_frames == 1` → existing `resize_image_bytes()`, no change |
| Varying frame durations | Collected per-frame into a list, passed to `save()` |
| GIF with transparency | Each frame converted to RGBA before resize |
| GIF flagged as "needs_client" | CSV-flagged identically to static images |
| GIF already correct size | Status: "correct", no resize needed |
