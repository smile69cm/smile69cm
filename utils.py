"""
Utility Functions
Common utilities for the Instagram automation system
"""

import json
import os
import time
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()  # Load .env if present (optional but safe)

# ✅ These are hardcoded — OK for private use, but be careful if you share this
TELEGRAM_BOT_TOKEN = "7849473914:AAFT1Vpwnb94iiuza0yM4n7ft5w0t56pbFs"
ADMIN_ID = 5483152516  # Your Telegram user ID

# Configuration file paths
CONFIG_FILE = "config.json"
SESSION_MONITOR = "monitor_session.json"
SESSION_MAIN = "main_session.json"
VERIFICATION_FILE = "verification_pending.json"
REPLIED_FILE = "replied.json"

# States for conversation
(POST_NAME, POST_URL, POST_KEYWORDS, POST_DM, EDIT_NAME, EDIT_KEYWORDS, EDIT_DM,
 LOGIN_USERNAME, LOGIN_PASSWORD, LOGIN_VERIFY) = range(10)

def load_config():
    """Load configuration from JSON file"""
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "instagram_username": "",
            "instagram_password": "", 
            "posts": [],
            "telegram_token": "",
            "admin_user_id": ""
        }
    except json.JSONDecodeError:
        print("Error: config.json is corrupted")
        return {}

def save_config(cfg):
    """Save configuration to JSON file"""
    with open("config.json", "w") as f:
        json.dump(cfg, f, indent=2)

def load_replied_comments():
    """Load replied comments tracking with post-wise data"""
    try:
        with open("replied.json", "r") as f:
            data = json.load(f)
            # Ensure proper structure
            if "total" not in data:
                data["total"] = []
            if "posts" not in data:
                data["posts"] = {}
            # Convert lists to sets for faster lookup
            data["total"] = set(data["total"])
            for post_url in data["posts"]:
                data["posts"][post_url] = set(data["posts"][post_url])
            return data
    except FileNotFoundError:
        return {"total": set(), "posts": {}}
    except json.JSONDecodeError:
        print("Error: replied.json is corrupted, resetting...")
        return {"total": set(), "posts": {}}

def save_replied_comments(replied_data):
    """Save replied comments tracking with post-wise data"""
    # Convert sets back to lists for JSON serialization
    data_to_save = {
        "total": list(replied_data["total"]),
        "posts": {url: list(comments) for url, comments in replied_data["posts"].items()}
    }
    
    with open("replied.json", "w") as f:
        json.dump(data_to_save, f, indent=2)

def get_post_stats():
    """Get detailed statistics for each post"""
    try:
        with open("enhanced_posts.json", "r") as f:
            posts = json.load(f)
            
        stats = {}
        for post in posts:
            post_id = post["id"]
            stats[post_id] = {
                "name": post.get("name", "Unnamed"),
                "url": post.get("url", ""),
                "keywords": post.get("keywords", []),
                "total_comments": post.get("stats", {}).get("total_comments", 0),
                "keyword_matches": post.get("stats", {}).get("keyword_matches", 0),
                "dms_sent": post.get("stats", {}).get("dms_sent", 0),
                "replies_sent": post.get("stats", {}).get("replies_sent", 0),
                "last_check": post.get("stats", {}).get("last_check", "Never"),
                "status": "Active" if post.get("active", True) else "Inactive"
            }
        
        return stats
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print("Error: enhanced_posts.json is corrupted")
        return {}

def extract_post_id_from_url(url):
    """Extract Instagram post ID from URL"""
    if "instagram.com/p/" in url:
        return url.split("/p/")[1].split("/")[0]
    elif "instagram.com/reel/" in url:
        return url.split("/reel/")[1].split("/")[0]
    return None

def check_file_status():
    """Check status of important files"""
    files_to_check = [
        "config.json",
        "main_session.json", 
        "monitor_session.json",
        "enhanced_posts.json",
        "replied.json"
    ]
    
    status = {}
    for file in files_to_check:
        if os.path.exists(file):
            try:
                stat = os.stat(file)
                status[file] = {
                    "exists": True,
                    "size": stat.st_size,
                    "modified": time.ctime(stat.st_mtime)
                }
            except:
                status[file] = {"exists": True, "error": "Cannot read file stats"}
        else:
            status[file] = {"exists": False}
    
    return status

def clean_old_files():
    """Clean up old and temporary files"""
    temp_files = [
        "__pycache__",
        "*.pyc",
        ".DS_Store",
        "Thumbs.db"
    ]
    
    cleaned = []
    for pattern in temp_files:
        if pattern == "__pycache__":
            if os.path.exists("__pycache__"):
                import shutil
                shutil.rmtree("__pycache__")
                cleaned.append("__pycache__")
    
    return cleaned

# Instagram Authentication Functions (moved from instagram_auth.py)
def create_instagram_client():
    """Create Instagram client with proper settings"""
    from instagrapi import Client
    client = Client()
    client.set_user_agent("Instagram 280.0.0.22.112 Android")
    return client

def clear_instagram_sessions():
    """Clear existing Instagram session files"""
    session_files = ["main_session.json", "monitor_session.json"]
    cleared = []
    
    for file in session_files:
        if os.path.exists(file):
            try:
                os.remove(file)
                cleared.append(file)
            except Exception as e:
                print(f"Could not remove {file}: {e}")
    
    if cleared:
        print(f"Cleared old sessions: {', '.join(cleared)}")
    
    return len(cleared) > 0

def setup_instagram_credentials():
    """Interactive Instagram credential setup"""
    print("Instagram Authentication Setup")
    print("=" * 35)
    
    username = input("Instagram username: ").strip()
    password = input("Instagram password: ").strip()
    
    if not username or not password:
        print("Username and password required")
        return False
    
    # Update config with credentials
    config = load_config()
    config["instagram_username"] = username
    config["instagram_password"] = password
    save_config(config)
    
    print("Credentials saved to configuration")
    return True