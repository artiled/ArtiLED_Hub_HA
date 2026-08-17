# Third-party components

ArtiLED's own code in this repository is proprietary (see the Copyright section
of `README.md`). The bundled browser libraries below are not ours and keep their
own licences. Their full texts are in `LICENSES/`.

Nothing here is minified by us, re-headered, or relicensed.

| File | Upstream | Version | Licence | Obligation |
|---|---|---|---|---|
| `frontend/iro.js` | [jaames/iro.js](https://github.com/jaames/iro.js) | 5.5.1 | **MPL-2.0** | ⚠ **modified — see below** |
| `frontend/grapick.min.js`, `.css` | [artf/grapick](https://github.com/artf/grapick) | 0.1.13 | MIT | notice must travel with the distribution |
| `frontend/reinvented-color-wheel.min.js`, `.css` | [luncheon/reinvented-color-wheel](https://github.com/luncheon/reinvented-color-wheel) | — | WTFPL | none |

## ⚠ iro.js is PATCHED — this creates an obligation

MPL-2.0 §3.2 requires that recipients of a modified MPL file can get that file's
**source** under the MPL. So:

- `frontend/iro.js` is shipped **unminified**, with James Daniel's original
  header comment intact, and stays that way.
- **Never minify it, never rewrite its header, never relicense it.** Doing any of
  those breaks both the licence and the reason the patch is legible.
- The patch itself is small and stays visible in this repository's history.

Because every install of this integration ships the readable, header-intact
source of the modified file, the §3.2 obligation is satisfied by the
distribution itself.

## grapick and the missing notice

grapick declares MIT in its `package.json` but ships **no LICENSE file and no
copyright line** — not in its repository, not in its npm tarball (checked
2026-08-17 against 0.1.13, the version bundled here). MIT still requires the
notice to travel with the distribution, so `LICENSES/GRAPICK-MIT.txt` reproduces
the standard MIT text attributed to the author npm records, and states plainly
why no year appears.

## reinvented-color-wheel

WTFPL across every published version. It imposes no notice requirement, and
upstream ships no LICENSE file to reproduce. Listed here for completeness.

## Font Awesome Pro — used, deliberately NOT distributed

The Hub stores its room and zone icons as Font Awesome **Pro** classes, and
ArtiLED holds a Pro licence. The icon paths are **not** in this repository and
must never be: Font Awesome's Pro licence does not permit making standalone
copies of Pro icons available to non-licensees, and this repository is public.

⚠ An earlier version shipped `frontend/fa-icons.json` — 3,241 Pro icons, 1.9 MB
— and it was published here on 2026-08-17 before the conflict was noticed. The
repository was deleted and rebuilt without it.

The integration now reads the paths it needs from **the customer's own Hub** at
runtime (`icons.py`), where the licensed Font Awesome tree already lives, and
caches them in that instance's config directory. The icons never leave the
licensed context, and only the few dozen a Hub actually uses are read.

`tests/test_frontend.js` fails if a bundled icon file, an FA Pro licence header,
or the old generator reappears in the package.
