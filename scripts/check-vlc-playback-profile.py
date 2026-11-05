#!/usr/bin/env python3
"""Verify the reduced candidate's actual linked module inventory (not approval)."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

def check(module_source, config):
    modules = sorted(set(re.findall(r'vlc_entry__([A-Za-z0-9_]+)', module_source)))
    if not modules:
        raise ValueError('Missing linked module inventory')
    forbidden = [name for name in modules if any(name.startswith(prefix) or ('_' + prefix) in name or ('_lib' + prefix) in name for prefix in config['forbiddenModules'])]
    if forbidden:
        raise ValueError('Forbidden playback-only modules remain: ' + ', '.join(forbidden))
    # Core compatibility features must not vanish as a side effect of stripping.
    for required in ('avcodec', 'mkv', 'mp4', 'adaptive', 'filesystem', 'freetype', 'jpeg', 'telx'):
        if not any(name == required or name.endswith('_' + required) or name.endswith('_lib' + required) for name in modules):
            raise ValueError('Required playback module missing: ' + required)
    return {'linkedModuleCount': len(modules), 'linkedModules': modules, 'distributionApproved': False}

if __name__ == '__main__':
    try:
        source = Path(sys.argv[1]).read_text()
        print(json.dumps(check(source, json.loads((ROOT / 'Configuration/VLCSourceBuild.json').read_text())), indent=2))
    except (ValueError, OSError, IndexError) as error:
        sys.exit(str(error))
