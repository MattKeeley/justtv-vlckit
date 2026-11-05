# Rebuild the JustTV VLCKit source candidate

Use macOS with Xcode27.2, Python3.12+, GNU make4.x, pkg-config/autotools and at least16GiB free (more for all four SDKs). No hosted credentials or private application repository are required. Obtain the matching VLC-source-inputs.tar asset and extract it. This repository contains the exact candidate builder/config/patches.

From this repository root:

```sh
python3.12 scripts/vlc-source-build.py prepare --workspace /absolute/new/vlc-work --source-cache /absolute/extracted/sources
```

Copy the asset's contrib-tarballs/ into vlc-work/vlckit/libvlc/vlc/contrib/tarballs/ and host-tool-tarballs/ into vlc-work/vlckit/libvlc/vlc/extras/tools/. Build each SDK sequentially with `python3.12 scripts/vlc-source-build.py build --workspace /absolute/new/vlc-work --sdk SDK --jobs 8`, where SDK is iphoneos, iphonesimulator, appletvos or appletvsimulator. Set TMPDIR to a writable dedicated workspace directory if the host toolchain requires it. Internet may still be needed for Python build dependencies/tool bootstrap. Preserve all logs/receipts.

The recipe pins VLCKit/libVLC archives by SHA256, applies12 upstream patches plus2 JustTV patches, retains GPL/GNUv3-disabled upstream options, disables FreeType mmap/OpenCV/zvbi and explicitly retains JPEG/telx. The known zvbi GPL-only packet decoder is excluded; basic text teletext fallback remains, advanced bitmap teletext behavior is not promised.

Run check-vlc-playback-profile.py against every evidence/SDK/static-module-list.c. It must reject OpenCV/zvbi and require core decoding/JPEG/telx. Before packaging, copy the independently reviewed Vendor/VLC/PrivacyInfo.xcprivacy into each finished framework bundle (after validating the source-use assumptions for your modifications), and use xcodebuild -create-xcframework with those four frameworks. Do not substitute this iOS/tvOS-only XCFramework in a macOS target.

This source package permits modification/rebuilding of the library; use an interface-compatible replacement to test with the application. App-recipient signing/replacement instructions and distribution acceptance are separate deliverables. A successful build does not independently approve privacy/license/distribution of arbitrary modifications.
