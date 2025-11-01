#!/usr/bin/env python3
"""
Script to find the cheapest combination of train tickets for a journey.
Compares buying a single direct ticket vs. buying multiple segment tickets.
"""

import csv
import sys
from typing import List, Tuple, Optional


def parse_tsv_file(filepath: str) -> Tuple[List[str], List[str], List[List[Optional[float]]]]:
    """
    Parse a TSV file containing train ticket prices.

    Returns:
        - stations: List of station names
        - times: List of arrival times at each station
        - prices: 2D matrix where prices[i][j] = price from station i to station j
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        rows = list(reader)

    # Extract times from first row (skip first 2 columns which contain metadata)
    times = [cell.strip() for cell in rows[0][2:] if cell.strip()]

    # Extract station names from second row (skip first 2 columns)
    stations = [cell.strip() for cell in rows[1][2:] if cell.strip()]

    # Build price matrix
    n = len(stations)
    prices = [[None for _ in range(n)] for _ in range(n)]

    # Parse price rows (starting from row 2, which is index 2)
    for i in range(n):
        if i + 2 < len(rows):
            row = rows[i + 2]
            # Skip first 2 columns (time and station name)
            # Then skip i columns (the diagonal and stations before)
            for j in range(i, n):
                col_idx = 2 + j
                if col_idx < len(row):
                    price_str = row[col_idx].strip()
                    if price_str and price_str != '?' and price_str != '0':
                        try:
                            # Handle German decimal format (comma as decimal separator)
                            price_str = price_str.replace(',', '.')
                            prices[i][j] = float(price_str)
                        except ValueError:
                            prices[i][j] = None

    return stations, times, prices


def find_cheapest_route(stations: List[str], prices: List[List[Optional[float]]]) -> Tuple[float, List[Tuple[int, int]]]:
    """
    Find the cheapest combination of tickets from first to last station.

    Uses dynamic programming to find the minimum cost path.

    Returns:
        - min_cost: The minimum cost to travel from first to last station
        - path: List of (from_index, to_index) tuples representing the tickets to buy
    """
    n = len(stations)

    # dp[i] = (min_cost_to_reach_i, previous_station_index)
    dp = [float('inf')] * n
    dp[0] = 0
    prev = [-1] * n

    # Dynamic programming: for each station, try all possible previous stations
    for i in range(1, n):
        for j in range(i):
            if prices[j][i] is not None and dp[j] != float('inf'):
                cost = dp[j] + prices[j][i]
                if cost < dp[i]:
                    dp[i] = cost
                    prev[i] = j

    # Reconstruct the path
    if dp[n-1] == float('inf'):
        return float('inf'), []

    path = []
    current = n - 1
    while prev[current] != -1:
        path.append((prev[current], current))
        current = prev[current]

    path.reverse()

    return dp[n-1], path


def format_price(price: float) -> str:
    """Format price with German decimal separator."""
    return f"{price:.2f}".replace('.', ',')


def analyze_tickets(filepath: str):
    """Analyze a ticket file and print results."""
    print(f"\n{'='*80}")
    print(f"Analyzing: {filepath}")
    print(f"{'='*80}\n")

    stations, times, prices = parse_tsv_file(filepath)

    print(f"Route: {stations[0]} → {stations[-1]}")
    print(f"Number of stations: {len(stations)}")
    print(f"\nStations: {' → '.join(stations)}\n")

    # Get direct ticket price
    direct_price = prices[0][-1]

    if direct_price is None:
        print("⚠️  No direct ticket available from start to end!")
        direct_price = float('inf')
    else:
        print(f"Direct ticket price: {format_price(direct_price)} EUR")

    # Find cheapest combination
    min_cost, path = find_cheapest_route(stations, prices)

    if min_cost == float('inf'):
        print("\n❌ No valid route found!")
        return

    print(f"Cheapest combination: {format_price(min_cost)} EUR")

    # Calculate savings
    if direct_price != float('inf'):
        savings = direct_price - min_cost
        savings_percent = (savings / direct_price) * 100

        print(f"\n{'='*80}")
        if savings > 0.01:  # Account for floating point precision
            print(f"💰 SAVINGS: {format_price(savings)} EUR ({savings_percent:.1f}%)")
        elif savings < -0.01:
            print(f"⚠️  Warning: Combination is more expensive by {format_price(-savings)} EUR")
        else:
            print(f"ℹ️  Same price as direct ticket")
        print(f"{'='*80}\n")

    # Show ticket breakdown
    if len(path) > 1 or (len(path) == 1 and path[0][0] != 0 or path[0][1] != len(stations) - 1):
        print("Tickets to buy:")
        for i, (from_idx, to_idx) in enumerate(path, 1):
            price = prices[from_idx][to_idx]
            print(f"  {i}. {stations[from_idx]} → {stations[to_idx]}: {format_price(price)} EUR")
    else:
        print("Buy a single direct ticket (no savings from splitting)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python find_cheapest_tickets.py <tsv_file> [<tsv_file2> ...]")
        print("\nExample: python find_cheapest_tickets.py data/*.tsv")
        sys.exit(1)

    for filepath in sys.argv[1:]:
        try:
            analyze_tickets(filepath)
        except Exception as e:
            print(f"\n❌ Error processing {filepath}: {e}")
            import traceback
            traceback.print_exc()

    print()


if __name__ == "__main__":
    main()
