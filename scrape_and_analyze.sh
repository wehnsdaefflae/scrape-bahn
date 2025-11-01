#!/bin/bash
# scrape_and_analyze.sh
# Automated script to scrape train prices and analyze for cheapest route
# Usage: ./scrape_and_analyze.sh "Origin" "Destination" --date "DD.MM.YYYY" --time "HH:MM" [--connect|--headed]

set -e  # Exit on error

# Parse command line arguments
ORIGIN=""
DESTINATION=""
DATE=""
TIME=""
BROWSER_MODE="--connect"
OUTPUT_FILE=""

# Get first two positional arguments
if [ -n "$1" ]; then
    ORIGIN="$1"
    shift
fi

if [ -n "$1" ]; then
    DESTINATION="$1"
    shift
fi

# Parse remaining arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --date)
            DATE="$2"
            shift 2
            ;;
        --time)
            TIME="$2"
            shift 2
            ;;
        --connect|--headed|--headless)
            BROWSER_MODE="$1"
            shift
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$ORIGIN" ] || [ -z "$DESTINATION" ]; then
    echo "Usage: $0 \"Origin\" \"Destination\" --date \"DD.MM.YYYY\" --time \"HH:MM\" [--connect|--headed]"
    echo ""
    echo "Example:"
    echo "  $0 \"Hamburg\" \"München\" --date \"25.11.2025\" --time \"10:00\" --connect"
    exit 1
fi

# Generate output filename if not provided
if [ -z "$OUTPUT_FILE" ]; then
    SAFE_ORIGIN=$(echo "$ORIGIN" | tr ' ' '_' | tr -cd '[:alnum:]_-')
    SAFE_DEST=$(echo "$DESTINATION" | tr ' ' '_' | tr -cd '[:alnum:]_-')
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    OUTPUT_FILE="data/${SAFE_ORIGIN}_to_${SAFE_DEST}_${TIMESTAMP}.tsv"
fi

# Ensure data directory exists
mkdir -p data

echo "=========================================="
echo "Train Ticket Price Scraper & Analyzer"
echo "=========================================="
echo "Origin:      $ORIGIN"
echo "Destination: $DESTINATION"
echo "Date:        ${DATE:-today}"
echo "Time:        ${TIME:-10:00}"
echo "Browser:     $BROWSER_MODE"
echo "Output:      $OUTPUT_FILE"
echo ""

# Build scraper command
SCRAPER_CMD="./venv/bin/python scrape_bahn_prices.py \"$ORIGIN\" \"$DESTINATION\""

if [ -n "$DATE" ]; then
    SCRAPER_CMD="$SCRAPER_CMD --date \"$DATE\""
fi

if [ -n "$TIME" ]; then
    SCRAPER_CMD="$SCRAPER_CMD --time \"$TIME\""
fi

SCRAPER_CMD="$SCRAPER_CMD $BROWSER_MODE --output \"$OUTPUT_FILE\""

# Run scraper
echo "Step 1: Scraping prices..."
echo "Running: $SCRAPER_CMD"
echo ""

eval $SCRAPER_CMD

# Check if scraper succeeded
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Price scraping failed!"
    exit 1
fi

# Check if output file was created
if [ ! -f "$OUTPUT_FILE" ]; then
    echo ""
    echo "ERROR: Output file not created: $OUTPUT_FILE"
    exit 1
fi

echo ""
echo "Step 2: Analyzing prices..."
echo "Running: ./venv/bin/python find_cheapest_tickets.py \"$OUTPUT_FILE\""
echo ""

# Run analyzer
./venv/bin/python find_cheapest_tickets.py "$OUTPUT_FILE"

# Check if analyzer succeeded
if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Price analysis failed!"
    exit 1
fi

echo ""
echo "=========================================="
echo "Complete! Data saved to: $OUTPUT_FILE"
echo "=========================================="
