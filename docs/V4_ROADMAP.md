# V4 Roadmap: Performance, Anti-Ban & Intelligent Data Fetching

## 1. On-Demand Data Fetching (基于前端心跳的按需爬虫)
- **Status:** Planned
- **Description:** Shift from continuous background polling of the entire Watchlist to a demand-driven model.
- **Implementation:**
  - Backend maintains an `ActiveWatchers` registry (symbol -> active sessions).
  - Frontend sends heartbeat every N seconds (e.g., 5-15s) when a stock detail page is open.
  - Windows Crawler queries the active list every 10 seconds.
  - If a stock is active, it runs the high-frequency tick fetch (e.g., every 3-5 seconds).
  - If inactive, the crawler ignores it, saving 90%+ API requests.
  - At 15:05 daily, run a batch final cleanup for the entire Watchlist.

## 2. Smart Snapshotting (涟漪侦测法 - 动态频率控制)
- **Status:** Planned
- **Description:** Implement variable-frequency snapshot polling to avoid rate-limits while catching volatility.
- **Implementation:** 
  - Poll the entire market's basic volume data (lightweight API) every 10-30 seconds.
  - Calculate `Current Volume - Previous Volume`.
  - If the delta exceeds a threshold (e.g., 1000 lots), trigger an immediate Level-2 snapshot for that specific symbol.
  - For quiet stocks, reduce snapshot frequency to 1-2 minutes.

## 3. Alternative Data Sources (PC Client WebSockets)
- **Status:** Idea stage 
- **Description:** Explore memory reading, hook interception, or local proxying of official PC trading clients (e.g., THS, EastMoney, QMT) to eliminate HTTP-based rate limits entirely, treating the local client as an institution-grade data WebSocket.
