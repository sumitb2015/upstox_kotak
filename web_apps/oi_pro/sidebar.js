/**
 * Shared Sidebar Navigation - OI Pro Dashboard
 * Single source of truth for all nav links across all pages.
 * Usage: Include <div id="sidebar-root"></div> in body, then <script src="/sidebar.js"></script>
 */
(function () {
    const NAV_ITEMS = [
        {
            href: "/",
            title: "Dashboard",
            svg: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline>'
        },
        {
            href: "/pop",
            title: "Premium vs PoP Analysis",
            svg: '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline>'
        },
        {
            href: "/pcr",
            title: "PCR By Strike",
            svg: '<line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line>'
        },
        {
            href: "/straddle",
            title: "ATM Straddle Analysis",
            svg: '<path d="M3 3v18h18"></path><path d="m19 9-5 5-4-4-3 3"></path>'
        },
        {
            href: "/option-chain",
            title: "Option Chain",
            svg: '<line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line>'
        },
        {
            href: "/cumulative",
            title: "Cumulative OI Analysis",
            svg: '<path d="M18 20V10"></path><path d="M12 20V4"></path><path d="M6 20v-6"></path>'
        },
        {
            href: "/gex",
            title: "Net GEX Regime",
            svg: '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>'
        },
        {
            href: "/max-pain",
            title: "Max Pain & IV Smile",
            svg: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line>'
        },
        {
            href: "/multi-strike",
            title: "Multi-Strike Analysis",
            svg: '<path d="M3 3v18h18"></path><line x1="13" y1="17" x2="13" y2="8"></line><line x1="18" y1="17" x2="18" y2="12"></line><line x1="8" y1="17" x2="8" y2="12"></line><path d="M18 3h3v3M9 3h3v3M3 3h3v3"></path>'
        },
        {
            href: "/multi",
            title: "Multi-Option Chart",
            svg: '<path d="M3 3v18h18"></path><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path>'
        },
        {
            href: "/strike",
            title: "Strike Analytics",
            svg: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V9a2 2 0 00-2-2h-2M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2m0 0h2" />'
        },
        {
            href: "/greeks",
            title: "Greeks Exposure",
            svg: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 17.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>'
        },
        {
            href: "/strike-greeks",
            title: "Strike Greeks History",
            svg: '<path d="M12 20V10"></path><path d="M18 20V4"></path><path d="M6 20v-4"></path>'
        },
        {
            href: "/heatmap",
            title: "Exposure Change Heatmap",
            svg: '<rect x="3" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="3" width="7" height="7" rx="1"></rect><rect x="3" y="14" width="7" height="7" rx="1"></rect><rect x="14" y="14" width="7" height="7" rx="1"></rect>'
        },
        {
            href: "/strategies",
            title: "Strategy Command Center",
            svg: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>'
        }
    ];

    function renderSidebar() {
        const currentPath = window.location.pathname;

        // Build nav HTML
        const itemsHTML = NAV_ITEMS.map(function (item) {
            // Exact match for home, prefix match for others
            const isActive = item.href === "/"
                ? currentPath === "/"
                : currentPath === item.href || currentPath.startsWith(item.href + "/");

            const baseClasses = "flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all hover:scale-105";
            const activeClasses = "bg-emerald-500 shadow-[0_0_20px_rgba(16,185,129,0.3)]";
            const inactiveClasses = "bg-slate-800/50 hover:bg-emerald-500/20 text-slate-400 hover:text-emerald-400";
            const strokeColor = isActive ? "white" : "currentColor";

            return '<a href="' + item.href + '" class="' + baseClasses + ' ' + (isActive ? activeClasses : inactiveClasses) + '" title="' + item.title + '">' +
                '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="' + strokeColor + '" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
                item.svg +
                '</svg>' +
                '</a>';
        }).join('\n');

        const navHTML = '<nav style="position:fixed;left:0;top:0;height:100%;width:4rem;background:#0b0f1a;border-right:1px solid rgba(51,65,85,0.4);display:flex;flex-direction:column;align-items:center;padding:1.5rem 0;gap:1.25rem;z-index:50;overflow-y:auto;scrollbar-width:thin;scrollbar-color:#1e293b transparent;">' +
            itemsHTML +
            '</nav>';

        const root = document.getElementById('sidebar-root');
        if (root) {
            root.innerHTML = navHTML;
        } else {
            // Fallback: inject at top of body if no placeholder found
            const div = document.createElement('div');
            div.innerHTML = navHTML;
            document.body.insertBefore(div.firstChild, document.body.firstChild);
        }
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', renderSidebar);
    } else {
        renderSidebar();
    }
})();
