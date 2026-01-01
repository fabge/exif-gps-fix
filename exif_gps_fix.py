#!/usr/bin/env python3
"""
EXIF GPS Fix Tool

Copies GPS coordinates from iPhone photos to Fujifilm camera photos
by matching timestamps within a configurable time window.

Usage:
    python exif_gps_fix.py --source <iphone_folder> --target <fuji_folder> [--dry-run]
"""

import argparse
import json
import subprocess
import sys
from bisect import bisect_left
from datetime import datetime
from pathlib import Path

# Supported image extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.heic', '.heif', '.raf', '.dng', '.tiff', '.tif', '.png'}


def check_exiftool():
    """Check if exiftool is installed."""
    try:
        subprocess.run(['exiftool', '-ver'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def parse_exif_record(exif):
    """Parse a single exiftool JSON record into our format."""
    # Parse timestamp (try DateTimeOriginal first, then CreateDate)
    timestamp = None
    for date_field in ['DateTimeOriginal', 'CreateDate']:
        if exif.get(date_field):
            try:
                timestamp = datetime.strptime(exif[date_field], '%Y:%m:%d %H:%M:%S')
                break
            except ValueError:
                continue

    # Parse GPS data
    gps = None
    has_gps = False
    if 'GPSLatitude' in exif and 'GPSLongitude' in exif:
        lat = exif.get('GPSLatitude')
        lon = exif.get('GPSLongitude')
        if lat is not None and lon is not None:
            has_gps = True
            gps = {
                'lat': float(lat),
                'lon': float(lon),
                'alt': float(exif.get('GPSAltitude', 0)) if exif.get('GPSAltitude') else None,
            }

    return {'timestamp': timestamp, 'gps': gps, 'has_gps': has_gps}


def get_batch_exif_data(file_paths, batch_size=100, show_progress=False):
    """
    Extract EXIF data from multiple files using batched exiftool calls.

    Returns dict mapping file_path -> exif_data (or None on error).
    """
    results = {}
    total = len(file_paths)

    for i in range(0, total, batch_size):
        batch = file_paths[i : i + batch_size]

        if show_progress:
            progress = min(i + batch_size, total)
            print(f"\r  Reading EXIF data: {progress}/{total}", end='', flush=True)

        try:
            cmd = [
                'exiftool',
                '-json',
                '-n',
                '-DateTimeOriginal',
                '-CreateDate',
                '-GPSLatitude',
                '-GPSLongitude',
                '-GPSAltitude',
            ] + [str(p) for p in batch]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            for exif in data:
                file_path = Path(exif.get('SourceFile', ''))
                results[file_path] = parse_exif_record(exif)

        except (subprocess.CalledProcessError, json.JSONDecodeError):
            for p in batch:
                results[p] = None

    if show_progress:
        print()  # Newline after progress

    return results


def build_gps_index(source_folder):
    """
    Scan source folder for photos with GPS data.

    Returns a sorted list of (timestamp, gps_data, filename) tuples.
    """
    source_path = Path(source_folder)
    index = []

    print(f"Scanning source folder for GPS reference photos: {source_path}")

    files = [f for f in source_path.rglob('*') if f.suffix.lower() in IMAGE_EXTENSIONS and ".gps_studio_thumbs" not in f.parts]
    print(f"  Found {len(files)} image files")

    all_exif = get_batch_exif_data(files, show_progress=True)

    for file_path in files:
        exif = all_exif.get(file_path)
        if exif and exif['timestamp'] and exif['has_gps']:
            index.append((exif['timestamp'], exif['gps'], file_path.name))

    # Sort by timestamp
    index.sort(key=lambda x: x[0])

    print(f"  {len(index)} photos with GPS data indexed")
    return index


def find_closest_match(timestamp, gps_index, max_diff_minutes=None):
    """
    Find the closest GPS reference photo to the given timestamp.

    Uses binary search for efficiency.
    Args:
        timestamp: datetime to match
        gps_index: sorted list of (timestamp, gps_data, filename)
        max_diff_minutes: if set, only return match if within this window

    Returns (gps_data, source_filename, time_diff_seconds, is_within_threshold)
    or (None, None, None, False) if no reference photos exist.
    """
    if not gps_index or not timestamp:
        return None, None, None, False

    # Binary search for closest timestamp
    timestamps = [entry[0] for entry in gps_index]
    pos = bisect_left(timestamps, timestamp)

    # Check adjacent entries to find closest
    candidates = []
    if pos > 0:
        candidates.append(pos - 1)
    if pos < len(gps_index):
        candidates.append(pos)

    best_match = None
    best_diff = float('inf')

    for idx in candidates:
        diff = abs((gps_index[idx][0] - timestamp).total_seconds())
        if diff < best_diff:
            best_diff = diff
            best_match = idx

    if best_match is not None:
        entry = gps_index[best_match]
        is_within = max_diff_minutes is None or (best_diff / 60) <= max_diff_minutes
        return entry[1], entry[2], best_diff, is_within

    return None, None, None, False


def write_gps_data(file_path, gps_data, dry_run=False):
    """
    Write GPS coordinates to a file using exiftool.

    Returns True on success, False on failure.
    """
    lat = gps_data['lat']
    lon = gps_data['lon']
    alt = gps_data['alt']

    # Determine lat/lon references
    lat_ref = 'N' if lat >= 0 else 'S'
    lon_ref = 'E' if lon >= 0 else 'W'

    args = [
        'exiftool',
        '-overwrite_original_in_place',
        f'-GPSLatitude={abs(lat)}',
        f'-GPSLatitudeRef={lat_ref}',
        f'-GPSLongitude={abs(lon)}',
        f'-GPSLongitudeRef={lon_ref}',
    ]

    if alt is not None:
        alt_ref = 0 if alt >= 0 else 1  # 0 = above sea level, 1 = below
        args.extend(
            [
                f'-GPSAltitude={abs(alt)}',
                f'-GPSAltitudeRef={alt_ref}',
            ],
        )

    args.append(str(file_path))

    if dry_run:
        return True

    try:
        subprocess.run(args, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Error writing GPS to {file_path}: {e.stderr.decode()}", file=sys.stderr)
        return False


def format_time_diff(seconds):
    """Format time difference in human-readable form."""
    minutes = int(seconds / 60)
    secs = int(seconds % 60)
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def main():
    parser = argparse.ArgumentParser(
        description='Copy GPS coordinates from iPhone photos to Fuji photos based on timestamp matching.',
    )
    parser.add_argument(
        '--source',
        '-s',
        required=True,
        help='Folder containing iPhone photos with GPS data (reference source)',
    )
    parser.add_argument(
        '--target',
        '-t',
        required=True,
        help='Folder containing Fuji photos to add GPS data to',
    )
    parser.add_argument(
        '--max-time-diff',
        '-m',
        type=int,
        default=30,
        help='Maximum time difference in minutes for matching (default: 30)',
    )
    parser.add_argument(
        '--dry-run',
        '-d',
        action='store_true',
        help='Preview matches without writing any changes',
    )
    parser.add_argument(
        '--skip-existing',
        action='store_true',
        default=True,
        help='Skip files that already have GPS data (default: True)',
    )

    args = parser.parse_args()

    # Check exiftool is available
    if not check_exiftool():
        print("Error: exiftool is not installed.", file=sys.stderr)
        print("Install it with: brew install exiftool (macOS) or apt install libimage-exiftool-perl (Linux)", file=sys.stderr)
        sys.exit(1)

    # Validate paths
    source_path = Path(args.source)
    target_path = Path(args.target)

    if not source_path.exists():
        print(f"Error: Source folder does not exist: {source_path}", file=sys.stderr)
        sys.exit(1)

    if not target_path.exists():
        print(f"Error: Target folder does not exist: {target_path}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN MODE - No files will be modified ===\n")

    # Build GPS index from source photos
    gps_index = build_gps_index(source_path)

    if not gps_index:
        print("\nError: No photos with GPS data found in source folder.", file=sys.stderr)
        sys.exit(1)

    # Process target photos
    print(f"\nProcessing target folder: {target_path}")

    target_files = [f for f in target_path.rglob('*') if f.suffix.lower() in IMAGE_EXTENSIONS and ".gps_studio_thumbs" not in f.parts]
    print(f"  Found {len(target_files)} image files")

    target_exif = get_batch_exif_data(target_files, show_progress=True)

    stats = {
        'matched': 0,
        'skipped_has_gps': 0,
        'skipped_no_timestamp': 0,
        'no_match': 0,
        'errors': 0,
    }

    matches = []
    no_matches = []

    for file_path in target_files:
        exif = target_exif.get(file_path)

        if not exif:
            stats['errors'] += 1
            continue

        if not exif['timestamp']:
            stats['skipped_no_timestamp'] += 1
            continue

        if args.skip_existing and exif['has_gps']:
            stats['skipped_has_gps'] += 1
            continue

        # Find closest match
        gps_data, source_file, time_diff, is_within = find_closest_match(
            exif['timestamp'],
            gps_index,
            args.max_time_diff,
        )

        if is_within and gps_data:
            matches.append(
                {
                    'target': file_path,
                    'source': source_file,
                    'time_diff': time_diff,
                    'gps': gps_data,
                    'timestamp': exif['timestamp'],
                },
            )
            stats['matched'] += 1
        else:
            no_matches.append(
                {
                    'target': file_path,
                    'closest_source': source_file,
                    'time_diff': time_diff,
                    'timestamp': exif['timestamp'],
                },
            )
            stats['no_match'] += 1

    # Print matches
    if matches:
        print("Matches found:")
        print("-" * 80)
        for match in sorted(matches, key=lambda x: x['timestamp']):
            print(f"  {match['target'].name}")
            print(f"    <- {match['source']} (time diff: {format_time_diff(match['time_diff'])})")
            print(f"    GPS: {match['gps']['lat']:.6f}, {match['gps']['lon']:.6f}")

            if not args.dry_run:
                success = write_gps_data(match['target'], match['gps'])
                if not success:
                    stats['errors'] += 1
                    stats['matched'] -= 1
            print()

    # Print no matches (with closest reference for adjusting threshold)
    if no_matches:
        print(f"\nNo match found (outside {args.max_time_diff}min window):")
        print("-" * 80)
        for item in sorted(no_matches, key=lambda x: x['time_diff'] if x['time_diff'] else float('inf')):
            print(f"  {item['target'].name}")
            if item['closest_source'] and item['time_diff']:
                diff_minutes = item['time_diff'] / 60
                print(f"    Closest: {item['closest_source']} (time diff: {format_time_diff(item['time_diff'])} = {diff_minutes:.1f}min)")
            else:
                print("    No reference photos found")
        print()

    # Print summary
    print("=" * 80)
    print("Summary:")
    print(f"  Photos matched and {'would be ' if args.dry_run else ''}updated: {stats['matched']}")
    print(f"  Skipped (already has GPS): {stats['skipped_has_gps']}")
    print(f"  Skipped (no timestamp): {stats['skipped_no_timestamp']}")
    print(f"  No match found (outside {args.max_time_diff}min window): {stats['no_match']}")
    if stats['errors']:
        print(f"  Errors: {stats['errors']}")

    if args.dry_run and stats['matched'] > 0:
        print("\nRun without --dry-run to apply changes.")


if __name__ == '__main__':
    main()
