---
name: Web Dashboard Development
description: Best practices for building high-performance, interactive financial dashboards using FastAPI (Backend) and React/Plotly (Frontend).
---

# Web Dashboard Development Skill

This skill outlines the standard architecture and best practices for building financial dashboards within the Upstox Algo ecosystem.

## 1. Architecture Stack
- **Backend**: FastAPI (Python). High-performance, easy to use with Pandas.
- **Frontend**: React (via CDN for simplicity) + Babel (Standalone).
- **Styling**: Tailwind CSS (via CDN).
- **Visualization**: Plotly.js (via CDN).
- **Icons**: SVG Icons (Lucide-react style) or inline SVGs.

## 2. Best Practices

### A. Frontend (React + Plotly)
1.  **Relative API Paths**:
    -   **ALWAYS** use relative paths for API calls (e.g., `fetch('/api/data')`).
    -   **NEVER** hardcode `http://localhost:8000`. This ensures the app works regardless of the port it's running on (e.g., 8001, 8002).

2.  **Auto-Refresh Pattern**:
    -   Use `useEffect` with `setInterval` to poll data.
    -   Include a "Last Updated" timestamp in the UI.
    ```javascript
    useEffect(() => {
        const interval = setInterval(fetchData, 60000); // 60s
        return () => clearInterval(interval);
    }, []);
    ```

3.  **Visualization enhancements**:
    -   **Log Scale**: Use `type: 'log'` in Plotly `layout.yaxis` for data with wide ranges (e.g., PCR, Volume).
    -   **Sentiment Coloring**: Use conditional colors (Green/Red) based on thresholds (e.g., PCR > 1).
    -   **Tooltips**: Customize `hoverinfo` or `hovertemplate` to show precise data.
    -   **Responsiveness**: Ensure charts resize by setting `responsive: true` in Plotly config and using `w-full` logic.
    -   **3D Surface Rendering**: When rendering Plotly `surface` charts, ensure the `z` data is explicitly structured as an array of arrays (e.g., a 2D matrix representing values across X and Y). Pass exact matching flat arrays for `x` and `y` axes. Failure to format `z` as strictly 2D will result in a blank canvas rendering despite successful plotting of scatter points.
5.  **Dual-Chart Layout (Price + OI)**:
    -   Professional dashboards MUST use a synchronized dual-chart layout:
        -   **Top Chart**: Price (Candlestick or Line with Area fill).
        -   **Bottom Chart**: Open Interest Change (Line Chart).
    -   Keep the height ratio approximately 2:1 or 3:2.
    -   Ensure X-axes are synchronized so zooming on one zooms the other.
6.  **OI Normalization (Change from Open)**:
    -   **Rule**: Never plot raw absolute OI on a time-series chart. It is difficult to read.
    -   **Standard**: Always plot **OI Change = Current OI - Initial OI (at session start)**.
    -   This ensures the chart starts at zero and clearly shows build-up (positive) vs. unwinding (negative).
    -   **Visuals**: Use a clean line chart WITHOUT shading (`fill: null`) to prevent visual clutter when multiple strikes are plotted.

4.  **UI/UX Standards (Premium Glassmorphism & Toggles)**:
    -   **Background**: Use deep dark backgrounds (e.g., `#030712` or `#060910`).
    -   **Dark Mode Retention**: For authentication and core analytical pages (like Login), enforce Dark Mode persistently by defaulting `document.documentElement.classList.add('dark')` and hardcoding deep slate backgrounds to prevent bright flashes on system theme changes.
    -   **Segmented Controls (Tabs)**: Avoid native `<select>` dropdowns for critical switches like Nifty vs. Bank Nifty. Implement Shadcn-style segmented tabs (`<button>` groups with conditional bg/text highlighting) for superior user experience and modern look.
    -   **Glass Cards**: Use semi-transparent surfaces `rgba(15, 23, 42, 0.8)` with heavy blur `backdrop-filter: blur(20px)` and subtle borders `rgba(255,255,255,0.07)`. Enhance with **hover-lift** (`transition-transform hover:-translate-y-1`) and **dynamic glow effects** (e.g., colored shadows `shadow-[0_0_15px_-5px_...`] driven by data like green for gainers or red for losers.
    -   **Typography**: Use `Inter` font, extremely bold weights (`font-black`/`800`) for metrics, and wide tracking `tracking-[0.15em]` for uppercase sublabels.
    -   **Color Coding**: Standardize on `#10b981` (Emerald) for positive/Put dominant, `#f87171` (Rose) for negative/Call dominant, and `#fbbf24` (Amber) for Spot prices.
    -   **ATM High-Contrast (Light Mode)**: For the ATM strike, prioritize readability by using high-contrast text (`text-amber-900` / bold) and distinct cell backgrounds (e.g., `bg-amber-500/20`) to prevent washing out in light backgrounds. 
    -   **Loading States**: Always implement a "Loading..." spinner or shimmer effect while waiting for initial API or WebSocket payloads to prevent layout jump.
    -   **Sentiment Badges**: Implement explicit visual badges (Bullish/Bearish/Neutral) dynamically driven by underlying data differences.
    -   **HQ Layout (Modern Minimalist)**: For "HQ" style dashboards, use a single centered column `max-w-7xl mx-auto` with significant top/bottom padding. Avoid cluttered grids; instead, use floating glass cards with large typography.
    -   **Multi-Column Glass Tooltips**: 
        - Pattern: Use a professional grid within the Recharts/Plotly tooltip.
        - Styling: `bg-slate-950/90 backdrop-blur-xl border border-white/10 rounded-2xl shadow-2xl`.
        - Content: Align labels to the left and values to the right in high-contrast emerald/rose text.
    -   **Header Index Tickers**: For multi-chart apps, integrate a sleek real-time ticker for parent indices (e.g., NIFTY 50) directly into the `<h1>` or adjacent header space. Use a discrete vertical separator `w-px bg-border/40` to distinguish the app title from the live feed.
6.  **Dynamic X-Axis Focus (Intraday)**:
    -   **Standard**: Instead of a static 9:15-15:30 X-axis, use a dynamic range that follows the current time.
    -   **Rule**: End the chart at `current_time + 10 minutes`. This provides a focused view of the morning's action without a long, empty tail to the right.
    -   **Implementation**: Calculate `xEnd = new Date(new Date().getTime() + 10 * 60 * 1000)` on every update.
8.  **Professional Chart Smoothing & Scaling**:
    -   **Line Quality**: Use `line: { shape: 'spline', smoothing: 0.5, width: 2 }` for all premium time-series charts. This creates a high-end, organic look.
    -   **Tight Y-Axis Scaling**: 
        -   **Rule**: Never let charts look "flat". 
        -   **Technique**: Calculate data `min` and `max`, then apply a ±15% padding: `range: [min * 0.85, max * 1.15]`.
        -   **Fixed Range**: Set `fixedrange: true` on both axes to prevent accidental user scrolling/panning that breaks the calibrated view.
7.  **Grouped Table Layouts (Static Data)**:
    -   For non-time-series data (like Holidays or Corporate Actions), avoid broad grids.
    -   **Pattern**: Use a professional table with monthly/category grouping, sticky headers, and status-based row emphasis (e.g., lower opacity for past events).
    -   **KPI Strips**: Always include a KPI strip at the top (e.g., Total Holidays, Next Holiday) for quick info at a glance.

### B. WebSocket Optimization (Backend & Frontend)
1.  **Backend Async Loop (The 1-Second Broadcaster)**:
    -   When sending real-time data over WebSockets, use a non-blocking `asyncio.wait_for` to handle incoming subscription requests, catching the `TimeoutError` to execute the periodic 1-second broadcast loop.
    -   *Rule*: Pull data instantly from an in-memory dictionary cache (`streamer.get_latest_data(key)`) inside the periodic loop rather than event-driven pushing to clients, which easily causes backpressure.
    -   Always send explicit `type: "status"` messages (`loading`, `ready`, `error`) so the frontend can react.

2.  **Frontend Sync Guard (Preventing Duplicate Chart Data)**:
    -   **Crucial Issue**: Backend often broadcasts data every 1s, even if market prices haven't moved (especially out of hours or low liquidity).
    -   **Solution**: Only append to chart history arrays IF the core values have changed.
    ```javascript
    // Example Sync Guard
    const priceChanged = (msg.ce_sum !== lastCe) || (msg.pe_sum !== lastPe);
    if (priceChanged) {
        h.times.push(msg.timestamp);
        h.ce.push(msg.ce_sum);
        // ... trim arrays to MAX_POINTS ...
        renderCharts(h); // Re-render ONLY when actual data moved
    }
    // Note: Live KPI scalar numbers can update every tick regardless.
    ```

3.  **Real-Time Line Fills (Plotly)**:
    -   To visualize price momentum, use `fill: 'tozeroy'` with explicit color tracking in Plotly.
    -   **Crucial**: For **Daily OI Change** charts, do NOT use fills. Use simple lines to keep the multi-strike view readable.

### B. Backend (FastAPI)
1.  **Port Management**:
    -   Dynamically find an available port if the default is busy.
    -   **Do not** fail if port 8000 is occupied; try 8001, 8002, etc.

2.  **Data Serving**:
    -   Convert Pandas DataFrames to JSON using `df.to_dict(orient='records')`.
    -   Handle `NaN` and `Infinite` values before serialization (replace with `None` or `0`).

## 3. reusable Components (Snippets)

### Sidebar Navigation
Use a fixed sidebar for multi-page apps to ensure easy switching between views.
```html
<nav class="fixed left-0 top-0 h-full w-20 bg-[#0b0f1a] ...">
  <!-- Icons -->
</nav>
```

### Formatters
```javascript
const formatNumber = (num) => {
    if (!num) return "0";
    if (num >= 10000000) return (num / 10000000).toFixed(2) + 'Cr';
    if (num >= 100000) return (num / 100000).toFixed(2) + 'L';
    return num.toString();
};
```
