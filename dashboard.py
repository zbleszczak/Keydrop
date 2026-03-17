#!/usr/bin/env python3
"""
KeyDrop Bot Dashboard - Flask Web Interface
Real-time monitoring and control for KeyDrop bots
"""

from flask import Flask, render_template, jsonify, request, Response
from flask_cors import CORS
import os
import json
import subprocess
import time
import re
from datetime import datetime
from collections import defaultdict
import psutil

app = Flask(__name__)
CORS(app)

# Configuration
LOG_FILE = ""
BOT_SCRIPT = ""
COOKIES_DIR = ""

# Bot accounts list
ACCOUNTS = [
    "account1", "account2"
]


def get_bot_processes():
    """Get all running keydrop bot processes"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'python' in cmdline.lower() and 'keydrop.py' in cmdline:
                processes.append({
                    'pid': proc.info['pid'],
                    'started': datetime.fromtimestamp(proc.info['create_time']).strftime('%Y-%m-%d %H:%M:%S'),
                    'uptime': time.time() - proc.info['create_time']
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes


def parse_log_stats():
    """Parse log file and extract statistics per bot"""
    stats = defaultdict(lambda: {
        'successful_joins': 0,
        'failed_joins': 0,
        'balance': 'Unknown',
        'last_activity': 'Never',
        'last_activity_time': 0,
        'daily_case_status': 'Unknown',
        'deposit_valid_hours': 0,
        'last_join': 'Never',
        'errors': []
    })

    if not os.path.exists(LOG_FILE):
        return stats

    try:
        # Check if log file was modified recently (last 60 seconds)
        log_mod_time = os.path.getmtime(LOG_FILE)
        current_time = time.time()
        log_is_active = (current_time - log_mod_time) < 60

        # Read last 5000 lines for performance
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[-5000:]

        for line in lines:
            # Extract account name from log line
            match = re.match(r'\[([^\]]+)\]', line)
            if not match:
                continue

            account = match.group(1)
            if account not in ACCOUNTS:
                continue

            # Only mark as active if log file was recently modified AND account appears in logs
            if log_is_active and stats[account]['last_activity'] == 'Never':
                stats[account]['last_activity'] = 'Active'

            # Check for successful joins
            if 'OK Joined!' in line or 'SUCCESS' in line:
                stats[account]['successful_joins'] += 1
                if 'Total:' in line:
                    total_match = re.search(r'Total: (\d+)', line)
                    if total_match:
                        stats[account]['total_joins'] = int(total_match.group(1))

            # Check for failed joins
            if 'FAILED after' in line or 'X FAILED' in line:
                stats[account]['failed_joins'] += 1

            # Extract balance
            if 'BALANCE:' in line:
                balance_match = re.search(r'BALANCE: ([\d.]+\s+\w+)', line)
                if balance_match:
                    stats[account]['balance'] = balance_match.group(1)

            # Extract deposit validity
            if 'Deposit valid for' in line:
                hours_match = re.search(r'Deposit valid for ([\d.]+) more hours', line)
                if hours_match:
                    stats[account]['deposit_valid_hours'] = float(hours_match.group(1))

            # Daily case status
            if 'Daily case opened!' in line:
                stats[account]['daily_case_status'] = 'Opened today'
            elif 'Daily case on cooldown' in line:
                stats[account]['daily_case_status'] = 'On cooldown'
            elif 'Daily case not available' in line:
                stats[account]['daily_case_status'] = 'Not available'

            # Track errors
            if 'Error' in line or 'Exception' in line:
                error_msg = line.strip()[:100]
                if error_msg not in stats[account]['errors']:
                    stats[account]['errors'].append(error_msg)
                    # Keep only last 3 errors
                    stats[account]['errors'] = stats[account]['errors'][-3:]

    except Exception as e:
        print(f"Error parsing log: {e}")

    return dict(stats)


def tail_log(lines=100):
    """Get last N lines from log file"""
    if not os.path.exists(LOG_FILE):
        return []

    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            return f.readlines()[-lines:]
    except Exception as e:
        return [f"Error reading log: {e}"]


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')


@app.route('/screenshots')
def screenshots_page():
    """Screenshots viewer page"""
    return render_template('screenshots.html')


@app.route('/api/screenshots')
def list_screenshots():
    """Get list of all screenshots"""
    screenshots_dir = ""
    if not os.path.exists(screenshots_dir):
        return jsonify({'screenshots': []})

    files = []
    for filename in os.listdir(screenshots_dir):
        if filename.endswith('.png'):
            filepath = os.path.join(screenshots_dir, filename)
            files.append({
                'name': filename,
                'size': os.path.getsize(filepath),
                'modified': os.path.getmtime(filepath),
                'url': f'/api/screenshot/{filename}'
            })

    # Sort by modification time (newest first)
    files.sort(key=lambda x: x['modified'], reverse=True)

    return jsonify({'screenshots': files})


@app.route('/api/screenshot/<filename>')
def get_screenshot(filename):
    """Serve a specific screenshot"""
    from flask import send_file
    screenshots_dir = ""
    filepath = os.path.join(screenshots_dir, filename)

    if os.path.exists(filepath) and filename.endswith('.png'):
        return send_file(filepath, mimetype='image/png')
    else:
        return jsonify({'error': 'Screenshot not found'}), 404


@app.route('/api/status')
def status():
    """Get overall bot status"""
    processes = get_bot_processes()
    stats = parse_log_stats()

    # Calculate totals
    total_joins = sum(s['successful_joins'] for s in stats.values())
    total_fails = sum(s['failed_joins'] for s in stats.values())
    success_rate = (total_joins / (total_joins + total_fails) * 100) if (total_joins + total_fails) > 0 else 0

    return jsonify({
        'running': len(processes) > 0,
        'processes': processes,
        'total_bots': len(ACCOUNTS),
        'total_joins': total_joins,
        'total_fails': total_fails,
        'success_rate': round(success_rate, 1),
        'accounts': stats
    })


@app.route('/api/logs')
def logs():
    """Get recent log entries"""
    lines = int(request.args.get('lines', 100))
    return jsonify({
        'logs': tail_log(lines)
    })


@app.route('/api/logs/stream')
def stream_logs():
    """Stream logs in real-time using Server-Sent Events"""
    def generate():
        last_size = 0
        while True:
            try:
                if os.path.exists(LOG_FILE):
                    current_size = os.path.getsize(LOG_FILE)
                    if current_size > last_size:
                        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                            f.seek(last_size)
                            new_lines = f.read()
                            if new_lines:
                                yield f"data: {json.dumps({'logs': new_lines})}\n\n"
                        last_size = current_size
                time.sleep(1)
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                time.sleep(5)

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/control/start', methods=['POST'])
def start_bot():
    """Start the main bot script"""
    processes = get_bot_processes()
    if processes:
        return jsonify({'success': False, 'message': 'Bot is already running'})

    try:
        # Open log file for output
        log_file = open(LOG_FILE, 'a')
        subprocess.Popen(
            ['python3', BOT_SCRIPT],
            cwd=os.path.dirname(BOT_SCRIPT),
            stdout=log_file,
            stderr=log_file,
            start_new_session=True
        )
        return jsonify({'success': True, 'message': 'Bot started successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to start: {e}'})


@app.route('/api/control/stop', methods=['POST'])
def stop_bot():
    """Stop all bot processes"""
    processes = get_bot_processes()
    if not processes:
        return jsonify({'success': False, 'message': 'No bots running'})

    try:
        subprocess.run(['pkill', '-f', 'python.*keydrop.py'])
        return jsonify({'success': True, 'message': 'All bots stopped'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to stop: {e}'})


@app.route('/api/control/restart', methods=['POST'])
def restart_bot():
    """Restart all bots"""
    try:
        # Stop
        subprocess.run(['pkill', '-f', 'python.*keydrop.py'])
        time.sleep(2)

        # Start
        log_file = open(LOG_FILE, 'a')
        subprocess.Popen(
            ['python3', BOT_SCRIPT],
            cwd=os.path.dirname(BOT_SCRIPT),
            stdout=log_file,
            stderr=log_file,
            start_new_session=True
        )
        return jsonify({'success': True, 'message': 'Bots restarted'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to restart: {e}'})


@app.route('/api/control/restart_account/<account>', methods=['POST'])
def restart_account(account):
    """Restart a specific account (NOT IMPLEMENTED YET - requires bot architecture change)"""
    # This would require modifying the main bot script to support individual account control
    # For now, return a message that this feature needs implementation
    return jsonify({
        'success': False,
        'message': 'Individual account restart requires bot architecture update. Use full restart for now.'
    })


@app.route('/api/control/kill_zombies', methods=['POST'])
def kill_zombies():
    """Kill all Xvfb and Python zombie processes"""
    try:
        subprocess.run(['pkill', '-9', 'Xvfb'])
        subprocess.run(['pkill', '-9', '-f', 'python.*keydrop.py'])
        time.sleep(1)
        return jsonify({'success': True, 'message': 'All zombie processes killed'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to kill zombies: {e}'})


@app.route('/api/config')
def get_config():
    """Get current bot configuration"""
    config_file = ""
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)
        else:
            config = {
                "min_value": 30.0,
                "preferred_categories": ["amateur"],
                "contender_duration_hours": 0,
                "init_force": False
            }
        return jsonify(config)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update bot configuration"""
    config_file = ""
    try:
        new_config = request.json

        # Validate
        if 'contender_duration_hours' in new_config:
            new_config['contender_duration_hours'] = float(new_config['contender_duration_hours'])
        if 'min_value' in new_config:
            new_config['min_value'] = float(new_config['min_value'])

        # Save
        with open(config_file, 'w') as f:
            json.dump(new_config, f, indent=2)

        return jsonify({'success': True, 'message': 'Configuration saved! Restart bots to apply changes.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to save config: {e}'})


if __name__ == '__main__':
    print("🚀 Starting KeyDrop Dashboard on http://0.0.0.0:5000")
    print("📊 Dashboard will be available at: http://YOUR_IP:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
