#!/usr/bin/env python3
"""Build an isolated, source-preserving VLC candidate. Never approves distribution.

prepare requires an empty directory. build can resume one SDK in that directory.
No installed app, SwiftPM cache, source pin or release-approval flag is modified.
Python 3.12+ is required for safe tar extraction.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'Configuration/VLCSourceBuild.json'
MARKER = 'justtv-vlc-source-build.json'
SDKS = {
    'iphoneos': ('iphone', 'device', 'iOS'),
    'iphonesimulator': ('iphone', 'simulator', 'iOS Simulator'),
    'appletvos': ('appletv', 'device', 'tvOS'),
    'appletvsimulator': ('appletv', 'simulator', 'tvOS Simulator'),
}


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def run(args, cwd, **kwargs):
    return subprocess.run([str(arg) for arg in args], cwd=cwd, check=True, **kwargs)


def extract_source(archive, destination):
    """Refuse traversal/special files; allow only links within the source root."""
    require(not destination.exists(), f'Refusing to overwrite {destination}')
    with tarfile.open(archive) as source:
        members = source.getmembers()
        roots = {Path(member.name).parts[0] for member in members if member.name}
        require(len(roots) == 1, 'Source archive must have exactly one root')
        top = roots.pop()
        for member in members:
            path = Path(member.name)
            require(not path.is_absolute() and '..' not in path.parts,
                    'Unsafe source archive path')
            require(member.isfile() or member.isdir() or member.issym(), 'Source archive contains a special file')
            if member.issym():
                target = Path(member.linkname)
                normalized = Path(posixpath.normpath(str(path.parent / target)))
                require(not target.is_absolute() and normalized.parts[0] == top,
                        'Source archive link escapes its root')
        temporary = destination.with_name(destination.name + '.extracting')
        temporary.mkdir()
        source.extractall(temporary, filter='data')
        (temporary / top).rename(destination)
        temporary.rmdir()


def recipe_fingerprint():
    config = json.loads(CONFIG.read_text())
    paths = [CONFIG, Path(__file__).resolve(), ROOT / config['buildProfile']] + [ROOT / item for item in config['patches']]
    return {str(path.relative_to(ROOT)): sha256(path) for path in paths}


def prepare(workspace, cache=None):
    require(sys.version_info >= (3, 12), 'Use Python 3.12 or newer')
    require(not workspace.exists() or not any(workspace.iterdir()), 'Preparation requires an empty workspace')
    workspace.mkdir(parents=True, exist_ok=True)
    config = json.loads(CONFIG.read_text())
    downloads = workspace / 'sources'
    downloads.mkdir()
    for name in ('vlckit', 'libvlc'):
        pin = config[name]
        archive = downloads / f'{name}.tar.gz'
        cached = cache / f'{name}.tar.gz' if cache else None
        if cached and cached.is_file():
            shutil.copyfile(cached, archive)
        else:
            require(pin['url'].startswith('https://codeload.github.com/videolan/'), 'Unexpected source host')
            with urllib.request.urlopen(pin['url'], timeout=90) as response, archive.open('xb') as target:
                shutil.copyfileobj(response, target)
        require(sha256(archive) == pin['sha256'], f'{name} source checksum mismatch')
    kit = workspace / 'vlckit'
    extract_source(downloads / 'vlckit.tar.gz', kit)
    vlc = kit / 'libvlc/vlc'
    extract_source(downloads / 'libvlc.tar.gz', vlc)
    patches = sorted((kit / 'libvlc/patches').glob('*.patch'))
    require(len(patches) == 12, 'Upstream patch inventory changed')
    patches += [ROOT / path for path in config['patches']]
    receipt = {'schemaVersion': 1, 'recipe': recipe_fingerprint(), 'sources': config,
               'patches': [], 'distributionApproved': False}
    for patch in patches:
        run(['git', 'apply', '--check', patch], vlc)
        run(['git', 'apply', patch], vlc)
        receipt['patches'].append({'name': patch.name, 'sha256': sha256(patch)})
    # GitHub source archives omit Git metadata; VLC's build still requires its revision.
    (vlc / 'src/revision.txt').write_text(config['libvlc']['revision'] + '-justtv-playback\n')
    # Preserve pristine inputs plus exact patches separately from build products.
    shutil.copytree(ROOT / 'Vendor/VLC', workspace / 'justtv-modifications')
    shutil.copyfile(Path(__file__), workspace / 'justtv-modifications/vlc-source-build.py')
    shutil.copyfile(CONFIG, workspace / 'justtv-modifications/VLCSourceBuild.json')
    write_json(workspace / MARKER, receipt)
    print(f'Prepared pinned sources and {len(patches)} patches: {workspace}')


def check_workspace(workspace):
    marker = workspace / MARKER
    require(marker.is_file(), 'Not a prepared JustTV VLC workspace')
    receipt = json.loads(marker.read_text())
    require(receipt['recipe'] == recipe_fingerprint(), 'Build recipe changed; prepare a new workspace')
    return receipt


def collect_evidence(workspace, sdk, framework):
    """Record facts, not compliance conclusions or guessed license classifications."""
    vlc = workspace / 'vlckit/libvlc/vlc'
    evidence = workspace / 'evidence' / sdk
    evidence.mkdir(parents=True, exist_ok=True)
    binary = framework / 'VLCKit'
    symbols = run(['xcrun', 'nm', '-u', binary], workspace, capture_output=True, text=True).stdout
    (evidence / 'undefined-symbols.txt').write_text(symbols)
    require(not any(symbol in symbols.split() for symbol in ('_fstatfs', '_statfs', '_statvfs', '_fstatvfs')),
            'Candidate still imports a volume-capacity API; review all included dependencies')
    with (evidence / 'binary-uuids.txt').open('w') as output:
        run(['xcrun', 'dwarfdump', '--uuid', binary], workspace, stdout=output)
    build = vlc / f'build-{sdk}-arm64'
    for relative in ('static-lib/static-libs-list', 'static-lib/static-module-list.c',
                     'build/config.log', 'build/config.h'):
        path = build / relative
        require(path.is_file(), f'Missing build evidence: {relative}')
        shutil.copyfile(path, evidence / path.name)
    inventories = []
    # Keep fetched source archives, patched contrib trees and recipes in this
    # workspace until the full corresponding-source delivery has been verified.
    for path in sorted((vlc / 'contrib/tarballs').glob('*')):
        if path.is_file():
            inventories.append({'file': str(path.relative_to(workspace)), 'sha256': sha256(path)})
    write_json(evidence / 'source-archives.json', inventories)
    configs = list((vlc / 'contrib').glob('contrib-*/config.mak'))
    for index, path in enumerate(configs):
        text = path.read_text()
        require('GPL := 1' not in text and 'GNUV3 := 1' not in text, 'Unexpected GPL/GNUv3 contrib configuration')
        shutil.copyfile(path, evidence / f'contrib-{index}-config.mak')
    write_json(evidence / 'candidate.json', {
        'sdk': sdk, 'binarySHA256': sha256(binary), 'distributionApproved': False,
        'remaining': ['SDK-wide privacy review/manifest', 'codec notices and corresponding-source delivery',
                      'replacement/relink verification', 'prerelease acceptance',
                      'signed distribution and physical playback verification'],
    })


def build_environment(environment):
    env = environment.copy()
    # Apple make 3.81's jobserver is incompatible with current Ninja. Use an
    # installed GNU make 4.x; never silently install tools or rewrite the host.
    make = env.get('MAKE') or shutil.which('gmake')
    require(make, 'Install GNU make 4.x (brew install make), or set MAKE to its path')
    version = subprocess.check_output([make, '--version'], text=True).splitlines()[0]
    require(version.startswith('GNU Make 4.'), 'The source build requires GNU make 4.x')
    env['MAKE'] = make
    macro_dirs = [Path('/opt/homebrew/share/aclocal'), Path('/usr/local/share/aclocal')]
    macro_path = [str(path) for path in macro_dirs if (path / 'pkg.m4').is_file()]
    if env.get('ACLOCAL_PATH'):
        macro_path.append(env['ACLOCAL_PATH'])
    if macro_path:
        env['ACLOCAL_PATH'] = os.pathsep.join(macro_path)
    return env


def build(workspace, sdk, jobs):
    receipt = check_workspace(workspace)
    minimum = receipt['sources']['minimumFreeGiB'] * 1024**3
    require(shutil.disk_usage(workspace).free >= minimum,
            f'Build needs at least {receipt["sources"]["minimumFreeGiB"]} GiB free; no files were deleted')
    kit = workspace / 'vlckit'
    vlc = kit / 'libvlc/vlc'
    build_dir = vlc / f'build-{sdk}-arm64'
    build_dir.mkdir(exist_ok=True)
    logs = workspace / 'logs'
    logs.mkdir(exist_ok=True)
    env = os.environ.copy()
    env = build_environment(env)
    env['MAKEFLAGS'] = f'-j{jobs}'
    env['JUSTTV_VLC_SOURCE_ROOT'] = str(vlc)
    env['VLC_PATH'] = os.environ.get('PATH', '')
    env['CCC_OVERRIDE_OPTIONS'] = 'x-v'
    with (logs / f'{sdk}-libvlc.log').open('a') as log:
        run(['bash', vlc / 'extras/package/apple/build.sh', '--arch=aarch64',
             f'--sdk={sdk}', f'--config={ROOT / receipt["sources"]["buildProfile"]}', '--disable-debug', f'-j{jobs}'], build_dir,
            env=env, stdout=log, stderr=subprocess.STDOUT)
    family, kind, destination = SDKS[sdk]
    static = build_dir / 'static-lib'
    install = vlc / f'install-{family}-{kind}'
    install.mkdir(exist_ok=True)
    shutil.copyfile(static / 'libvlc-full-static.a', install / f'libvlc-{kind}-static.a')
    shutil.copyfile(static / 'static-module-list.c',
                    kit / f'Headers/Internal/vlc-plugins-{family}-{kind}-arm64.h')
    archive = workspace / 'archives' / f'{sdk}.xcarchive'
    with (logs / f'{sdk}-framework.log').open('a') as log:
        run(['xcodebuild', 'archive', '-project', kit / 'VLCKit.xcodeproj', '-scheme', 'VLCKit',
             '-configuration', 'Release', '-sdk', sdk, '-destination', f'generic/platform={destination}',
             '-archivePath', archive, '-derivedDataPath', workspace / 'derived' / sdk,
             'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'CODE_SIGNING_ALLOWED=NO', 'SKIP_INSTALL=NO',
             'IPHONEOS_DEPLOYMENT_TARGET=18.0', 'TVOS_DEPLOYMENT_TARGET=18.0'],
            kit, env=env, stdout=log, stderr=subprocess.STDOUT)
    framework = archive / 'Products/Library/Frameworks/VLCKit.framework'
    collect_evidence(workspace, sdk, framework)
    print(f'Built candidate for {sdk}. Not distribution-approved: {framework}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'build'])
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--source-cache', type=Path)
    parser.add_argument('--sdk', choices=SDKS)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    require(args.workspace.is_absolute(), 'Workspace must be an absolute path')
    require(not args.workspace.is_symlink(), 'Workspace cannot be a symlink')
    workspace = args.workspace.resolve()
    require(workspace not in (Path('/'), Path.home(), ROOT) and not ROOT.is_relative_to(workspace),
            'Use a dedicated build directory, not a home/repository root')
    require(1 <= args.jobs <= 16, 'Use between 1 and 16 build jobs')
    if args.action == 'prepare':
        prepare(workspace, args.source_cache)
    else:
        require(args.sdk, 'build requires --sdk')
        build(workspace, args.sdk, args.jobs)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        sys.exit(f'VLC candidate build stopped: {error}')
