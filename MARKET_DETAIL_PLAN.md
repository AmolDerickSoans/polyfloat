# Market Detail Display - Comprehensive Implementation Plan

## Date: 2025-12-28

---

## Problem Analysis

### Current Issues
1. ✅ **Orderbook** - Implementation exists but may not be displaying correctly
2. ❌ **Market Details** - Limited metadata shown (only ticker, status, volume, liquidity)
3. ❌ **Charts/Graphs** - Not implemented for market selection (ChartManager exists but not integrated)
4. ❌ **Price History** - No historical price data fetching
5. ❌ **Trade Tape** - TimeAndSales widget exists but not visible in current layout

### Root Causes
1. `setup_market()` has stub implementations with comments like "Logic would go here"
2. No candlestick/price history API calls implemented in providers
3. ChartManager exists but not triggered on market selection
4. OrderBook display logic works, but may have issues with data flow
5. Market metadata is too basic - missing many rich fields available from APIs

---

## Available Data Analysis

### Polymarket API Data Available

#### Market Metadata (Already Captured)
```json
{
  "id": "572469",
  "question": "Will Trump nominate Kevin Warsh as the next Fed chair?",
  "conditionId": "0x...",
  "slug": "will-trump-nominate-kevin-warsh...",
  "endDate": "2026-12-31T00:00:00Z",
  "startDate": "2025-08-05T17:28:15.5166Z",
  "liquidity": "56596.5482",
  "liquidityNum": 56596.5482,
  "volume": "2634904.495318",
  "volume24hr": 78281.00002299999,
  "volume1wk": 632702.1238300008,
  "volume1mo": 2408709.7411980066,
  "volumeNum": 2634904.495318,
  "outcomes": ["Yes", "No"],
  "outcomePrices": ["0.335", "0.665"],
  "lastTradePrice": 0.33,
  "bestBid": 0.33,
  "bestAsk": 0.34,
  "spread": 0.01,
  "oneDayPriceChange": 0.005,
  "oneWeekPriceChange": -0.005,
  "oneMonthPriceChange": 0.045,
  "description": "...",
  "image": "https://...",
  "clobTokenIds": ["...", "..."],
  "active": true,
  "closed": false,
  "competitive": 0.9734965562559322,
  "rewardsMinSize": 100,
  "rewardsMaxSpread": 3.5
}
```

#### Additional Data Available via API
- **Orderbook** ✅ - Already implemented via CLOB API
- **Trade History** - CLOB API endpoint exists but not fully utilized
- **Price History** - Could be calculated from trades or events data
- **Market Events** - Real-time via WebSocket (partially implemented)

### Kalshi API Data Available

#### Market Metadata (Already Captured)
```json
{
  "_ticker": "KXELONMARS-99",
  "_event_ticker": "KXELONMARS-99",
  "_subtitle": "",
  "_status": "active",
  "_open_time": "2025-08-28T20:45:00Z",
  "_close_time": "2099-08-01T04:59:00Z",
  "_expiration_time": "2099-08-08T15:00:00Z",
  "_volume": "32922",
  "_volume_24h": "187",
  "_liquidity": "6702566",
  "_open_interest": "13293",
  "_last_price": "6",
  "_previous_price": "8",
  "_yes_bid": "6",
  "_yes_ask": "10",
  "_no_bid": "90",
  "_no_ask": "94",
  "_can_close_early": true
}
```

#### Additional Data Available via Kalshi API
From `docs/kalshi/openapi-index.md`:
- **Candlesticks** - `/series/{series_ticker}/markets/{ticker}/candlesticks` (Line 889)
- **Candlesticks (Events)** - `/series/{series_ticker}/events/{ticker}/candlesticks` (Line 971)
- **Market Candlesticks** - `/markets/candlesticks` (Line 2440)
- **Trades** - `/markets/trades` (Line 946)
- **Orderbook** ✅ - `/markets/{ticker}/orderbook` (Line 1624) - Already implemented
- **Forecast History** - `/series/{series_ticker}/events/{ticker}/forecast_percentile_history` (Line 1222)
- **Event Metadata** - `/events/{event_ticker}/metadata` (Line 1192)

---

## Comprehensive Display Requirements

### 1. **Enhanced Market Metadata Panel**

#### Current Display
- Ticker
- Status
- 24h Volume
- Liquidity

#### Should Display (Polymarket)
- **Basic Info**
  - Question/Title
  - Market ID (short form)
  - Status (Active/Closed/Resolved)
  - Created Date
  - End Date
  
- **Pricing Info**
  - Last Trade Price
  - Best Bid/Ask
  - Spread (in bps)
  - Current Prices for all outcomes
  
- **Volume & Liquidity**
  - Total Volume
  - 24h Volume
  - 1 Week Volume
  - Liquidity (USD)
  - Open Interest
  
- **Price Changes**
  - 1 Day Change (%)
  - 1 Week Change (%)
  - 1 Month Change (%)
  
- **Market Quality**
  - Competitive Score (0-1)
  - Rewards (if applicable)

#### Should Display (Kalshi)
- **Basic Info**
  - Ticker
  - Event Ticker
  - Subtitle
  - Status
  - Open/Close/Expiration Times
  
- **Pricing Info**
  - Last Price (cents)
  - Previous Price
  - Yes Bid/Ask
  - No Bid/Ask
  - Implied Probability
  
- **Volume & Liquidity**
  - Total Volume (contracts)
  - 24h Volume
  - Liquidity (cents)
  - Open Interest (contracts)
  
- **Market Features**
  - Can Close Early
  - Strike Type/Values (if applicable)
  - Risk Limit

---

### 2. **Order Book Display** ✅ (Already Working)

Current implementation is good but could be enhanced:
- Show more depth levels (10-20 instead of 5)
- Add cumulative size visualization
- Show total bid/ask volume
- Show mid-price
- Add spread indicator in bps

---

### 3. **Price Chart/Graph** ❌ (CRITICAL - NOT IMPLEMENTED)

#### Requirements
- Display historical price movement
- Support multiple timeframes (1H, 4H, 1D, 1W, 1M)
- Show volume bars below price
- Real-time updates via WebSocket
- Support for multiple outcomes (Yes/No on same chart)
- Annotations for significant events

#### Implementation Options

**Option A: Inline Chart (Recommended)**
- Use `plotext` for terminal-based inline charts in TUI
- Pros: Stays in terminal, fast, no external dependencies
- Cons: Limited interactivity, lower resolution

**Option B: External Window (Current ChartManager approach)**
- Use PyWry + HTML/JavaScript for rich interactive charts
- Pros: Beautiful, highly interactive, better for analysis
- Cons: Opens separate window, more complex

**Option C: Hybrid**
- Small inline preview in TUI
- Hotkey to open full interactive chart in external window
- Best of both worlds

#### Data Sources

**Polymarket:**
- No direct candlestick API endpoint
- Options:
  1. Fetch trade history and build candlesticks client-side
  2. Use price snapshots from market metadata over time
  3. Poll market prices periodically and cache for charting

**Kalshi:**
- ✅ Native candlestick API available
- Multiple endpoints for different granularities
- Can fetch directly: `get_candlesticks(ticker, period="1h")`
- Periods: 1m, 5m, 15m, 1h, 4h, 1d

---

### 4. **Trade Tape / Time & Sales** ❌ (Widget exists but not shown)

#### Current State
- `TimeAndSales` widget exists in code
- Not included in current layout
- Has `add_trade()` method ready

#### Requirements
- Show recent trades (last 50-100)
- Columns: Time, Price, Size, Side (Buy/Sell)
- Color-coded by side (green=buy, red=sell)
- Auto-scroll with new trades
- Calculate statistics: VWAP, trade frequency

#### Data Sources
- **Polymarket**: WebSocket trade events + CLOB trade history API
- **Kalshi**: WebSocket trade events + `/markets/trades` endpoint

---

### 5. **Additional Useful Panels**

#### Market Statistics
- VWAP (Volume Weighted Average Price)
- High/Low (24h, 7d, all-time)
- Number of traders/participants
- Average trade size
- Liquidity score/depth

#### Related Markets
- Show other markets in the same event
- Show similar markets by topic
- Quick navigation between related markets

#### Market Description
- Full description text (scrollable)
- Resolution criteria
- Source information
- Tags/categories

---

## Implementation Plan

### Phase 1: Fix Current Display Issues (Priority: CRITICAL)
**Estimated Time: 2-3 hours**

1. **Debug and fix orderbook display**
   - Add comprehensive error logging to `setup_market()`
   - Test with both Polymarket and Kalshi markets
   - Ensure OrderbookDepth widget updates properly
   - Verify PriceLevel data flow

2. **Enhance market metadata display**
   - Expand `MarketMetadata.render()` to show all available fields
   - Create separate layouts for Polymarket vs Kalshi
   - Format numbers properly (currency, percentages, dates)
   - Add tooltips/explanations for fields

3. **Add error handling and loading states**
   - Show loading spinner while fetching data
   - Display clear error messages
   - Handle missing data gracefully
   - Add retry logic for failed requests

### Phase 2: Implement Price Charts (Priority: HIGH)
**Estimated Time: 4-6 hours**

1. **Add candlestick data fetching to KalshiProvider**
   ```python
   async def get_candlesticks(
       self, 
       market_id: str, 
       period: str = "1h",
       limit: int = 100
   ) -> List[Dict]:
       """
       Fetch candlestick data for a market
       periods: 1m, 5m, 15m, 1h, 4h, 1d
       """
       # Call /series/{series}/markets/{ticker}/candlesticks
       # Or /markets/candlesticks with ticker param
       pass
   ```

2. **Add price history method to PolyProvider**
   ```python
   async def get_price_history(
       self,
       token_id: str,
       period: str = "1h",
       limit: int = 100
   ) -> List[Dict]:
       """
       Build price history from trades or snapshots
       May need to poll market prices over time
       """
       pass
   ```

3. **Create inline chart widget using plotext**
   ```python
   class PriceChart(Static):
       """Inline terminal chart for price history"""
       data: reactive[Optional[PriceSeries]] = reactive(None)
       
       def render(self) -> RenderableType:
           if not self.data or not self.data.points:
               return Panel("No chart data", border_style="dim")
           
           # Use plotext to render chart as string
           plt.clear_figure()
           plt.plot(self.data.timestamps(), self.data.prices())
           plt.title(self.data.name)
           chart_str = plt.build()
           
           return Panel(chart_str, title="Price Chart", border_style="green")
   ```

4. **Integrate chart into MarketDetail layout**
   - Add PriceChart widget to layout
   - Fetch and populate data in `setup_market()`
   - Add timeframe selector (buttons for 1H, 4H, 1D, etc.)
   - Update chart in real-time from WebSocket

5. **Add hotkey to open external interactive chart**
   - Bind key (e.g., 'g' for graph)
   - Use existing ChartManager to open PyWry window
   - Populate with richer data and interactivity

### Phase 3: Add Trade Tape (Priority: MEDIUM)
**Estimated Time: 2-3 hours**

1. **Add TimeAndSales widget to layout**
   - Place below charts or in separate panel
   - Make collapsible/toggleable
   - Set appropriate height (10-15 lines)

2. **Integrate trade data feed**
   - Connect to WebSocket trade events
   - Add trade data to TimeAndSales widget
   - Implement auto-scroll and size limit

3. **Fetch historical trades on market selection**
   ```python
   # In setup_market()
   trades = await provider.get_history(market_id, limit=50)
   tape.populate(trades)
   ```

4. **Add trade statistics**
   - Calculate VWAP from recent trades
   - Show trade frequency (trades/minute)
   - Display buy/sell volume ratio

### Phase 4: Polish and Enhancement (Priority: LOW)
**Estimated Time: 3-4 hours**

1. **Add market description panel**
   - Show full description in scrollable widget
   - Display resolution criteria
   - Show market image/icon

2. **Implement related markets**
   - Fetch markets from same event
   - Add quick navigation
   - Show mini-stats for related markets

3. **Add market statistics panel**
   - Calculate and display VWAP, high/low
   - Show participant count if available
   - Display liquidity score

4. **Optimize performance**
   - Cache market data
   - Implement data refresh intervals
   - Add background data fetching
   - Optimize WebSocket subscriptions

---

## Proposed New Layout

```
┌────────────────────────────────────────────────────────────────────┐
│  LEFT COLUMN (30%)                                                 │
├────────────────────────────────────────────────────────────────────┤
│  [Polymarket] [Kalshi] [Both]  (Radio buttons side-by-side)      │
│                                                                    │
│  Search: [_____________________________]                          │
│                                                                    │
│  ┌────────────────────────────────────┐                          │
│  │ Market List (15 lines)             │                          │
│  │  • Market 1                        │                          │
│  │  • Market 2                        │                          │
│  │  • Market 3                        │                          │
│  └────────────────────────────────────┘                          │
│                                                                    │
│  Agent Chat (remainder)                                           │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  RIGHT COLUMN (70%)                                                │
├────────────────────────────────────────────────────────────────────┤
│  Market: Will Trump win 2024 election?                            │
│                                                                    │
│  ┌──────────────────┬──────────────────┬──────────────────────┐  │
│  │ Market Metadata  │  Order Book      │  Statistics          │  │
│  │                  │                  │                      │  │
│  │ Status: Active   │  Bids    | Asks  │  24h High: $0.52    │  │
│  │ Price: $0.51     │  0.51|100| 0.52  │  24h Low: $0.48     │  │
│  │ Volume: 1.2M     │  0.50|250| 0.53  │  VWAP: $0.505       │  │
│  │ Liquidity: 50K   │  0.49|180| 0.54  │  Spread: 2 bps      │  │
│  │ Spread: 0.01     │  ...             │                      │  │
│  │ 1d Change: +2%   │                  │                      │  │
│  └──────────────────┴──────────────────┴──────────────────────┘  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Price Chart                    [1H][4H][1D][1W][1M] (G:Graph)│ │
│  │                                                              │ │
│  │  0.55 ┤     ╭─╮                                             │ │
│  │  0.50 ┤   ╭─╯ ╰─╮                                           │ │
│  │  0.45 ┤ ╭─╯     ╰──╮                                        │ │
│  │  0.40 ┼─┴──────────┴───                                     │ │
│  │       12:00   16:00   20:00   00:00                         │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Time & Sales (Recent Trades)                                 │ │
│  │  Time     Price   Size    Side                               │ │
│  │  10:45:23  0.51   150    BUY (green)                         │ │
│  │  10:45:20  0.50   200    SELL (red)                          │ │
│  │  10:45:18  0.51   100    BUY (green)                         │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  [Description panel - collapsible]                                │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## Testing Checklist

### Polymarket
- [ ] Search for market
- [ ] Click on market
- [ ] Verify orderbook displays with correct prices
- [ ] Verify metadata shows all key fields
- [ ] Verify chart shows price history
- [ ] Verify trade tape shows recent trades
- [ ] Verify WebSocket updates work
- [ ] Test with different market types (binary, multi-outcome)

### Kalshi
- [ ] Search for market
- [ ] Click on market
- [ ] Verify orderbook displays with correct prices
- [ ] Verify metadata shows all key fields
- [ ] Verify chart shows candlestick data
- [ ] Verify trade tape shows recent trades
- [ ] Verify WebSocket updates work
- [ ] Test with different market types

### Cross-Platform
- [ ] Switch between Polymarket and Kalshi smoothly
- [ ] Verify data doesn't mix between providers
- [ ] Test error handling for failed API calls
- [ ] Test with slow network connections
- [ ] Verify memory usage is reasonable with many markets

---

## Key Files to Modify

1. **src/polycli/tui.py** (Main TUI)
   - Enhance `MarketMetadata.render()` 
   - Fix `MarketDetail.setup_market()`
   - Add `PriceChart` widget class
   - Integrate `TimeAndSales` into layout
   - Add chart data fetching logic

2. **src/polycli/providers/kalshi.py**
   - Add `get_candlesticks()` method
   - Add `get_market_metadata()` method for detailed info
   - Enhance trade history fetching

3. **src/polycli/providers/polymarket.py**
   - Add `get_price_history()` or `get_trades()` method
   - Enhance trade history fetching
   - Add data aggregation for charts

4. **src/polycli/tui.css**
   - Add styles for new panels
   - Adjust layout for chart display
   - Style trade tape

5. **src/polycli/utils/charting.py** (Optional)
   - Enhance for better integration
   - Add more chart types

---

## API Endpoints to Implement

### Kalshi
1. ✅ `/markets/{ticker}/orderbook` - Already implemented
2. **NEW** `/series/{series_ticker}/markets/{ticker}/candlesticks`
3. **NEW** `/markets/candlesticks?ticker={ticker}`
4. **NEW** `/markets/trades?ticker={ticker}`
5. **NEW** `/events/{event_ticker}/metadata`

### Polymarket
1. ✅ CLOB orderbook - Already implemented
2. **ENHANCE** CLOB trade history with aggregation
3. **NEW** Price polling/caching for chart building
4. ✅ WebSocket - Already implemented, needs enhancement

---

## Success Criteria

1. ✅ **Orderbook** displays correctly with >5 levels for both providers
2. ✅ **Market metadata** shows comprehensive info (>10 fields)
3. ✅ **Price chart** displays with historical data on market selection
4. ✅ **Trade tape** shows recent trades in real-time
5. ✅ **Error handling** gracefully handles API failures
6. ✅ **Performance** smooth with <1s market selection latency
7. ✅ **Real-time updates** work via WebSocket for both providers

---

## Estimated Total Time: 11-16 hours

- Phase 1 (Fix current): 2-3 hours ⚡ **START HERE**
- Phase 2 (Charts): 4-6 hours 🔥 **HIGHEST IMPACT**
- Phase 3 (Trade tape): 2-3 hours
- Phase 4 (Polish): 3-4 hours

---

## Next Steps

1. ✅ Present this plan to user for approval
2. Start with Phase 1 to fix immediate issues
3. Implement Phase 2 for charts (biggest user value)
4. Continue with Phases 3-4 as time allows
