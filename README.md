# EXIF GPS Fix

Tools to copy GPS coordinates from smartphone photos to camera photos by matching timestamps.

When you shoot with a dedicated camera, your photos might not have GPS data. But your phone was probably in your pocket, taking photos with GPS. This tool matches timestamps between your camera and phone photos, then copies the GPS coordinates over.

## Requirements

- Python 3.x
- [exiftool](https://exiftool.org/) - for reading/writing EXIF metadata
  ```bash
  # macOS
  brew install exiftool

  # Linux
  apt install libimage-exiftool-perl
  ```

For the web UI:
```bash
pip install flask pillow
```

For Gemini Vision location detection (optional):
```bash
pip install google-generativeai
export GEMINI_API_KEY=your_api_key
```

## Tools

### 1. GPS Studio (Web UI)

Visual interface for reviewing and applying GPS fixes.

```bash
python gps_studio.py
```

Opens at http://localhost:8001

**Features:**
- Side-by-side comparison of camera and phone photos
- Adjustable time window with live filtering
- Confidence indicators (green/yellow/red based on time difference)
- Manual location entry (type coordinates or place names)
- Gemini Vision AI for identifying locations from images
- Dry-run mode to preview changes

### 2. CLI Tool

Batch process photos from the command line.

```bash
# Preview matches (dry run)
python exif_gps_fix.py \
  --source "/path/to/phone/photos" \
  --target "/path/to/camera/photos" \
  --dry-run

# Apply GPS data
python exif_gps_fix.py \
  --source "/path/to/phone/photos" \
  --target "/path/to/camera/photos"

# Custom time window (default: 30 minutes)
python exif_gps_fix.py \
  --source "/path/to/phone/photos" \
  --target "/path/to/camera/photos" \
  --max-time-diff 120
```

### 3. Find Missing GPS

Scan folders to find images without GPS metadata.

```bash
# Summary by folder
python find_missing_gps.py /path/to/photos

# List individual files
python find_missing_gps.py /path/to/photos --list

# Show date ranges
python find_missing_gps.py /path/to/photos --with-dates
```

## How It Works

1. Scans the source folder (phone photos) and builds an index of timestamps + GPS coordinates
2. For each photo in the target folder (camera photos) missing GPS:
   - Finds the closest timestamp match in the source index
   - If within the time window, copies the GPS coordinates
3. Uses binary search for efficient matching across large photo libraries

## Supported Formats

`.jpg`, `.jpeg`, `.heic`, `.heif`, `.raf`, `.dng`, `.tiff`, `.tif`, `.png`
