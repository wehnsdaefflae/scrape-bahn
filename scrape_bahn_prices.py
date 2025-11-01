#!/usr/bin/env python3
"""
Script to scrape train ticket prices from bahn.de using Playwright.
Creates a TSV file with a price matrix for all station segments on a route.
"""

import argparse
import asyncio
import csv
import logging
import os
import re
import sys
from datetime import datetime
from typing import List, Tuple, Optional

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout

# Setup logging to file
logging.basicConfig(
    filename='/tmp/scraper.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def log(msg):
    """Log to both file and console"""
    logging.info(msg)
    print(msg, flush=True)


async def search_connection(page: Page, origin: str, destination: str, departure_time: str, departure_date: str = None, first_search: bool = False) -> bool:
    """Search for a train connection on bahn.de using the search form."""
    log(f"\nSearching for connection: {origin} → {destination}")

    # Handle cookie dialog and navigate to bahn.de on first search
    if first_search:
        log("  First search - handling cookies...")
        await page.goto("https://www.bahn.de", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        try:
            cookie_button = page.locator('button:has-text("Alle Cookies zulassen")').or_(
                page.locator('button:has-text("Nur erforderliche Cookies zulassen")')
            )
            if await cookie_button.count() > 0:
                log("  Accepting cookies...")
                await cookie_button.first.click()
                await page.wait_for_timeout(1000)
        except Exception as e:
            pass
    else:
        # For subsequent searches, just go to homepage
        await page.goto("https://www.bahn.de", wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)

    # Wait for search form
    await page.wait_for_selector('role=combobox[name="Start"]', timeout=10000)

    # Fill in origin
    log(f"  Filling origin field: {origin}")
    origin_field = page.get_by_role('combobox', name='Start')
    await origin_field.click()
    await origin_field.fill(origin)
    await page.wait_for_timeout(1000)

    # Press Enter to select suggestion
    log("  Pressing Enter to select origin...")
    await origin_field.press('Enter')
    await page.wait_for_timeout(500)

    # Fill in destination
    log(f"  Filling destination field: {destination}")
    dest_field = page.get_by_role('combobox', name='Ziel')
    await dest_field.click()
    await dest_field.fill(destination)
    await page.wait_for_timeout(1000)

    # Press Enter to select suggestion
    log("  Pressing Enter to select destination...")
    await dest_field.press('Enter')
    await page.wait_for_timeout(1000)

    # Set date and time if provided
    if departure_date or departure_time:
        log(f"  Setting date/time: {departure_date} {departure_time}")
        try:
            # Wait for search form to be fully ready
            await page.wait_for_selector('button:has-text("Suchen")', state='visible', timeout=10000)

            # Click the date/time button to open the dialog
            # The button text is like "Heute, ab 20:53 Hinfahrt ändern"
            datetime_btn = page.locator('button:has-text("Hinfahrt ändern")').first
            log("  Clicking date/time button...")
            await datetime_btn.click(timeout=10000)
            await page.wait_for_timeout(1000)

            # Wait for the dialog to open
            await page.wait_for_selector('dialog', state='visible', timeout=5000)

            # Set the date if provided (format: DD.MM.YYYY)
            if departure_date:
                day, month, year = departure_date.split('.')

                # Fill day spinbutton
                day_spinbutton = page.get_by_role('spinbutton', name='Tag')
                await day_spinbutton.fill(day)

                # Fill month spinbutton
                month_spinbutton = page.get_by_role('spinbutton', name='Monat')
                await month_spinbutton.fill(month)

                # Fill year spinbutton
                year_spinbutton = page.get_by_role('spinbutton', name='Jahr')
                await year_spinbutton.fill(year)

            # Set the time if provided (format: HH:MM)
            if departure_time:
                hours, minutes = departure_time.split(':')

                # Fill hours spinbutton
                hours_spinbutton = page.get_by_role('spinbutton', name='Stunden')
                await hours_spinbutton.fill(hours)

                # Fill minutes spinbutton
                minutes_spinbutton = page.get_by_role('spinbutton', name='Minuten')
                await minutes_spinbutton.fill(minutes)

            # Click the "Übernehmen" (Apply) button to close the dialog
            apply_btn = page.locator('button:has-text("Übernehmen")').first
            await apply_btn.click()

            # Wait for the dialog to close
            await page.wait_for_selector('dialog', state='hidden', timeout=5000)
            await page.wait_for_timeout(500)

            log(f"  Date/time set successfully")
        except Exception as e:
            log(f"  Warning: Could not set date/time: {e}")

    # Click search button
    search_btn = page.get_by_role('button', name='Suchen').first
    await search_btn.click()

    # Wait for results to load
    try:
        await page.wait_for_load_state('networkidle', timeout=20000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        # If networkidle times out, that's okay - results might already be there
        log(f"  Note: networkidle timeout (this is expected when reusing browser): {e}")
        await page.wait_for_timeout(2000)

    # Check for Details buttons (even if networkidle failed)
    try:
        connections = page.get_by_role('button', name=re.compile(r'Details|öffne Details', re.IGNORECASE))
        count = await connections.count()

        if count > 0:
            log(f"  Found {count} connections")
            return True
        else:
            log(f"  No connections found")
            return False
    except Exception as e:
        log(f"  Error checking for connections: {e}")
        return False


async def extract_stops_from_connection(page: Page) -> Tuple[List[str], List[str], List[str]]:
    """Extract intermediate stops from the first suitable connection.

    Returns:
        Tuple of (stations, times, train_ids) where train_ids[i] is the train ID for station i
    """
    log("Extracting stops from connection details...")

    # Find the first connection with a reasonable duration (prefer direct or few transfers)
    connections = page.locator('article').or_(page.locator('listitem')).filter(has=page.locator('heading[level="2"]'))

    # Click details on the first connection
    log("  Clicking Details button...")
    details_btn = page.get_by_role('button', name=re.compile(r'Details', re.IGNORECASE)).first
    await details_btn.wait_for(state='visible', timeout=5000)

    # Check if panel is already open
    is_expanded = await details_btn.get_attribute('aria-expanded')
    log(f"  Details panel state before click: {is_expanded}")

    # Only click if not already expanded
    if is_expanded != 'true':
        await details_btn.scroll_into_view_if_needed()
        await page.wait_for_timeout(200)
        await details_btn.click()
        # Wait for details content to appear instead of fixed 3000ms wait
        await page.wait_for_selector('.verbindungs-halt', timeout=5000)

    # Verify Details panel is open by checking aria-expanded
    is_expanded_after = await details_btn.get_attribute('aria-expanded')
    log(f"  Details panel opened: {is_expanded_after == 'true'}")

    # Try to expand ALL intermediate stops if there are buttons like "4 Haltestellen"
    # There may be multiple buttons if the connection has transfers
    try:
        expand_stops_btns = page.locator('button:has-text("Haltestellen")')
        btn_count = await expand_stops_btns.count()
        log(f"  Found {btn_count} expand buttons for intermediate stops")
        if btn_count > 0:
            # Click all expand buttons to show all intermediate stops
            for i in range(btn_count):
                try:
                    btn = expand_stops_btns.nth(i)
                    btn_text = await btn.text_content()
                    log(f"  Clicking expand button: {btn_text}")
                    await btn.click()
                    await page.wait_for_timeout(200)
                except Exception as e:
                    log(f"  Could not click expand button {i}: {e}")
    except Exception as e:
        log(f"  Could not expand stops: {e}")

    # Extract train number and date
    train_number = "Unknown"
    date_str = "Unknown"

    try:
        # Try to find train number (e.g., "ICE 503") in the first connection
        # Train numbers appear in spans with class verbindungsabschnitt-visualisierung__verkehrsmittel-text
        train_elem = page.locator('.verbindung-list__result-item--0 .verbindungsabschnitt-visualisierung__verkehrsmittel-text').first
        if await train_elem.count() > 0:
            train_text = await train_elem.text_content()
            train_number = train_text.strip()
            log(f"  Extracted train number: {train_number}")
    except Exception as e:
        log(f"  Could not extract train number: {e}")

    try:
        # Extract date
        date_elem = page.locator('text:text-matches("\\w+\\.\\s+\\d+\\.\\s+\\w+\\.\\s+\\d+")').first
        if await date_elem.count() > 0:
            date_text = await date_elem.text_content()
            date_str = date_text.strip()
    except:
        pass

    # Extract all stations, times, and per-segment train IDs using JavaScript
    log("  Extracting stations, times, and train IDs per segment...")

    segments_data = await page.evaluate('''() => {
        const segments = [];

        // Find all train segments (.verbindungs-abschnitt)
        const abschnitte = document.querySelectorAll('.verbindungs-abschnitt');

        abschnitte.forEach((abschnitt, segmentIndex) => {
            const segment = {
                trainId: null,
                stations: [],
                times: []
            };

            // Get train ID for this segment from ri-transport-chip element
            const trainChip = abschnitt.querySelector('ri-transport-chip');
            if (trainChip) {
                segment.trainId = trainChip.getAttribute('transport-text');
            }

            // Get all halts in this segment
            const halts = abschnitt.querySelectorAll('.verbindungs-halt');

            // Origin (first halt)
            if (halts.length > 0) {
                const originLink = halts[0].querySelector('a[href*="bahnhof.de"]');
                const originTime = halts[0].querySelector('time');
                if (originLink && originTime) {
                    segment.stations.push(originLink.textContent.trim());
                    segment.times.push(originTime.textContent.trim());
                }
            }

            // Intermediate stops in this segment
            const zwischenhalte = abschnitt.querySelectorAll('.verbindungs-zwischenhalte__zwischenhalt-container');
            zwischenhalte.forEach(container => {
                const name = container.querySelector('.verbindungs-zwischenhalt__name')?.textContent.trim();
                const departureTime = container.querySelector('.verbindungs-zwischenhalt__abfahrts-zeit time')?.textContent.trim();

                if (name && departureTime) {
                    segment.stations.push(name);
                    segment.times.push(departureTime);
                }
            });

            // Destination (last halt) - only add if it's different from last added station
            if (halts.length > 1) {
                const destLink = halts[halts.length - 1].querySelector('a[href*="bahnhof.de"]');
                const destTime = halts[halts.length - 1].querySelector('time');
                if (destLink && destTime) {
                    const destStation = destLink.textContent.trim();
                    const destTimeStr = destTime.textContent.trim();
                    // Add destination
                    segment.stations.push(destStation);
                    segment.times.push(destTimeStr);
                }
            }

            if (segment.stations.length > 0) {
                segments.push(segment);
            }
        });

        return segments;
    }''')

    # Flatten segments into single lists with train ID mapping
    stations = []
    times = []
    train_ids = []

    for segment in segments_data:
        train_id = segment['trainId'] or train_number
        segment_stations = segment['stations']
        segment_times = segment['times']

        for i, (station, time) in enumerate(zip(segment_stations, segment_times)):
            # Skip if this is the first station of a non-first segment and it's the same as the last added station
            # (destination of previous segment = origin of current segment)
            if stations and station == stations[-1]:
                continue

            stations.append(station)
            times.append(time)
            train_ids.append(train_id)

    log(f"  Found {len(stations)} stations across {len(segments_data)} train segment(s)")
    log(f"  Stations: {stations}")
    log(f"  Train IDs per station: {train_ids}")

    return stations, times, train_ids


async def get_ticket_price(page: Page, origin: str, destination: str, departure_time: str, departure_date: str = None, expected_train_id: str = None) -> Optional[float]:
    """Get the ticket price for a specific route segment.

    Args:
        page: Playwright page object
        origin: Starting station
        destination: Ending station
        departure_time: Departure time (HH:MM format)
        departure_date: Departure date (DD.MM.YYYY format)
        expected_train_id: Expected train ID (e.g., "ICE 503") to verify we get the same connection

    Returns:
        Price in EUR if found and train ID matches, None otherwise
    """
    log(f"  Getting price: {origin} → {destination}")

    if not await search_connection(page, origin, destination, departure_time, departure_date, first_search=False):
        return None

    # If expected_train_id is provided, search through all connections to find the matching train
    connection_index = 0
    if expected_train_id and expected_train_id != "Unknown":
        try:
            # Search through all 5 connection results to find the one with matching train ID
            found_match = False
            for i in range(5):
                train_elem = page.locator(f'.verbindung-list__result-item--{i} .verbindungsabschnitt-visualisierung__verkehrsmittel-text').first
                if await train_elem.count() > 0:
                    actual_train_id = await train_elem.text_content()
                    actual_train_id = actual_train_id.strip()

                    if actual_train_id == expected_train_id:
                        log(f"    Train ID verified: {actual_train_id} (connection #{i+1})")
                        connection_index = i
                        found_match = True
                        break
                    elif i == 0:
                        log(f"    First connection has {actual_train_id}, searching for {expected_train_id}...")

            if not found_match:
                log(f"    Train ID not found in any of the 5 connections! Expected: {expected_train_id}")
                log(f"    Skipping - could not find matching connection")
                return None
        except Exception as e:
            log(f"    Error verifying train ID: {e}")
            return None

    # Extract price from the matching connection
    try:
        # First get the connection element, then search for price within it
        connection_elem = page.locator(f'.verbindung-list__result-item--{connection_index}').first
        if await connection_elem.count() > 0:
            # Look for price in format "ab XX,XX €" or just "XX,XX €"
            price_element = connection_elem.locator('text=/\\d+,\\d+\\s*€/').first
            if await price_element.count() > 0:
                price_text = await price_element.text_content()
                # Extract numeric value (format: "ab 79,99 €" or "79,99 €")
                match = re.search(r'(\d+),(\d+)', price_text)
                if match:
                    price = float(f"{match.group(1)}.{match.group(2)}")
                    log(f"    Found price: {price} EUR")
                    return price
    except Exception as e:
        log(f"    Error extracting price: {e}")

    return None


async def create_price_matrix(page: Page, stations: List[str], times: List[str],
                               departure_time: str, departure_date: str = None, train_ids: List[str] = None) -> List[List[Optional[float]]]:
    """Create a price matrix for all station pairs.

    Args:
        page: Playwright page object
        stations: List of station names in order
        times: List of departure times for each station
        departure_time: Initial departure time
        departure_date: Departure date (DD.MM.YYYY format)
        train_ids: List of train IDs per station (train_ids[i] = train ID for station i)

    Returns:
        Price matrix where prices[i][j] is the price from station i to station j
    """
    n = len(stations)
    prices = [[None for _ in range(n)] for _ in range(n)]

    # Calculate total number of combinations to query
    total_combinations = n * (n - 1) // 2
    current_combination = 0

    log(f"\nCreating price matrix for {n} stations...")
    log(f"  Total segment combinations to query: {total_combinations}")
    if train_ids:
        unique_trains = set(train_ids)
        log(f"  Connection uses {len(unique_trains)} train(s): {', '.join(sorted(unique_trains))}")

    # Get prices for all combinations where i < j (only forward direction)
    for i in range(n):
        for j in range(i + 1, n):
            current_combination += 1
            # Use the departure time of the origin station (station i)
            segment_departure_time = times[i]
            # Use the train ID of the departure station (station i)
            segment_train_id = train_ids[i] if train_ids else None
            log(f"\n  [{current_combination}/{total_combinations}] Querying: {stations[i]} → {stations[j]} (dep. {segment_departure_time}, train: {segment_train_id})")
            price = await get_ticket_price(page, stations[i], stations[j], segment_departure_time, departure_date, segment_train_id)
            if price is not None:
                log(f"    ✓ Price: €{price:.2f}")
            else:
                log(f"    ✗ Price not available (train ID mismatch or not found)")
            prices[i][j] = price
            # No extra wait needed - search_connection already waits for page load

    log(f"\n✓ Price matrix complete: {current_combination} segments queried")
    return prices


def write_tsv_file(filename: str, date: str, train: str, stations: List[str],
                   times: List[str], prices: List[List[Optional[float]]]):
    """Write the price matrix to a TSV file in the expected format."""
    log(f"\nWriting TSV file: {filename}")

    with open(filename, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')

        # Row 1: Date, train number, and arrival times
        row1 = [date, train] + times
        writer.writerow(row1)

        # Row 2: Empty, empty, and station names
        row2 = ['', ''] + stations
        writer.writerow(row2)

        # Rows 3+: Departure time, station name, and prices
        for i in range(len(stations)):
            row = [times[i], stations[i]]
            # Add empty cells for stations before i
            row.extend([''] * i)
            # Add prices for stations after i
            for j in range(i, len(stations)):
                if i == j:
                    row.append('0')
                elif prices[i][j] is not None:
                    # Format with comma as decimal separator (German format)
                    price_str = f"{prices[i][j]:.2f}".replace('.', ',')
                    row.append(price_str)
                else:
                    row.append('?')
            writer.writerow(row)

    log(f"TSV file written successfully!")


async def main():
    parser = argparse.ArgumentParser(
        description='Scrape train ticket prices from bahn.de'
    )
    parser.add_argument('origin', help='Start station (e.g., "Berlin Gesundbrunnen")')
    parser.add_argument('destination', help='Destination station (e.g., "Bamberg")')
    parser.add_argument('--date', '-d',
                        help='Departure date in DD.MM.YYYY format (default: today)')
    parser.add_argument('--time', '-t', default='10:00',
                        help='Departure time in HH:MM format (default: 10:00)')
    parser.add_argument('--output', '-o',
                        help='Output TSV filename (default: auto-generated)')
    parser.add_argument('--headless', action='store_true', default=False,
                        help='Run browser in headless mode (invisible)')
    parser.add_argument('--headed', action='store_true',
                        help='Run browser in headed mode (visible browser window, default)')
    parser.add_argument('--connect', action='store_true',
                        help='Connect to existing browser at localhost:9222 (use debug_browser.py or Chrome with --remote-debugging-port=9222)')

    args = parser.parse_args()

    log(f"\n=== Bahn.de Price Scraper ===")
    log(f"Origin: {args.origin}")
    log(f"Destination: {args.destination}")

    # Determine headless mode
    headless = args.headless and not args.headed

    # Set date to today if not provided
    if args.date:
        search_date = args.date
    else:
        search_date = datetime.now().strftime("%d.%m.%Y")

    log(f"Date: {search_date}")
    log(f"Time: {args.time}")

    # Generate output filename if not provided
    if args.output:
        output_file = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_origin = re.sub(r'[^\w\-]', '_', args.origin)
        safe_dest = re.sub(r'[^\w\-]', '_', args.destination)
        output_file = f"data/{safe_origin}_to_{safe_dest}_{timestamp}.tsv"

    log(f"Output file: {output_file}")

    async with async_playwright() as p:
        if args.connect:
            # Connect to existing browser at localhost:9222
            log(f"\nConnecting to existing browser at localhost:9222...")
            try:
                browser = await p.chromium.connect_over_cdp("http://localhost:9222")
                contexts = browser.contexts
                if contexts:
                    context = contexts[0]
                else:
                    log("Error: No browser context found in existing browser")
                    return 1

                # Use the last (most recently active) page
                pages = context.pages
                if pages:
                    page = pages[-1]  # Use last page (most recently active)
                    log(f"✓ Connected to existing browser! Using active tab.")
                else:
                    page = await context.new_page()
                    log(f"✓ Connected to existing browser! Created new tab.")
            except Exception as e:
                log(f"Error connecting to browser: {e}")
                log("Make sure debug_browser.py is running or Chrome is started with --remote-debugging-port=9222")
                return 1
        else:
            # Launch new browser
            log(f"\nStarting browser (headless={headless})...")

            # Use absolute path to the extension
            extension_path = os.path.expanduser("./BJFGAMBNHCCAKKHMKEPDOEKMCKOIJDLC_1_3_4_0")

            # Use persistent context to support BrowserMCP extension
            context = await p.chromium.launch_persistent_context(
                "",  # Empty string = temporary user data directory
                headless=headless,
                locale='de-DE',
                timezone_id='Europe/Berlin',
                args=[
                    '--no-first-run',
                    '--no-default-browser-check',
                    f'--disable-extensions-except={extension_path}',
                    f'--load-extension={extension_path}'
                ]
            )

            # Get existing page or create new one
            pages = context.pages
            if pages:
                page = pages[0]
            else:
                page = await context.new_page()

        try:
            # Step 1: Search for the main route to get all stations
            if not await search_connection(page, args.origin, args.destination, args.time, search_date, first_search=True):
                log("Failed to find initial connection")
                return 1

            # Step 2: Extract all intermediate stops
            stations, times, train_ids = await extract_stops_from_connection(page)

            if len(stations) < 2:
                log("Error: Could not extract enough stations from the connection")
                return 1

            # For TSV header: use first train if single-train, or "Multiple" for multi-train connections
            unique_trains = list(set(train_ids))
            if len(unique_trains) == 1:
                train_display = unique_trains[0]
            else:
                train_display = f"Multiple ({', '.join(sorted(unique_trains))})"

            # Step 3: Get prices for all segment combinations
            prices = await create_price_matrix(page, stations, times, args.time, search_date, train_ids)

            # Step 4: Write to TSV file
            write_tsv_file(output_file, search_date, train_display, stations, times, prices)

            log(f"\n✓ Successfully created price matrix!")
            log(f"✓ Output file: {output_file}")

        finally:
            # Only close context if we launched a new browser
            if not args.connect:
                await context.close()

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        log("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        log(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
