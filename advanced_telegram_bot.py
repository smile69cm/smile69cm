"""
Advanced Instagram Automation Bot with Enhanced Post Management
Features: Named posts, individual controls, edit/remove functionality, account recovery
"""

import json
import os
import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext, ConversationHandler
from utils import load_config, save_config, ADMIN_ID, TELEGRAM_BOT_TOKEN

# Conversation states
POST_NAME, POST_URL, POST_KEYWORDS, POST_DM = range(4)
EDIT_NAME, EDIT_KEYWORDS, EDIT_DM = range(4, 7)
LOGIN_USERNAME, LOGIN_PASSWORD, VERIFICATION_CODE = range(7, 10)

# Account recovery class
class AccountRecovery:
    def __init__(self):
        self.recovery_steps = {
            "CHECKPOINT": [
                "Open Instagram app on your phone",
                "Try to log in normally", 
                "Complete any identity verification requested",
                "Enable two-factor authentication in settings",
                "Wait 24 hours before using automation"
            ],
            "CHALLENGE": [
                "Open Instagram app and check for security notifications",
                "Complete any verification challenges shown",
                "Verify your phone number and email if requested",
                "Post some normal content (stories, posts, likes)",
                "Wait 2-3 hours then try bot again"
            ],
            "RATE_LIMITED": [
                "Stop all automation for 24-48 hours",
                "Use Instagram normally (browse, like, comment)",
                "Don't use any third-party apps or tools",
                "Post regular content to show normal activity",
                "Try automation again after waiting period"
            ],
            "GENERAL": [
                "Use Instagram app normally for 1-2 days",
                "Post content, view stories, like posts naturally",
                "Avoid any automation or third-party tools",
                "Check Instagram app for any notifications",
                "Re-enter your credentials in the bot"
            ]
        }
    
    def get_recovery_plan(self, error_type):
        return self.recovery_steps.get(error_type, self.recovery_steps["GENERAL"])

class PostManager:
    def __init__(self):
        self.file_path = "enhanced_posts.json"
    
    def load_posts(self):
        """Load posts from file"""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def save_posts(self, posts):
        """Save posts to file"""
        try:
            with open(self.file_path, 'w') as f:
                json.dump(posts, f, indent=2)
        except Exception as e:
            print(f"Error saving posts: {e}")
    
    def add_post(self, name, url, keywords, message):
        """Add new post"""
        posts = self.load_posts()
        post = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "url": url,
            "keywords": keywords,
            "message": message,
            "enabled": True,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "stats": {"replies": 0, "dms": 0}
        }
        posts.append(post)
        self.save_posts(posts)
        self.sync_legacy()
        return post
    
    def get_post(self, post_id):
        """Get post by ID"""
        posts = self.load_posts()
        return next((p for p in posts if p["id"] == post_id), None)
    
    def update_post(self, post_id, updates):
        """Update post"""
        posts = self.load_posts()
        for i, post in enumerate(posts):
            if post["id"] == post_id:
                posts[i].update(updates)
                self.save_posts(posts)
                self.sync_legacy()
                return True
        return False
    
    def delete_post(self, post_id):
        """Delete post"""
        posts = self.load_posts()
        posts = [p for p in posts if p["id"] != post_id]
        self.save_posts(posts)
        self.sync_legacy()
        return True
    
    def toggle_post(self, post_id):
        """Toggle post status"""
        post = self.get_post(post_id)
        if post:
            new_status = not post.get("enabled", True)
            self.update_post(post_id, {"enabled": new_status})
            return new_status
        return None
    
    def sync_legacy(self):
        """Sync with legacy config format"""
        try:
            posts = self.load_posts()
            cfg = load_config()
            cfg["posts"] = []
            
            for post in posts:
                if post.get("enabled", True):
                    cfg["posts"].append({
                        "url": post["url"],
                        "keywords": post["keywords"],
                        "message": post["message"]
                    })
            
            save_config(cfg)
        except Exception as e:
            print(f"Error syncing legacy: {e}")

pm = PostManager()

def check_access(user_id):
    return user_id == ADMIN_ID

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Post", callback_data="add_post"),
         InlineKeyboardButton("📋 Manage Posts", callback_data="view_posts")],
        [InlineKeyboardButton("🔐 Login Accounts", callback_data="login_menu"),
         InlineKeyboardButton("📊 Statistics", callback_data="stats")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
    ])

def posts_keyboard():
    posts = pm.load_posts()
    keyboard = []
    
    for post in posts[:8]:  # Show max 8 posts
        status = "✅" if post.get("enabled") else "⏸️"
        name = post["name"][:15] + "..." if len(post["name"]) > 15 else post["name"]
        keyboard.append([InlineKeyboardButton(f"{status} {name}", callback_data=f"post_{post['id']}")])
    
    # Add refresh and back buttons
    keyboard.append([InlineKeyboardButton("🔄 Refresh Posts", callback_data="refresh_posts")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="main")])
    return InlineKeyboardMarkup(keyboard)

def post_actions_keyboard(post_id):
    post = pm.get_post(post_id)
    if not post:
        return None
    
    toggle_text = "⏸️ Pause" if post.get("enabled") else "▶️ Start"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Name", callback_data=f"edit_name_{post_id}"),
         InlineKeyboardButton("🔑 Keywords", callback_data=f"edit_keys_{post_id}")],
        [InlineKeyboardButton("💬 Edit DM", callback_data=f"edit_dm_{post_id}"),
         InlineKeyboardButton(toggle_text, callback_data=f"toggle_{post_id}")],
        [InlineKeyboardButton("📊 Stats", callback_data=f"stats_{post_id}"),
         InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{post_id}")],
        [InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{post_id}"),
         InlineKeyboardButton("🔙 Back", callback_data="view_posts")]
    ])

async def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not check_access(user_id):
        await update.message.reply_text("Access denied. This bot is private.")
        return
    
    posts = pm.load_posts()
    active = len([p for p in posts if p.get("enabled")])
    
    text = (f"🤖 Advanced Instagram Automation\n\n"
            f"📋 Posts: {len(posts)} total, {active} active\n"
            f"🎯 Individual post controls available\n\n"
            f"Choose an option:")
    
    await update.message.reply_text(text, reply_markup=main_keyboard())

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    if not check_access(user_id):
        await query.edit_message_text("Access denied.")
        return
    
    await query.answer()
    
    # Main menu
    if data == "main":
        posts = pm.load_posts()
        active = len([p for p in posts if p.get("enabled")])
        text = (f"🤖 Advanced Instagram Automation\n\n"
                f"📋 Posts: {len(posts)} total, {active} active\n"
                f"Choose an option:")
        await query.edit_message_text(text, reply_markup=main_keyboard())
    
    # Add post
    elif data == "add_post":
        await query.message.reply_text(
            "➕ Create New Post\n\n"
            "First, give this post a memorable name:\n"
            "Example: 'Product Launch' or 'Daily Tips'"
        )
        return POST_NAME
    
    # View posts
    elif data == "view_posts":
        posts = pm.load_posts()
        if not posts:
            text = "📋 No posts created yet.\n\nUse 'Add Post' to create your first automated post."
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main")]])
        else:
            text = "📋 Your Posts\n\nSelect a post to manage:"
            keyboard = posts_keyboard()
        
        await query.edit_message_text(text, reply_markup=keyboard)
    
    # View specific post
    elif data.startswith("post_"):
        post_id = data.replace("post_", "")
        post = pm.get_post(post_id)
        
        if not post:
            await query.edit_message_text("Post not found.")
            return
        
        status = "✅ Active" if post.get("enabled") else "⏸️ Paused"
        keywords = ", ".join(post["keywords"][:3])
        if len(post["keywords"]) > 3:
            keywords += f" (+{len(post['keywords'])-3} more)"
        
        # Enhanced stats with member count
        stats = post.get('stats', {})
        total_comments = stats.get('total_comments_found', 0)
        unique_commenters = len(stats.get('comment_users', []))
        dm_count = stats.get('dms', 0)
        unique_dm_users = len(stats.get('dm_users', []))
        
        text = (f"📄 {post['name']}\n\n"
                f"🔗 URL: {post['url'][:40]}...\n"
                f"🔑 Keywords: {keywords}\n"
                f"💬 DM: {post['message'][:30]}...\n"
                f"📊 Status: {status}\n\n"
                f"📈 Detailed Stats:\n"
                f"👥 Total Comments: {total_comments}\n"
                f"🆔 Unique Commenters: {unique_commenters}\n"
                f"💬 Replies Sent: {stats.get('replies', 0)}\n"
                f"📩 DMs Sent: {dm_count}\n"
                f"👤 Unique DM Recipients: {unique_dm_users}\n\n"
                f"📅 Created: {post['created']}")
        
        await query.edit_message_text(text, reply_markup=post_actions_keyboard(post_id))
    
    # Toggle post
    elif data.startswith("toggle_"):
        post_id = data.replace("toggle_", "")
        new_status = pm.toggle_post(post_id)
        
        if new_status is not None:
            status_text = "activated" if new_status else "paused"
            await query.answer(f"Post {status_text}!", show_alert=True)
            
            # Refresh view
            post = pm.get_post(post_id)
            if post:
                status = "✅ Active" if post.get("enabled") else "⏸️ Paused"
                keywords = ", ".join(post["keywords"][:3])
                if len(post["keywords"]) > 3:
                    keywords += f" (+{len(post['keywords'])-3} more)"
                
                # Enhanced stats with member count
                stats = post.get('stats', {})
                total_comments = stats.get('total_comments_found', 0)
                unique_commenters = len(stats.get('comment_users', []))
                dm_count = stats.get('dms', 0)
                unique_dm_users = len(stats.get('dm_users', []))
                
                text = (f"📄 {post['name']}\n\n"
                        f"🔗 URL: {post['url'][:40]}...\n"
                        f"🔑 Keywords: {keywords}\n"
                        f"💬 DM: {post['message'][:30]}...\n"
                        f"📊 Status: {status}\n\n"
                        f"📈 Detailed Stats:\n"
                        f"👥 Total Comments: {total_comments}\n"
                        f"🆔 Unique Commenters: {unique_commenters}\n"
                        f"💬 Replies Sent: {stats.get('replies', 0)}\n"
                        f"📩 DMs Sent: {dm_count}\n"
                        f"👤 Unique DM Recipients: {unique_dm_users}\n\n"
                        f"📅 Created: {post['created']}")
                
                await query.edit_message_text(text, reply_markup=post_actions_keyboard(post_id))
    
    # Refresh individual post
    elif data.startswith("refresh_"):
        post_id = data.replace("refresh_", "")
        post = pm.get_post(post_id)
        
        if not post:
            await query.answer("Post not found!", show_alert=True)
            return
        
        await query.answer("Refreshing post data...", show_alert=False)
        
        # Refresh this specific post's data
        try:
            from advanced_instagram_monitor import AdvancedInstagramMonitor
            monitor = AdvancedInstagramMonitor()
            monitor.load_sessions()
            
            ig_post_id = post.get("ig_post_id")
            if ig_post_id:
                # Scan for latest comments
                comments = monitor.scan_comments(ig_post_id, amount=30)
                for comment in comments:
                    username = comment['user']['username']
                    monitor.update_post_stats(post["id"], "comment_found", username)
                    
                    # Check if keyword matches for new comments
                    if monitor.fuzzy_keyword_match(comment['text'], post.get("keywords", [])):
                        print(f"New keyword match found for {post['name']}")
            
        except Exception as e:
            print(f"Error refreshing post {post['name']}: {e}")
        
        # Reload post with updated data
        post = pm.get_post(post_id)
        if post:
            status = "✅ Active" if post.get("enabled") else "⏸️ Paused"
            keywords = ", ".join(post["keywords"][:3])
            if len(post["keywords"]) > 3:
                keywords += f" (+{len(post['keywords'])-3} more)"
            
            # Enhanced stats with member count
            stats = post.get('stats', {})
            total_comments = stats.get('total_comments_found', 0)
            unique_commenters = len(stats.get('comment_users', []))
            dm_count = stats.get('dms', 0)
            unique_dm_users = len(stats.get('dm_users', []))
            
            text = (f"📄 {post['name']} (Refreshed)\n\n"
                    f"🔗 URL: {post['url'][:40]}...\n"
                    f"🔑 Keywords: {keywords}\n"
                    f"💬 DM: {post['message'][:30]}...\n"
                    f"📊 Status: {status}\n\n"
                    f"📈 Latest Stats:\n"
                    f"👥 Total Comments: {total_comments}\n"
                    f"🆔 Unique Commenters: {unique_commenters}\n"
                    f"💬 Replies Sent: {stats.get('replies', 0)}\n"
                    f"📩 DMs Sent: {dm_count}\n"
                    f"👤 Unique DM Recipients: {unique_dm_users}\n\n"
                    f"📅 Created: {post['created']}")
            
            await query.edit_message_text(text, reply_markup=post_actions_keyboard(post_id))
    
    # Delete post
    elif data.startswith("delete_"):
        post_id = data.replace("delete_", "")
        post = pm.get_post(post_id)
        
        if post:
            pm.delete_post(post_id)
            await query.answer("Post deleted!", show_alert=True)
            
            text = f"🗑️ Post '{post['name']}' has been deleted."
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Posts", callback_data="view_posts")]])
            await query.edit_message_text(text, reply_markup=keyboard)
    
    # Edit handlers
    elif data.startswith("edit_name_"):
        post_id = data.replace("edit_name_", "")
        context.user_data['edit_post_id'] = post_id
        context.user_data['edit_type'] = 'name'
        await query.message.reply_text("✏️ Enter new post name:")
        return EDIT_NAME
    
    elif data.startswith("edit_keys_"):
        post_id = data.replace("edit_keys_", "")
        context.user_data['edit_post_id'] = post_id
        context.user_data['edit_type'] = 'keywords'
        await query.message.reply_text(
            "🔑 Enter keywords (comma separated)\n\n"
            "💡 Tips for better matching:\n"
            "• Add variations: link, links, ling\n"
            "• Include typos: hii, hi, hai\n"
            "• Single words work best\n"
            "• Bot auto-detects: partial matches, typos, character substitutions"
        )
        return EDIT_KEYWORDS
    
    elif data.startswith("edit_dm_"):
        post_id = data.replace("edit_dm_", "")
        context.user_data['edit_post_id'] = post_id
        context.user_data['edit_type'] = 'dm'
        await query.message.reply_text("💬 Enter new DM message:")
        return EDIT_DM
    
    # Enhanced Statistics
    elif data == "stats":
        posts = pm.load_posts()
        total_replies = sum(p.get("stats", {}).get("replies", 0) for p in posts)
        total_dms = sum(p.get("stats", {}).get("dms", 0) for p in posts)
        total_comments = sum(p.get("stats", {}).get("total_comments_found", 0) for p in posts)
        active_posts = len([p for p in posts if p.get("enabled")])
        
        # Calculate unique users across all posts
        all_commenters = set()
        all_dm_recipients = set()
        for post in posts:
            stats = post.get("stats", {})
            all_commenters.update(stats.get("comment_users", []))
            all_dm_recipients.update(stats.get("dm_users", []))
        
        text = (f"📊 System-Wide Statistics\n\n"
                f"📋 Total Posts: {len(posts)}\n"
                f"✅ Active Posts: {active_posts}\n\n"
                f"📈 Activity Summary:\n"
                f"👥 Total Comments Found: {total_comments}\n"
                f"🆔 Unique Commenters: {len(all_commenters)}\n"
                f"💬 Total Replies Sent: {total_replies}\n"
                f"📩 Total DMs Sent: {total_dms}\n"
                f"👤 Unique DM Recipients: {len(all_dm_recipients)}")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Post Details", callback_data="post_details"),
             InlineKeyboardButton("🔄 Refresh Stats", callback_data="refresh_stats")],
            [InlineKeyboardButton("🔙 Back", callback_data="main")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard)
    
    # Post Details for enhanced statistics
    elif data == "post_details":
        posts = pm.load_posts()
        if not posts:
            text = "📊 No posts to show detailed stats for."
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="stats")]])
        else:
            text = "📊 Individual Post Statistics\n\n"
            
            for i, post in enumerate(posts[:5]):  # Show first 5 posts
                stats = post.get('stats', {})
                total_comments = stats.get('total_comments_found', 0)
                unique_commenters = len(stats.get('comment_users', []))
                dm_count = stats.get('dms', 0)
                
                status_icon = "✅" if post.get("enabled") else "⏸️"
                post_name = post['name'][:12] + "..." if len(post['name']) > 12 else post['name']
                
                text += (f"{status_icon} {post_name}\n"
                        f"   👥 {total_comments} comments, 🆔 {unique_commenters} users\n"
                        f"   📩 {dm_count} DMs sent\n\n")
            
            if len(posts) > 5:
                text += f"... and {len(posts) - 5} more posts"
            
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Stats", callback_data="stats")]])
        
        await query.edit_message_text(text, reply_markup=keyboard)
    
    # Refresh functionality for stats
    elif data == "refresh_stats":
        await query.answer("Refreshing statistics...", show_alert=False)
        
        # Force refresh Instagram monitor to get latest data
        try:
            from advanced_instagram_monitor import AdvancedInstagramMonitor
            monitor = AdvancedInstagramMonitor()
            monitor.load_sessions()
            
            # Get latest posts data with updated stats
            posts = pm.load_posts()
            
            # Calculate fresh statistics
            total_replies = sum(p.get("stats", {}).get("replies", 0) for p in posts)
            total_dms = sum(p.get("stats", {}).get("dms", 0) for p in posts)
            active_posts = sum(1 for p in posts if p.get("enabled", True))
            
            # Get unique users from all posts
            all_commenters = set()
            all_dm_recipients = set()
            
            for post in posts:
                stats = post.get("stats", {})
                all_commenters.update(stats.get("comment_users", []))
                all_dm_recipients.update(stats.get("dm_users", []))
            
            from datetime import datetime
            current_time = datetime.now().strftime("%H:%M:%S")
            
            text = (f"📊 System Statistics (Refreshed)\n\n"
                f"📄 Posts: {len(posts)} total, {active_posts} active\n"
                f"🆔 Unique Commenters: {len(all_commenters)}\n"
                f"💬 Total Replies Sent: {total_replies}\n"
                f"📩 Total DMs Sent: {total_dms}\n"
                f"👤 Unique DM Recipients: {len(all_dm_recipients)}\n\n"
                f"⏰ Last Updated: {current_time}")
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Post Details", callback_data="post_details"),
                 InlineKeyboardButton("🔄 Refresh Stats", callback_data="refresh_stats")],
                [InlineKeyboardButton("🔙 Back", callback_data="main")]
            ])
            
            try:
                await query.edit_message_text(text, reply_markup=keyboard)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    print(f"Error refreshing stats: {e}")
                await query.answer("Stats refreshed!")
                
        except Exception as e:
            await query.edit_message_text(
                f"❌ Failed to refresh stats: {str(e)[:50]}...",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="stats")]])
            )
            
            # Update stats by simulating a quick scan
            for post in posts:
                if post.get("enabled"):
                    ig_post_id = post.get("ig_post_id")
                    if ig_post_id:
                        try:
                            # Quick comment scan to update stats
                            comments = monitor.scan_comments(ig_post_id, amount=10)
                            for comment in comments:
                                username = comment['user']['username']
                                monitor.update_post_stats(post["id"], "comment_found", username)
                        except Exception as e:
                            print(f"Error refreshing post {post['name']}: {e}")
        
        except Exception as e:
            print(f"Error during refresh: {e}")
        
        # Reload and display updated posts
        posts = pm.load_posts()
        if not posts:
            text = "📋 No posts created yet.\n\nUse 'Add Post' to create your first automated post."
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main")]])
        else:
            text = "📋 Your Posts (Refreshed)\n\nSelect a post to manage:"
            keyboard = posts_keyboard()
        
        await query.edit_message_text(text, reply_markup=keyboard)
    
    elif data == "refresh_stats":
        await query.answer("Refreshing statistics...", show_alert=False)
        
        # Force refresh all statistics
        try:
            from advanced_instagram_monitor import AdvancedInstagramMonitor
            monitor = AdvancedInstagramMonitor()
            monitor.load_sessions()
            
            posts = pm.load_posts()
            
            # Update all post statistics
            for post in posts:
                if post.get("enabled"):
                    ig_post_id = post.get("ig_post_id")
                    if ig_post_id:
                        try:
                            # Scan for latest comments and update stats
                            comments = monitor.scan_comments(ig_post_id, amount=20)
                            for comment in comments:
                                username = comment['user']['username']
                                monitor.update_post_stats(post["id"], "comment_found", username)
                        except Exception as e:
                            print(f"Error refreshing stats for {post['name']}: {e}")
        
        except Exception as e:
            print(f"Error during stats refresh: {e}")
        
        # Reload posts with updated stats
        posts = pm.load_posts()
        total_replies = sum(p.get("stats", {}).get("replies", 0) for p in posts)
        total_dms = sum(p.get("stats", {}).get("dms", 0) for p in posts)
        total_comments = sum(p.get("stats", {}).get("total_comments_found", 0) for p in posts)
        active_posts = len([p for p in posts if p.get("enabled")])
        
        # Calculate unique users across all posts
        all_commenters = set()
        all_dm_recipients = set()
        for post in posts:
            stats = post.get("stats", {})
            all_commenters.update(stats.get("comment_users", []))
            all_dm_recipients.update(stats.get("dm_users", []))
        
        text = (f"📊 System Statistics (Refreshed)\n\n"
                f"📋 Total Posts: {len(posts)}\n"
                f"✅ Active Posts: {active_posts}\n\n"
                f"📈 Latest Activity:\n"
                f"👥 Total Comments Found: {total_comments}\n"
                f"🆔 Unique Commenters: {len(all_commenters)}\n"
                f"💬 Total Replies Sent: {total_replies}\n"
                f"📩 Total DMs Sent: {total_dms}\n"
                f"👤 Unique DM Recipients: {len(all_dm_recipients)}")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Post Details", callback_data="post_details"),
             InlineKeyboardButton("🔄 Refresh Stats", callback_data="refresh_stats")],
            [InlineKeyboardButton("🔙 Back", callback_data="main")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard)
    
    # Settings handler
    elif data == "settings":
        from advanced_instagram_monitor import AdvancedInstagramMonitor
        monitor = AdvancedInstagramMonitor()
        
        try:
            monitor.load_sessions()
            auth_status = "✅ Instagram accounts authenticated"
            
            # Test authentication
            test_result = monitor.scan_comments('3648406004343711848', amount=1)
            if not test_result:
                auth_status = "⚠️ Instagram authentication expired - needs re-login"
        except Exception as e:
            auth_status = f"❌ Instagram authentication failed: {str(e)[:50]}"
        
        posts = pm.load_posts()
        active_posts = len([p for p in posts if p.get("enabled")])
        
        # Check individual account status
        import os
        from instagrapi import Client
        
        main_status = "❌ Not Available"
        monitor_status = "❌ Not Available"
        
        try:
            # Check main account
            if os.path.exists('main_session.json'):
                try:
                    cl = Client()
                    cl.load_settings('main_session.json')
                    cl.login_by_sessionid(cl.sessionid)
                    user_info = cl.account_info()
                    main_status = f"✅ @{user_info.username}"
                except Exception as e:
                    main_status = f"❌ {str(e)[:30]}..."
            
            # Check monitor account  
            if os.path.exists('monitor_session.json'):
                try:
                    cl = Client()
                    cl.load_settings('monitor_session.json')
                    cl.login_by_sessionid(cl.sessionid)
                    user_info = cl.account_info()
                    monitor_status = f"✅ @{user_info.username}"
                except Exception as e:
                    monitor_status = f"❌ {str(e)[:30]}..."
        except Exception as e:
            print(f"Error checking accounts: {e}")
        
        text = (f"⚙️ System Settings\n\n"
                f"📊 Posts: {len(posts)} total, {active_posts} active\n\n"
                f"🔐 Account Status:\n"
                f"Main Account: {main_status}\n"
                f"Monitor Account: {monitor_status}\n\n"
                f"Options:")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh Auth", callback_data="refresh_auth"),
             InlineKeyboardButton("🧹 Reset System", callback_data="reset_system")],
            [InlineKeyboardButton("📊 System Stats", callback_data="system_stats"),
             InlineKeyboardButton("🔙 Back", callback_data="main")]
        ])
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
        except Exception as e:
            if "Message is not modified" not in str(e):
                print(f"Error editing message: {e}")
            await query.answer()
    
    # Settings sub-handlers
    elif data == "refresh_auth":
        await query.answer("Refreshing authentication...", show_alert=True)
        # Force reload sessions
        from advanced_instagram_monitor import AdvancedInstagramMonitor
        monitor = AdvancedInstagramMonitor()
        try:
            monitor.load_sessions()
            await query.edit_message_text(
                "✅ Authentication refreshed!\n\nInstagram sessions reloaded successfully.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="settings")]])
            )
        except Exception as e:
            await query.edit_message_text(
                f"❌ Failed to refresh authentication:\n{str(e)[:100]}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="settings")]])
            )
    
    elif data == "system_stats":
        posts = pm.load_posts()
        total_replies = sum(p["stats"]["replies"] for p in posts)
        total_dms = sum(p["stats"]["dms"] for p in posts)
        
        import os
        files_info = []
        for file in ['main_session.json', 'monitor_session.json', 'enhanced_posts.json']:
            if os.path.exists(file):
                size = os.path.getsize(file)
                files_info.append(f"{file}: {size} bytes")
        
        text = (f"📊 Detailed System Statistics\n\n"
                f"📋 Posts: {len(posts)}\n"
                f"💬 Total Replies: {total_replies}\n"
                f"📩 Total DMs: {total_dms}\n\n"
                f"📁 System Files:\n" + "\n".join(files_info))
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="settings")]])
        await query.edit_message_text(text, reply_markup=keyboard)
    
    elif data == "reset_system":
        text = (f"⚠️ Reset System\n\n"
                f"This will:\n"
                f"• Stop all monitoring\n"
                f"• Clear Instagram sessions\n"
                f"• Reset authentication\n\n"
                f"Posts will be preserved.\n"
                f"Are you sure?")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="settings"),
             InlineKeyboardButton("✅ Confirm Reset", callback_data="confirm_reset")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard)
    
    elif data == "confirm_reset":
        try:
            import os
            # Remove session files
            for file in ['main_session.json', 'monitor_session.json']:
                if os.path.exists(file):
                    os.remove(file)
            
            await query.edit_message_text(
                "✅ System Reset Complete!\n\nInstagram sessions cleared.\nYou'll need to re-authenticate accounts.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main", callback_data="main")]])
            )
        except Exception as e:
            await query.edit_message_text(
                f"❌ Reset failed: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="settings")]])
            )
    
    # Login menu with dual account status for ban protection
    elif data == "login_menu":
        import json
        import os
        
        # Check both account statuses
        monitor_status = "❌ Not logged in"
        main_status = "❌ Not logged in"
        
        if os.path.exists("monitor_session.json"):
            try:
                with open("monitor_session.json", 'r') as f:
                    data = json.load(f)
                    username = data.get('authorization_data', {}).get('username', 'Unknown')
                    monitor_status = f"✅ Logged in (@{username})"
            except:
                monitor_status = "⚠️ Session corrupted"
        
        if os.path.exists("main_session.json"):
            try:
                with open("main_session.json", 'r') as f:
                    data = json.load(f)
                    username = data.get('authorization_data', {}).get('username', 'Unknown')
                    main_status = f"✅ Logged in (@{username})"
            except:
                main_status = "⚠️ Session corrupted"
        
        text = (f"🔐 Instagram Account Management\n\n"
                f"📱 Monitor Account: {monitor_status}\n"
                f"🎯 Main Account: {main_status}\n\n"
                f"Monitor account watches posts safely.\n"
                f"Main account sends DMs and replies.\n\n"
                f"Choose an action:")
        
        keyboard = []
        
        # Add login/logout options based on status
        if "❌" in monitor_status or "⚠️" in monitor_status:
            keyboard.append([InlineKeyboardButton("📱 Login Monitor", callback_data="login_monitor")])
        else:
            keyboard.append([InlineKeyboardButton("📱 Logout Monitor", callback_data="logout_monitor")])
        
        if "❌" in main_status or "⚠️" in main_status:
            keyboard.append([InlineKeyboardButton("🎯 Login Main", callback_data="login_main")])
        else:
            keyboard.append([InlineKeyboardButton("🎯 Logout Main", callback_data="logout_main")])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Main", callback_data="main")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "login_monitor":
        # Direct monitor account login
        await query.edit_message_text(
            "📱 Monitor Account Login\n\nEnter monitor account username:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="login_menu")]])
        )
        context.user_data['login_type'] = 'monitor'
        return LOGIN_USERNAME
    
    elif data == "login_main":
        # Direct main account login
        await query.edit_message_text(
            "🎯 Main Account Login\n\nEnter main account username:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="login_menu")]])
        )
        context.user_data['login_type'] = 'main'
        return LOGIN_USERNAME
    
    # Individual post stats
    elif data.startswith("stats_"):
        post_id = data.replace("stats_", "")
        post = pm.get_post(post_id)
        
        if not post:
            await query.answer("Post not found!", show_alert=True)
            return ConversationHandler.END
        
        stats = post.get('stats', {'replies': 0, 'dms': 0})
        
        text = (f"📊 Post Statistics: {post['name']}\n\n"
                f"🔗 URL: {post['url'][:40]}...\n"
                f"🔑 Keywords: {', '.join(post['keywords'])}\n"
                f"📅 Created: {post['created']}\n"
                f"📊 Status: {'✅ Active' if post.get('enabled') else '⏸️ Paused'}\n\n"
                f"📈 Performance:\n"
                f"💬 Comment Replies: {stats['replies']}\n"
                f"📩 DMs Sent: {stats['dms']}\n"
                f"🎯 Total Actions: {stats['replies'] + stats['dms']}")
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Post", callback_data=f"post_{post_id}")]])
        await query.edit_message_text(text, reply_markup=keyboard)
    
    # Logout handlers
    elif data == "logout_monitor":
        import os
        if os.path.exists("monitor_session.json"):
            os.remove("monitor_session.json")
            await query.edit_message_text(
                "📱 Monitor account logged out successfully!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Login", callback_data="login_menu")]])
            )
        else:
            await query.edit_message_text(
                "📱 Monitor account was not logged in.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Login", callback_data="login_menu")]])
            )
    
    elif data == "logout_main":
        import os
        if os.path.exists("main_session.json"):
            os.remove("main_session.json")
            await query.edit_message_text(
                "🔑 Main account logged out successfully!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Login", callback_data="login_menu")]])
            )
        else:
            await query.edit_message_text(
                "🔑 Main account was not logged in.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Login", callback_data="login_menu")]])
            )
    
    return ConversationHandler.END

# Message handlers for adding posts
async def handle_post_name(update: Update, context: CallbackContext):
    name = update.message.text.strip()
    
    if len(name) < 3:
        await update.message.reply_text("Name too short. Please enter at least 3 characters:")
        return POST_NAME
    
    context.user_data['post_name'] = name
    await update.message.reply_text(
        f"✅ Post name: '{name}'\n\n"
        f"Now send the Instagram post URL:"
    )
    return POST_URL

async def handle_post_url(update: Update, context: CallbackContext):
    url = update.message.text.strip()
    
    if "instagram.com" not in url:
        await update.message.reply_text("Please send a valid Instagram URL:")
        return POST_URL
    
    context.user_data['post_url'] = url
    await update.message.reply_text(
        "🔑 Step 3: Smart Keywords\n\n"
        "Enter keywords that trigger DMs (comma separated):\n"
        "Example: link, info, details, price\n\n"
        "💡 Advanced Features:\n"
        "• Auto-detects typos (ling → link)\n"
        "• Partial matches (hii contains hi)\n"
        "• Character swaps (pric3 → price)\n"
        "• No need for multiple variations!"
    )
    return POST_KEYWORDS

async def handle_post_keywords(update: Update, context: CallbackContext):
    keywords_text = update.message.text.strip()
    keywords = [k.strip().lower() for k in keywords_text.split(",") if k.strip()]
    
    if not keywords:
        await update.message.reply_text("Please enter at least one keyword:")
        return POST_KEYWORDS
    
    context.user_data['post_keywords'] = keywords
    await update.message.reply_text("💬 Enter the DM message to send:")
    return POST_DM

async def handle_post_dm(update: Update, context: CallbackContext):
    message = update.message.text.strip()
    
    if len(message) < 5:
        await update.message.reply_text("DM message too short. Please enter at least 5 characters:")
        return POST_DM
    
    # Create post
    post = pm.add_post(
        context.user_data['post_name'],
        context.user_data['post_url'],
        context.user_data['post_keywords'],
        message
    )
    
    text = (f"✅ Post Created!\n\n"
            f"📄 Name: {post['name']}\n"
            f"🔗 URL: {post['url'][:40]}...\n"
            f"🔑 Keywords: {', '.join(post['keywords'])}\n"
            f"💬 DM: {message[:30]}...\n\n"
            f"Post is now active and monitoring!")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Manage Posts", callback_data="view_posts"),
         InlineKeyboardButton("🏠 Main Menu", callback_data="main")]
    ])
    
    await update.message.reply_text(text, reply_markup=keyboard)
    return ConversationHandler.END

# Edit handlers
async def handle_edit(update: Update, context: CallbackContext):
    text = update.message.text.strip()
    post_id = context.user_data.get('edit_post_id')
    edit_type = context.user_data.get('edit_type')
    
    if not post_id or not edit_type:
        await update.message.reply_text("Session expired. Please try again.")
        return ConversationHandler.END
    
    success = False
    
    if edit_type == 'name' and len(text) >= 3:
        success = pm.update_post(post_id, {"name": text})
        result_text = f"✅ Name updated to: '{text}'"
    elif edit_type == 'keywords':
        keywords = [k.strip().lower() for k in text.split(",") if k.strip()]
        if keywords:
            success = pm.update_post(post_id, {"keywords": keywords})
            result_text = f"✅ Keywords updated to: {', '.join(keywords)}"
    elif edit_type == 'dm' and len(text) >= 5:
        success = pm.update_post(post_id, {"message": text})
        result_text = "✅ DM message updated!"
    
    if success:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Post", callback_data=f"post_{post_id}")]])
        await update.message.reply_text(result_text, reply_markup=keyboard)
    else:
        await update.message.reply_text("❌ Update failed. Please check your input and try again.")
    
    return ConversationHandler.END

# Instagram login handlers
async def handle_login_username(update: Update, context: CallbackContext):
    username = update.message.text.strip()
    login_type = context.user_data.get('login_type')
    
    if len(username) < 3:
        await update.message.reply_text("Username too short. Please enter a valid Instagram username:")
        return LOGIN_USERNAME
    
    context.user_data['login_username'] = username
    
    if login_type == 'monitor':
        await update.message.reply_text(f"📱 Monitor Account: @{username}\n\nThis account will check comments for keywords.\n\nEnter password:")
    else:
        await update.message.reply_text(f"🎯 Main Account: @{username}\n\nThis account will send DMs and reply to comments.\n\nEnter password:")
    
    return LOGIN_PASSWORD

async def handle_login_password(update: Update, context: CallbackContext):
    password = update.message.text.strip()
    
    # Direct login flow
    username = context.user_data.get('login_username')
    login_type = context.user_data.get('login_type')
    
    if not username or not login_type:
        await update.message.reply_text("Session expired. Please try again.")
        return ConversationHandler.END
    
    if len(password) < 6:
        await update.message.reply_text("Password too short. Please enter your Instagram password:")
        return LOGIN_PASSWORD
    
    await update.message.reply_text("🔄 Logging in to Instagram...")
    
    try:
        from instagrapi import Client
        from instagrapi.exceptions import LoginRequired, ChallengeRequired, BadPassword
        
        client = Client()
        
        # Attempt login
        try:
            client.login(username, password)
            
            # Save session
            session_file = Path(f"{login_type}_session.json")
            client.dump_settings(session_file)
            
            if login_type == 'monitor':
                role_description = "📱 Monitor Account Active\n\n🔍 Role: Check comments for keywords\n⚡ Safe monitoring mode\n\nThis account will scan posts for keywords without taking any risky actions."
            else:
                role_description = "🎯 Main Account Active\n\n💬 Role: Send DMs and reply to comments\n⚡ Action mode\n\nThis account will handle all messaging and reply actions."
            
            await update.message.reply_text(
                f"✅ Login successful!\n\nAccount: @{username}\n\n{role_description}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Login", callback_data="login_menu")]])
            )
            
        except ChallengeRequired as e:
            await update.message.reply_text(
                f"⚠️ Instagram Challenge Required\n\n"
                f"Instagram requires additional verification for @{username}.\n"
                f"Please log in through the Instagram app first, then try again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Login", callback_data="login_menu")]])
            )
            
        except BadPassword:
            await update.message.reply_text(
                f"❌ Login Failed\n\n"
                f"Incorrect password for @{username}.\n"
                f"Please check your credentials and try again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Login", callback_data="login_menu")]])
            )
            
        except Exception as e:
            error_msg = str(e)[:100]
            await update.message.reply_text(
                f"❌ Login Error\n\n"
                f"Failed to login @{username}:\n{error_msg}\n\n"
                f"Please try again or contact support.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Login", callback_data="login_menu")]])
            )
            
    except Exception as e:
        await update.message.reply_text(
            f"❌ System Error\n\n"
            f"Failed to initialize login system: {str(e)[:100]}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Login", callback_data="login_menu")]])
        )
    
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "❌ Operation cancelled.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main")]])
    )
    return ConversationHandler.END

def main():
    print("Starting Advanced Instagram Automation Bot...")
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler, pattern="^add_post$"),
            CallbackQueryHandler(button_handler, pattern="^edit_"),
            CallbackQueryHandler(button_handler, pattern="^login_"),
        ],
        states={
            POST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_post_name)],
            POST_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_post_url)],
            POST_KEYWORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_post_keywords)],
            POST_DM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_post_dm)],
            EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit)],
            EDIT_KEYWORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit)],
            EDIT_DM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit)],
            LOGIN_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_login_username)],
            LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_login_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ Advanced bot ready!")
    app.run_polling()

if __name__ == "__main__":
    main()