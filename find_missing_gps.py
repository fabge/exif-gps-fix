#!/usr/bin/env python3
"""
Find images missing GPS metadata.

Scans folders recursively and reports which images lack GPS coordinates,
grouped by folder with summary statistics.

Usage:
    python find_missing_gps.py <folder> [--list] [--with-dates]
"""

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.heic', '.heif', '.raf', '.dng', '.tiff', '.tif', '.png'}


def check_exiftool():
    """Check if exiftool is installed."""
    try:
        subprocess.run(['exiftool', '-ver'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_batch_image_info(file_paths, batch_size=100, show_progress=False):
    """
    Extract GPS presence and date from multiple images in batches.

    Returns dict mapping file_path -> {'has_gps': bool, 'timestamp': datetime or None}
    """
    results = {}
    total = len(file_paths)

    for i in range(0, total, batch_size):
        batch = file_paths[i : i + batch_size]

        if show_progress:
            progress = min(i + batch_size, total)
            print(f"\rReading EXIF data: {progress}/{total}", end='', flush=True)

        try:
            cmd = [
                'exiftool',
                '-json',
                '-n',
                '-GPSLatitude',
                '-GPSLongitude',
                '-DateTimeOriginal',
                '-CreateDate',
            ] + [str(p) for p in batch]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            for exif in data:
                file_path = Path(exif.get('SourceFile', ''))

                # Check GPS
                has_gps = 'GPSLatitude' in exif and 'GPSLongitude' in exif and exif['GPSLatitude'] is not None and exif['GPSLongitude'] is not None

                # Parse timestamp
                timestamp = None
                for date_field in ['DateTimeOriginal', 'CreateDate']:
                    if exif.get(date_field):
                        try:
                            timestamp = datetime.strptime(exif[date_field], '%Y:%m:%d %H:%M:%S')
                            break
                        except ValueError:
                            continue

                results[file_path] = {'has_gps': has_gps, 'timestamp': timestamp}

        except (subprocess.CalledProcessError, json.JSONDecodeError):
            # Fall back to marking batch as failed
            for p in batch:
                results[p] = None

    if show_progress:
        print()  # Newline after progress

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Find images missing GPS metadata, grouped by folder.',
    )
    parser.add_argument(
        'folder',
        help='Folder to scan (recursive)',
    )
    parser.add_argument(
        '--list',
        '-l',
        action='store_true',
        help='List individual files missing GPS',
    )
    parser.add_argument(
        '--with-dates',
        action='store_true',
        help='Show date range for missing images (slower)',
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Show all folders, including those with complete GPS coverage',
    )

    args = parser.parse_args()

    if not check_exiftool():
        print("Error: exiftool is not installed.", file=sys.stderr)
        print("Install with: brew install exiftool (macOS) or apt install libimage-exiftool-perl (Linux)", file=sys.stderr)
        sys.exit(1)

    root_path = Path(args.folder).resolve()
    if not root_path.exists():
        print(f"Error: Folder does not exist: {root_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning: {root_path}\n")

    # Collect all images
    all_files = [f for f in root_path.rglob('*') if f.suffix.lower() in IMAGE_EXTENSIONS]
    print(f"Found {len(all_files)} images")

    if not all_files:
        sys.exit(0)

    # Batch process all files
    all_info = get_batch_image_info(all_files, show_progress=True)

    # Group by folder
    folders = defaultdict(lambda: {'with_gps': [], 'missing_gps': []})

    for file_path in all_files:
        info = all_info.get(file_path)
        if info is None:
            continue

        # Use relative folder path for grouping
        rel_folder = file_path.parent.relative_to(root_path)
        folder_key = str(rel_folder) if str(rel_folder) != '.' else '(root)'

        entry = {'path': file_path, 'timestamp': info['timestamp']}

        if info['has_gps']:
            folders[folder_key]['with_gps'].append(entry)
        else:
            folders[folder_key]['missing_gps'].append(entry)

    # Sort folders by number of missing images (descending)
    sorted_folders = sorted(
        folders.items(),
        key=lambda x: len(x[1]['missing_gps']),
        reverse=True,
    )

    # Print results
    total_missing = 0
    total_with_gps = 0
    folders_with_missing = 0

    print("=" * 70)
    print("FOLDERS WITH MISSING GPS DATA")
    print("=" * 70)

    for folder_name, data in sorted_folders:
        missing = data['missing_gps']
        with_gps = data['with_gps']
        total = len(missing) + len(with_gps)

        total_missing += len(missing)
        total_with_gps += len(with_gps)

        if not missing and not args.all:
            continue

        if missing:
            folders_with_missing += 1

        pct_missing = (len(missing) / total * 100) if total > 0 else 0

        # Folder header
        print(f"\n{folder_name}/")
        print(f"  {len(missing)}/{total} missing GPS ({pct_missing:.0f}%)")

        # Date range for missing images
        if args.with_dates and missing:
            timestamps = [e['timestamp'] for e in missing if e['timestamp']]
            if timestamps:
                min_date = min(timestamps).strftime('%Y-%m-%d')
                max_date = max(timestamps).strftime('%Y-%m-%d')
                if min_date == max_date:
                    print(f"  Date: {min_date}")
                else:
                    print(f"  Dates: {min_date} to {max_date}")

        # List individual files
        if args.list and missing:
            for entry in sorted(missing, key=lambda x: x['timestamp'] or datetime.min):
                name = entry['path'].name
                if entry['timestamp']:
                    date_str = entry['timestamp'].strftime('%Y-%m-%d %H:%M')
                    print(f"    - {name} ({date_str})")
                else:
                    print(f"    - {name}")

    # Summary
    total_images = total_missing + total_with_gps
    pct_missing = (total_missing / total_images * 100) if total_images > 0 else 0

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total images:        {total_images}")
    print(f"With GPS:            {total_with_gps}")
    print(f"Missing GPS:         {total_missing} ({pct_missing:.1f}%)")
    print(f"Folders with gaps:   {folders_with_missing}")

    if total_missing > 0:
        print("\nTip: Use exif_gps_fix.py to backfill GPS from iPhone photos.")


if __name__ == '__main__':
    main()
