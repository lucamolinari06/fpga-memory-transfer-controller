#!/usr/bin/env python3
"""Seal a freshly reproduced P0 reference before replay; never replace history."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / 'results/raw/memory_timing/reference-sha256.json'
    if destination.exists():
        raise SystemExit('Refusing to replace an existing reference manifest.')
    source = ROOT / 'results/raw/single_buffer/summary.json'
    report = json.loads(source.read_text())
    if not report.get('passed') or len(report.get('runs', [])) != 78:
        raise SystemExit('A complete passing 78-run P0 reference is required.')
    paths = set(report['source_sha256'])
    paths.update(str(p.relative_to(ROOT))
                 for p in source.parent.rglob('*') if p.is_file())
    manifest = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in sorted(paths)}
    for name, digest in report['source_sha256'].items():
        if manifest[name] != digest:
            raise SystemExit('Stale reference source: ' + name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2) + '\n')
    (destination.parent / 'reference-origin.json').write_text(json.dumps({
        'origin': 'fresh local reproduction',
        'meaning': 'Exact replay is against this freshly executed reference, not a downloaded historical archive.',
        'files': len(manifest),
        'summary_sha256': manifest[str(source.relative_to(ROOT))],
    }, indent=2) + '\n')
    print('PASS sealed fresh P0 reference:', len(manifest), 'files')


if __name__ == '__main__':
    main()
