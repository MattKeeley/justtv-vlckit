// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "JustTVVLCKit",
    platforms: [.iOS("18.0"), .tvOS("18.0")],
    products: [.library(name: "VLCKit", targets: ["JustTVVLCKitBinary"])],
    targets: [.binaryTarget(
        name: "JustTVVLCKitBinary",
        url: "https://github.com/MattKeeley/justtv-vlckit/releases/download/4.0.0-a25-justtv.1/VLCKit.xcframework.zip",
        checksum: "ff51459986fb7f690082fd1199685f458e0841b973a2e5c22607b8c3bc9a0944"
    )]
)
