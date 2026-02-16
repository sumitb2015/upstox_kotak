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

4.  **UI/UX Standards**:
    -   **Dark Mode**: Default to dark theme (`bg-slate-950`, `text-slate-200`).
    -   **Glassmorphism**: Use semi-transparent backgrounds with blur (`backdrop-filter: blur(16px)`).
    -   **Grid Layouts**: Use CSS Grid for dense data displays (e.g., Option Chain, PCR Grid).

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
