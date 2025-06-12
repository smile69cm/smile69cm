"""
Advanced Instagram monitoring system compatible with enhanced post management
"""

import time
import json
import os
import re
import random
from pathlib import Path
from datetime import datetime, timedelta
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired, ClientError
from utils import load_config, save_config, load_replied_comments, save_replied_comments, TELEGRAM_BOT_TOKEN, ADMIN_ID
import asyncio
from telegram import Bot

class SafetyDelayManager:
    """Manages safety delays to prevent rate limiting and improve reliability"""
    
    def __init__(self):
        self.last_dm_time = None
        self.last_reply_time = None
        self.last_comment_scan_time = None
        self.action_history = []
        self.rate_limit_cooldown = None
        
    def get_smart_delay(self, action_type, recent_actions_count=0):
        """Calculate smart delay based on action type and recent activity"""
        base_delays = {
            'dm': (45, 75),           # 45-75 seconds between DMs
            'reply': (25, 40),        # 25-40 seconds between replies
            'scan': (8, 15),          # 8-15 seconds between scans
            'between_actions': (35, 55) # 35-55 seconds between different actions
        }
        
        min_delay, max_delay = base_delays.get(action_type, (30, 60))
        
        # Increase delays if many recent actions
        if recent_actions_count > 3:
            min_delay += 15
            max_delay += 25
        elif recent_actions_count > 1:
            min_delay += 8
            max_delay += 12
            
        # Add randomization for natural behavior
        return random.randint(min_delay, max_delay)
    
    def should_wait_for_rate_limit(self):
        """Check if we should wait due to rate limiting"""
        if self.rate_limit_cooldown and datetime.now() < self.rate_limit_cooldown:
            remaining = (self.rate_limit_cooldown - datetime.now()).seconds
            print(f"⏳ Rate limit cooldown: {remaining}s remaining")
            return True
        return False
    
    def set_rate_limit_cooldown(self, duration_minutes=10):
        """Set rate limit cooldown period"""
        self.rate_limit_cooldown = datetime.now() + timedelta(minutes=duration_minutes)
        print(f"🛡️ Rate limit protection: {duration_minutes} minute cooldown")
    
    def wait_for_action(self, action_type, force_wait=False):
        """Wait appropriate time before performing action"""
        if self.should_wait_for_rate_limit():
            return False
            
        current_time = datetime.now()
        recent_actions = len([a for a in self.action_history if current_time - a['time'] < timedelta(minutes=5)])
        
        # Calculate required delay
        delay = self.get_smart_delay(action_type, recent_actions)
        
        # Check last action timing
        last_action_time = None
        if action_type == 'dm' and self.last_dm_time:
            last_action_time = self.last_dm_time
        elif action_type == 'reply' and self.last_reply_time:
            last_action_time = self.last_reply_time
        elif action_type == 'scan' and self.last_comment_scan_time:
            last_action_time = self.last_comment_scan_time
            
        if last_action_time:
            time_since_last = (current_time - last_action_time).seconds
            if time_since_last < delay or force_wait:
                wait_time = max(0, delay - time_since_last)
                if wait_time > 0:
                    print(f"⏳ Safety delay ({action_type}): {wait_time}s...")
                    time.sleep(wait_time)
        
        # Record this action
        self.action_history.append({
            'type': action_type,
            'time': datetime.now()
        })
        
        # Update last action time
        if action_type == 'dm':
            self.last_dm_time = datetime.now()
        elif action_type == 'reply':
            self.last_reply_time = datetime.now()
        elif action_type == 'scan':
            self.last_comment_scan_time = datetime.now()
            
        # Clean old history (keep last 2 hours)
        cutoff = current_time - timedelta(hours=2)
        self.action_history = [a for a in self.action_history if a['time'] > cutoff]
        
        return True

class AdvancedInstagramMonitor:
    def __init__(self):
        self.monitor_client = None
        self.main_client = None
        self.monitoring = False
        self.safety_manager = SafetyDelayManager()
        self.posts_file = "enhanced_posts.json"
        self.processed_users = {}  # Track users who received DMs to prevent duplicates
        self.telegram_bot = None
        self.admin_chat_id = None
        self.single_account_mode = False
        
    def load_sessions(self):
        """Load Instagram sessions - with IP restriction handling"""
        try:
            from utils import TELEGRAM_BOT_TOKEN, ADMIN_ID
            if TELEGRAM_BOT_TOKEN:
                self.telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)
                self.admin_chat_id = ADMIN_ID
            
            # Check if we're in IP restricted mode
            config_file = "config.json"
            ip_restricted = False
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r") as f:
                        config = json.load(f)
                        ip_restricted = config.get("ip_restricted", False)
                except:
                    pass
            
            if ip_restricted:
                print("IP restrictions detected - running in limited mode")
                print("Instagram functionality will be limited until restrictions lift")
                self.monitor_client = None
                self.main_client = None
                return
            
            monitor_path = Path("monitor_session.json")
            main_path = Path("main_session.json")
            
            # Try to load sessions
            if monitor_path.exists():
                try:
                    self.monitor_client = Client()
                    self.monitor_client.load_settings(monitor_path)
                    # Test the session
                    self.monitor_client.account_info()
                    print("Monitor account loaded for watching posts")
                except Exception as e:
                    print(f"Monitor session invalid: {e}")
                    self.monitor_client = None
            else:
                print("No monitor session found")
                self.monitor_client = None
            
            if main_path.exists():
                try:
                    self.main_client = Client()
                    self.main_client.load_settings(main_path)
                    # Test the session
                    self.main_client.account_info()
                    print("Main account loaded for actions")
                except Exception as e:
                    print(f"Main session invalid: {e}")
                    self.main_client = None
            else:
                print("No main session found")
                self.main_client = None
            
            if self.monitor_client and self.main_client:
                print("Dual account mode: Monitor and main sessions loaded")
                self.single_account_mode = False
            elif self.monitor_client and not self.main_client:
                print("Monitor account available but main account authentication required")
                print("⚠️ DMs and comment replies need main account login")
                self.single_account_mode = False
                # Don't use monitor as main - keep them separate
                self.main_client = None
            elif self.main_client and not self.monitor_client:
                print("Main account available but monitor account missing")
                self.single_account_mode = False
            else:
                print("No valid Instagram sessions - running in limited mode")
                print("DMs and comment replies require authentication")
                
        except Exception as e:
            error_msg = f"Session loading error: {e}"
            print(error_msg)
    def send_telegram_message(self, message):
        """Send message to admin via Telegram - disabled to prevent spam"""
        # Telegram messaging disabled to prevent spam
        pass
    
    def _refresh_monitor_session(self):
        """Refresh monitor account session"""
        try:
            monitor_path = Path("monitor_session.json")
            if monitor_path.exists():
                self.monitor_client = Client()
                self.monitor_client.load_settings(monitor_path)
                print("Monitor session refreshed successfully")
                return True
        except Exception as e:
            print(f"Monitor session refresh failed: {e}")
        
        print("Monitor session expired - Instagram restrictions detected")
        return False
    
    def _refresh_main_session(self):
        """Refresh main account session"""
        try:
            main_path = Path("main_session.json")
            if main_path.exists():
                self.main_client = Client()
                self.main_client.load_settings(main_path)
                print("Main session refreshed successfully")
                return True
        except Exception as e:
            print(f"Main session refresh failed: {e}")
        
        print("Main session expired - Instagram restrictions detected")
        return False
    
    def load_enhanced_posts(self):
        """Load enhanced posts from file"""
        if os.path.exists(self.posts_file):
            try:
                with open(self.posts_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def save_enhanced_posts(self, posts):
        """Save enhanced posts to file"""
        try:
            with open(self.posts_file, 'w') as f:
                json.dump(posts, f, indent=2)
        except Exception as e:
            print(f"Error saving posts: {e}")
    
    def get_post_id_from_url(self, url):
        """Extract Instagram post ID from URL"""
        try:
            if "/p/" in url:
                code = url.split("/p/")[1].split("/")[0]
            elif "/reel/" in url:
                code = url.split("/reel/")[1].split("/")[0]
            else:
                return None
            
            if self.monitor_client:
                media_id = self.monitor_client.media_pk_from_code(code)
                return str(media_id)
        except Exception as e:
            print(f"Error extracting post ID: {e}")
        return None
    
    def scan_comments(self, post_id, amount=50):
        """Scan comments on Instagram post with accurate counting"""
        try:
            if not self.monitor_client:
                print("No monitor client available for comment scanning")
                return []
            
            # Try to get real comments with proper error handling
            try:
                # Get all comments for accurate count
                all_comments = self.monitor_client.media_comments(post_id, amount=200)
                
                # Take only the requested amount for processing
                comments = all_comments[:amount] if len(all_comments) > amount else all_comments
                
                print(f"Found {len(all_comments)} total comments, processing {len(comments)} for post {post_id}")
                
                # Convert to standard format
                formatted_comments = []
                for comment in comments:
                    try:
                        formatted_comments.append({
                            'pk': str(comment.pk),
                            'user': {'pk': str(comment.user.pk), 'username': comment.user.username},
                            'text': comment.text,
                            'created_at': str(getattr(comment, 'created_at', '2025-06-11T12:00:00Z'))
                        })
                    except Exception as format_error:
                        print(f"Error formatting comment: {format_error}")
                        continue
                
                # Update accurate total count in post stats
                self.update_total_comment_count(post_id, len(all_comments))
                
                return formatted_comments
                
            except LoginRequired:
                print("Session expired during comment scanning")
                if self.single_account_mode:
                    self._refresh_main_session()
                else:
                    self._refresh_monitor_session()
                return []
            except Exception as e:
                error_str = str(e).lower()
                if "media not found" in error_str:
                    print(f"Post {post_id} not found or private")
                elif "rate limit" in error_str:
                    print("Rate limited - waiting before next scan")
                    import time
                    time.sleep(5)
                else:
                    print(f"Error getting comments: {e}")
                return []
            
        except Exception as e:
            print(f"Error scanning comments for post {post_id}: {e}")
            return []

    def update_total_comment_count(self, post_id, total_count):
        """Update the total comment count for accurate display"""
        try:
            posts = self.load_enhanced_posts()
            for post in posts:
                if post.get('ig_post_id') == post_id:
                    if 'stats' not in post:
                        post['stats'] = {}
                    post['stats']['total_comments_actual'] = total_count
                    break
            self.save_enhanced_posts(posts)
        except Exception as e:
            print(f"Error updating comment count: {e}")
    
    def send_dm(self, user_id, message):
        """Enhanced DM sending with advanced safety delays and reliability"""
        try:
            # Track DM attempts but allow multiple DMs per user (one per comment)
            print(f"📤 Sending DM to user {user_id} for new comment")
            
            # Apply safety delay before DM
            if not self.safety_manager.wait_for_action('dm'):
                print("⚠️ Rate limit active, skipping DM")
                return False
            
            # DMs require main account - do not use monitor as fallback
            if not self.main_client:
                print("❌ Main account not authenticated - DM sending disabled")
                print("💡 Please login to your main Instagram account to enable DM functionality")
                return False
            
            client_to_use = self.main_client
            
            # Verify client is still authenticated
            try:
                client_to_use.account_info()
            except Exception as auth_error:
                print(f"⚠️ Client authentication expired: {auth_error}")
                if client_to_use == self.main_client:
                    self._refresh_main_session()
                else:
                    self._refresh_monitor_session()
                return False
            
            # Enhanced retry logic with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Use direct_send method for DMs
                    thread = client_to_use.direct_send(message, [user_id])
                    if thread:
                        print(f"✅ DM sent to user {user_id}")
                        # Track successful DM (but allow multiple DMs per user)
                        self.processed_users[str(user_id)] = datetime.now()
                        return True
                    else:
                        print(f"DM failed - no thread returned for user {user_id}")
                        
                except Exception as dm_error:
                    error_str = str(dm_error).lower()
                    print(f"DM attempt {attempt + 1}/{max_retries} failed: {dm_error}")
                    
                    if "rate limit" in error_str or "too many requests" in error_str:
                        # Set rate limit cooldown
                        self.safety_manager.set_rate_limit_cooldown(15)
                        wait_time = 60 * (attempt + 1)  # Exponential backoff
                        print(f"🛡️ Rate limited, waiting {wait_time} seconds...")
                        time.sleep(wait_time)
                    elif "login_required" in error_str:
                        print("🔐 Session expired, refreshing...")
                        if client_to_use == self.main_client:
                            self._refresh_main_session()
                        else:
                            self._refresh_monitor_session()
                        return False
                    elif "spam" in error_str or "blocked" in error_str:
                        print("🚫 Account restricted, cooling down...")
                        self.safety_manager.set_rate_limit_cooldown(30)
                        return False
                    elif attempt < max_retries - 1:
                        # Progressive delay between retries
                        delay = random.randint(5, 15) * (attempt + 1)
                        print(f"⏳ Retrying in {delay}s...")
                        time.sleep(delay)
                    continue
            
            print(f"❌ All DM attempts failed for user {user_id}")
            return False
            
        except Exception as e:
            print(f"DM system error: {e}")
            return False
    
    def reply_to_comment(self, post_id, comment_id, reply_text):
        """Enhanced comment reply with advanced safety delays and reliability"""
        try:
            # Apply safety delay before replying
            if not self.safety_manager.wait_for_action('reply'):
                print("⚠️ Rate limit active, skipping comment reply")
                return False
            
            # Comment replies require main account - do not use monitor as fallback
            if not self.main_client:
                print("❌ Main account not authenticated - comment reply disabled")
                print("💡 Please login to your main Instagram account to enable comment replies")
                return False
            
            client_to_use = self.main_client
            
            # Enhanced retry logic for comment replies
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Reply to the comment
                    result = client_to_use.media_comment(post_id, reply_text, replied_to_comment_id=comment_id)
                    if result:
                        print(f"✅ Replied to comment {comment_id}")
                        return True
                    else:
                        print(f"❌ Failed to reply to comment {comment_id}")
                        if attempt < max_retries - 1:
                            delay = random.randint(3, 8)
                            print(f"⏳ Retrying reply in {delay}s...")
                            time.sleep(delay)
                        continue
                        
                except LoginRequired:
                    print("🔐 Session expired during comment reply")
                    if client_to_use == self.main_client:
                        self._refresh_main_session()
                    else:
                        self._refresh_monitor_session()
                    return False
                    
                except Exception as reply_error:
                    error_str = str(reply_error).lower()
                    print(f"Reply attempt {attempt + 1}/{max_retries} failed: {reply_error}")
                    
                    if "rate limit" in error_str or "too many requests" in error_str:
                        # Set rate limit protection
                        self.safety_manager.set_rate_limit_cooldown(10)
                        wait_time = 30 * (attempt + 1)
                        print(f"🛡️ Rate limited on reply, waiting {wait_time}s...")
                        time.sleep(wait_time)
                    elif "no longer available" in error_str or "not found" in error_str:
                        print("📝 Comment/post no longer available, skipping reply")
                        return False  # Don't retry for unavailable content
                    elif "spam" in error_str or "blocked" in error_str:
                        print("🚫 Reply blocked, account may be restricted")
                        self.safety_manager.set_rate_limit_cooldown(20)
                        return False
                    elif attempt < max_retries - 1:
                        delay = random.randint(5, 12) * (attempt + 1)
                        print(f"⏳ Retrying reply in {delay}s...")
                        time.sleep(delay)
                    continue
            
            print(f"❌ All reply attempts failed for comment {comment_id}")
            return False
                
        except Exception as e:
            print(f"Error in reply function: {e}")
            return False
    
    def update_post_stats(self, post_id, action_type, username=None):
        """Update post statistics"""
        try:
            posts = self.load_enhanced_posts()
            for post in posts:
                if post["id"] == post_id:
                    if action_type == "dm":
                        post["stats"]["dms"] += 1
                        if "dm_users" not in post["stats"]:
                            post["stats"]["dm_users"] = []
                        if username and username not in post["stats"]["dm_users"]:
                            post["stats"]["dm_users"].append(username)
                    elif action_type == "reply":
                        post["stats"]["replies"] += 1
                    elif action_type == "comment_found":
                        if "total_comments_found" not in post["stats"]:
                            post["stats"]["total_comments_found"] = 0
                        post["stats"]["total_comments_found"] += 1
                        if "comment_users" not in post["stats"]:
                            post["stats"]["comment_users"] = []
                        if username and username not in post["stats"]["comment_users"]:
                            post["stats"]["comment_users"].append(username)
                    
                    self.save_enhanced_posts(posts)
                    break
        except Exception as e:
            print(f"Error updating stats: {e}")
    
    def fuzzy_keyword_match(self, comment_text, keywords):
        """Enhanced keyword matching with typo tolerance and partial matches"""
        comment_lower = comment_text.lower()
        
        for keyword in keywords:
            keyword_lower = keyword.lower().strip()
            
            # Exact match
            if keyword_lower in comment_lower:
                return True
            
            # Handle variations and typos
            # Remove spaces and check
            comment_no_spaces = re.sub(r'\s+', '', comment_lower)
            keyword_no_spaces = re.sub(r'\s+', '', keyword_lower)
            
            if keyword_no_spaces in comment_no_spaces:
                return True
            
            # Check for common typos and character substitutions
            # Create pattern for typo tolerance
            typo_pattern = self.create_typo_pattern(keyword_lower)
            if re.search(typo_pattern, comment_lower):
                return True
            
            # Word boundary matching for partial words
            words_in_comment = re.findall(r'\b\w+\b', comment_lower)
            for word in words_in_comment:
                # Check if keyword is contained in any word (like "hii" contains "hi")
                if keyword_lower in word or word in keyword_lower:
                    return True
                
                # Levenshtein-like simple distance check for typos
                if len(word) > 2 and len(keyword_lower) > 2:
                    if self.simple_typo_check(word, keyword_lower):
                        return True
        
        return False
    
    def create_typo_pattern(self, keyword):
        """Create regex pattern to catch common typos"""
        # Replace characters that are commonly mistyped
        pattern = keyword
        # Common substitutions
        substitutions = {
            'a': '[a@]', 'e': '[e3]', 'i': '[i1]', 'o': '[o0]', 's': '[s5z]',
            'l': '[l1]', 't': '[t7]', 'g': '[g9]', 'b': '[b6]'
        }
        
        for char, replacement in substitutions.items():
            pattern = pattern.replace(char, replacement)
        
        # Allow for missing or extra characters
        flexible_pattern = ''
        for i, char in enumerate(pattern):
            if char.isalpha() or char in '[]':
                flexible_pattern += char + '?'  # Make each character optional
            else:
                flexible_pattern += char
        
        return flexible_pattern
    
    def simple_typo_check(self, word1, word2):
        """Simple typo detection - allows 1-2 character differences"""
        if abs(len(word1) - len(word2)) > 2:
            return False
        
        differences = 0
        max_len = max(len(word1), len(word2))
        min_len = min(len(word1), len(word2))
        
        for i in range(min_len):
            if word1[i] != word2[i]:
                differences += 1
        
        differences += abs(len(word1) - len(word2))
        
        # Allow up to 2 differences for words longer than 4 characters
        tolerance = 2 if max_len > 4 else 1
        return differences <= tolerance
    
    def monitor_posts(self):
        """Main monitoring loop"""
        print("Starting advanced Instagram monitoring...")
        
        while self.monitoring:
            try:
                # Load enhanced posts
                enhanced_posts = self.load_enhanced_posts()
                active_posts = [p for p in enhanced_posts if p.get("enabled", True)]
                
                if not active_posts:
                    print("No active posts to monitor")
                    time.sleep(30)
                    continue
                
                print(f"Monitoring {len(active_posts)} active posts...")
                
                # Load replied comments tracking
                replied_data = load_replied_comments()
                
                for post in active_posts:
                    try:
                        # Get or generate Instagram post ID
                        ig_post_id = post.get("ig_post_id")
                        if not ig_post_id:
                            ig_post_id = self.get_post_id_from_url(post["url"])
                            if ig_post_id:
                                # Update post with ID
                                enhanced_posts = self.load_enhanced_posts()
                                for p in enhanced_posts:
                                    if p["id"] == post["id"]:
                                        p["ig_post_id"] = ig_post_id
                                        break
                                self.save_enhanced_posts(enhanced_posts)
                        
                        if not ig_post_id:
                            print(f"Cannot get post ID for: {post['name']}")
                            continue
                        
                        # Scan comments
                        comments = self.scan_comments(ig_post_id, amount=30)
                        
                        # Initialize tracking for this post
                        post_url = post['url']
                        if post_url not in replied_data.get("posts", {}):
                            replied_data.setdefault("posts", {})[post_url] = set()
                        
                        new_matches = 0
                        
                        for comment in comments:
                            comment_id = str(comment['pk'])
                            username = comment['user']['username']
                            
                            # Skip if already processed - check both global and post-specific tracking
                            if (comment_id in replied_data.get("total", set()) or 
                                comment_id in replied_data.get("posts", {}).get(post_url, set())):
                                continue
                            
                            # Enhanced keyword matching with fuzzy logic
                            comment_text = comment['text']
                            keywords = post.get("keywords", [])
                            
                            # Update stats for every comment found (regardless of keyword match)
                            self.update_post_stats(post["id"], "comment_found", username)
                            
                            if self.fuzzy_keyword_match(comment_text, keywords):
                                print(f"Keyword match in '{post['name']}' by @{username}: {comment['text'][:50]}...")
                                
                                # Mark as processed IMMEDIATELY to prevent duplicates
                                replied_data["total"].add(comment_id)
                                replied_data["posts"][post_url].add(comment_id)
                                
                                # Save tracking data immediately
                                save_replied_comments(replied_data)
                                
                                # Send DM FIRST for EACH matching comment (multiple DMs per user allowed)
                                user_id = comment['user']['pk']
                                print(f"📤 Sending DM #{new_matches + 1} to @{username} for comment: {comment['text'][:30]}...")
                                dm_success = self.send_dm(user_id, post["message"])
                                if dm_success:
                                    self.update_post_stats(post["id"], "dm", username)
                                    print(f"✅ DM sent to user @{username} for comment: {comment['text'][:30]}...")
                                else:
                                    print(f"❌ Failed to send DM to @{username}")
                                
                                # Smart delay between DM and reply using safety manager
                                self.safety_manager.wait_for_action('between_actions', force_wait=True)
                                
                                # Reply to comment SECOND with enhanced safety delays
                                reply_message = "Check your DM! 📩"
                                reply_success = self.reply_to_comment(ig_post_id, comment_id, reply_message)
                                if reply_success:
                                    self.update_post_stats(post["id"], "reply")
                                    print(f"✅ Replied to comment by @{username}")
                                else:
                                    print(f"❌ Failed to reply to comment by @{username}")
                                
                                # Progressive delay for multiple matches
                                if new_matches > 0:
                                    progressive_delay = self.safety_manager.get_smart_delay('between_actions', new_matches)
                                    print(f"⏳ Progressive safety delay: {progressive_delay}s...")
                                    time.sleep(progressive_delay)
                                
                                new_matches += 1
                        
                        if new_matches > 0:
                            print(f"Post '{post['name']}': {new_matches} new matches processed")
                        
                    except Exception as e:
                        print(f"Error processing post '{post.get('name', 'Unknown')}': {e}")
                        continue
                
                # Save tracking data
                save_replied_comments(replied_data)
                
                # Sync with legacy config for compatibility
                self.sync_legacy_config(enhanced_posts)
                
                print("Monitoring cycle completed. Waiting 3 minutes...")
                time.sleep(180)
                
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                time.sleep(180)
    
    def sync_legacy_config(self, enhanced_posts):
        """Sync enhanced posts to legacy config for compatibility"""
        try:
            cfg = load_config()
            legacy_posts = []
            
            for post in enhanced_posts:
                if post.get("enabled", True):
                    legacy_posts.append({
                        "url": post["url"],
                        "keywords": post["keywords"],
                        "message": post["message"],
                        "ig_post_id": post.get("ig_post_id")
                    })
            
            cfg["posts"] = legacy_posts
            save_config(cfg)
            
        except Exception as e:
            print(f"Error syncing legacy config: {e}")
    
    def start_monitoring(self):
        """Start the monitoring system"""
        print("Starting Advanced Instagram Monitor...")
        
        # Load sessions
        self.load_sessions()
        
        if not self.monitor_client and not self.main_client:
            error_msg = "No Instagram sessions available. Please login first."
            print(error_msg)
            self.send_telegram_message(f"❌ {error_msg}")
            return False
        
        self.monitoring = True
        
        try:
            self.monitor_posts()
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
        except Exception as e:
            print(f"Monitoring error: {e}")
        finally:
            self.monitoring = False
        
        return True
    
    def stop_monitoring(self):
        """Stop the monitoring system"""
        self.monitoring = False
        print("Monitoring stopped")

def start():
    """Start the advanced Instagram monitoring system"""
    monitor = AdvancedInstagramMonitor()
    return monitor.start_monitoring()

if __name__ == "__main__":
    start()