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

4.  **UI/UX Standards (Premium Glassmorphism)**:
    -   **Background**: Use deep dark backgrounds (e.g., `#030712`).
    -   **Glass Cards**: Use semi-transparent surfaces `rgba(15, 23, 42, 0.8)` with heavy blur `backdrop-filter: blur(20px)` and subtle borders `rgba(255,255,255,0.07)`.
    -   **Typography**: Use `Inter` font, extremely bold weights (`font-black`/`800`) for metrics, and wide tracking `tracking-[0.15em]` for uppercase sublabels.
    -   **Color Coding**: Standardize on `#10b981` (Emerald) for positive/Put dominant, `#f87171` (Rose) for negative/Call dominant, and `#fbbf24` (Amber) for Spot prices.
    -   **Loading States**: Always implement a "Loading..." spinner or shimmer effect while waiting for initial API or WebSocket payloads to prevent layout jump.
    -   **Sentiment Badges**: Implement explicit visual badges (Bullish/Bearish/Neutral) dynamically driven by underlying data differences.

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
    -   To visualize momentum, use `fill: 'tozeroy'` with explicit color tracking in Plotly instead of raw bar charts.
    -   Split data streams into discrete `positiveY` and `negativeY` arrays on the frontend dynamically to give independent positive/negative fill colors.

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
