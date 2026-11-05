# Third-party notices

This package contains a modified VLCKit/libVLC build plus the components listed in COMPONENTS.json. Preserve THIRD_PARTY_NOTICES.txt and the matching source asset when redistributing. FreeType is used under its FreeType License: this software is based in part on the work of the FreeType Team. The zvbi library is excluded due to its GPL-only packet-decoder exception; LGPL telx text teletext remains.

The candidate modifications disable the Apple fstatfs read-ahead heuristic, disable FreeType mmap font loading, remove optional network/discovery/output/OpenCV/zvbi features, and retain explicit JPEG/telx decoding. Exact source revisions, patches and build recipe are in the source asset and repository. Some source bundles contain tools/tests/alternative license texts not selected for the runtime library; retain notices without inferring that every source file is linked.

No patent license or cryptographic export approval is asserted beyond rights explicitly granted in the included upstream notices.

The 2026-11-05 linked-file notice correction is included in THIRD_PARTY_NOTICES.txt and separately in THIRD_PARTY_NOTICES_ADDENDUM.txt. The existing release source archive already preserves these original headers. The supplemental release asset corrects binary documentation without replacing the SDK/source assets or moving the release tag.
