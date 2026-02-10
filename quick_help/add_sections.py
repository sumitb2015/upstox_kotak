"""
Add additional sections to the Upstox API Reference notebook
Sections to add:
- Market Holidays & Timings
- Order Management (Place, Modify, Cancel)
- Portfolio & Positions
"""

import json

# New cells to add before the "Quick Testing Playground" section

new_cells = [
    # Market Holidays & Timings Section
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## 10. Market Holidays & Timings"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Get Market Holidays\n",
            "from lib.api.market_data import get_market_holidays\n",
            "\n",
            "holidays = get_market_holidays()\n",
            "if holidays:\n",
            "    print(\"Market Holidays:\")\n",
            "    for holiday in holidays:\n",
            "        print(f\"  {holiday}\")"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Check Market Status\n",
            "from lib.api.market_data import get_market_status\n",
            "\n",
            "status = get_market_status()\n",
            "print(f\"Market Status: {status}\")\n",
            "print(\"\\nMarket Hours:\")\n",
            "print(\"  Pre-market: 9:00 AM - 9:15 AM\")\n",
            "print(\"  Regular: 9:15 AM - 3:30 PM\")\n",
            "print(\"  Post-market: 3:40 PM - 4:00 PM\")"
        ]
    },
    # Order Management Section
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## 11. Order Management\n",
            "\n",
            "**⚠️ WARNING:** These functions place real orders. Use with caution!"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Import Order Management Functions\n",
            "from lib.api.order_management import (\n",
            "    place_order, modify_order, cancel_order,\n",
            "    get_order_book, get_order_details, get_trade_history\n",
            ")\n",
            "\n",
            "print(\"✅ Order management functions imported\")\n",
            "print(\"\\nAvailable Functions:\")\n",
            "print(\"  - place_order(): Place a new order\")\n",
            "print(\"  - modify_order(): Modify an existing order\")\n",
            "print(\"  - cancel_order(): Cancel an order\")\n",
            "print(\"  - get_order_book(): Get all orders\")\n",
            "print(\"  - get_order_details(): Get specific order details\")\n",
            "print(\"  - get_trade_history(): Get executed trades\")"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Get Order Book (View existing orders)\n",
            "order_book = get_order_book(access_token)\n",
            "\n",
            "if order_book and 'data' in order_book:\n",
            "    orders = order_book['data']\n",
            "    print(f\"Total Orders: {len(orders)}\")\n",
            "    \n",
            "    if orders:\n",
            "        print(\"\\nRecent Orders:\")\n",
            "        for order in orders[:5]:  # Show first 5\n",
            "            print(f\"  Order ID: {order.get('order_id')}\")\n",
            "            print(f\"  Symbol: {order.get('trading_symbol')}\")\n",
            "            print(f\"  Type: {order.get('transaction_type')} {order.get('quantity')}\")\n",
            "            print(f\"  Status: {order.get('status')}\")\n",
            "            print(f\"  Price: ₹{order.get('price', 0):.2f}\")\n",
            "            print(\"---\")\n",
            "else:\n",
            "    print(\"No orders found or unable to fetch order book\")"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Get Trade History\n",
            "trades = get_trade_history(access_token)\n",
            "\n",
            "if trades and 'data' in trades:\n",
            "    trade_list = trades['data']\n",
            "    print(f\"Total Trades: {len(trade_list)}\")\n",
            "    \n",
            "    if trade_list:\n",
            "        print(\"\\nRecent Trades:\")\n",
            "        for trade in trade_list[:5]:  # Show first 5\n",
            "            print(f\"  Symbol: {trade.get('trading_symbol')}\")\n",
            "            print(f\"  Type: {trade.get('transaction_type')} {trade.get('quantity')}\")\n",
            "            print(f\"  Price: ₹{trade.get('price', 0):.2f}\")\n",
            "            print(f\"  Time: {trade.get('exchange_timestamp')}\")\n",
            "            print(\"---\")\n",
            "else:\n",
            "    print(\"No trades found\")"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Place Order Example (COMMENTED OUT FOR SAFETY)\n",
            "# ⚠️ UNCOMMENT ONLY WHEN READY TO PLACE A REAL ORDER\n",
            "\n",
            "# Example: Place a MARKET BUY order\n",
            "# order_response = place_order(\n",
            "#     access_token=access_token,\n",
            "#     instrument_token=atm_ce_key,  # From earlier cells\n",
            "#     quantity=25,\n",
            "#     transaction_type=\"BUY\",\n",
            "#     order_type=\"MARKET\",\n",
            "#     product=\"INTRADAY\",\n",
            "#     validity=\"DAY\"\n",
            "# )\n",
            "# print(f\"Order Response: {order_response}\")\n",
            "\n",
            "print(\"⚠️ Order placement code is commented out for safety\")\n",
            "print(\"Uncomment and modify parameters to place a real order\")"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Modify Order Example (COMMENTED OUT FOR SAFETY)\n",
            "# ⚠️ UNCOMMENT ONLY WHEN READY TO MODIFY A REAL ORDER\n",
            "\n",
            "# order_id = \"240123000123456\"  # Replace with actual order ID\n",
            "# modify_response = modify_order(\n",
            "#     access_token=access_token,\n",
            "#     order_id=order_id,\n",
            "#     quantity=50,  # New quantity\n",
            "#     order_type=\"LIMIT\",\n",
            "#     price=100.0  # New price\n",
            "# )\n",
            "# print(f\"Modify Response: {modify_response}\")\n",
            "\n",
            "print(\"⚠️ Order modification code is commented out for safety\")"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Cancel Order Example (COMMENTED OUT FOR SAFETY)\n",
            "# ⚠️ UNCOMMENT ONLY WHEN READY TO CANCEL A REAL ORDER\n",
            "\n",
            "# order_id = \"240123000123456\"  # Replace with actual order ID\n",
            "# cancel_response = cancel_order(access_token, order_id)\n",
            "# print(f\"Cancel Response: {cancel_response}\")\n",
            "\n",
            "print(\"⚠️ Order cancellation code is commented out for safety\")"
        ]
    },
    # Portfolio & Positions Section
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## 12. Portfolio & Positions"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Get Current Positions\n",
            "from lib.api.portfolio import get_positions, get_holdings, get_funds\n",
            "\n",
            "positions = get_positions(access_token)\n",
            "\n",
            "if positions and 'data' in positions:\n",
            "    pos_list = positions['data']\n",
            "    print(f\"Total Positions: {len(pos_list)}\")\n",
            "    \n",
            "    if pos_list:\n",
            "        print(\"\\nOpen Positions:\")\n",
            "        for pos in pos_list:\n",
            "            print(f\"  Symbol: {pos.get('trading_symbol')}\")\n",
            "            print(f\"  Quantity: {pos.get('quantity')}\")\n",
            "            print(f\"  Avg Price: ₹{pos.get('average_price', 0):.2f}\")\n",
            "            print(f\"  LTP: ₹{pos.get('last_price', 0):.2f}\")\n",
            "            print(f\"  P&L: ₹{pos.get('pnl', 0):.2f}\")\n",
            "            print(\"---\")\n",
            "else:\n",
            "    print(\"No open positions\")"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Get Holdings (Long-term investments)\n",
            "holdings = get_holdings(access_token)\n",
            "\n",
            "if holdings and 'data' in holdings:\n",
            "    holding_list = holdings['data']\n",
            "    print(f\"Total Holdings: {len(holding_list)}\")\n",
            "    \n",
            "    if holding_list:\n",
            "        print(\"\\nHoldings:\")\n",
            "        for holding in holding_list[:5]:  # Show first 5\n",
            "            print(f\"  Symbol: {holding.get('trading_symbol')}\")\n",
            "            print(f\"  Quantity: {holding.get('quantity')}\")\n",
            "            print(f\"  Avg Price: ₹{holding.get('average_price', 0):.2f}\")\n",
            "            print(f\"  Current Value: ₹{holding.get('current_value', 0):.2f}\")\n",
            "            print(\"---\")\n",
            "else:\n",
            "    print(\"No holdings found\")"
        ]
    },
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# Get Fund/Margin Information\n",
            "funds = get_funds(access_token)\n",
            "\n",
            "if funds and 'data' in funds:\n",
            "    fund_data = funds['data']\n",
            "    print(\"Fund Information:\")\n",
            "    print(f\"  Available Margin: ₹{fund_data.get('available_margin', 0):,.2f}\")\n",
            "    print(f\"  Used Margin: ₹{fund_data.get('used_margin', 0):,.2f}\")\n",
            "    print(f\"  Total Balance: ₹{fund_data.get('total_balance', 0):,.2f}\")\n",
            "else:\n",
            "    print(\"Unable to fetch fund information\")"
        ]
    }
]

print(f"Created {len(new_cells)} new cells to add to the notebook")
print("\\nSections added:")
print("  - Market Holidays & Timings")
print("  - Order Management (Place, Modify, Cancel)")
print("  - Portfolio & Positions")
print("\\nThese cells should be inserted before the 'Quick Testing Playground' section")
