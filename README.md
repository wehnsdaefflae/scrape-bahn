# Train Ticket Optimizer

This tool analyzes train ticket prices to determine if buying multiple segment tickets is cheaper than buying a single direct ticket for the entire journey.

## Setup

A Python virtual environment has been created. To activate it:

```bash
source venv/bin/activate
```

## Scraping Price Data

The `scrape_bahn_prices.py` script automatically extracts train prices from Bahn.de to generate the TSV price matrix files.

### Prerequisites

**Option 1: Using debug_browser.py (Recommended)**

Start the persistent debug browser with BrowserMCP extension:

```bash
./venv/bin/python debug_browser.py
```

This launches a Chromium instance that can be used by both:
- The scraper script (with `--connect` flag)
- BrowserMCP tools for interactive debugging

The browser stays running until you press Ctrl+C.

**Option 2: Manual Chrome with CDP**

Start Chrome with remote debugging enabled:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
```

Then navigate to https://www.bahn.de in the browser

### Basic Usage

```bash
./venv/bin/python scrape_bahn_prices.py "ORIGIN" "DESTINATION" \
  --date "DD.MM.YYYY" \
  --time "HH:MM" \
  --connect \
  --output data/output.tsv
```

### Options

- `--date`: Journey date in German format (DD.MM.YYYY), defaults to today
- `--time`: Journey time (HH:MM), defaults to 10:00
- `--connect`: Connect to existing Chrome browser at localhost:9222 (recommended)
- `--headed`: Launch a visible browser window (slower, not recommended)
- `--output`: Output TSV file path (required)

### Examples

Simple query with existing browser:
```bash
./venv/bin/python scrape_bahn_prices.py "Berlin Gesundbrunnen" "Bamberg" \
  --date "02.11.2025" \
  --time "05:35" \
  --connect \
  --output data/berlin_bamberg.tsv
```

With default date/time:
```bash
./venv/bin/python scrape_bahn_prices.py "München" "Hamburg" \
  --connect \
  --output data/muenchen_hamburg.tsv
```

### How the Scraper Works

1. **Connects to browser**: Uses Chrome DevTools Protocol to connect to existing browser
2. **Searches main route**: Enters origin, destination, date, and time
3. **Extracts all stops**: Expands the Details panel and intermediate stops to get all stations on the route
4. **Identifies train**: Extracts the train number (e.g., "ICE 503")
5. **Builds price matrix**: For each station pair, searches for that specific segment and verifies it uses the same train
6. **Outputs TSV**: Generates a price matrix file with all segment prices

### Train Verification

The scraper ensures all segment prices come from the same train connection by:
- Extracting the train ID from the main connection (e.g., "ICE 503")
- Using departure times from the Details panel for each segment search
- Searching through all 5 connection results to find the matching train ID
- Skipping segments that don't match the train (marked as "?" in the output)

This ensures price consistency - all segment prices are from the same actual train journey.

## All-in-One Script

The `scrape_and_analyze.sh` script combines scraping and analysis into a single command:

```bash
./scrape_and_analyze.sh "Origin" "Destination" --date "DD.MM.YYYY" --time "HH:MM" [--connect|--headed]
```

### Example

```bash
# With debug_browser.py running
./scrape_and_analyze.sh "Hamburg" "München" --date "25.11.2025" --time "10:00" --connect

# Without persistent browser
./scrape_and_analyze.sh "Hamburg" "München" --date "25.11.2025" --time "10:00" --headed
```

This script:
1. Scrapes prices from Bahn.de
2. Saves the TSV file to `data/` directory (auto-named or custom via `--output`)
3. Analyzes the prices and shows the cheapest route
4. Handles errors gracefully

## Analyzing Price Data

Run the script with one or more TSV files:

```bash
./venv/bin/python find_cheapest_tickets.py data/*.tsv
```

Or with the virtual environment activated:

```bash
python find_cheapest_tickets.py data/*.tsv
```

## Results

For the provided data files:

### Route 1: Berlin Gesundbrunnen → Bamberg (28.11.2025, ICE 705)
- Direct ticket: 56,29 EUR
- Cheapest combination: 56,29 EUR
- **Result**: No savings - buy the direct ticket

### Route 2: Bamberg → Berlin Gesundbrunnen (01.12.2025, ICE 704)
- Direct ticket: 26,29 EUR
- Cheapest combination: 26,29 EUR
- **Result**: No savings - buy the direct ticket

## How It Works

The script uses dynamic programming to find the optimal combination of tickets:

1. Parses the TSV file to extract station names and prices
2. Builds a price matrix where `prices[i][j]` = cost from station i to station j
3. Uses dynamic programming to compute the minimum cost path from start to end
4. Compares the result with the direct ticket price
5. Shows potential savings and the specific tickets to purchase

## TSV File Format

The expected format is:
- Row 1: Date, train number, and arrival times
- Row 2: Station names
- Row 3+: Price matrix (rows = departure stations, columns = arrival stations)

Prices should use comma as decimal separator (German format).
Use "?" for unavailable tickets.
