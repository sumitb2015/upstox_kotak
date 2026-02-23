# Exposure Change Heatmap Calculation Guide

This guide explains the step-by-step logic used to compute the colors and values on the **Exposure Change Heatmap** in OI Pro.

---

## 📅 Calculation Workflow

### Step 1: Calculate Net Delta at each snapshot

Every minute/snapshot, we calculate the total directional exposure for a strike.

**Example: 10:00 AM | Strike 25,200**

| Metric | Call Side | Put Side |
| :--- | :--- | :--- |
| **Delta** | +0.45 | -0.40 |
| **OI** | 1,000 contracts | 800 contracts |
| **Lot Size** | 65 | 65 |

**Formula:**
$$\text{Net Delta} = (\text{Call Delta} \times \text{Call OI} \times \text{Lot Size}) + (\text{Put Delta} \times \text{Put OI} \times \text{Lot Size})$$

**Calculation:**
$$(0.45 \times 1000 \times 65) + (-0.40 \times 800 \times 65)$$
$$= 29,250 + (-20,800)$$
$$= \mathbf{+8,450}$$

---

### Step 2: Calculate the Change (Velocity)

We compare the current snapshot to the previous one to find the "Intensity" of the move.

**Example: 10:01 AM (Next Snapshot)**
- **Net Delta₁₀:₀₁**: $+7,800$ (OI shifted or Price moved)

**Formula:**
$$\text{Change} = \text{Net Delta}_{current} - \text{Net Delta}_{previous}$$

**Calculation:**
$$7,800 - 8,450 = \mathbf{-650}$$

> **Interpretation**: Net delta **dropped by 650** units — bearish pressure or profit-taking on longs.

---

### Step 3: Normalize Across Strikes (Intensity)

To visualize this relative to the rest of the market, we find the **biggest absolute change** across all strikes in that same time column (e.g., 4,500).

**Formula:**
$$\text{Intensity} = \frac{\text{Change}}{\text{Max Absolute Change in Column}}$$

**Calculation:**
$$\frac{-650}{4,500} = \mathbf{-14.4\%}$$

---

### Step 4: Assign Color

The Intensity determines the box color:

| Intensity | Visual State | Meaning |
| :--- | :--- | :--- |
| **Above +2%** | 🟩 **Green** | Bullish building (Longs added / Put cover) |
| **Below -2%** | 🟥 **Red** | Bearish building (Shorts added / Call unwind) |
| **±2% Range** | ⬛ **Dark / Black** | Quiet (No significant positioning shift) |

*The brightness of the box scales with the intensity percentage (max brightness at 100%).*

---

## 🧠 The Simple Mental Model

1.  **Green Box**: Net delta went **UP** (Bulls active or Put writers covering).
2.  **Red Box**: Net delta went **DOWN** (Bears active or Call long unwinding).
3.  **Brightness**: How big that move was **relative to other strikes** at that exact time.

---

## ⚙️ Settings Profile
- **Scan Range**: ATM ± 8 strikes.
- **Update Frequency**: Default 1 Minute (supports dynamic 3/5/10 min resolution).
- **Persistence**: Data recovered from CSV on restart.
