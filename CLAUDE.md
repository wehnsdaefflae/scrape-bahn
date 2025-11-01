# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based train ticket optimizer that analyzes train ticket prices to determine if buying multiple segment tickets is cheaper than buying a single direct ticket for an entire journey. The project consists of two main components:

1. **Price Scraper** (`scrape_bahn_prices.py`): Automated web scraper that extracts train prices from Bahn.de
2. **Price Analyzer** (`find_cheapest_tickets.py`): Dynamic programming algorithm that finds optimal ticket combinations

## Development Commands

### Environment Setup
```bash
# Activate virtual environment
source venv/bin/activate
```

### Scraping Train Prices

**Prerequisites**: Start Chrome with remote debugging:
```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

**Basic scraping** (recommended - uses existing browser):
```bash
./venv/bin/python scrape_bahn_prices.py "Berlin Gesundbrunnen" "Bamberg" \
  --date "02.11.2025" \
  --time "05:35" \
  --connect \
  --output data/output.tsv
```

**Scraping options**:
- `--connect`: Connect to Chrome at localhost:9222 (recommended, faster, reuses browser state)
- `--headed`: Launch visible browser window (slower, creates new browser instance)
- `--headless`: Run invisible browser (default if neither --connect nor --headed specified)
- `--date DD.MM.YYYY`: Journey date in German format (default: today)
- `--time HH:MM`: Journey time (default: 10:00)

### Analyzing Prices

```bash
# Single file
./venv/bin/python find_cheapest_tickets.py data/tickets\ -\ Tabellenblatt1.tsv

# Multiple files
./venv/bin/python find_cheapest_tickets.py data/*.tsv
```

## Architecture

### Web Scraping Architecture (`scrape_bahn_prices.py`)

**Technology**: Playwright async API with Chrome DevTools Protocol (CDP) support

**Key Components**:

1. **Browser Connection** (lines 483-507):
   - CDP mode (`--connect`): Connects to existing Chrome at localhost:9222, reuses active tab
   - Persistent context mode: Launches new browser with BrowserMCP extension loaded from `BJFGAMBNHCCAKKHMKEPDOEKMCKOIJDLC_1_3_4_0/`

2. **Search Engine** (`search_connection`, lines 33-169):
   - Navigates to bahn.de, handles cookie consent
   - Fills origin/destination using role-based selectors: `role=combobox[name="Start"]`
   - Presses Enter to select first autocomplete match (no verification of which station was selected)
   - Sets date/time via dialog spinbuttons
   - Waits for connection results (up to 20s networkidle timeout)

3. **Station Extraction** (`extract_stops_from_connection`, lines 171-294):
   - Clicks Details button on first connection
   - Expands ALL intermediate stops by clicking buttons matching `"Haltestellen"`
   - Extracts train ID from `.verbindung-list__result-item--0 .verbindungsabschnitt-visualisierung__verkehrsmittel-text`
   - Uses JavaScript evaluation to parse DOM for stations and departure times:
     - `.verbindungs-halt` for origin/destination
     - `.verbindungs-zwischenhalte__zwischenhalt-container` for intermediate stops
   - Returns: stations list, departure times list, train ID (e.g., "ICE 503")

4. **Train Verification & Price Extraction** (`get_ticket_price`, lines 297-362):
   - Searches for specific segment (origin → destination)
   - **Critical**: Searches through ALL 5 connection results (`.verbindung-list__result-item--{0-4}`) to find matching train ID
   - Extracts price from matching connection using scoped selector (get connection element first, then search for price within it)
   - Returns None if train ID doesn't match (ensures all prices are from same train)

5. **Price Matrix Builder** (`create_price_matrix`, lines 365-396):
   - Queries all i→j combinations where i < j (forward direction only)
   - Uses station-specific departure times (`times[i]`) for each segment search
   - Optimized: no artificial delays between queries (removed 1000ms waits)

6. **TSV Writer** (`write_tsv_file`, lines 399-432):
   - Row 1: Date, train number, arrival times
   - Row 2: Empty, empty, station names
   - Row 3+: Time, station name, prices (German format with comma decimal separator)

**Critical Implementation Details**:
- Station selection: Autocomplete first match is selected without verification - could select wrong station if name is ambiguous
- Wait time optimizations: Details panel uses element wait instead of fixed 3500ms delay, expand buttons reduced to 200ms
- Price selector: Must use two-step approach (get connection element, then search within) due to Playwright selector limitations
- Train verification ensures price consistency across all segments

### Price Analysis Architecture (`find_cheapest_tickets.py`)

**Core Algorithm**: Dynamic Programming with path reconstruction

**Key Components**:

1. **TSV Parser** (`parse_tsv_file`, lines 12-53):
   - Extracts stations from row 2, times from row 1
   - Builds price matrix: `prices[i][j]` = cost from station i to station j
   - Handles German decimal format (comma → period conversion)
   - Treats "?", "0", and empty cells as None (unavailable)

2. **DP Algorithm** (`find_cheapest_route`, lines 56-94):
   - `dp[i]` = minimum cost to reach station i from station 0
   - `prev[i]` = previous station index in optimal path
   - For each station i, evaluates all possible previous stations j where j < i
   - Reconstructs path by backtracking through `prev` array
   - Returns: minimum cost + list of (from_station, to_station) tuples

3. **Analysis Engine** (`analyze_tickets`, lines 102-154):
   - Compares direct ticket (`prices[0][-1]`) vs. optimal segmented route
   - Calculates savings amount and percentage
   - Formats output with German price formatting
   - Shows ticket breakdown if segmentation provides savings

**Algorithm Complexity**: O(n²) where n = number of stations

## TSV File Format

Input/output format for price matrices:

```
02.11.2025	ICE 503	05:35	05:45	07:22	07:48	08:31	09:15
		Berlin Gesundbrunnen	Berlin Hbf	Bitterfeld	Leipzig Hbf	Erfurt Hbf	Bamberg
05:35	Berlin Gesundbrunnen	0	?	39,99	43,99	59,99	79,99
05:45	Berlin Hbf		0	35,99	39,99	59,99	79,99
07:22	Bitterfeld			0	17,99	39,99	67,99
07:48	Leipzig Hbf				0	33,99	59,99
08:31	Erfurt Hbf					0	55,99
09:15	Bamberg						0
```

- Tab-delimited
- Row 1: Date, train ID, arrival times for each station
- Row 2: Empty, empty, station names
- Row 3+: Departure time, station name, price matrix (diagonal = 0, below diagonal = empty)
- "?" = unavailable segment (e.g., different train required)
- Prices use comma as decimal separator (German format)

## Dependencies

- **Python 3.12+**
- **Playwright**: `pip install playwright` + `playwright install chromium`
- Standard library: `csv`, `argparse`, `asyncio`, `logging`, `re`, `datetime`

## Debugging & Logs

- Scraper logs to both console and `/tmp/scraper.log`
- Use BrowserMCP tools to inspect page structure, DOM, and UI elements
- Chrome extension directory: `BJFGAMBNHCCAKKHMKEPDOEKMCKOIJDLC_1_3_4_0/` (do not delete)

## Known Limitations

1. **Station autocomplete**: Script selects first match without verification - ambiguous station names may cause incorrect searches
2. **Train availability**: Only searches first connection for station extraction - may miss better connections
3. **Price availability**: Some segments marked "?" when train ID doesn't match across all 5 search results
4. **Single train constraint**: All segment prices must come from the same train connection (by train ID)
