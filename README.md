# Keydrop Giveaway Bot

This repository contains an advanced Python bot designed to automatically join giveaways on Keydrop.com. It features a sophisticated master/worker architecture for multi-account synchronization, a robust authentication system, and a comprehensive web dashboard for real-time monitoring and control.

## ✨ Features

- **Multi-Account Support**: Run multiple accounts simultaneously in a synchronized master/worker setup.
- **Master/Worker Architecture**: The "master" account detects new giveaways and instantly signals all "worker" accounts to join, maximizing entry speed.
- **Automatic Login**:
    - **Steam Login**: Full support for logging in via Steam, including handling of 2FA/Steam Guard codes fetched from a Gmail account.
    - **Cookie-based Login**: Use existing session cookies for faster, non-intrusive authentication.
- **Daily Case Opening**: Automatically checks for and opens the free daily case for each account.
- **Web Dashboard**: A Flask-based web interface for real-time monitoring of all bot accounts, viewing stats, streaming logs, and controlling the bot processes.
- **Configurable Filters**: Customize which giveaways to join based on minimum value (PLN) and category (e.g., "amateur", "contender").
- **Dynamic Cooldowns**: The bot automatically detects an account's profile level and adjusts its giveaway joining cooldown accordingly.
- **Robust Automation**: Built with Playwright, it includes features to bypass bot detection, handle modals, and manage browser state effectively.

## 🛠️ Setup & Configuration

### 1. Prerequisites
- Python 3.8+
- A modern web browser (Firefox is recommended by the script)

### 2. Clone the Repository
```bash
git clone https://github.com/zbleszczak/Keydrop.git
cd Keydrop
```

### 3. Install Dependencies
The bot uses Playwright for browser automation. You also need to install dependencies for the web dashboard and virtual display support on Linux.

```bash
pip install playwright flask flask-cors psutil
playwright install
```
On Linux, for headless execution, it's recommended to install `xvfbwrapper`:
```bash
pip install xvfbwrapper
```

### 4. Configure Accounts
All configuration is done within the `keydrop.py` script. Open the file and edit the `ACCOUNTS` list at the top.

```python
# keydrop.py

ACCOUNTS = [
    {
        "name": "ACCOUNT_1", # Your Steam username
        "keydrop_cookies": "account_1_keydrop.json",
        "steam_cookies": "account_1_steam.json",
        "auth_method": "steam",  # "cookies" or "steam"
        "password": "PUT_STEAM_PASSWORD_HERE"  # Required if auth_method="steam"
    },
    {
        "name": "ACCOUNT_2",
        "keydrop_cookies": "account_2_keydrop.json",
        "steam_cookies": "account_2_steam.json",
        "auth_method": "cookies", # This account will use cookies
    },
    # ...add more accounts here
]
```

- **`name`**: Your Steam username. This is used for login and for identifying the account in logs.
- **`keydrop_cookies` / `steam_cookies`**: Filenames for storing session cookies. The bot will create these in a `cookies/` directory.
- **`auth_method`**:
    - `"steam"`: The bot will perform a full login to Steam using the provided `name` and `password`. This is required for the first run or when cookies expire.
    - `"cookies"`: The bot will attempt to log in using only the stored cookie files. If cookies are invalid or missing, the account will be skipped.
- **`password`**: Your Steam account password. **Only needed if `auth_method` is set to `"steam"`**.

#### Steam Guard (Email) Configuration
If your Steam account uses email-based Steam Guard, you can configure the bot to fetch codes automatically.

In `keydrop.py`, fill in the `GMAIL_EMAIL` and `GMAIL_APP_PASSWORD` variables. You must use a Google App Password, not your regular password.

```python
# Gmail credentials for fetching Steam Guard codes
GMAIL_EMAIL = "your.email@gmail.com"
GMAIL_APP_PASSWORD = "your-google-app-password"
```

## 🚀 Running the Bot

### Main Bot Script

The primary bot logic is in `keydrop.py`. You can configure the giveaway parameters at the bottom of the file in the `launcher` function call.

```python
# bottom of keydrop.py
if __name__ == "__main__":
    launcher(init_force=False, min_value=30.0, preferred_categories=["amateur"], contender_duration_hours=20)
```

To start the bot, run:
```bash
python3 keydrop.py
```
The script will launch instances for all configured accounts in headless mode. The first account in the `ACCOUNTS` list will act as the master.

### Web Dashboard

The `dashboard.py` script provides a web interface to monitor your bots.

**Note**: Before running, you may need to edit `dashboard.py` to set the correct paths for `LOG_FILE`, `BOT_SCRIPT`, etc., and update the `ACCOUNTS` list to match your configuration.

To start the dashboard server (on Linux/macOS):
```bash
./start_dashboard.sh
```
Alternatively, you can run it directly:
```bash
python3 dashboard.py
```
The dashboard will be available at `http://<your_server_ip>:5000`.

## 🤖 Bot Architecture (Master/Worker)

The bot uses a powerful master/worker model for efficiency:
1.  **Master**: The first account defined in the `ACCOUNTS` list is designated as the "master". It's responsible for actively scanning the Keydrop giveaway page.
2.  **Workers**: All other accounts are "workers". They remain idle until they receive a signal.
3.  **Synchronization**: When the master detects a new or changed giveaway that meets the configured criteria (value, category), it immediately sends a "join signal" to all worker processes.
4.  **Execution**: Upon receiving the signal, the master and all workers navigate to the giveaway page and click the join button almost simultaneously.

This architecture ensures that all accounts can enter a giveaway within seconds of it appearing, significantly increasing the chances of a successful join across the board.

## 🖥️ Web Dashboard

The web dashboard is a central hub for managing and monitoring your bot farm.

- **Real-time Status**: See which bots are running, their uptime, and overall success rates.
- **Account Stats**: View detailed statistics for each account, including successful/failed joins, balance, and daily case status.
- **Live Logs**: Stream the bot's console output directly in your browser, with color-coding for errors, successes, and warnings.
- **Bot Control**: Start, stop, and restart all bot processes directly from the UI.
- **Screenshots Viewer**: A dedicated page (`/screenshots`) to view any screenshots the bot may have saved for debugging purposes.

## 📁 File Structure

```
.
├── keydrop.py             # The main bot script for Linux/macOS.
├── dashboard.py           # Flask web server for the monitoring dashboard.
├── templates/             # HTML templates for the web dashboard.
│   ├── dashboard.html
│   └── screenshots.html
├── start_dashboard.sh     # Script to launch the web dashboard.
├── backup.py              # An identical backup of the main bot script.
└── keydrop_windows.py     # A configuration snippet for Windows paths (not a runnable script).
```

## ⚠️ Disclaimer

This bot automates actions on Keydrop.com. Using bots may be against the platform's Terms of Service. Use this software at your own risk. The author is not responsible for any account suspension, ban, or other penalties incurred from using this bot.
