#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Reset a stamped checkout back to the shipping placeholder template.

`publish.ps1` stamps @@OWNER@@ / @@REPO@@ / @@SLUG@@ / @@ATREPO@@ with real
values. That is a one-way transform: once stamped, the working tree holds the
published values, not the template. If you need the template back (renaming the
owner/repo, publishing a fork, or regenerating the docs), run:

    python tools/reset-template.py --owner <current-owner> --repo <current-repo>

It only touches the templated files and never this script's own replacements.
"""
from __future__ import annotations

import argparse
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

O = '@@OWNER@@'
R = '@@REPO@@'
S = '@@SLUG@@'
A = '@@ATREPO@@'

# Only these files carry placeholders. The skill payload never does.
FILES = [
    'README.md',
    'LICENSE',
    'install.ps1',
    'install.sh',
    '.claude-plugin/marketplace.json',
    'plugins/company-deep-analysis/.claude-plugin/plugin.json',
]


def convert(text: str, owner: str, repo: str) -> str:
    slug = f'{owner}/{repo}'
    # Composite strings MUST be replaced before the generic ones, otherwise the
    # bare owner/repo passes would consume the separators (@ and /) and produce
    # e.g. "company-deep-analysismy-skills".
    text = text.replace(f'/plugin marketplace add {slug}', f'/plugin marketplace add {S}')
    text = text.replace(f'/plugin install company-deep-analysis@{repo}',
                        f'/plugin install company-deep-analysis{A}')
    text = text.replace(f'--repo {slug}', f'--repo {S}')
    text = text.replace(f'https://github.com/{slug}', f'https://github.com/{O}/{R}')
    text = text.replace(f'raw.githubusercontent.com/{slug}', f'raw.githubusercontent.com/{O}/{R}')
    text = text.replace(f'"url": "https://github.com/{owner}"',
                        f'"url": "https://github.com/{O}"')
    # catch-alls last
    text = text.replace(owner, O)
    text = text.replace(repo, R)
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--owner', required=True, help='owner value currently stamped in the files')
    ap.add_argument('--repo', required=True, help='repo value currently stamped in the files')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    changed = []
    for rel in FILES:
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        if not os.path.exists(path):
            continue
        t = open(path, encoding='utf-8').read()
        new = convert(t, args.owner, args.repo)
        if rel.endswith('plugin.json'):
            new = re.sub(r'("version"\s*:\s*")[^"]+(")', r'\g<1>1.0.0\g<2>', new)
        if new != t:
            if not args.dry_run:
                open(path, 'w', encoding='utf-8', newline='').write(new)
            changed.append(rel)

    print(('would revert: ' if args.dry_run else 'reverted: ')
          + (', '.join(changed) if changed else '(nothing to do)'))

    print()
    print('placeholder distribution:')
    any_left = False
    for rel in FILES:
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        if not os.path.exists(path):
            continue
        t = open(path, encoding='utf-8').read()
        hits = re.findall(r'@@[A-Z]+@@', t)
        if hits:
            any_left = True
            print(f'  {rel:<58} {dict(Counter(hits))}')
    if not any_left:
        print('  (none found - files may not be stamped, or tokens were lost)')

    # A stamped value left behind means a template token went missing.
    leaks = []
    for rel in FILES:
        path = os.path.join(ROOT, rel.replace('/', os.sep))
        if not os.path.exists(path):
            continue
        t = open(path, encoding='utf-8').read()
        if args.owner in t or args.repo in t:
            leaks.append(rel)
    print()
    print('leftover stamped values:', ', '.join(leaks) if leaks else 'clean')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
