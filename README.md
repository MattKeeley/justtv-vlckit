# JustTV VLCKit source build

A source-built variant of VideoLAN VLCKit4.0.0-a25 for arm64 iOS18+/tvOS18+ device and simulator. No macOS slice is included. It removes optional output/discovery/OpenCV/zvbi functionality, removes the Apple volume-capacity heuristic, and selects FreeType stdio font loading; JPEG and LGPL telx text teletext remain. Advanced zvbi bitmap teletext is not supplied.

This release source includes pinned inputs, patches, exact component/source notices, rebuild instructions and a framework privacy manifest scoped to the reviewed JustTV playback use. See README_REBUILD.md, NOTICES.md, COMPONENTS.json and the matching source asset. Reassess declarations for materially different host-app use.

The LGPL library may be modified and rebuilt; retain required notices/source and provide an appropriate recipient-usable replacement route for applications distributing it. The included scripts never automatically approve a distribution.

No account, provider playlist, app source, signing identity or private credential is included in this repository.
