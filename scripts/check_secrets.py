"""Reject credential-bearing MongoDB URLs without printing their values.

Run `python scripts/check_secrets.py --history` before pushing.
This targeted guard is not a general-purpose secret scanner.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys

URI = re.compile(rb'''mongodb(?:\+srv)?://[^\s"'<>\\]+''', re.I)


def contains_credentials(data: bytes) -> bool:
    return any(b'@' in m.split(b'://', 1)[1].split(b'/', 1)[0]
               for m in URI.findall(data))


def git(*args, **kwargs):
    return subprocess.check_output(['git', *args], **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args()
    failures = []
    for raw in git('ls-files', '-z').split(b'\0'):
        if not raw:
            continue
        path = Path(raw.decode())
        if path.name == '.env' or path.as_posix() == '.streamlit/secrets.toml':
            failures.append(f'Tracked secrets file: {path}')
        if path.is_file() and contains_credentials(path.read_bytes()):
            failures.append(f'Credential-bearing MongoDB URL: {path}')
    if args.history:
        ids = [line.split(b' ', 1)[0]
               for line in git('rev-list', '--objects', '--all').splitlines()]
        metadata = git('cat-file', '--batch-check=%(objectname) %(objecttype)',
                       input=b'\n'.join(ids) + b'\n')
        for entry in metadata.splitlines():
            oid, kind = entry.split()
            if kind == b'blob' and contains_credentials(git('cat-file', 'blob', oid.decode())):
                failures.append(f'Credential-bearing MongoDB URL in historical blob: {oid.decode()}')
    if failures:
        print('\n'.join(failures), file=sys.stderr)
        return 1
    print('MongoDB credential scan passed' + (' (including all local history).' if args.history else '.'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
