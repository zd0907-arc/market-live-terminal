import sys
import os
import logging
import json

# Add project root to path
sys.path.append(os.getcwd())

from backend.app.services.analysis import calculate_realtime_aggregation
from backend.app.db.crud import get_sentiment_history_aggregated

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_aggregation(symbol="sz000833", date="2026-02-13"):
    print(f"--- Debugging for {symbol} on {date} ---")
    
    # 1. Test Main Force Aggregation
    print("\n[1] Testing calculate_realtime_aggregation...")
    try:
        data = calculate_realtime_aggregation(symbol, date)
        chart_data = data.get('chart_data', [])
        print(f"Chart Data Points: {len(chart_data)}")
        if chart_data:
            print("First Point:", chart_data[0])
            print("Last Point:", chart_data[-1])
        else:
            print("!!! Chart Data is EMPTY !!!")
            
        cum_data = data.get('cumulative_data', [])
        print(f"Cumulative Data Points: {len(cum_data)}")
    except Exception as e:
        print(f"Error in calculate_realtime_aggregation: {e}")

    # 2. Test Sentiment History (CVD)
    print("\n[2] Testing get_sentiment_history_aggregated...")
    try:
        sent_data = get_sentiment_history_aggregated(symbol, date)
        print(f"Sentiment Data Points: {len(sent_data)}")
        if sent_data:
            print("First Point:", sent_data[0])
        else:
            print("!!! Sentiment Data is EMPTY !!!")
    except Exception as e:
        print(f"Error in get_sentiment_history_aggregated: {e}")

if __name__ == "__main__":
    debug_aggregation()