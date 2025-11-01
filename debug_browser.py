#!/usr/bin/env python3
"""
Persistent debug browser for both scraping and BrowserMCP tools.

This script launches a Playwright Chromium browser with:
- Chrome DevTools Protocol (CDP) enabled on localhost:9222
- BrowserMCP extension loaded
- Persistent context that stays running

Both the scraper (with --connect flag) and BrowserMCP tools can connect
to this same browser instance simultaneously.

Usage:
    python debug_browser.py

Then in another terminal:
    ./venv/bin/python scrape_bahn_prices.py "Origin" "Dest" --connect --output data/output.tsv
"""

import asyncio
import os
import signal
import sys
from playwright.async_api import async_playwright

# Flag to handle graceful shutdown
shutdown_flag = False

def signal_handler(_signum, _frame):
    """Handle Ctrl+C gracefully"""
    global shutdown_flag
    print("\n\nShutdown signal received. Closing browser...")
    shutdown_flag = True

async def main():
    """Launch and maintain persistent debug browser"""
    global shutdown_flag

    print("=" * 60)
    print("Debug Browser Launcher")
    print("=" * 60)
    print("Starting Chromium with CDP enabled on localhost:9222")
    print("Press Ctrl+C to stop")
    print("=" * 60)

    # Use absolute path to the extension
    extension_path = os.path.abspath("./BJFGAMBNHCCAKKHMKEPDOEKMCKOIJDLC_1_3_4_0")

    if not os.path.exists(extension_path):
        print(f"ERROR: BrowserMCP extension not found at {extension_path}")
        return 1

    print(f"\nLoading BrowserMCP extension from: {extension_path}")

    async with async_playwright() as p:
        # Launch persistent context with CDP enabled
        context = await p.chromium.launch_persistent_context(
            "",  # Empty string = temporary user data directory
            headless=False,  # Must be headed for CDP
            locale='de-DE',
            timezone_id='Europe/Berlin',
            args=[
                '--remote-debugging-port=9222',  # Enable CDP on port 9222
                '--no-first-run',
                '--no-default-browser-check',
                f'--disable-extensions-except={extension_path}',
                f'--load-extension={extension_path}'
            ]
        )

        # Create initial page
        if context.pages:
            page = context.pages[0]
        else:
            page = await context.new_page()

        # Navigate to blank page
        await page.goto("about:blank")

        print("\n" + "=" * 60)
        print("✓ Browser is running!")
        print("=" * 60)
        print("CDP endpoint: localhost:9222")
        print("BrowserMCP extension: Loaded")
        print("\nYou can now:")
        print("  1. Use BrowserMCP tools to connect to this browser")
        print("  2. Run scraper with --connect flag")
        print("  3. Manually browse to https://www.bahn.de")
        print("\nPress Ctrl+C to stop the browser")
        print("=" * 60)

        # Keep browser running until interrupted
        try:
            while not shutdown_flag:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

        print("\nClosing browser...")
        await context.close()

    print("Browser closed. Goodbye!")
    return 0

if __name__ == "__main__":
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
