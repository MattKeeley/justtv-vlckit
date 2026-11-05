#!/usr/bin/env python3
"""Offline safety and source-patch regression tests for the candidate builder."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('vlc_build', Path(__file__).with_name('vlc-source-build.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class SourceBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, names, link=None):
        archive = self.root / 'source.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            for name in names:
                entry = tarfile.TarInfo(name)
                data = b'fixture'
                entry.size = len(data)
                output.addfile(entry, io.BytesIO(data))
            if link:
                entry = tarfile.TarInfo('source/link')
                entry.type = tarfile.SYMTYPE
                entry.linkname = link
                output.addfile(entry)
        return archive

    def test_extracts_single_root(self):
        builder.extract_source(self.archive(['source/file']), self.root / 'result')
        self.assertEqual((self.root / 'result/file').read_text(), 'fixture')

    def test_rejects_traversal(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe source archive path'):
            builder.extract_source(self.archive(['source/../../escape']), self.root / 'result')

    def test_rejects_multiple_roots(self):
        with self.assertRaisesRegex(ValueError, 'exactly one root'):
            builder.extract_source(self.archive(['one/file', 'two/file']), self.root / 'result')

    def test_rejects_external_symlink(self):
        with self.assertRaisesRegex(ValueError, 'link escapes'):
            builder.extract_source(self.archive(['source/file'], '../../escape'), self.root / 'result')

    def test_accepts_internal_documentation_symlink(self):
        builder.extract_source(self.archive(['source/file'], 'file'), self.root / 'result')
        self.assertEqual((self.root / 'result/link').read_text(), 'fixture')

    def test_does_not_overwrite_source(self):
        result = self.root / 'result'
        result.mkdir()
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
            builder.extract_source(self.archive(['source/file']), result)

    def test_prepare_does_not_overwrite_workspace(self):
        (self.root / 'keep').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'empty workspace'):
            builder.prepare(self.root)
        self.assertEqual((self.root / 'keep').read_text(), 'keep')

    def test_unowned_workspace_cannot_build(self):
        with self.assertRaisesRegex(ValueError, 'Not a prepared'):
            builder.check_workspace(self.root)

    def test_modified_recipe_cannot_resume(self):
        builder.write_json(self.root / builder.MARKER, {'recipe': {}})
        with self.assertRaisesRegex(ValueError, 'recipe changed'):
            builder.check_workspace(self.root)

    def test_source_checksum_is_required(self):
        cache = self.root / 'cache'
        cache.mkdir()
        (cache / 'vlckit.tar.gz').write_bytes(b'not the pinned source')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            builder.prepare(self.root / 'candidate', cache)

    def test_low_disk_stops_before_build(self):
        receipt = {'sources': {'minimumFreeGiB': 16}}
        with patch.object(builder, 'check_workspace', return_value=receipt), \
             patch.object(builder.shutil, 'disk_usage', return_value=type('Usage', (), {'free': 1})()), \
             patch.object(builder, 'run') as run:
            with self.assertRaisesRegex(ValueError, '16 GiB free'):
                builder.build(self.root, 'iphoneos', 4)
            run.assert_not_called()

    def test_old_make_is_rejected_before_compilation(self):
        with patch.object(builder.subprocess, 'check_output', return_value='GNU Make 3.81\n'):
            with self.assertRaisesRegex(ValueError, 'GNU make 4.x'):
                builder.build_environment({'MAKE': '/usr/bin/make'})

    def test_build_environment_preserves_input_and_selects_gmake(self):
        original = {'PATH': '/usr/bin', 'ACLOCAL_PATH': '/custom/macros'}
        with patch.object(builder.shutil, 'which', return_value='/tools/gmake'), \
             patch.object(builder.subprocess, 'check_output', return_value='GNU Make 4.4.1\n'):
            result = builder.build_environment(original)
        self.assertEqual(result['MAKE'], '/tools/gmake')
        self.assertIn('/custom/macros', result['ACLOCAL_PATH'].split(':'))
        self.assertNotIn('MAKE', original)

    def test_playback_profile_removes_conflicting_enables(self):
        source = self.root / 'vlc/extras/package/apple'
        source.mkdir(parents=True)
        (source / 'build.conf').write_text('VLC_CONTRIB_OPTIONS_BASE=(--enable-libdsm --enable-taglib --enable-opencv4 --enable-zvbi --enable-ass)\nVLC_CONFIG_OPTIONS_BASE=()\nVLC_MODULE_REMOVAL_LIST_BASE=()\n')
        profile = builder.ROOT / json.loads(builder.CONFIG.read_text())['buildProfile']
        result = subprocess.run(['bash', '-c', 'source "$1"; printf "%s\\n" "${VLC_CONTRIB_OPTIONS_BASE[@]}" "${VLC_CONFIG_OPTIONS_BASE[@]}"', 'profile-test', str(profile)],
            env={**__import__('os').environ, 'JUSTTV_VLC_SOURCE_ROOT': str(self.root / 'vlc')}, capture_output=True, text=True, check=True)
        flags = result.stdout.splitlines()
        self.assertNotIn('--enable-libdsm', flags)
        self.assertNotIn('--enable-taglib', flags)
        self.assertNotIn('--enable-opencv4', flags)
        self.assertNotIn('--enable-zvbi', flags)
        self.assertIn('--enable-ass', flags)
        self.assertIn('--enable-jpeg', flags)
        self.assertIn('--enable-telx', flags)
        for flag in ['--disable-sout', '--disable-chromecast', '--disable-upnp', '--disable-sftp', '--disable-nfs', '--disable-opencv', '--disable-opencv4', '--disable-zvbi']:
            self.assertIn(flag, flags)
        for flag in ['--disable-net', '--disable-avcodec', '--disable-live555', '--disable-ass']:
            self.assertNotIn(flag, flags)
        self.assertIn(json.loads(builder.CONFIG.read_text())['buildProfile'], builder.recipe_fingerprint())

    def test_reduced_inventory_rejects_removed_or_missing_features(self):
        audit_spec = importlib.util.spec_from_file_location('profile_audit', Path(__file__).with_name('check-vlc-playback-profile.py'))
        audit = importlib.util.module_from_spec(audit_spec)
        audit_spec.loader.exec_module(audit)
        config = json.loads(builder.CONFIG.read_text())
        source = ' '.join('vlc_entry__' + name for name in ['avcodec', 'mkv', 'mp4', 'adaptive', 'filesystem', 'freetype', 'jpeg', 'telx'])
        self.assertEqual(audit.check(source, config)['linkedModuleCount'], 8)
        qualified = ' '.join('vlc_entry__category_lib' + name for name in ['avcodec', 'mkv', 'mp4', 'adaptive', 'filesystem', 'freetype', 'jpeg', 'telx'])
        self.assertEqual(audit.check(qualified, config)['linkedModuleCount'], 8)
        for suffix in [' vlc_entry__stream_out_transcode', ' vlc_entry__bonjour', ' vlc_entry__smb2', ' vlc_entry__services_discovery_bonjour', ' vlc_entry__stream_out_transcode_libtranscode', ' vlc_entry__video_filter_libopencv_example', ' vlc_entry__video_filter_libopencv_wrapper', ' vlc_entry__codec_libzvbi']:
            with self.assertRaisesRegex(ValueError, 'Forbidden'):
                audit.check(source + suffix, config)
        with self.assertRaisesRegex(ValueError, 'Required'):
            audit.check(source.replace('vlc_entry__mkv', ''), config)
        with self.assertRaisesRegex(ValueError, 'Required'):
            audit.check(source.replace('vlc_entry__jpeg', ''), config)
        with self.assertRaisesRegex(ValueError, 'Required'):
            audit.check(source.replace('vlc_entry__telx', ''), config)

    def test_no_automatic_distribution_approval(self):
        config = json.loads(builder.CONFIG.read_text())
        self.assertTrue(config['candidateOnly'])
        review = json.loads((builder.ROOT / 'Configuration/VLCDependencyReview.json').read_text())
        self.assertFalse(review['distributionApproved'])

    def test_apple_branch_patch_compiles_without_volume_api(self):
        # Apply the actual distributable patch to its minimal upstream context,
        # then compile both Apple and fallback branches without the whole SDK.
        source = self.root / 'modules/access/file.c'
        source.parent.mkdir(parents=True)
        source.write_text('''#include <stdbool.h>
static bool IsRemote (int fd)
{
#if defined(__APPLE__)
    /* This has to preceed the general fstatvfs implmentation below,
     * as even though Darwin has fstatvfs, it does not expose the
     * MNT_LOCAL in the statvfs.f_flag field.
     */
    struct statfs sfs;

    if (fstatfs (fd, &sfs))
        return false;

    return !((sfs.f_flags & MNT_LOCAL) == MNT_LOCAL);

#elif defined (HAVE_FSTATVFS) && defined (MNT_LOCAL)
    struct statvfs stf;
#else
    (void)fd;
    return false;
#endif
}
int main(void) { return IsRemote(1) ? 1 : 0; }
''')
        patch_file = builder.ROOT / json.loads(builder.CONFIG.read_text())['patches'][0]
        subprocess.run(['git', 'apply', str(patch_file)], cwd=self.root, check=True, capture_output=True)
        for name, flag in [('apple', '-D__APPLE__'), ('fallback', '-U__APPLE__')]:
            output = self.root / name
            subprocess.run(['cc', flag, '-Wall', '-Wextra', '-Werror', str(source), '-o', str(output)],
                           check=True, capture_output=True)
            subprocess.run([str(output)], check=True)


if __name__ == '__main__':
    unittest.main()
