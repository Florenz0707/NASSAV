#!/usr/bin/env python3
"""
Batch-generate thumbnails for existing cover images.
Usage:
  python3 scripts/generate_thumbnails.py [--force] [--sizes small,medium,large]

Requires: Pillow (`pip install pillow`)

This script looks for cover images under `resource/cover` and writes
thumbnails into `resource/cover/thumbnails/{size}/{AVID}.jpg`.
"""
import argparse
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
COVER_DIR = BASE_DIR / 'resource' / 'cover'
THUMB_DIR = COVER_DIR / 'thumbnails'

SIZES = {
    'small': 200,
    'medium': 600,
    'large': 1200,
}


def generate_for_file(src_path: Path, sizes, force=False):
    try:
        from PIL import Image
    except Exception:
        print('Pillow is required. Install with: pip install pillow')
        return 0

    created = 0
    avid = src_path.stem
    for name, width in sizes.items():
        dest = THUMB_DIR / name / f"{avid}.jpg"
        if dest.exists() and not force and dest.stat().st_mtime >= src_path.stat().st_mtime:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(src_path) as im:
                if im.mode in ('RGBA', 'P'):
                    im = im.convert('RGB')
                w, h = im.size
                if w <= width:
                    im.save(dest, format='JPEG', quality=85)
                else:
                    ratio = width / float(w)
                    new_h = int(h * ratio)
                    im = im.resize((width, new_h), Image.LANCZOS)
                    im.save(dest, format='JPEG', quality=85)
            created += 1
            print(f'Wrote {dest}')
        except Exception as e:
            print(f'Failed to write {dest}: {e}')
    return created


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', help='Regenerate even if thumbnail exists')
    parser.add_argument('--sizes', default='small,medium,large', help='Comma list of sizes to generate')
    args = parser.parse_args()

    sizes = {k: v for k, v in SIZES.items() if k in [s.strip() for s in args.sizes.split(',') if s.strip()]}
    if not sizes:
        print('No sizes selected')
        sys.exit(1)

    if not COVER_DIR.exists():
        print('Cover dir not found:', COVER_DIR)
        sys.exit(1)

    imgs = list(COVER_DIR.glob('*'))
    imgs = [p for p in imgs if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')]
    total = 0
    for img in imgs:
        total += generate_for_file(img, sizes, force=args.force)

    print(f'Done. Generated {total} thumbnails.')


if __name__ == '__main__':
    main()
