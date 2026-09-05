# Third-party licenses

This tool bundles two prebuilt third-party executables under `tools/`. Neither is part of
this project; both are redistributed under their own terms, reproduced here in full.

Nothing in this directory covers Sonic Mania itself. No game content is distributed — the
builder requires a `Data.rsdk` that you supply from your own legitimate copy.

---

## FFmpeg — downloaded at runtime, **not** redistributed

Used to downsample SFX, re-encode the FMVs and resize images.

**This project does not ship ffmpeg.** It is fetched on first use from
[ffbinaries](https://ffbinaries.com) into a per-user cache directory
(`builder/ffmpeg_fetch.py`), so no ffmpeg binary is distributed with the tool and the
GPL's obligations — shipping the licence text, making corresponding source available — do
not attach to this project. What follows is attribution and disclosure, not compliance:
the tool downloads and runs a sizeable third-party binary on your behalf, so it should be
clear what that is and on what terms.

> **If you ever mirror the binary yourself** — hosting it on your own release page rather
> than linking to upstream — you are conveying it again and every GPL obligation returns.
> Restore the full `COPYING` texts and provide the corresponding source for that build.

| | |
|---|---|
| Upstream | https://ffmpeg.org |
| Builds | https://ffbinaries.com — pinned to **6.1**, verified by sha256 on download |
| License | **GPL v3** as built (see below) |
| Text | `ffmpeg/LICENSE.md` — ffmpeg's own summary, reproduced verbatim |

`LICENSE.md` is upstream's file and refers to `COPYING.GPLv2`, `COPYING.GPLv3`,
`COPYING.LGPLv2.1` and `COPYING.LGPLv3`, which are **not** included here — they are only
needed when redistributing a build, which this project does not do. The canonical texts
are at https://www.gnu.org/licenses/ and in any ffmpeg source tree.

FFmpeg is LGPL v2.1+ by default, but the builds bundled here are configured with
`--enable-gpl` and `--enable-version3`, which makes the resulting binaries **GPL v3**.
Confirm what you are shipping with `ffmpeg -version` and read the `configuration:` line:

- `--enable-gpl` present → GPL, not LGPL
- `--enable-version3` present alongside it → GPL **v3**
- `--enable-nonfree` present → **do not redistribute**; that combination is not
  distributable under any of these licenses

The builder invokes ffmpeg as a separate executable rather than linking against it, and
does not redistribute it at all, so none of this places the project's own source under the
GPL. If you ever go back to bundling a build, the obligation returns: ship these texts and
make that build's corresponding source available.

The pinned builds, for reference:

| Platform | Archive | Source |
|---|---|---|
| Windows | `ffmpeg-6.1-win-64.zip` | https://github.com/ffbinaries/ffbinaries-prebuilt |
| macOS | `ffmpeg-6.1-macos-64.zip` (tessus) | https://evermeet.cx/ffmpeg/ |
| Linux | `ffmpeg-6.1-linux-64.zip` | https://github.com/ffbinaries/ffbinaries-prebuilt |

The Xiph codecs ffmpeg uses here — libtheora and libvorbis — are BSD-style and add no
obligations beyond ffmpeg's own.

---

## extract-xiso — downloaded at runtime

Used to write the final Xbox ISO.

| | |
|---|---|
| Upstream | https://github.com/XboxDev/extract-xiso |
| License | Modified BSD |
| Text | `extract-xiso/LICENSE.TXT` |
| Pinned to | `build-202505152050`, verified by sha256 on download |

Like ffmpeg, extract-xiso is now fetched on first use rather than bundled. Its own
`LICENSE.TXT` ships inside the release archive and is extracted alongside the binary, so
the notice below travels with the copy on disk as well.

Copyright `in@fishtank.com`. The terms are permissive: do not claim authorship of the
code, retain the copyright notice, and accept that it comes with no warranty. Portions
also carry the Apache Software License 1.1 (the bundled `getopt` implementation); see
`LICENSE.TXT`.
