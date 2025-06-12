import os
import sys
import time
import asyncio
from threading import Thread

def main():
    print("Starting Enhanced Instagram Automation System...")
    
    # Import and start advanced Instagram monitoring in background thread
    try:
        from advanced_instagram_monitor import start as start_instagram
        instagram_thread = Thread(target=start_instagram, daemon=True)
        instagram_thread.start()
        print("Advanced Instagram automation system started")
    except Exception as e:
        print(f"Failed to start Instagram automation: {e}")
    
    # Run advanced Telegram bot in main thread
    try:
        from advanced_telegram_bot import main as start_telegram
        print("Starting Advanced Telegram control interface...")
        start_telegram()
    except Exception as e:
        print(f"Failed to start Telegram bot: {e}")

if __name__ == "__main__":
    main()
