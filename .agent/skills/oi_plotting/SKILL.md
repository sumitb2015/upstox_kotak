---
name: OI Plotting Skill
description: Instructions for real-time visual tracking of Open Interest (OI) trends using matplotlib and Upstox V3 data.
---

# OI Plotting Skill

This skill covers the implementation and usage of real-time visual analytics for Open Interest (OI) trends.

## 📊 1. Core Principles
- **V3 Intraday Data**: Always use `api_version="2.0"` in `get_intra_day_candle_data` to ensure non-zero OI values are returned for option contracts.
- **Timezone Alignment**: The Upstox API returns IST timestamps with timezone offset. These must be localized to `Asia/Kolkata` and stripped of timezone info before plotting to align with fixed market-hour axes (9:15 AM - 3:30 PM).
- **Dual Visuals**: Plotting both CE (Green) and PE (Red) on a single chart provides immediate sentiment skew visibility.

## 🛠️ 2. Visualization Tools
The primary utility is located at `scripts/plotting/plot_oi_realtime.py`.

### Key Features
- **Automatic ATM Discovery**: If no strike is provided, the script calculates the current ATM based on spot price.
- **Fixed Market Axis**: X-axis is locked to `09:15 AM` to `03:30 PM` IST for consistent daily tracking.
- **Animated Updates**: Real-time refresh every 60 seconds using `animation.FuncAnimation`.
- **Large Value Formatting**: Y-axis uses thousand-separators (e.g., `5,000,000`) for readability.

## 🚀 3. Usage Patterns

### Standard Dual ATM Monitoring
Highly recommended for intraday sentiment tracking.
```bash
python scripts/plotting/plot_oi_realtime.py
```

### Multi-Strike Comparison
Compare OI build-up across different support/resistance levels.
```bash
python scripts/plotting/plot_oi_realtime.py --symbol BANKNIFTY --strike 52000,52500 --type BOTH
```

### Specific Directional Tracking
```bash
python scripts/plotting/plot_oi_realtime.py --symbol NIFTY --strike 25000 --type PE
```

## 📐 4. Implementation Details
When building or modifying OI plots:
1. **Initial Population**: Call the animate function once before starting the timer to avoid empty charts.
2. **Y-Axis Scaling**: Use `ax.autoscale_view(scalex=False, scaley=True)` to keep the time axis stable while adjusting to OI changes.
3. **Legend Stability**: Dynamically update legend labels inside the animation loop to show current OI values.

```python
# Formatting large OI values
from matplotlib.ticker import FuncFormatter
ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{int(x):,}'))
```
