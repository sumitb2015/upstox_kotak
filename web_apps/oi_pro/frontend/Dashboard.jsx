import React, { useState, useEffect } from 'react';
import { 
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, 
  Tooltip, Legend, ResponsiveContainer, Cell 
} from 'recharts';
import { Activity, Shield, TrendingUp, BarChart2, Layers } from 'lucide-react';

const BUILDUP_COLORS = {
  "Long Buildup": "#10b981",    // Emerald
  "Short Buildup": "#ef4444",   // Rose
  "Short Covering": "#0ea5e9",  // Sky
  "Long Unwinding": "#f59e0b",  // Amber
  "Neutral": "#94a3b8"          // Slate
};

const Dashboard = () => {
  const [data, setData] = useState([]);
  const [metadata, setMetadata] = useState({});
  const [loading, setLoading] = useState(true);
  const [symbol, setSymbol] = useState("NIFTY");

  useEffect(() => {
    fetchData();
  }, [symbol]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const resp = await fetch(`http://localhost:8000/api/option-chain?symbol=${symbol}`);
      const result = await resp.json();
      if (result.status === "success") {
        // Flatten data for scatter: Strike vs OI (CE/PE separately)
        const scatterData = [];
        result.data.forEach(strike => {
          if (strike.ce_oi > 0) {
            scatterData.push({
              strike: strike.strike_price,
              oi: strike.ce_oi,
              type: "CE",
              buildup: strike.ce_buildup,
              ltp: strike.ce_ltp
            });
          }
          if (strike.pe_oi > 0) {
            scatterData.push({
              strike: strike.strike_price,
              oi: strike.pe_oi,
              type: "PE",
              buildup: strike.pe_buildup,
              ltp: strike.pe_ltp
            });
          }
        });
        setData(scatterData);
        setMetadata(result.metadata);
      }
    } catch (err) {
      console.error("Fetch failed", err);
    }
    setLoading(false);
  };

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const d = payload[0].payload;
      return (
        <div className="bg-slate-900 border border-slate-700 p-3 rounded-lg shadow-xl">
          <p className="text-slate-400 text-xs uppercase font-bold mb-1">{d.type} {d.strike}</p>
          <p className="text-white text-lg font-bold">OI: {d.oi.toLocaleString()}</p>
          <p className="text-slate-300 text-sm">LTP: ₹{d.ltp.toFixed(2)}</p>
          <div className="mt-2 text-xs px-2 py-1 rounded inline-block" 
               style={{ backgroundColor: `${BUILDUP_COLORS[d.buildup]}22`, color: BUILDUP_COLORS[d.buildup] }}>
            {d.buildup}
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="min-h-screen bg-[#0a0c10] text-slate-200 font-inter">
      {/* Sidebar Navigation */}
      <nav className="fixed left-0 top-0 h-full w-20 bg-[#0d1117] border-r border-slate-800 flex flex-col items-center py-8 gap-8">
        <div className="w-12 h-12 bg-emerald-500 rounded-xl flex items-center justify-center shadow-lg shadow-emerald-500/20">
          <Activity className="text-white w-6 h-6" />
        </div>
        <div className="p-3 text-slate-500 hover:text-emerald-400 transition-colors cursor-pointer"><Layers /></div>
        <div className="p-3 text-slate-500 hover:text-emerald-400 transition-colors cursor-pointer"><TrendingUp /></div>
        <div className="p-3 text-slate-500 hover:text-emerald-400 transition-colors cursor-pointer"><BarChart2 /></div>
        <div className="mt-auto p-3 text-slate-500 hover:text-rose-400 transition-colors cursor-pointer"><Shield /></div>
      </nav>

      {/* Main Content */}
      <main className="pl-20 pr-8 py-8">
        <header className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-extrabold text-white tracking-tight">OI Pro Analytics</h1>
            <p className="text-slate-500">Sophisticated derivative sentiment engine</p>
          </div>
          <div className="flex gap-4">
            <select 
              className="bg-[#161b22] border border-slate-700 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            >
              <option value="NIFTY">NIFTY 50</option>
              <option value="BANKNIFTY">BANK NIFTY</option>
              <option value="FINNIFTY">FIN NIFTY</option>
            </select>
            <div className="bg-emerald-500/10 text-emerald-400 px-4 py-2 rounded-lg text-sm font-bold border border-emerald-500/20">
              LIVE
            </div>
          </div>
        </header>

        {/* Info Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-[#161b22] p-6 rounded-2xl border border-slate-800 relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full -mr-16 -mt-16 group-hover:scale-110 transition-transform"></div>
            <p className="text-slate-500 text-sm font-bold uppercase mb-2 tracking-wider">Spot Price</p>
            <h2 className="text-4xl font-black text-white">₹{metadata.spot?.toLocaleString() || "---"}</h2>
            <div className="mt-4 flex items-center gap-2 text-emerald-400 text-xs font-bold">
              <TrendingUp size={14} /> LIVE FROM NSE
            </div>
          </div>
          <div className="bg-[#161b22] p-6 rounded-2xl border border-slate-800">
            <p className="text-slate-500 text-sm font-bold uppercase mb-2 tracking-wider">Put-Call Ratio (PCR)</p>
            <h2 className="text-4xl font-black text-white">{metadata.pcr?.toFixed(2) || "---"}</h2>
            <p className={`mt-4 text-xs font-bold ${metadata.pcr > 1 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {metadata.pcr > 1 ? 'BULLISH SENTIMENT' : 'BEARISH SENTIMENT'}
            </p>
          </div>
          <div className="bg-[#161b22] p-6 rounded-2xl border border-slate-800">
            <p className="text-slate-500 text-sm font-bold uppercase mb-2 tracking-wider">Active Expiry</p>
            <h2 className="text-3xl font-black text-white truncate">{metadata.expiry || "---"}</h2>
            <p className="mt-5 text-slate-500 text-xs font-bold uppercase">Weekly Expiration</p>
          </div>
        </div>

        {/* Scatter Plot */}
        <div className="bg-[#161b22] p-8 rounded-3xl border border-slate-800 shadow-2xl">
          <div className="flex justify-between items-end mb-8">
            <div>
              <h3 className="text-xl font-bold text-white mb-1">OI Distribution Scatter</h3>
              <p className="text-slate-500 text-sm">Strike Price vs Open Interest (Colored by Buildup)</p>
            </div>
            <div className="flex gap-4 text-[10px] font-bold uppercase tracking-widest">
              {Object.entries(BUILDUP_COLORS).map(([label, color]) => (
                <div key={label} className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }}></div>
                  <span className="text-slate-400">{label}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="h-[500px] w-full mt-4">
            {loading ? (
              <div className="h-full flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500"></div>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#21262d" vertical={false} />
                  <XAxis 
                    type="number" 
                    dataKey="strike" 
                    name="Strike" 
                    domain={['auto', 'auto']}
                    stroke="#484f58"
                    fontSize={12}
                    tickFormatter={(val) => val.toLocaleString()}
                  />
                  <YAxis 
                    type="number" 
                    dataKey="oi" 
                    name="OI" 
                    stroke="#484f58"
                    fontSize={12}
                    tickFormatter={(val) => (val / 1000000).toFixed(1) + 'M'}
                  />
                  <ZAxis type="number" range={[100, 100]} />
                  <Tooltip content={<CustomTooltip />} cursor={{ strokeDasharray: '3 3', stroke: '#30363d' }} />
                  <Scatter name="Options" data={data}>
                    {data.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={BUILDUP_COLORS[entry.buildup]} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
