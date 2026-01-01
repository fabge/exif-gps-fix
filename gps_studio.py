#!/usr/bin/env python3
"""GPS Studio - Visual workflow for fixing photo GPS metadata."""

import hashlib
import json
import os
import tempfile
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_file

app = Flask(__name__)

# Session state
SESSION_FILE = Path(tempfile.gettempdir()) / "gps_studio_session.json"
THUMB_DIR = Path(__file__).parent / ".thumbs"
THUMB_SIZE = 300

# Image extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.heic', '.heif', '.raf', '.dng', '.tiff', '.tif', '.png'}

HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>GPS Studio</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #1a1a1a;
            color: #fff;
            min-height: 100vh;
        }

        /* Header */
        header {
            padding: 15px 20px;
            border-bottom: 1px solid #333;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1 { font-size: 1.3rem; font-weight: 500; }
        .status {
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 13px;
            display: none;
        }
        .status.success { display: block; background: #4CAF50; }
        .status.error { display: block; background: #f44336; }
        .status.info { display: block; background: #2196F3; }

        /* Tabs */
        .tabs {
            display: flex;
            gap: 4px;
            padding: 10px 20px 0;
            background: #222;
        }
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            border: none;
            background: transparent;
            color: #888;
            font-size: 14px;
            border-radius: 8px 8px 0 0;
            transition: all 0.2s;
        }
        .tab:hover { color: #fff; background: #2a2a2a; }
        .tab.active { color: #fff; background: #1a1a1a; }
        .tab .badge {
            background: #444;
            padding: 2px 6px;
            border-radius: 10px;
            font-size: 11px;
            margin-left: 6px;
        }
        .tab.active .badge { background: #4CAF50; }

        /* Tab content */
        .tab-content {
            display: none;
            padding: 20px;
            min-height: calc(100vh - 110px);
        }
        .tab-content.active { display: block; }

        /* Buttons */
        button {
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: opacity 0.2s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        button:hover { opacity: 0.8; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary { background: #4CAF50; color: white; }
        .btn-secondary { background: #2196F3; color: white; }
        .btn-danger { background: #f44336; color: white; }
        .btn-outline {
            background: transparent;
            border: 1px solid #444;
            color: #fff;
        }

        /* Forms */
        input[type="text"], select {
            padding: 10px 12px;
            border: 1px solid #444;
            border-radius: 6px;
            background: #2a2a2a;
            color: #fff;
            font-size: 14px;
            width: 100%;
        }
        input[type="text"]:focus, select:focus {
            outline: none;
            border-color: #4CAF50;
        }
        label {
            display: block;
            margin-bottom: 6px;
            color: #aaa;
            font-size: 13px;
        }
        /* Section cards */
        .card {
            background: #222;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
        }
        .card-title {
            font-size: 16px;
            font-weight: 500;
            margin-bottom: 15px;
        }

        /* Stats grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .stat-card {
            background: #2a2a2a;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-value {
            font-size: 28px;
            font-weight: 600;
            color: #4CAF50;
        }
        .stat-value.warning { color: #ff9800; }
        .stat-value.danger { color: #f44336; }
        .stat-label {
            font-size: 12px;
            color: #888;
            margin-top: 5px;
        }

        /* Match grid */
        .match-grid {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .match-row {
            display: grid;
            grid-template-columns: 40px 1fr 40px 1fr 100px;
            gap: 15px;
            align-items: center;
            background: #2a2a2a;
            padding: 12px;
            border-radius: 8px;
            border-left: 4px solid #4CAF50;
        }
        .match-row.medium { border-left-color: #ff9800; }
        .match-row.low { border-left-color: #f44336; }
        .match-row.no-match { border-left-color: #666; opacity: 0.7; }

        .match-checkbox {
            width: 20px;
            height: 20px;
            cursor: pointer;
        }
        .match-photo {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .match-thumb {
            width: 60px;
            height: 60px;
            object-fit: cover;
            border-radius: 4px;
            cursor: pointer;
        }
        .match-info {
            flex: 1;
            min-width: 0;
        }
        .match-filename {
            font-size: 13px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .match-meta {
            font-size: 11px;
            color: #888;
            margin-top: 2px;
        }
        .match-arrow {
            color: #666;
            font-size: 20px;
        }
        .match-diff {
            text-align: right;
            font-size: 12px;
        }
        .match-diff .time {
            font-weight: 500;
        }
        .match-diff .gps {
            font-size: 10px;
            color: #888;
        }

        /* Bulk actions */
        .bulk-actions {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            padding: 10px;
            background: #222;
            border-radius: 8px;
        }

        /* Unmatched card */
        .unmatched-card {
            background: #2a2a2a;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            display: grid;
            grid-template-columns: 120px 1fr auto;
            gap: 15px;
            align-items: start;
        }
        .unmatched-thumb {
            width: 120px;
            height: 90px;
            object-fit: cover;
            border-radius: 4px;
            cursor: pointer;
        }
        .unmatched-info h3 {
            font-size: 14px;
            margin-bottom: 8px;
        }
        .unmatched-result {
            background: #333;
            padding: 10px;
            border-radius: 4px;
            margin-top: 10px;
            font-size: 13px;
        }
        .unmatched-result .location {
            font-weight: 500;
            color: #4CAF50;
        }
        .unmatched-result .confidence {
            font-size: 11px;
            color: #888;
        }
        .unmatched-actions {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        /* Apply tab */
        .apply-summary {
            background: #2a2a2a;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .apply-summary h3 {
            margin-bottom: 15px;
        }
        .apply-list {
            max-height: 300px;
            overflow-y: auto;
            font-size: 13px;
            font-family: monospace;
            background: #1a1a1a;
            padding: 10px;
            border-radius: 4px;
        }
        .apply-item {
            padding: 4px 0;
            border-bottom: 1px solid #333;
        }
        .apply-item:last-child { border-bottom: none; }
        .progress-bar {
            height: 8px;
            background: #333;
            border-radius: 4px;
            overflow: hidden;
            margin: 15px 0;
        }
        .progress-fill {
            height: 100%;
            background: #4CAF50;
            transition: width 0.3s;
        }
        .toggle-group {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
        }
        .toggle {
            position: relative;
            width: 50px;
            height: 26px;
        }
        .toggle input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        .toggle-slider {
            position: absolute;
            cursor: pointer;
            inset: 0;
            background: #444;
            border-radius: 26px;
            transition: 0.3s;
        }
        .toggle-slider:before {
            position: absolute;
            content: "";
            height: 20px;
            width: 20px;
            left: 3px;
            bottom: 3px;
            background: white;
            border-radius: 50%;
            transition: 0.3s;
        }
        .toggle input:checked + .toggle-slider {
            background: #4CAF50;
        }
        .toggle input:checked + .toggle-slider:before {
            transform: translateX(24px);
        }

        /* Preview modal */
        .preview-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.95);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }
        .preview-modal.active { display: flex; }
        .preview-modal img {
            max-width: 90vw;
            max-height: 90vh;
            object-fit: contain;
            transition: opacity 0.15s;
        }
        .preview-modal .close-btn {
            position: absolute;
            top: 20px;
            right: 20px;
            background: transparent;
            border: none;
            color: #fff;
            font-size: 32px;
            cursor: pointer;
            opacity: 0.7;
        }
        .preview-modal .close-btn:hover { opacity: 1; }

        /* Empty state */
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #666;
        }
        .empty-state h2 {
            font-size: 18px;
            margin-bottom: 10px;
            color: #888;
        }

        /* Loading spinner */
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid #fff;
            border-radius: 50%;
            border-top-color: transparent;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <header>
        <h1>GPS Studio</h1>
        <span class="status" id="status"></span>
    </header>

    <nav class="tabs">
        <button class="tab active" data-tab="scan">Scan</button>
        <button class="tab" data-tab="match">Match <span class="badge" id="matchCount">0</span></button>
        <button class="tab" data-tab="unmatched">Unmatched <span class="badge" id="unmatchedCount">0</span></button>
        <button class="tab" data-tab="apply">Apply</button>
    </nav>

    <!-- Scan Tab -->
    <div class="tab-content active" id="tab-scan">
        <div class="card">
            <div class="card-title">Folder Selection</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div>
                    <label>Source Folder (smartphone photos with GPS)</label>
                    <input type="text" id="sourceFolder" value="/Volumes/data/photos/Smartphone Photos/2025">
                </div>
                <div>
                    <label>Target Folder (camera photos needing GPS)</label>
                    <input type="text" id="targetFolder" value="/Volumes/data/photos/2025">
                </div>
            </div>
            <div style="margin-top: 15px;">
                <button class="btn-primary" onclick="runScan()">
                    Scan Folders
                </button>
            </div>
        </div>

        <div id="scanResults" style="display: none;">
            <div class="card" style="margin-bottom: 15px;">
                <div style="display: flex; align-items: center; gap: 20px;">
                    <label style="margin: 0; white-space: nowrap;">Time Window:</label>
                    <input type="range" id="timeWindow" min="5" max="480" value="120"
                           style="flex: 1; accent-color: #4CAF50;">
                    <span id="windowValue" style="min-width: 50px; font-weight: 500;">2h</span>
                </div>
            </div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" id="statTotal">0</div>
                    <div class="stat-label">Total in Target</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="statHasGps">0</div>
                    <div class="stat-label">Already Have GPS</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value warning" id="statMissing">0</div>
                    <div class="stat-label">Missing GPS</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="statMatched">0</div>
                    <div class="stat-label">Can Match</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value danger" id="statNoMatch">0</div>
                    <div class="stat-label">No Match</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Match Tab -->
    <div class="tab-content" id="tab-match">
        <div class="bulk-actions">
            <button class="btn-outline" onclick="selectAll('high')">Select High Confidence</button>
            <button class="btn-outline" onclick="selectAll('medium')">Select Medium</button>
            <button class="btn-outline" onclick="selectAll('all')">Select All</button>
            <button class="btn-outline" onclick="selectAll('none')">Deselect All</button>
            <span style="margin-left: auto; color: #888;" id="selectedCount">0 selected</span>
        </div>
        <div class="match-grid" id="matchGrid">
            <div class="empty-state">
                <h2>No matches yet</h2>
                <p>Run a scan first to find GPS matches</p>
            </div>
        </div>
    </div>

    <!-- Unmatched Tab -->
    <div class="tab-content" id="tab-unmatched">
        <div class="card" style="margin-bottom: 20px;">
            <p style="color: #888; font-size: 13px;">
                Photos that couldn't be matched by timestamp. Enter a location or coordinates manually,
                or use Gemini Vision AI to identify locations (requires GEMINI_API_KEY).
            </p>
        </div>
        <div id="unmatchedGrid">
            <div class="empty-state">
                <h2>No unmatched photos</h2>
                <p>Run a scan first</p>
            </div>
        </div>
    </div>

    <!-- Apply Tab -->
    <div class="tab-content" id="tab-apply">
        <div class="card">
            <div class="toggle-group">
                <label class="toggle">
                    <input type="checkbox" id="dryRun" checked>
                    <span class="toggle-slider"></span>
                </label>
                <span>Dry Run (preview only, no changes)</span>
            </div>
            <div class="apply-summary" id="applySummary">
                <h3>Changes to Apply</h3>
                <p style="color: #888;">Select matches in the Match tab, then apply here.</p>
                <div class="apply-list" id="applyList"></div>
            </div>
            <div class="progress-bar" id="progressBar" style="display: none;">
                <div class="progress-fill" id="progressFill" style="width: 0%"></div>
            </div>
            <button class="btn-primary" onclick="applyChanges()" id="applyBtn">
                Apply Selected Changes
            </button>
            <div id="applyResults" style="margin-top: 20px; display: none;"></div>
        </div>
    </div>

    <!-- Preview Modal -->
    <div class="preview-modal" id="previewModal" onclick="closePreview()">
        <button class="close-btn">&times;</button>
        <img id="previewImage" src="" alt="Preview">
    </div>

    <script>
        let scanData = null;
        let selectedMatches = new Set();

        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
            });
        });

        function showStatus(msg, type = 'info') {
            const el = document.getElementById('status');
            el.textContent = msg;
            el.className = 'status ' + type;
            if (type !== 'info') {
                setTimeout(() => el.className = 'status', 4000);
            }
        }

        // Format time window for display
        function formatWindow(minutes) {
            if (minutes < 60) return `${minutes}m`;
            if (minutes % 60 === 0) return `${minutes / 60}h`;
            return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
        }

        // Filter matches based on current time window
        function getFilteredMatches() {
            if (!scanData?.all_matches) return { matches: [], noMatches: [] };

            const windowMinutes = parseInt(document.getElementById('timeWindow').value);
            const windowSeconds = windowMinutes * 60;
            const matches = [];
            const noMatches = [];

            scanData.all_matches.forEach(m => {
                if (m.time_diff !== null && m.time_diff <= windowSeconds && m.gps) {
                    matches.push(m);
                } else {
                    noMatches.push(m);
                }
            });

            return { matches, noMatches };
        }

        // Update view based on current slider value
        function updateFilteredView() {
            const windowMinutes = parseInt(document.getElementById('timeWindow').value);
            document.getElementById('windowValue').textContent = formatWindow(windowMinutes);

            const { matches, noMatches } = getFilteredMatches();

            // Update stats
            document.getElementById('statMatched').textContent = matches.length;
            document.getElementById('statNoMatch').textContent = noMatches.length;
            document.getElementById('matchCount').textContent = matches.length;
            document.getElementById('unmatchedCount').textContent = noMatches.length;

            // Re-render grids
            renderMatchGrid(matches);
            renderUnmatchedGrid(noMatches);
            updateApplyList();
        }

        // Slider event listener
        document.getElementById('timeWindow').addEventListener('input', updateFilteredView);

        async function runScan() {
            const source = document.getElementById('sourceFolder').value;
            const target = document.getElementById('targetFolder').value;

            if (!source || !target) {
                showStatus('Please enter both folders', 'error');
                return;
            }

            showStatus('Scanning folders...', 'info');

            try {
                const res = await fetch(`/api/scan?source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`);
                const data = await res.json();

                if (data.error) {
                    showStatus('Error: ' + data.error, 'error');
                    return;
                }

                scanData = data;
                selectedMatches.clear();
                renderScanResults();
                updateFilteredView();  // This renders grids with current slider value
                showStatus('Scan complete!', 'success');

            } catch (e) {
                showStatus('Scan failed: ' + e.message, 'error');
            }
        }

        function renderScanResults() {
            document.getElementById('scanResults').style.display = 'block';
            document.getElementById('statTotal').textContent = scanData.total;
            document.getElementById('statHasGps').textContent = scanData.has_gps;
            document.getElementById('statMissing').textContent = scanData.missing_gps;
            // statMatched and statNoMatch are updated by updateFilteredView()
        }

        function getConfidenceClass(timeDiff) {
            const mins = timeDiff / 60;
            if (mins <= 30) return 'high';
            if (mins <= 120) return 'medium';
            return 'low';
        }

        function formatTimeDiff(seconds) {
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            if (mins > 60) {
                const hrs = Math.floor(mins / 60);
                const m = mins % 60;
                return `${hrs}h ${m}m`;
            }
            return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
        }

        function renderMatchGrid(matches) {
            const grid = document.getElementById('matchGrid');

            if (!matches || matches.length === 0) {
                grid.innerHTML = '<div class="empty-state"><h2>No matches found</h2><p>Try increasing the time window</p></div>';
                return;
            }

            grid.innerHTML = matches.map((m) => {
                const conf = getConfidenceClass(m.time_diff);
                const checked = selectedMatches.has(m.target) ? 'checked' : '';
                const targetEsc = m.target.replace(/'/g, "\\'");
                return `
                    <div class="match-row ${conf}">
                        <input type="checkbox" class="match-checkbox" data-target="${m.target}" ${checked} onchange="toggleMatch('${targetEsc}')">
                        <div class="match-photo">
                            <img class="match-thumb" src="/api/thumb?path=${encodeURIComponent(m.target)}" onclick="openPreview('/api/photo?path=${encodeURIComponent(m.target)}')">
                            <div class="match-info">
                                <div class="match-filename">${m.target_name}</div>
                                <div class="match-meta">${m.target_time || ''}</div>
                            </div>
                        </div>
                        <div class="match-arrow">→</div>
                        <div class="match-photo">
                            <img class="match-thumb" src="/api/thumb?path=${encodeURIComponent(m.source)}" onclick="openPreview('/api/photo?path=${encodeURIComponent(m.source)}')">
                            <div class="match-info">
                                <div class="match-filename">${m.source_name}</div>
                                <div class="match-meta">GPS: ${m.gps.lat.toFixed(4)}, ${m.gps.lon.toFixed(4)}</div>
                            </div>
                        </div>
                        <div class="match-diff">
                            <div class="time">${formatTimeDiff(m.time_diff)}</div>
                            <div class="gps">${conf} confidence</div>
                        </div>
                    </div>
                `;
            }).join('');

            updateSelectedCount();
        }

        function renderUnmatchedGrid(noMatches) {
            const grid = document.getElementById('unmatchedGrid');

            if (!noMatches || noMatches.length === 0) {
                grid.innerHTML = '<div class="empty-state"><h2>All photos can be matched!</h2><p>Try decreasing the time window to see unmatched photos</p></div>';
                return;
            }

            grid.innerHTML = noMatches.map((m, idx) => {
                const targetEsc = m.target.replace(/'/g, "\\'");
                return `
                <div class="unmatched-card" id="unmatched-${idx}">
                    <img class="unmatched-thumb" src="/api/thumb?path=${encodeURIComponent(m.target)}" onclick="openPreview('/api/photo?path=${encodeURIComponent(m.target)}')">
                    <div class="unmatched-info">
                        <h3>${m.target_name}</h3>
                        <div style="color: #888; font-size: 12px;">${m.target_time || 'No timestamp'}</div>
                        ${m.closest_source ? `<div style="color: #666; font-size: 11px; margin-top: 5px;">Closest: ${m.closest_source} (${formatTimeDiff(m.time_diff)})</div>` : ''}
                        <div style="margin-top: 10px; display: flex; gap: 8px;">
                            <input type="text" id="location-input-${idx}" placeholder="Paris, France or 48.85, 2.35" style="flex: 1; padding: 6px 8px; font-size: 12px;">
                            <button class="btn-outline" style="padding: 6px 12px; font-size: 12px;" onclick="lookupLocation(${idx}, '${targetEsc}')">Set</button>
                        </div>
                        <div class="unmatched-result" id="unmatched-result-${idx}" style="display: none;"></div>
                    </div>
                    <div class="unmatched-actions">
                        <button class="btn-secondary" onclick="analyzeWithGemini(${idx}, '${targetEsc}')">
                            Analyze
                        </button>
                    </div>
                </div>
            `}).join('');
        }

        function toggleMatch(target) {
            if (selectedMatches.has(target)) {
                selectedMatches.delete(target);
            } else {
                selectedMatches.add(target);
            }
            updateSelectedCount();
            updateApplyList();
        }

        function selectAll(mode) {
            if (!scanData) return;

            const { matches } = getFilteredMatches();

            if (mode === 'none') {
                selectedMatches.clear();
            } else {
                matches.forEach(m => {
                    const conf = getConfidenceClass(m.time_diff);
                    if (mode === 'all' || mode === conf || (mode === 'medium' && conf !== 'low')) {
                        selectedMatches.add(m.target);
                    }
                });
            }

            document.querySelectorAll('.match-checkbox').forEach(cb => {
                cb.checked = selectedMatches.has(cb.dataset.target);
            });

            updateSelectedCount();
            updateApplyList();
        }

        function updateSelectedCount() {
            document.getElementById('selectedCount').textContent = `${selectedMatches.size} selected`;
        }

        function updateApplyList() {
            const list = document.getElementById('applyList');
            if (selectedMatches.size === 0) {
                list.innerHTML = '<div style="color: #666;">No matches selected</div>';
                return;
            }

            // Build lookup map from all_matches
            const matchMap = {};
            if (scanData?.all_matches) {
                scanData.all_matches.forEach(m => {
                    if (m.gps) matchMap[m.target] = m;
                });
            }

            list.innerHTML = Array.from(selectedMatches).map(target => {
                const m = matchMap[target];
                if (!m) return '';
                return `<div class="apply-item">${m.target_name} ← (${m.gps.lat.toFixed(4)}, ${m.gps.lon.toFixed(4)})</div>`;
            }).filter(Boolean).join('');
        }

        async function analyzeWithGemini(idx, imagePath) {
            const resultDiv = document.getElementById(`unmatched-result-${idx}`);
            resultDiv.style.display = 'block';
            resultDiv.innerHTML = '<span class="spinner"></span> Analyzing with Gemini...';

            try {
                const res = await fetch('/api/geointel', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({image_path: imagePath})
                });
                const data = await res.json();

                if (data.error) {
                    resultDiv.innerHTML = `<span style="color: #f44336;">Error: ${data.error}</span>`;
                    return;
                }

                const pathEsc = imagePath.replace(/'/g, "\\'");
                resultDiv.innerHTML = `
                    <div class="location">${data.location}</div>
                    <div class="confidence">Confidence: ${data.confidence}</div>
                    <div style="margin-top: 8px; font-size: 12px; color: #aaa;">${data.explanation || ''}</div>
                    ${data.coordinates ? `
                        <div style="margin-top: 10px;">
                            <button class="btn-primary" onclick="approveLocation(${idx}, '${pathEsc}', ${data.coordinates.lat}, ${data.coordinates.lon})">
                                Approve (${data.coordinates.lat.toFixed(4)}, ${data.coordinates.lon.toFixed(4)})
                            </button>
                        </div>
                    ` : ''}
                `;
            } catch (e) {
                resultDiv.innerHTML = `<span style="color: #f44336;">Error: ${e.message}</span>`;
            }
        }

        // Look up location via Nominatim (handles both place names and coordinates)
        async function lookupLocation(idx, target) {
            const input = document.getElementById(`location-input-${idx}`);
            const resultDiv = document.getElementById(`unmatched-result-${idx}`);
            const query = input.value.trim();

            if (!query) {
                showStatus('Please enter a location', 'error');
                return;
            }

            resultDiv.style.display = 'block';
            resultDiv.innerHTML = '<span class="spinner"></span> Looking up location...';

            try {
                const res = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
                const data = await res.json();

                if (data.error) {
                    resultDiv.innerHTML = `<span style="color: #f44336;">${data.error}</span>`;
                    return;
                }

                const targetEsc = target.replace(/'/g, "\\'");
                resultDiv.innerHTML = `
                    <div class="location">${data.location}</div>
                    <div class="confidence">${data.lat.toFixed(4)}, ${data.lon.toFixed(4)}</div>
                    <div style="margin-top: 10px;">
                        <button class="btn-primary" onclick="approveLocation(${idx}, '${targetEsc}', ${data.lat}, ${data.lon})">
                            Approve
                        </button>
                    </div>
                `;
            } catch (e) {
                resultDiv.innerHTML = `<span style="color: #f44336;">Error: ${e.message}</span>`;
            }
        }

        function approveLocation(idx, target, lat, lon) {
            // Add to approved list
            if (!scanData.approved_unmatched) scanData.approved_unmatched = [];

            // Find the item by target path
            const { noMatches } = getFilteredMatches();
            const item = noMatches.find(m => m.target === target);
            if (!item) return;

            scanData.approved_unmatched.push({
                target: item.target,
                target_name: item.target_name,
                gps: {lat, lon}
            });

            document.getElementById(`unmatched-${idx}`).style.opacity = '0.5';
            document.getElementById(`unmatched-result-${idx}`).innerHTML += '<div style="color: #4CAF50; margin-top: 5px;">Approved!</div>';

            showStatus('Location approved. Apply in Apply tab.', 'success');
        }

        async function applyChanges() {
            const dryRun = document.getElementById('dryRun').checked;
            const btn = document.getElementById('applyBtn');
            const progressBar = document.getElementById('progressBar');
            const progressFill = document.getElementById('progressFill');
            const results = document.getElementById('applyResults');

            // Collect all changes
            const changes = [];

            // Build lookup map from all_matches
            const matchMap = {};
            if (scanData?.all_matches) {
                scanData.all_matches.forEach(m => {
                    if (m.gps) matchMap[m.target] = m;
                });
            }

            // From timestamp matches
            selectedMatches.forEach(target => {
                const m = matchMap[target];
                if (m) changes.push({target: m.target, gps: m.gps});
            });

            // From approved unmatched (manual/Gemini)
            if (scanData.approved_unmatched) {
                scanData.approved_unmatched.forEach(g => {
                    changes.push({target: g.target, gps: g.gps});
                });
            }

            if (changes.length === 0) {
                showStatus('No changes selected', 'error');
                return;
            }

            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Processing...';
            progressBar.style.display = 'block';
            progressFill.style.width = '0%';
            results.style.display = 'block';
            results.innerHTML = `<div style="color: #888;">Processing ${changes.length} files...</div>`;

            try {
                const res = await fetch('/api/apply', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({changes, dry_run: dryRun})
                });

                if (!res.ok) {
                    throw new Error(`Server error: ${res.status} ${res.statusText}`);
                }

                const data = await res.json();

                progressFill.style.width = '100%';

                if (data.error) {
                    results.innerHTML = `<div style="color: #f44336;">Error: ${data.error}</div>`;
                    showStatus('Apply failed', 'error');
                } else {
                    const mode = dryRun ? 'Would update' : 'Updated';
                    let html = `
                        <div style="color: ${data.errors > 0 ? '#ff9800' : '#4CAF50'}; margin-bottom: 10px;">
                            ${mode} ${data.success} files${data.errors > 0 ? `, ${data.errors} errors` : ''}
                        </div>
                    `;
                    if (data.error_details && data.error_details.length > 0) {
                        html += `<div style="font-size: 12px; color: #f44336; margin-bottom: 10px;">
                            ${data.error_details.join('<br>')}
                        </div>`;
                    }
                    html += `<div style="font-size: 12px; color: #888;">
                        ${dryRun ? 'Uncheck "Dry Run" to apply for real.' : 'GPS data has been written to files.'}
                    </div>`;
                    results.innerHTML = html;
                    showStatus(dryRun ? 'Dry run complete!' : 'Changes applied!', 'success');
                }

            } catch (e) {
                progressFill.style.width = '0%';
                results.innerHTML = `<div style="color: #f44336;">Error: ${e.message}</div>`;
                showStatus('Apply failed: ' + e.message, 'error');
            }

            btn.disabled = false;
            btn.innerHTML = 'Apply Selected Changes';
        }

        function openPreview(src) {
            const img = document.getElementById('previewImage');
            img.style.opacity = '0';
            img.src = src;
            img.onload = () => img.style.opacity = '1';
            document.getElementById('previewModal').classList.add('active');
        }

        function closePreview() {
            document.getElementById('previewModal').classList.remove('active');
        }

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') closePreview();
        });

        // Load saved session
        async function loadSession() {
            try {
                const res = await fetch('/api/session');
                const data = await res.json();
                if (data.source) document.getElementById('sourceFolder').value = data.source;
                if (data.target) document.getElementById('targetFolder').value = data.target;
            } catch (e) {}
        }

        loadSession();
    </script>
</body>
</html>"""


def get_session():
    """Load session data."""
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text())
    return {}


def save_session(data):
    """Save session data."""
    SESSION_FILE.write_text(json.dumps(data))


@app.route("/")
def index():
    return HTML


@app.route("/api/session")
def api_session():
    return jsonify(get_session())


@app.route("/api/thumb")
def api_thumb():
    """Serve thumbnail for an image."""
    path = request.args.get("path", "")
    if not path or not Path(path).exists():
        return "Not found", 404

    path = Path(path)

    # Use central thumbs directory in project folder
    THUMB_DIR.mkdir(exist_ok=True)

    # Hash-based thumb filename (unique per full path)
    thumb_name = hashlib.md5(str(path).encode()).hexdigest() + ".jpg"
    thumb_path = THUMB_DIR / thumb_name

    if not thumb_path.exists():
        # Generate thumbnail
        try:
            from PIL import Image

            with Image.open(path) as img:
                # Handle EXIF rotation
                try:
                    from PIL import ExifTags

                    for orientation in ExifTags.TAGS:
                        if ExifTags.TAGS[orientation] == 'Orientation':
                            break
                    exif = img._getexif()
                    if exif and orientation in exif:
                        if exif[orientation] == 3:
                            img = img.rotate(180, expand=True)
                        elif exif[orientation] == 6:
                            img = img.rotate(270, expand=True)
                        elif exif[orientation] == 8:
                            img = img.rotate(90, expand=True)
                except Exception:
                    pass

                img.thumbnail((THUMB_SIZE, THUMB_SIZE))
                img = img.convert("RGB")
                img.save(thumb_path, "JPEG", quality=80)
        except Exception as e:
            return f"Error generating thumbnail: {e}", 500

    return send_file(thumb_path, mimetype="image/jpeg")


@app.route("/api/photo")
def api_photo():
    """Serve full image."""
    path = request.args.get("path", "")
    if not path or not Path(path).exists():
        return "Not found", 404
    return send_file(path)


@app.route("/api/scan")
def api_scan():
    """Scan folders and find matches."""
    source = request.args.get("source", "")
    target = request.args.get("target", "")

    if not source or not target:
        return jsonify({"error": "Source and target folders required"})

    source_path = Path(source)
    target_path = Path(target)

    if not source_path.exists():
        return jsonify({"error": f"Source folder not found: {source}"})
    if not target_path.exists():
        return jsonify({"error": f"Target folder not found: {target}"})

    # Save session (folder paths only, window is client-side)
    save_session({"source": source, "target": target})

    # Import our existing functions
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from exif_gps_fix import build_gps_index, find_closest_match, get_batch_exif_data

    # Build GPS index from source
    gps_index = build_gps_index(source_path)

    # Get target files (exclude our thumbnail directories)
    target_files = [f for f in target_path.rglob("*") if f.suffix.lower() in IMAGE_EXTENSIONS and ".gps_studio_thumbs" not in f.parts]
    target_exif = get_batch_exif_data(target_files, show_progress=False)

    # Analyze - return ALL matches, let frontend filter by time window
    results = {
        "total": len(target_files),
        "has_gps": 0,
        "missing_gps": 0,
        "all_matches": [],  # All photos missing GPS with their closest match
    }

    for file_path in target_files:
        exif = target_exif.get(file_path)
        if not exif:
            continue

        if exif["has_gps"]:
            results["has_gps"] += 1
            continue

        results["missing_gps"] += 1

        target_time = exif["timestamp"].strftime("%Y-%m-%d %H:%M") if exif["timestamp"] else None

        # Find closest match (no window filter - return closest regardless)
        gps_data, source_file, time_diff, _ = find_closest_match(
            exif["timestamp"],
            gps_index,
            max_diff_minutes=None,
        )

        # Find source file full path if we have a match
        source_full = ""
        if source_file:
            source_files = list(source_path.rglob(source_file))
            source_full = str(source_files[0]) if source_files else ""

        results["all_matches"].append(
            {
                "target": str(file_path),
                "target_name": file_path.name,
                "target_time": target_time,
                "source": source_full,
                "source_name": source_file,
                "time_diff": time_diff,  # seconds, or None if no timestamp
                "gps": gps_data,  # GPS from closest match, or None
            },
        )

    # Sort by time diff (None values at end)
    results["all_matches"].sort(key=lambda x: x["time_diff"] if x["time_diff"] is not None else float("inf"))

    return jsonify(results)


@app.route("/api/geointel", methods=["POST"])
def api_geointel():
    """Analyze image with Gemini Vision."""
    data = request.get_json()
    image_path = data.get("image_path", "")

    if not image_path or not Path(image_path).exists():
        return jsonify({"error": "Image not found"})

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return jsonify({"error": "GEMINI_API_KEY environment variable not set"})

    try:
        import google.generativeai as genai
        from PIL import Image

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        # Load and resize image for API
        img = Image.open(image_path)
        img.thumbnail((1024, 1024))

        prompt = """Analyze this image and identify where it was taken.

Return ONLY a JSON object in this exact format (no other text):
{
    "location": "City, Country",
    "coordinates": {"lat": 12.345, "lon": 67.890},
    "confidence": "high/medium/low",
    "explanation": "Brief explanation of how you identified this location"
}

If you cannot determine the location, set location to "Unknown" and coordinates to null."""

        response = model.generate_content([prompt, img])

        # Parse response
        text = response.text.strip()
        # Remove markdown code blocks if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        result = json.loads(text)
        return jsonify(result)

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Failed to parse Gemini response: {e}", "raw": text})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/geocode")
def api_geocode():
    """Geocode a location name using Nominatim."""
    import urllib.parse
    import urllib.request

    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "No query provided"})

    try:
        # Nominatim API (free, no key needed, but requires User-Agent)
        encoded = urllib.parse.quote(query)
        url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1"

        req = urllib.request.Request(url, headers={"User-Agent": "GPSStudio/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        if not data:
            return jsonify({"error": f"Location not found: {query}"})

        result = data[0]
        return jsonify(
            {
                "location": result.get("display_name", query),
                "lat": float(result["lat"]),
                "lon": float(result["lon"]),
            },
        )

    except Exception as e:
        return jsonify({"error": f"Geocoding failed: {e!s}"})


@app.route("/api/apply", methods=["POST"])
def api_apply():
    """Apply GPS changes to files."""
    try:
        data = request.get_json()
        changes = data.get("changes", [])
        dry_run = data.get("dry_run", True)

        if not changes:
            return jsonify({"error": "No changes provided"})

        # Import write function
        import sys

        sys.path.insert(0, str(Path(__file__).parent))
        from exif_gps_fix import write_gps_data

        success = 0
        errors = 0
        error_details = []
        total = len(changes)

        print(f"Applying GPS to {total} files (dry_run={dry_run})...")

        for i, change in enumerate(changes):
            target = change.get("target")
            gps = change.get("gps")

            if not target or not gps:
                errors += 1
                error_details.append("Invalid change entry")
                continue

            try:
                if dry_run:
                    success += 1
                else:
                    if write_gps_data(Path(target), gps, dry_run=False):
                        success += 1
                    else:
                        errors += 1
                        error_details.append(f"Failed to write: {Path(target).name}")

                # Progress logging every 10 files
                if (i + 1) % 10 == 0 or (i + 1) == total:
                    print(f"  Progress: {i + 1}/{total}")

            except Exception as e:
                errors += 1
                error_details.append(f"{Path(target).name}: {e!s}")

        result = {"success": success, "errors": errors}
        if error_details:
            result["error_details"] = error_details[:10]  # Limit to first 10
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": f"Server error: {e!s}"})


if __name__ == "__main__":
    print("Starting GPS Studio at http://localhost:8001")
    print("Press Ctrl+C to stop")
    webbrowser.open("http://localhost:8001")
    app.run(port=8001, debug=False, threaded=True)
