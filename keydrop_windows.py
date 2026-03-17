# =============================================================================
# CONFIGURATION
# =============================================================================

ACCOUNTS = [
    {
        "name": "ACCOUNT_1",
        "keydrop_cookies": "account_1.json",
        "steam_cookies": "account_1_steam.json",
        "auth_method": "cookies",
    },
    {
        "name": "ACCOUNT_2",
        "keydrop_cookies": "account_2.json",
        "steam_cookies": "account_2_steam.json",
        "auth_method": "cookies",
    },
    {
        "name": "ACCOUNT_3",
        "keydrop_cookies": "account_3.json",
        "steam_cookies": "account_3_steam.json",
        "auth_method": "cookies",
    },
]

# Optional: only if you actually use Steam Guard by email
GMAIL_EMAIL = ""
GMAIL_APP_PASSWORD = ""

# Cookies directory - Windows compatible paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_DIR = os.path.join(BASE_DIR, "cookies")
os.makedirs(COOKIES_DIR, exist_ok=True)

# Screenshots directory
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)