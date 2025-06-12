# Instagram + Telegram Automation Bot

This bot automates Instagram DMs and comments, controlled via a Telegram bot interface.

## 🔧 Features
- Monitor Instagram posts/comments
- Auto-reply via Telegram
- DM automation
- Secure config via environment variables

## 🚀 Setup & Deploy on Render (Free Hosting)
1. Upload this repo to GitHub
2. Create a **Background Worker** on [Render.com](https://render.com)
3. Set the following environment variables in Render:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_ADMIN_ID`
4. Set build and start commands:
   - Build: `pip install -r requirements.txt`
   - Start: `python main.py`
5. Done! The bot runs 24/7 for free.

## 📁 File Structure
- `.env.example`: Template for secrets
- `config.json`: Will be updated by Telegram bot
- `utils.py`: Loads credentials, manages paths

---
**Warning:** Never upload your `.env` or `config.json` with real credentials to GitHub!
