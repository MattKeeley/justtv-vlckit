# JustTV VLC source candidate

This directory holds our modifications to upstream VLC. It is **not** a vendored
binary and does not replace the currently pinned VideoLAN development package.
The app's release gate remains closed until a complete artifact is qualified.

## What is implemented

- `Configuration/VLCSourceBuild.json` pins both upstream source archives by
  revision and SHA-256. The current VLC 4 adapter is retained.
- `scripts/vlc-source-build.py prepare` uses a new, empty workspace. It verifies
  archives, safely extracts them, applies the twelve upstream VLCKit patches
  followed by the JustTV patches, and records the exact recipe and patch hashes.
- Our LGPL-2.1-or-later patch removes `fstatfs` from the Apple file-access
  read-ahead heuristic. It does not remove file playback, HTTP/HLS/RTSP, or
  modify network buffering. Apple file descriptors are treated as local.
- A second source patch disables FreeType's Meson mmap feature, selecting its
  portable stdio font loader instead of the Unix loader's system-font `fstat`
  path. This does not remove all SDK file metadata uses or qualify a manifest.
- `build` compiles a single arm64 device/simulator SDK at a time with upstream's
  GPL/GNUv3-disabled contrib configuration. It preserves source archives,
  generated configuration, linked-library/module lists, and binary identity.
- The symbol audit rejects remaining volume-capacity imports. This is a useful
  negative check, **not** a complete privacy audit or license determination.
- Nothing rewrites the SwiftPM artifact cache, changes the app dependency pin,
  invents a privacy reason, signs/uploads an app, or marks a build approved.

## Build

Requirements: macOS, Xcode with the iOS and tvOS SDKs, Python 3.12+, network
access to official upstream source hosts, and substantial free disk space.
The script checks for at least 16 GiB free before each SDK; that is a minimum,
not a promise about the full four-SDK build size. Build on a spacious volume.
Install GNU make 4.x and pkg-config first (`brew install make pkgconf`). The
builder selects `gmake` and Homebrew’s pkg-config macros; remaining missing host
tools are compiled locally by upstream. It never installs tools machine-wide. Do not run simultaneous SDK builds in the same workspace.

```sh
VLC_CANDIDATE_DIR=$(mktemp -d /private/tmp/justtv-vlc-candidate.XXXXXX)
python3 scripts/vlc-source-build.py prepare --workspace "$VLC_CANDIDATE_DIR"
python3 scripts/vlc-source-build.py build --workspace "$VLC_CANDIDATE_DIR" --sdk iphoneos
python3 scripts/vlc-source-build.py build --workspace "$VLC_CANDIDATE_DIR" --sdk iphonesimulator
python3 scripts/vlc-source-build.py build --workspace "$VLC_CANDIDATE_DIR" --sdk appletvos
python3 scripts/vlc-source-build.py build --workspace "$VLC_CANDIDATE_DIR" --sdk appletvsimulator
```

Logs are in `logs/`; unsigned candidate archives are in `archives/`; inventories
are in `evidence/<sdk>/`. Keep the entire workspace until source delivery is
verified. A command may stop after compilation if its binary audit fails.

Tests (offline):

```sh
python3 scripts/test-vlc-source-build.py
python3 scripts/test-privacy-gate.py
```

## Deliberately unfinished release decisions

Do not copy a guessed `PrivacyInfo.xcprivacy` into the vendor framework. Review
all linked modules/contribs and their actual API use, not only imported symbols.
The app's manifest is not a substitute. The release gate now rejects empty,
unreviewed, and altered framework manifests even if someone toggles the
distribution approval flag.

Before integrating a candidate, complete its framework manifest and bind the
reviewed file's SHA-256 in `VLCDependencyReview.json`; preserve all enabled
components' source, patches, build recipes and notices; verify a usable
replacement/relinking distribution; resolve codec/export review; accept or
replace the prerelease SDK; then run final signed builds and playback tests.
The local preparation receipt is not a public source-delivery endpoint.

Changing to stable 3.x is a separate adapter migration. The official iOS
3.7.5 artifact inspected on 2026-11-02 also lacks a privacy manifest; the
production directory has no matching 3.7.5 TV artifact. A version downgrade
alone therefore does not resolve the release blockers.

## JustTV playback-only profile

`playback-only.conf` is fingerprinted with the build recipe and passed explicitly
into upstream's Apple build. It retains the existing decoder/demuxer and subtitle
coverage, Apple output, local files, HTTP(S), adaptive streaming and RTSP. It
removes stream output/transcoding/encoders, Chromecast, SMB/NFS/SFTP browsing,
UPnP/mDNS/Bonjour discovery, archive browsing, TagLib metadata editing, and optional
OpenCV filters. JPEG is enabled explicitly because OpenCV previously supplied
that decoder dependency transitively. This
is a reduced playback build, not a claim that every retained codec is necessary.
Native AVKit AirPlay is independent of these VLC features.

After each source build, check the actual inventory before integrating it:

```sh
python3 scripts/check-vlc-playback-profile.py "$VLC_CANDIDATE_DIR/evidence/iphonesimulator/static-module-list.c"
```

The checker rejects removed capabilities that reappear and missing core playback
modules, including JPEG. Run it for each SDK. Source/configuration tests alone do not establish
binary size reduction, codec compatibility, privacy compliance or beta readiness.
Do not replace the working package until the candidate passes playback tests.

## Teletext license remediation

The source review found GPL-2-only packet-830 code in libzvbi despite the global
GPL-disabled contrib setting. The candidate profile therefore removes zvbi and
explicitly retains the already-available LGPL telx text subtitle decoder. The
inventory gate requires telx and rejects zvbi. This preserves basic text teletext
capability but does not promise zvbi's advanced bitmap/full teletext behavior;
validate a teletext fixture before making a broader compatibility claim.
See `Documentation/QA/BETA_2026-11-05/vlc/zvbi-license-finding.md`.
