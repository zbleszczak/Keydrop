# -*- coding: utf-8 -*-
from multiprocessing import Process, Manager
from playwright.sync_api import sync_playwright
import time
import json
import os
from datetime import datetime
import signal
import sys
import random
import imaplib
import email
import re

# =============================================================================
# CONFIGURATION
# =============================================================================

ACCOUNTS = [
    {
        "name": "ACCOUNT_1",
        "keydrop_cookies": "account_1_keydrop.json",
        "steam_cookies": "account_1_steam.json",
        "auth_method": "cookies",  # "cookies" albo "steam"
        # "password": "PUT_STEAM_PASSWORD_HERE"  # tylko jeśli auth_method="steam"
    },
]

# Gmail credentials for fetching Steam Guard codes
# Uzupełnij lokalnie, jeśli faktycznie używasz Steam Guard przez mail
GMAIL_EMAIL = ""
GMAIL_APP_PASSWORD = ""

# Cookies directory
COOKIES_DIR = "./cookies"
os.makedirs(COOKIES_DIR, exist_ok=True)

# =============================================================================
# COOKIE HELPERS
# =============================================================================

def save_cookies(page, filename):
    filepath = os.path.join(COOKIES_DIR, filename)
    cookies = page.context.cookies()
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(cookies, f)
    print(f"[{filename}] Cookies saved", flush=True)

def load_cookies(context, filename):
    filepath = os.path.join(COOKIES_DIR, filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                cookies = json.load(f)

            for cookie in cookies:
                if 'sameSite' in cookie:
                    if cookie['sameSite'] in ['unspecified', 'no_restriction']:
                        cookie['sameSite'] = 'None'
                    elif cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
                        cookie['sameSite'] = 'None'

            context.add_cookies(cookies)
            print(f"[{filename}] Cookies loaded", flush=True)
            return True
        except Exception as e:
            print(f"[{filename}] Failed: {e}", flush=True)
            return False
    return False

def save_storage_state(context, filename):
    filepath = os.path.join(COOKIES_DIR, filename.replace('.json', '_state.json'))
    context.storage_state(path=filepath)
    print(f"[{filename}] Storage state saved", flush=True)

# =============================================================================
# STEAM LOGIN WITH EMAIL VERIFICATION
# =============================================================================

def get_steam_guard_code(username, max_wait=120):
    print(f"    [EMAIL] Waiting for Steam Guard code for {username}...", flush=True)

    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            mail.select("INBOX")

            _, messages = mail.search(None, '(FROM "noreply@steampowered.com")')
            email_ids = messages[0].split()

            for email_id in reversed(email_ids[-20:]):
                _, msg_data = mail.fetch(email_id, "(RFC822)")
                email_body = msg_data[0][1]
                msg = email.message_from_bytes(email_body)

                subject = msg["subject"] or ""

                if any(keyword in subject.lower() for keyword in [
                    "steam guard", "access from", "verification",
                    "twoje konto steam", "dostep z nowej", "nowego urzadzenia"
                ]):
                    body = ""
                    html_body = ""

                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type == "text/plain":
                                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                            elif content_type == "text/html":
                                html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    else:
                        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

                    search_body = html_body if html_body else body

                    if username.lower() not in search_body.lower():
                        continue

                    print(f"    [EMAIL] Found email for {username}", flush=True)

                    code_match = re.search(r'>\s*([A-Z0-9]{5})\s*<', search_body)
                    if not code_match:
                        code_match = re.search(r'\b([A-Z][A-Z0-9]{4})\b', search_body)
                    if not code_match:
                        code_match = re.search(r'\b([A-Z0-9]{5})\b', search_body)

                    if code_match:
                        code = code_match.group(1)
                        if code.upper() not in ["STEAM", "GUARD", "EMAIL", "TWOJE", "KONTO", "VALVE"]:
                            print(f"    [EMAIL] Found code: {code}", flush=True)
                            mail.store(email_id, '+FLAGS', '\\Seen')
                            mail.logout()
                            return code

            mail.logout()

        except Exception as e:
            print(f"    [EMAIL] Error: {e}", flush=True)

        print(f"    [EMAIL] No code for {username} yet, waiting... ({int(time.time() - start_time)}s)", flush=True)
        time.sleep(5)

    print(f"    [EMAIL] Timeout waiting for Steam Guard code", flush=True)
    return None

def login_steam(page, username, password):
    print(f"[{username}] Logging into Steam...", flush=True)

    try:
        page.goto("https://steamcommunity.com/login/", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(3000)

        if "login" not in page.url.lower() or "id/" in page.url or "profiles/" in page.url:
            print(f"[{username}] Already logged into Steam!", flush=True)
            return True

        password_input = page.locator('input[type="password"]')
        if password_input.count() == 0:
            print(f"[{username}] No password field - might be logged in already", flush=True)
            page.goto("https://steamcommunity.com/", wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(2000)
            if "login" not in page.url.lower():
                print(f"[{username}] Confirmed: Already logged into Steam!", flush=True)
                return True

        try:
            page.wait_for_selector('input[type="text"]', timeout=15000)
        except:
            print(f"[{username}] Waiting for login form...", flush=True)
            page.wait_for_timeout(5000)

        username_input = None
        username_selectors = [
            'input._2GBWeup5cttgbTw8FM3tfx[type="text"]',
            'input[type="text"]:not([name="search"])',
            'form input[type="text"]',
            'input[type="text"]',
        ]

        for selector in username_selectors:
            try:
                inp = page.locator(selector).first
                if inp.count() > 0 and inp.is_visible():
                    username_input = inp
                    break
            except:
                continue

        if not username_input:
            print(f"[{username}] Could not find username input - checking if logged in...", flush=True)
            page.goto("https://steamcommunity.com/", wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(2000)
            if "login" not in page.url.lower():
                print(f"[{username}] Already logged into Steam!", flush=True)
                return True
            print(f"[{username}] Not logged in and no login form found", flush=True)
            return False

        username_input.fill(username)
        page.wait_for_timeout(500)

        password_input = page.locator('input[type="password"]').first
        password_input.fill(password)
        page.wait_for_timeout(500)

        sign_in_btn = page.locator('button.DjSvCZoKKfoNSmarsEcTS')
        if sign_in_btn.count() == 0:
            sign_in_btn = page.locator('button:has-text("Sign in"), button:has-text("Zaloguj")')
        sign_in_btn.click()

        print(f"[{username}] Submitted login, waiting...", flush=True)
        page.wait_for_timeout(5000)

        max_checks = 20
        for check in range(max_checks):
            page_content = page.content()
            current_url = page.url

            if "login" not in current_url.lower() and "steamcommunity.com" in current_url:
                print(f"[{username}] Steam login successful!", flush=True)
                return True

            code_inputs = page.locator('input[maxlength="1"]')
            if code_inputs.count() >= 5:
                print(f"[{username}] Email verification required", flush=True)

                code = get_steam_guard_code(username)

                if code:
                    print(f"[{username}] Entering code: {code}", flush=True)
                    code_inputs.nth(0).click()
                    page.wait_for_timeout(300)
                    page.keyboard.type(code, delay=150)

                    page.wait_for_timeout(5000)

                    if "login" not in page.url.lower():
                        print(f"[{username}] Steam login successful after verification!", flush=True)
                        return True
                else:
                    print(f"[{username}] Could not get email code", flush=True)
                    return False

            if any(keyword in page_content.lower() for keyword in ["incorrect", "wrong", "invalid", "nieprawidlowe", "bledne"]):
                print(f"[{username}] Invalid credentials", flush=True)
                return False

            print(f"[{username}] Waiting for page... ({check+1}/{max_checks})", flush=True)
            page.wait_for_timeout(2000)

        print(f"[{username}] Login timeout", flush=True)
        return False

    except Exception as e:
        print(f"[{username}] Steam login error: {e}", flush=True)
        return False

def login_keydrop_via_steam(page, username):
    print(f"[{username}] Logging into KeyDrop via Steam...", flush=True)

    try:
        page.goto("https://keydrop.com/pl/", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(3000)

        dismiss_modals(page)
        page.wait_for_timeout(1000)
        dismiss_modals(page)

        balance_elem = page.query_selector('[data-testid="header-quick-sell-account-balance"]')
        if balance_elem and balance_elem.is_visible():
            print(f"[{username}] Already logged into KeyDrop!", flush=True)
            return True

        print(f"[{username}] Looking for 'Login with Steam' button...", flush=True)

        login_clicked = False
        selectors = [
            '[data-testid="login-via-steam-main-page-btn"]',
            'button:has-text("Steam")',
            'a:has-text("Steam")',
        ]

        for selector in selectors:
            try:
                button = page.locator(selector).first
                if button.count() > 0:
                    print(f"[{username}] Clicking main login button...", flush=True)
                    button.click(force=True)
                    login_clicked = True
                    page.wait_for_timeout(2000)
                    break
            except:
                continue

        if not login_clicked:
            print(f"[{username}] Could not find main login button", flush=True)
            return False

        print(f"[{username}] Handling consent checkboxes...", flush=True)

        try:
            page.wait_for_timeout(1500)

            close_buttons = page.locator('button:has-text("X"), [aria-label="Close"], button[class*="close"]').all()
            for btn in close_buttons:
                try:
                    if btn.is_visible():
                        btn.click(force=True)
                        page.wait_for_timeout(500)
                except:
                    pass

            page.wait_for_timeout(1000)

            all_checkboxes = page.locator('input[type="checkbox"]').all()
            print(f"[{username}] Found {len(all_checkboxes)} total checkboxes", flush=True)

            modal_checkboxes = []
            for checkbox in all_checkboxes:
                try:
                    parent_label = checkbox.locator('xpath=ancestor::label[1]').first
                    if parent_label.count() > 0:
                        label_text = parent_label.inner_text()

                        if "COOKIES" in label_text.upper() or "CIASTECZK" in label_text.upper():
                            continue

                        if any(word in label_text.upper() for word in ["SALDO", "ULUBIONE", "BALANCE", "FAVORITE"]):
                            continue

                        if any(word in label_text for word in [
                            "Terms", "Service", "Privacy", "Policy", "Warunki",
                            "użytkowania", "prywatności", "18", "lat", "age",
                            "older", "wiek", "więcej"
                        ]):
                            modal_checkboxes.append((checkbox, label_text))
                except:
                    pass

            print(f"[{username}] Found {len(modal_checkboxes)} modal checkboxes", flush=True)

            clicked_count = 0
            for checkbox, label_text in modal_checkboxes:
                try:
                    checkbox.evaluate('''(el) => {
                        el.click();
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                    }''')

                    clicked_count += 1
                    print(f"[{username}] Clicked: {label_text[:40]}...", flush=True)
                    page.wait_for_timeout(1000)

                except Exception as e:
                    print(f"[{username}] Error clicking checkbox: {str(e)[:50]}", flush=True)

            print(f"[{username}] Clicked {clicked_count} checkboxes", flush=True)
            page.wait_for_timeout(2000)

            print(f"[{username}] Looking for enabled Steam button in modal...", flush=True)

            modal_steam_clicked = False
            modal_button_selector = 'button:has-text("Steam"):not([disabled])'

            try:
                modal_button = page.locator(modal_button_selector).last

                if modal_button.count() > 0:
                    is_visible = modal_button.is_visible()
                    print(f"[{username}] Found enabled Steam button, visible = {is_visible}", flush=True)

                    modal_button.click(force=True)
                    page.wait_for_timeout(3000)

                    if "steamcommunity.com" in page.url or "key-drop" in page.url or "keydrop.com" in page.url:
                        print(f"[{username}] Button click worked! URL: {page.url}", flush=True)
                        modal_steam_clicked = True
                    else:
                        print(f"[{username}] Button clicked but no navigation: {page.url}", flush=True)
                else:
                    print(f"[{username}] Button still disabled!", flush=True)

            except Exception as e:
                print(f"[{username}] Error finding/clicking button: {str(e)[:100]}", flush=True)

            if not modal_steam_clicked:
                print(f"[{username}] Could not click Steam button in modal", flush=True)
                return False

            print(f"[{username}] Current URL after modal: {page.url}", flush=True)

        except Exception as e:
            print(f"[{username}] Error handling modal: {str(e)[:100]}", flush=True)
            return False

        print(f"[{username}] Current URL: {page.url}", flush=True)

        if "steamcommunity.com" in page.url:
            print(f"[{username}] On Steam OAuth - authorizing...", flush=True)
            page.wait_for_timeout(2000)

            authorized = False

            try:
                auth_btn = page.locator('#imageButton, input[type="image"], input[type="submit"]').first
                if auth_btn.count() > 0 and auth_btn.is_visible(timeout=5000):
                    auth_btn.click()
                    print(f"[{username}] Clicked Steam authorize", flush=True)
                    page.wait_for_timeout(5000)
                    authorized = True
            except:
                pass

            if not authorized:
                try:
                    result = page.evaluate('() => { const form = document.querySelector("form"); if (form) { form.submit(); return true; } return false; }')
                    if result:
                        print(f"[{username}] Submitted form via JavaScript", flush=True)
                        page.wait_for_timeout(5000)
                        authorized = True
                except:
                    pass

            if not authorized:
                print(f"[{username}] Waiting for auto-redirect...", flush=True)
                page.wait_for_timeout(3000)

        print(f"[{username}] Final URL: {page.url}", flush=True)

        page.wait_for_timeout(3000)
        dismiss_modals(page)

        for _ in range(5):
            balance_elem = page.query_selector('[data-testid="header-quick-sell-account-balance"]')
            if balance_elem and balance_elem.is_visible():
                print(f"[{username}] KeyDrop login SUCCESS!", flush=True)
                return True
            page.wait_for_timeout(1000)

        print(f"[{username}] KeyDrop login FAILED", flush=True)
        return False

    except Exception as e:
        print(f"[{username}] KeyDrop login error: {e}", flush=True)
        return False

# =============================================================================
# AUTHENTICATION FLOW
# =============================================================================

def ensure_logged_in(page, context, account):
    username = account["name"]
    auth_method = account.get("auth_method", "steam")
    keydrop_cookies = account["keydrop_cookies"]
    steam_cookies = account.get("steam_cookies")

    print(f"\n[{username}] === AUTHENTICATION ({auth_method.upper()}) ===", flush=True)

    print(f"[{username}] Step 1: Checking KeyDrop cookies...", flush=True)
    if load_cookies(context, keydrop_cookies):
        page.goto("https://keydrop.com/pl/giveaways/list", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(4000)
        dismiss_modals(page)

        balance_elem = page.query_selector('[data-testid="header-quick-sell-account-balance"]')
        if balance_elem and balance_elem.is_visible():
            print(f"[{username}] KeyDrop cookies valid!", flush=True)
            return True
        else:
            print(f"[{username}] KeyDrop cookies expired", flush=True)
    else:
        print(f"[{username}] No KeyDrop cookies found", flush=True)

    if steam_cookies:
        print(f"[{username}] Step 2: Checking Steam cookies...", flush=True)
        if load_cookies(context, steam_cookies):
            page.goto("https://steamcommunity.com/", wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(2000)

            if "login" not in page.url.lower():
                print(f"[{username}] Steam cookies valid!", flush=True)

                if login_keydrop_via_steam(page, username):
                    save_cookies(page, keydrop_cookies)
                    print(f"[{username}] Logged in via Steam OAuth!", flush=True)
                    return True
                else:
                    print(f"[{username}] Steam OAuth failed", flush=True)
            else:
                print(f"[{username}] Steam cookies expired", flush=True)
        else:
            print(f"[{username}] No Steam cookies found", flush=True)
    else:
        print(f"[{username}] No Steam cookies configured", flush=True)

    if auth_method == "steam":
        password = account.get("password")

        if not password:
            print(f"[{username}] Missing password for steam auth", flush=True)
            return False

        print(f"[{username}] Step 3: Fresh Steam login...", flush=True)
        if login_steam(page, username, password):
            if steam_cookies:
                save_cookies(page, steam_cookies)

            if login_keydrop_via_steam(page, username):
                save_cookies(page, keydrop_cookies)
                return True

        print(f"[{username}] AUTHENTICATION FAILED", flush=True)
        return False

    print(f"[{username}] AUTHENTICATION FAILED (cookies-only mode)", flush=True)
    print(f"[{username}] Both KeyDrop and Steam cookies expired/missing", flush=True)
    print(f"[{username}] Account will be skipped (provide fresh cookies to use)", flush=True)
    return False

# =============================================================================
# PROFILE LEVEL DETECTION
# =============================================================================

def get_profile_level(page, account_name):
    cache_file = os.path.join(COOKIES_DIR, f"level_{account_name}.txt")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                lines = f.read().strip().split('\n')
                if len(lines) == 2:
                    cached_level = int(lines[0])
                    cached_time = float(lines[1])

                    if time.time() - cached_time < 86400:
                        print(f"[{account_name}] Profile Level: {cached_level} (cached)", flush=True)
                        return cached_level
                    else:
                        print(f"[{account_name}] Level cache expired, detecting...", flush=True)
        except:
            pass

    try:
        page.wait_for_timeout(2000)

        for attempt in range(3):
            level = page.evaluate('''() => {
                const elem = document.querySelector('[data-testid="user-avatar-level-xp-label"]');
                if (elem) {
                    const text = elem.textContent.trim();
                    const num = parseInt(text);
                    if (!isNaN(num) && num > 0) return num;
                }
                return 0;
            }''')

            if level > 0:
                print(f"[{account_name}] Profile Level: {level}", flush=True)
                try:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        f.write(f"{level}\n{time.time()}")
                except:
                    pass
                return level

            if attempt < 2:
                page.wait_for_timeout(2000)

        page.wait_for_timeout(2000)
        level_elem = page.query_selector('[data-testid="user-avatar-level-xp-label"]')
        if level_elem:
            try:
                level_text = level_elem.text_content().strip()
                level = int(level_text)
                if level > 0:
                    print(f"[{account_name}] Profile Level: {level}", flush=True)
                    try:
                        with open(cache_file, 'w', encoding='utf-8') as f:
                            f.write(f"{level}\n{time.time()}")
                    except:
                        pass
                    return level
            except (ValueError, AttributeError):
                pass

        print(f"[{account_name}] WARNING: Level not detected after retries, using default (0)", flush=True)
        return 0

    except Exception:
        print(f"[{account_name}] Level detection error, using default (0)", flush=True)
        return 0

def get_cooldown_for_level(level):
    if level < 10:
        return (86400, "24 hours")
    elif level < 15:
        return (172800, "2 days")
    elif level < 30:
        return (432000, "5 days")
    elif level < 50:
        return (864000, "10 days")
    else:
        return (1209600, "14 days")

# =============================================================================
# ORIGINAL BOT FUNCTIONS
# =============================================================================

def dismiss_modals(page):
    try:
        close_selectors = [
            'button[aria-label="Close"]',
            'button[aria-label="Zamknij"]',
            '[data-testid*="close"]',
            '[data-testid*="dismiss"]',
            'button:has-text("X")',
            'button:has-text("x")',
            '.modal button.close',
            '[role="dialog"] button',
        ]
        for selector in close_selectors:
            try:
                btn = page.query_selector(selector)
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(300)
                    return True
            except:
                continue
        page.keyboard.press('Escape')
        page.wait_for_timeout(200)
        return True
    except:
        return False

def get_giveaway_value_from_label(label):
    try:
        value_element = label.evaluate_handle('''
            el => {
                let cur = el;
                for (let i = 0; i < 15; i++) {
                    if (!cur.parentElement) break;
                    cur = cur.parentElement;
                    const spans = cur.querySelectorAll('span');
                    for (const s of spans) {
                        const t = (s.textContent || "").trim();
                        if (t.match(/\\d+[\\.,]?\\d*\\s*PLN/i)) return s;
                    }
                }
                return null;
            }
        ''').as_element()
        if value_element:
            raw_text = (value_element.inner_text() or "").strip()
            raw_text = raw_text.replace(',', '.').replace(' ', '').replace('PLN', '').strip()
            return float(raw_text)
    except:
        pass
    return 0.0

def find_join_link(page, min_value=30.0, debug=False, preferred_categories=None):
    labels = page.query_selector_all('[data-testid="label-single-card-giveaway-category"]')

    found_giveaways = []
    best_match = None
    best_value = 0.0

    for label in labels:
        try:
            txt = (label.inner_text() or "").strip().lower()
            value = get_giveaway_value_from_label(label)

            if debug:
                found_giveaways.append(f"{txt}={value:.2f}PLN")

            if value < min_value:
                continue

            if preferred_categories is None or txt in [c.lower() for c in preferred_categories]:
                handle = label.evaluate_handle('''
                    el => {
                        let cur = el;
                        for (let i = 0; i < 12; i++) {
                            if (!cur.parentElement) break;
                            cur = cur.parentElement;
                            const a = cur.querySelector('a[data-testid="btn-single-card-giveaway-join"]');
                            if (a) return a;
                        }
                        return null;
                    }
                ''').as_element()

                if handle and handle.is_visible():
                    if value > best_value:
                        best_match = (handle, value, txt)
                        best_value = value
        except:
            continue

    if best_match:
        handle, value, category = best_match
        return handle, value, category, found_giveaways if debug else []

    return None, 0.0, None, found_giveaways if debug else []

def click_join_sequence(page, stats, account_name=""):
    try:
        dismiss_modals(page)
        page.wait_for_timeout(200)

        labels = page.locator('[data-testid="giveaway-label"], div:has-text("PLN")').all()
        if not labels:
            print(f"[{account_name}] No giveaway labels", flush=True)
            return False

        label = labels[0]

        card = label.evaluate_handle('''
            el => {
                let cur = el;
                for (let i = 0; i < 12; i++) {
                    if (!cur.parentElement) break;
                    cur = cur.parentElement;
                    const found = cur.querySelector('a, div[data-testid="giveaway-card"]');
                    if (found) return found;
                }
                return null;
            }
        ''').as_element()

        if not card:
            print(f"[{account_name}] Cannot locate giveaway card container", flush=True)
            return False

        try:
            card.evaluate("(el)=>el.scrollIntoView({behavior:'instant', block:'center'});")
            page.wait_for_timeout(200)
        except:
            pass

        print(f"[{account_name}] Opening giveaway page...", flush=True)

        try:
            card.click(force=True, timeout=3000)
        except:
            try:
                page.evaluate("(el)=>el.click()", card)
            except:
                print(f"[{account_name}] Could not click giveaway card", flush=True)
                return False

        page.wait_for_timeout(1500)
        dismiss_modals(page)
        page.wait_for_timeout(500)

        selectors = [
            '[data-testid="btn-giveaway-join-the-giveaway"]',
            'button:has-text("Dolacz")',
            'button:has-text("Join")',
            'div[role="button"]:has-text("Join")',
            'div[role="button"]:has-text("Dolacz")',
            'button span:has-text("Join")',
            'button span:has-text("Dolacz")',
        ]

        join_btn = None
        for sel in selectors:
            btn = page.locator(sel).first
            if btn.count() > 0:
                join_btn = btn
                break

        if not join_btn:
            print(f"[{account_name}] No JOIN button found on giveaway page", flush=True)
            return False

        try:
            join_btn.evaluate("(el)=>el.scrollIntoView({behavior:'instant', block:'center'});")
            page.wait_for_timeout(150)
        except:
            pass

        print(f"[{account_name}] Clicking JOIN...", flush=True)

        try:
            join_btn.click(force=True, timeout=3000)
        except:
            try:
                join_btn.evaluate("(el)=>el.click()")
            except:
                print(f"[{account_name}] Failed to click JOIN", flush=True)
                return False

        page.wait_for_timeout(800)

        try:
            text = (join_btn.inner_text() or "").lower()
        except:
            text = ""

        if (
            "ponownie" in text or
            "again" in text or
            "leave" in text or
            join_btn.is_disabled()
        ):
            print(f"[{account_name}] SUCCESS", flush=True)
            stats['successful_joins'] = stats.get('successful_joins', 0) + 1
            return True

        print(f"[{account_name}] Clicked (assuming success)", flush=True)
        stats['successful_joins'] = stats.get('successful_joins', 0) + 1
        return True

    except Exception as e:
        print(f"[{account_name}] ERROR in click_join_sequence: {e}", flush=True)
        stats['failed_clicks'] = stats.get('failed_clicks', 0) + 1
        return False

def check_balance_simple(page, account_name):
    try:
        for attempt in range(3):
            try:
                balance_text = page.evaluate('''() => {
                    const elem = document.querySelector('[data-testid="header-quick-sell-account-balance"]');
                    return elem ? elem.innerText : null;
                }''')

                if balance_text:
                    text = balance_text.replace('\u00a0', '').replace(' ', '').replace(',', '.').replace('PLN', '').strip()
                    match = re.search(r'(\d+\.?\d*)', text)
                    if match:
                        value = float(match.group(1))
                        if 0 <= value < 100000:
                            return value

                if attempt < 2:
                    page.wait_for_timeout(1000)
            except:
                if attempt < 2:
                    page.wait_for_timeout(1000)

        return 0.0

    except Exception as e:
        print(f"[{account_name}] Balance check error: {e}", flush=True)
        return 0.0

def open_daily_case(page, account_name):
    try:
        print(f"[{account_name}] Checking for daily case...", flush=True)

        try:
            page.goto("https://keydrop.com/pl/case-battles/daily-free", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
        except Exception:
            print(f"[{account_name}] Daily case page timeout, skipping...", flush=True)
            try:
                page.goto("https://keydrop.com/pl/giveaways/list", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(500)
            except:
                pass
            return False

        dismiss_modals(page)

        open_selectors = [
            'button:has-text("Open")',
            'button:has-text("FREE")',
            'button:has-text("DARMOWA")',
            '[data-testid*="open"]',
            '[data-testid*="daily"]',
            'button[class*="open"]',
        ]

        button_found = False
        for selector in open_selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible() and not btn.is_disabled():
                    print(f"[{account_name}] Found daily case button: {selector}", flush=True)
                    btn.click(timeout=5000)
                    page.wait_for_timeout(3000)

                    print(f"[{account_name}] Daily case opened!", flush=True)
                    button_found = True
                    page.wait_for_timeout(2000)
                    break
            except:
                continue

        if not button_found:
            print(f"[{account_name}] No daily case available", flush=True)

        page.goto("https://keydrop.com/pl/giveaways/list", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1000)

        return button_found

    except Exception as e:
        print(f"[{account_name}] Daily case error (will retry later): {e}", flush=True)
        try:
            page.goto("https://keydrop.com/pl/giveaways/list", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1000)
        except:
            pass
        return False

# =============================================================================
# BOT INSTANCE
# =============================================================================

def bot_instance(account, shared_state, is_master=False, headless=False, min_value=30.0, preferred_categories=None, use_xvfb=True, contender_duration_hours=0):
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    account_name = account["name"]
    bot_start_time = time.time()
    contender_end_time = bot_start_time + (contender_duration_hours * 3600)

    cats_str = f"categories: {preferred_categories}" if preferred_categories else "ANY category"
    print(f"[{account_name}] STARTED {'[MASTER]' if is_master else '[WORKER]'} (min: {min_value} PLN, {cats_str})", flush=True)

    def _signal_handler(sig, frame):
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    retry_count = 0
    stats = {'total_attempts': 0, 'successful_joins': 0, 'button_clicks': 0, 'disabled_buttons': 0, 'inventory_value': 0.0}

    xvfb_display = None
    if use_xvfb and headless:
        try:
            from xvfbwrapper import Xvfb
            xvfb_display = Xvfb(width=1920, height=1080)
            xvfb_display.start()
            print(f"[{account_name}] Virtual display started", flush=True)
            headless = False
        except ImportError:
            print(f"[{account_name}] xvfbwrapper not installed, using headless", flush=True)
        except Exception as e:
            print(f"[{account_name}] Xvfb failed: {e}", flush=True)

    while True:
        browser = None
        try:
            if retry_count > 0:
                print(f"[{account_name}] Restarting #{retry_count}", flush=True)
                time.sleep(10)

            retry_count += 1

            with sync_playwright() as pw:
                launch_options = {
                    'headless': headless,
                    'firefox_user_prefs': {
                        'dom.webdriver.enabled': False,
                        'useAutomationExtension': False,
                        'general.platform.override': 'Win64',
                        'general.useragent.override': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
                    }
                }

                try:
                    browser = pw.firefox.launch(channel='nightly', **launch_options)
                except:
                    browser = pw.firefox.launch(**launch_options)

                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
                    viewport={'width': 1920, 'height': 1080},
                    locale='pl-PL',
                    timezone_id='Europe/Warsaw'
                )
                page = context.new_page()

                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => false });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['pl-PL','pl','en-US'] });
                    window.chrome = { runtime: {} };
                """)

                if not ensure_logged_in(page, context, account):
                    if account.get("auth_method") == "cookies":
                        print(f"[{account_name}] SKIPPING account (cookies expired/missing)", flush=True)
                        return
                    else:
                        print(f"[{account_name}] Could not authenticate, retrying in 60s...", flush=True)
                        time.sleep(60)
                        continue

                if 'keydrop.com' not in page.url:
                    page.goto('https://keydrop.com/pl/', wait_until='domcontentloaded', timeout=90000)
                    page.wait_for_timeout(2000)

                dismiss_modals(page)

                try:
                    page.wait_for_selector('[data-testid="user-avatar-level-xp-label"]', timeout=10000)
                    page.wait_for_timeout(1000)
                except:
                    print(f"[{account_name}] Level element not found in 10s, trying anyway...", flush=True)

                profile_level = get_profile_level(page, account_name)
                giveaway_cooldown, cooldown_desc = get_cooldown_for_level(profile_level)

                print(f"[{account_name}] Level {profile_level} -> Giveaway cooldown: {cooldown_desc}", flush=True)

                last_join_file = os.path.join(COOKIES_DIR, f"last_join_{account_name}.txt")
                last_giveaway_join = 0

                if os.path.exists(last_join_file):
                    try:
                        with open(last_join_file, 'r', encoding='utf-8') as f:
                            last_giveaway_join = float(f.read().strip())
                    except:
                        pass
                else:
                    last_giveaway_join = time.time()

                retry_count = 0

                page.goto('https://keydrop.com/pl/giveaways/list', wait_until='domcontentloaded', timeout=90000)
                page.wait_for_timeout(3000)
                dismiss_modals(page)

                if account_name not in shared_state['authenticated_bots']:
                    shared_state['authenticated_bots'].append(account_name)
                    if len(shared_state['authenticated_bots']) >= shared_state['expected_bot_count']:
                        shared_state['all_bots_ready'] = True

                joined = 0
                last_inventory_check = 0
                inventory_check_interval = 600

                daily_case_file = os.path.join(COOKIES_DIR, f"last_daily_case_{account_name}.txt")
                last_daily_case = 0
                if os.path.exists(daily_case_file):
                    try:
                        with open(daily_case_file, 'r', encoding='utf-8') as f:
                            last_daily_case = float(f.read().strip())
                    except:
                        pass

                daily_case_interval = 86400 + random.randint(-1800, 1800)
                check_count = 0
                last_cookie_save = time.time()
                cookie_save_interval = 3600
                last_reload = time.time()
                reload_interval = 900 + random.randint(-120, 120)
                last_seen_values = {}

                while True:
                    now = time.time()
                    current_categories = list(preferred_categories) if preferred_categories else []

                    if contender_duration_hours > 0 and now < contender_end_time and shared_state.get('all_bots_ready', False):
                        if "contender" not in [c.lower() for c in current_categories]:
                            current_categories.append("contender")

                    if now - last_daily_case >= daily_case_interval:
                        if open_daily_case(page, account_name):
                            last_daily_case = now
                            try:
                                with open(daily_case_file, 'w', encoding='utf-8') as f:
                                    f.write(str(last_daily_case))
                            except:
                                pass
                        else:
                            last_daily_case = now - daily_case_interval + 3600

                    if now - last_inventory_check >= inventory_check_interval:
                        inv_value = check_balance_simple(page, account_name)
                        stats['inventory_value'] = inv_value
                        last_inventory_check = now

                    if now - last_cookie_save >= cookie_save_interval:
                        try:
                            save_cookies(page, account["keydrop_cookies"])
                            last_cookie_save = now
                        except Exception as e:
                            print(f"[{account_name}] Cookie save failed: {e}", flush=True)

                    if now - last_reload >= reload_interval:
                        try:
                            page.goto("https://keydrop.com/pl/giveaways/list", wait_until="domcontentloaded", timeout=60000)
                            page.wait_for_timeout(1000)
                            dismiss_modals(page)
                            last_reload = now
                        except:
                            last_reload = now

                    labels = page.query_selector_all('[data-testid="label-single-card-giveaway-category"]')
                    current_page_values = {}

                    if is_master:
                        check_count += 1

                        for label in labels:
                            try:
                                cat = (label.inner_text() or "").strip().lower()
                                if current_categories and cat not in [c.lower() for c in current_categories]:
                                    continue

                                value = get_giveaway_value_from_label(label)

                                handle = label.evaluate_handle('''
                                    el => {
                                        let cur = el;
                                        for (let i = 0; i < 12; i++) {
                                            if (!cur.parentElement) break;
                                            cur = cur.parentElement;
                                            const a = cur.querySelector('a[data-testid="btn-single-card-giveaway-join"]');
                                            if (a) return a;
                                        }
                                        return null;
                                    }
                                ''').as_element()

                                if handle and handle.is_visible():
                                    if cat not in current_page_values or value > current_page_values[cat][0]:
                                        current_page_values[cat] = (value, handle)
                            except:
                                continue

                        should_join = False
                        join_target = None

                        for cat, (value, handle) in current_page_values.items():
                            last_value = last_seen_values.get(cat, 0.0)
                            if abs(value - last_value) > 0.01 and value >= min_value:
                                print(f"[{account_name}] {cat.upper()} CHANGED: {last_value:.2f} -> {value:.2f} PLN", flush=True)
                                should_join = True
                                join_target = (cat, value, handle)

                        for cat, (value, _) in current_page_values.items():
                            if value > 0:
                                last_seen_values[cat] = value

                        if should_join and join_target:
                            found_cat, found_value, join_link = join_target

                            time_since_join = time.time() - last_giveaway_join
                            time_until_next = giveaway_cooldown - time_since_join

                            if time_until_next <= 0:
                                time.sleep(1.0)
                                continue

                            giveaway_url = None
                            try:
                                giveaway_url = join_link.get_attribute('href')
                                if giveaway_url and not giveaway_url.startswith('http'):
                                    giveaway_url = 'https://keydrop.com' + giveaway_url
                            except:
                                pass

                            shared_state['giveaway_url'] = giveaway_url
                            shared_state['giveaway_category'] = found_cat
                            shared_state['join_signal'] = True
                            shared_state['signal_time'] = time.time()
                            shared_state['master_ready'] = False

                            try:
                                stats['total_attempts'] += 1
                                page.goto(giveaway_url, timeout=120000, wait_until='load')
                                page.wait_for_timeout(1000)

                                shared_state['master_ready'] = True
                                shared_state['click_time'] = time.time()

                                if click_join_sequence(page, stats, account_name):
                                    joined += 1
                                    last_giveaway_join = time.time()
                                    try:
                                        with open(last_join_file, 'w', encoding='utf-8') as f:
                                            f.write(str(last_giveaway_join))
                                    except:
                                        pass

                                page.goto('https://keydrop.com/pl/giveaways/list', timeout=120000, wait_until='load')
                                page.wait_for_timeout(1000)
                                dismiss_modals(page)

                            except Exception as e:
                                print(f"[{account_name}] Error: {e}", flush=True)

                        time.sleep(1.0)

                    else:
                        last_processed_signal = locals().get('last_processed_signal', 0)

                        if shared_state.get('join_signal', False):
                            signal_time = shared_state.get('signal_time', 0)

                            if signal_time > last_processed_signal and shared_state.get('master_ready', False):
                                if time.time() - shared_state.get('click_time', 0) < 45:
                                    time_since_join = time.time() - last_giveaway_join
                                    time_until_next = giveaway_cooldown - time_since_join

                                    if time_until_next <= 0:
                                        time.sleep(0.05)
                                        continue

                                    giveaway_url = shared_state.get('giveaway_url')
                                    last_processed_signal = signal_time

                                    if giveaway_url:
                                        try:
                                            stats['total_attempts'] += 1
                                            page.goto(giveaway_url, timeout=120000, wait_until='load')
                                            page.wait_for_timeout(1000)

                                            if click_join_sequence(page, stats, account_name):
                                                joined += 1
                                                last_giveaway_join = time.time()
                                                try:
                                                    with open(last_join_file, 'w', encoding='utf-8') as f:
                                                        f.write(str(last_giveaway_join))
                                                except:
                                                    pass

                                            page.goto('https://keydrop.com/pl/giveaways/list', timeout=120000, wait_until='load')
                                            page.wait_for_timeout(1000)
                                        except Exception as e:
                                            if "closed" not in str(e).lower():
                                                print(f"[{account_name}] [WORKER] Error: {e}", flush=True)

                        time.sleep(0.05)

        except KeyboardInterrupt:
            break
        except SystemExit:
            break
        except Exception as e:
            print(f"[{account_name}] ERROR: {e}", flush=True)
        finally:
            if browser:
                try:
                    browser.close()
                except:
                    pass

    if xvfb_display:
        try:
            xvfb_display.stop()
        except:
            pass

# =============================================================================
# LAUNCHER
# =============================================================================

def launcher(init_force=False, min_value=30.0, preferred_categories=None, contender_duration_hours=0):
    manager = Manager()
    shared_state = manager.dict()
    shared_state['join_signal'] = False
    shared_state['signal_time'] = 0
    shared_state['master_ready'] = False
    shared_state['click_time'] = 0
    shared_state['authenticated_bots'] = manager.list()
    shared_state['expected_bot_count'] = len([a for a in ACCOUNTS if a.get('auth_method') in ['steam', 'cookies']])
    shared_state['all_bots_ready'] = False

    procs = []
    for i, acc in enumerate(ACCOUNTS):
        p = Process(
            target=bot_instance,
            args=(acc, shared_state, i == 0, True, min_value, preferred_categories, True, contender_duration_hours)
        )
        p.start()
        procs.append(p)

        wait_time = 2
        print(f"Waiting {wait_time}s before starting next account...", flush=True)
        time.sleep(wait_time)

    print(f"\nAll {len(procs)} bots started! (HEADLESS MODE)", flush=True)
    print(f"Min value: {min_value} PLN | Categories: {preferred_categories}", flush=True)

    try:
        for p in procs:
            p.join()
    except KeyboardInterrupt:
        print("\nStopping all bots...", flush=True)
        for p in procs:
            p.terminate()
        for p in procs:
            p.join()

if __name__ == "__main__":
    launcher(init_force=False, min_value=30.0, preferred_categories=["amateur"], contender_duration_hours=20)