"""Procedural textures for the board's look: no UI framework imports.

Why textures rather than GL primitives. The previous board drew stones as
`Ellipse` and grid lines at `width=1`, and both alias badly on a phone: GL
gives an ellipse a hard, stair-stepped edge, and a 1-*pixel* line on a
3x-density panel is a hairline that lands on pixel boundaries unevenly, so
the grid reads as grainy rather than as ruled lines. Blitting a
pre-rendered RGBA texture instead gets antialiasing free from the GPU's
linear filtering, and the same gradient that smooths the edge is what makes
a stone look rounded and polished.

Everything here returns a raw RGBA `bytes` buffer plus its dimensions, so
it is plain arithmetic that tests can assert on without a display.
app.py wraps these in Kivy textures and never computes pixels itself.

Row order is top-to-bottom: row 0 is the top of the image. OpenGL treats
the first row of an uploaded buffer as the *bottom*, so app.py flips once
when it creates the texture. That matters because the lighting here is not
vertically symmetric -- the highlight sits above centre.

Sizes are in texels and independent of the display: a stone texture is
generated once and scaled to whatever radius the layout asks for.
"""

from __future__ import annotations

from math import hypot, sin, sqrt
from random import Random
from typing import Sequence, Tuple

__all__ = [
    "RGB",
    "TABLE_WOOD",
    "SLAB_WOOD",
    "GRID_LINE",
    "BLACK_STONE",
    "WHITE_STONE",
    "MARKER",
    "HINT",
    "PANEL_BG",
    "PANEL_EDGE",
    "TEXT",
    "TEXT_MUTED",
    "BUTTON_BG",
    "BUTTON_TEXT",
    "Texels",
    "stone_pixels",
    "disc_pixels",
    "ring_pixels",
    "cross_pixels",
    "soft_shadow_pixels",
    "wood_pixels",
]

RGB = Tuple[float, float, float]

# An aged kaya board on a dark table. Warm and low-contrast on purpose:
# the old boards this is imitating are honey-coloured and yellow with age,
# nothing like the saturated mustard a flat fill tends to land on.
SLAB_WOOD: RGB = (0.784, 0.604, 0.353)
TABLE_WOOD: RGB = (0.161, 0.114, 0.086)
GRID_LINE: RGB = (0.153, 0.098, 0.043)
BLACK_STONE: RGB = (0.075, 0.082, 0.098)  # slate: not pure black, faintly blue
WHITE_STONE: RGB = (0.957, 0.937, 0.886)  # clamshell: warm, never clinical
MARKER: RGB = (0.706, 0.145, 0.129)
# Legal-move dots. Green against the red of the pending-move ring, so
# "you may play here" and "about to play here" never look alike.
HINT: RGB = (0.145, 0.373, 0.212)
PANEL_BG: RGB = (0.129, 0.090, 0.071)
PANEL_EDGE: RGB = (0.298, 0.212, 0.145)
TEXT: RGB = (0.949, 0.906, 0.824)
TEXT_MUTED: RGB = (0.722, 0.639, 0.522)
BUTTON_BG: RGB = (0.263, 0.180, 0.122)
BUTTON_TEXT: RGB = (0.965, 0.929, 0.855)

# (pixels, width, height) -- what every generator returns.
Texels = Tuple[bytes, int, int]


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _byte(value: float) -> int:
    return int(_clamp01(value) * 255.0 + 0.5)


def _coverage(r: float, feather: float) -> float:
    """Antialiased disc coverage at normalised radius `r`.

    `feather` is the width of the soft edge in the same normalised units,
    set by the caller from the texture size so the edge is roughly one
    texel wide however large the texture is.
    """
    if r <= 1.0 - feather:
        return 1.0
    if r >= 1.0:
        return 0.0
    t = (1.0 - r) / feather
    return t * t * (3.0 - 2.0 * t)  # smoothstep, so the edge has no visible seam


def _normalise(vec: Sequence[float]) -> Tuple[float, float, float]:
    x, y, z = vec
    length = sqrt(x * x + y * y + z * z) or 1.0
    return (x / length, y / length, z / length)


# Light from above and to the left, slightly toward the viewer -- the
# convention that makes a shaded circle read as a sphere rather than as a
# flat disc with a smudge on it. y is positive downward.
_LIGHT = _normalise((-0.42, -0.55, 0.72))
_HALF = _normalise((_LIGHT[0], _LIGHT[1], _LIGHT[2] + 1.0))  # for the specular term


def stone_pixels(
    size: int,
    base: RGB,
    *,
    gloss: float = 0.55,
    shininess: float = 24.0,
    ambient: float = 0.34,
    rim: float = 0.16,
) -> Texels:
    """A lit sphere: the polished-stone look, antialiased at the edge.

    Blinn-Phong, which is overkill for a Go stone except that the specular
    highlight is the whole point -- it is what makes slate and clamshell
    look wet rather than printed.

    `gloss` scales the highlight, `shininess` tightens it (slate takes a
    harder, smaller highlight than clamshell), and `rim` adds a faint bounce
    along the lower-right edge so the stone separates from the wood instead
    of dissolving into it.
    """
    if size < 4:
        raise ValueError("stone texture needs at least 4 texels")
    br, bg, bb = base
    feather = 2.0 / size
    buf = bytearray(size * size * 4)
    i = 0
    for py in range(size):
        v = (py + 0.5) * 2.0 / size - 1.0
        for px in range(size):
            u = (px + 0.5) * 2.0 / size - 1.0
            r = hypot(u, v)
            alpha = _coverage(r, feather)
            if alpha <= 0.0:
                i += 4
                continue

            # Sphere normal. Clamped because the antialiased edge samples
            # marginally outside r == 1, where nz would go imaginary.
            nz = sqrt(max(0.0, 1.0 - min(1.0, r * r)))
            diffuse = u * _LIGHT[0] + v * _LIGHT[1] + nz * _LIGHT[2]
            if diffuse < 0.0:
                diffuse = 0.0
            shade = ambient + (1.0 - ambient) * diffuse

            spec = u * _HALF[0] + v * _HALF[1] + nz * _HALF[2]
            spec = (spec ** shininess) * gloss if spec > 0.0 else 0.0

            # Bounce light opposite the key light, strongest right at the
            # edge where the surface turns away from the viewer.
            bounce = rim * (r ** 3) * _clamp01(
                (u * -_LIGHT[0] + v * -_LIGHT[1]) * 0.5 + 0.5
            )

            buf[i] = _byte(br * shade + spec + bounce)
            buf[i + 1] = _byte(bg * shade + spec + bounce)
            buf[i + 2] = _byte(bb * shade + spec + bounce)
            buf[i + 3] = _byte(alpha)
            i += 4
    return (bytes(buf), size, size)


def disc_pixels(size: int, color: RGB, alpha: float = 1.0) -> Texels:
    """A flat antialiased disc, for star points and the last-move dot.

    These are small enough that shading would be invisible, but the jagged
    edge of a GL ellipse at this size is not.
    """
    if size < 2:
        raise ValueError("disc texture needs at least 2 texels")
    cr, cg, cb = color
    r8, g8, b8 = _byte(cr), _byte(cg), _byte(cb)
    feather = 2.0 / size
    buf = bytearray(size * size * 4)
    i = 0
    for py in range(size):
        v = (py + 0.5) * 2.0 / size - 1.0
        for px in range(size):
            u = (px + 0.5) * 2.0 / size - 1.0
            a = _coverage(hypot(u, v), feather) * alpha
            if a > 0.0:
                buf[i] = r8
                buf[i + 1] = g8
                buf[i + 2] = b8
                buf[i + 3] = _byte(a)
            i += 4
    return (bytes(buf), size, size)


def ring_pixels(size: int, color: RGB, thickness: float = 0.16) -> Texels:
    """An antialiased annulus: the ring around a stone awaiting confirmation.

    `thickness` is a fraction of the radius, so the ring keeps its weight
    whatever size it is scaled to.
    """
    if size < 4:
        raise ValueError("ring texture needs at least 4 texels")
    cr, cg, cb = color
    r8, g8, b8 = _byte(cr), _byte(cg), _byte(cb)
    feather = 2.0 / size
    inner = 1.0 - thickness
    buf = bytearray(size * size * 4)
    i = 0
    for py in range(size):
        v = (py + 0.5) * 2.0 / size - 1.0
        for px in range(size):
            u = (px + 0.5) * 2.0 / size - 1.0
            r = hypot(u, v)
            # Outside edge fades out, inside edge fades in; the product is
            # the band between them.
            a = _coverage(r, feather) * (1.0 - _coverage(r / inner, feather / inner))
            if a > 0.0:
                buf[i] = r8
                buf[i + 1] = g8
                buf[i + 2] = b8
                buf[i + 3] = _byte(a)
            i += 4
    return (bytes(buf), size, size)


def cross_pixels(size: int, color: RGB, thickness: float = 0.16) -> Texels:
    """An antialiased X, for marking dead stones during scoring.

    Diagonals are where aliasing is worst -- a GL line across a stone at
    this size looks like a staircase -- so this is a texture too.
    """
    if size < 4:
        raise ValueError("cross texture needs at least 4 texels")
    cr, cg, cb = color
    r8, g8, b8 = _byte(cr), _byte(cg), _byte(cb)
    feather = 2.0 / size
    half = thickness
    reach = 0.82  # arm length, leaving the stone's rim visible
    root2 = sqrt(2.0)
    buf = bytearray(size * size * 4)
    i = 0
    for py in range(size):
        v = (py + 0.5) * 2.0 / size - 1.0
        for px in range(size):
            u = (px + 0.5) * 2.0 / size - 1.0
            # Rotate into the diagonal frame: one axis runs along each arm.
            d1 = abs(u - v) / root2
            d2 = abs(u + v) / root2
            a = 0.0
            for across, along in ((d1, d2), (d2, d1)):
                arm = _smooth_band(across, half, feather) * _smooth_band(
                    along, reach, feather
                )
                if arm > a:
                    a = arm
            if a > 0.0:
                buf[i] = r8
                buf[i + 1] = g8
                buf[i + 2] = b8
                buf[i + 3] = _byte(a)
            i += 4
    return (bytes(buf), size, size)


def _smooth_band(distance: float, limit: float, feather: float) -> float:
    """1 well inside `limit`, 0 outside, smoothstepped across `feather`."""
    if distance <= limit - feather:
        return 1.0
    if distance >= limit:
        return 0.0
    t = (limit - distance) / feather
    return t * t * (3.0 - 2.0 * t)


def soft_shadow_pixels(size: int, strength: float = 0.42) -> Texels:
    """A blurred black blob, blitted under each stone.

    Contact shadow is doing more work here than it looks: without it the
    stones sit *in* the wood rather than *on* it, and the board reads flat
    no matter how well the stones themselves are shaded.
    """
    if size < 4:
        raise ValueError("shadow texture needs at least 4 texels")
    buf = bytearray(size * size * 4)
    i = 0
    for py in range(size):
        v = (py + 0.5) * 2.0 / size - 1.0
        for px in range(size):
            u = (px + 0.5) * 2.0 / size - 1.0
            r = hypot(u, v)
            if r < 1.0:
                falloff = (1.0 - r) ** 1.8
                buf[i + 3] = _byte(strength * falloff)
            i += 4
    return (bytes(buf), size, size)


def _noise_table(rng: Random, count: int = 2048) -> list:
    return [rng.random() * 2.0 - 1.0 for _ in range(count)]


def wood_pixels(
    width: int,
    height: int,
    base: RGB = SLAB_WOOD,
    *,
    seed: int = 7,
    grain: float = 0.055,
    speckle: float = 0.022,
    vignette: float = 0.13,
    sheen: float = 0.10,
) -> Texels:
    """Wood grain with a varnish sheen and a darkened edge.

    Grain is a few sine waves across x whose phase drifts with y, which is
    enough to look like sawn timber once it is stretched over the board and
    softened; `speckle` breaks up the regularity so the waves do not read as
    a pattern. The sheen is a broad diagonal brightening -- the reflection
    of a room in a lacquered surface -- and the vignette darkens the rim so
    the slab looks like a solid block with thickness.

    Deterministic for a given seed: the board should look the same every
    launch, and a test can assert on exact bytes.
    """
    if width < 2 or height < 2:
        raise ValueError("wood texture needs at least 2x2 texels")
    rng = Random(seed)
    noise = _noise_table(rng)
    n = len(noise)

    # Each wave gets its own frequency, amplitude, phase and a little
    # y-drift so the grain wanders instead of running dead straight.
    waves = []
    for k in range(4):
        waves.append(
            (
                (2.0 + k * 3.7) * (0.8 + 0.4 * rng.random()),  # cycles across x
                (1.0 / (k + 1.4)) * (0.6 + 0.8 * rng.random()),  # amplitude
                rng.random() * 6.283,  # phase
                (rng.random() - 0.5) * 2.4,  # drift with y
            )
        )
    amp_total = sum(abs(w[1]) for w in waves) or 1.0

    br, bg, bb = base
    buf = bytearray(width * height * 4)
    i = 0
    for py in range(height):
        fy = py / (height - 1)
        for px in range(width):
            fx = px / (width - 1)

            g = 0.0
            for cycles, amp, phase, drift in waves:
                g += amp * sin((fx * cycles + fy * drift) * 6.283 + phase)
            g /= amp_total

            # Max-norm distance, so the darkening follows the slab's square
            # edge rather than bulging in a circle.
            edge = max(abs(fx - 0.5), abs(fy - 0.5)) * 2.0
            dark = vignette * (edge ** 3)

            band = 1.0 - abs((fx * 0.72 + fy * 0.28) - 0.34) * 2.6
            shine = sheen * _clamp01(band) ** 2

            factor = (
                1.0
                + grain * g
                + speckle * noise[(px * 131 + py * 977) % n]
                - dark
                + shine
            )
            buf[i] = _byte(br * factor)
            buf[i + 1] = _byte(bg * factor)
            buf[i + 2] = _byte(bb * factor)
            buf[i + 3] = 255
            i += 4
    return (bytes(buf), width, height)
