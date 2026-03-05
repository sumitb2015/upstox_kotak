/**
 * Shared Sidebar Navigation - OI Pro Dashboard
 * Single source of truth for all nav links across all pages.
 * Usage: Include <div id="sidebar-root"></div> in body, then <script src="/sidebar.js"></script>
 */
(function () {

    // Auth Check: Redirect to login if not authenticated via JWT
    if (!localStorage.getItem('oi_pro_jwt') && window.location.pathname !== '/login') {
        window.location.href = '/login';
        return; // Stop execution
    }


    function getJWTPayload() {
        const token = localStorage.getItem('oi_pro_jwt');
        if (!token) return null;
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(function (c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            return JSON.parse(jsonPayload);
        } catch (e) {
            return null;
        }
    }

    const payload = getJWTPayload();
    const isAdmin = payload && payload.role === 'admin';

    // --- Broker Token Gate ---
    // Redirect non-admin users to /brokers if they have no active broker token.
    // Exempt on login/brokers and public pages. Admins always bypass.
    (function brokerGate() {
        const GATE_EXEMPT = ['/login', '/brokers', '/pricing', '/privacy', '/terms', '/contact'];
        const exempt = GATE_EXEMPT.some(p => window.location.pathname === p || window.location.pathname.startsWith(p + '/'));
        if (exempt || isAdmin) return; // Admins and exempt pages skip the gate
        const jwt = localStorage.getItem('oi_pro_jwt');
        if (!jwt) return;
        fetch('/api/broker/status', { headers: { 'Authorization': 'Bearer ' + jwt } })
            .then(r => { if (!r.ok) return null; return r.json(); })
            .then(data => { if (data && !data.has_token) window.location.href = '/brokers?no_broker=1'; })
            .catch(() => { }); // Fail open on network error
    })();

    // --- Global Auth Helpers ---
    window.fetchWithAuth = async (url, options = {}) => {
        const token = localStorage.getItem('oi_pro_jwt');
        if (token) {
            options.headers = {
                ...options.headers,
                'Authorization': `Bearer ${token}`
            };
        }
        const response = await fetch(url, options);
        if (response.status === 401 && !url.includes('/api/login')) {
            console.warn("Auth failed (401). Redirecting to login.");
            localStorage.removeItem('oi_pro_jwt');
            window.location.href = '/login';
        }
        return response;
    };

    window.getWsUrlWithAuth = (url) => {
        const token = localStorage.getItem('oi_pro_jwt');
        if (!token) return url;

        let targetUrl = url;
        if (!url.startsWith('ws:') && !url.startsWith('wss:')) {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.host;
            // Ensure path starts with /
            const path = url.startsWith('/') ? url : '/' + url;
            targetUrl = `${protocol}//${host}${path}`;
        }

        const separator = targetUrl.includes('?') ? '&' : '?';
        return `${targetUrl}${separator}token=${token}`;
    };

    const NAV_ITEMS = [
        {
            href: "/",
            title: "Dashboard",
            svg: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline>'
        },
        {
            href: "/market-watch",
            title: "Market Watch",
            svg: '<circle cx="12" cy="12" r="10"></circle><path d="M12 6v6l4 2"></path>'
        },
        {
            href: "/market-calendar",
            title: "Market Calendar",
            svg: '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line>'
        },
        {
            href: "/stock-dashboard",
            title: "Stock Dashboard",
            svg: '<line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line>'
        },
        {
            href: "/indices-dashboard",
            title: "Indices Dashboard",
            svg: '<line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line>'
        },
        {
            href: "/fii-dii",
            title: "FII / DII Analytics",
            svg: '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"></path><path d="M22 12A10 10 0 0 0 12 2v10z"></path>'
        },
        {
            href: "/future-intraday",
            title: "Future Intraday",
            svg: '<line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line>'
        },
        {
            href: "/future-price-oi",
            title: "Future Price vs OI",
            svg: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>'
        },
        {
            href: "/surface-3d",
            title: "3D Surface Analysis",
            svg: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line>'
        },
        {
            href: "/pop",
            title: "Seller's Edge",
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
            href: "/oi-buildup",
            title: "OI Trend Analyzer",
            svg: '<rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect>'
        },
        {
            href: "/cumulative",
            title: "Cumulative OI Analysis",
            svg: '<path d="M18 20V10"></path><path d="M12 20V4"></path><path d="M6 20v-6"></path>'
        },
        {
            href: "/cumulative-prices",
            title: "Cumulative Option Prices",
            svg: '<path d="M12 20V10"></path><path d="M18 20V4"></path><path d="M6 20v-4"></path>'
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
        },
        {
            href: "/news-pulse",
            title: "News Pulse",
            svg: '<path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"></path><path d="M18 14h-8"></path><path d="M15 18h-5"></path><path d="M10 6h8v4h-8V6Z"></path>'
        },
        {
            href: "/brokers",
            title: "Brokers",
            svg: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><polyline points="16 11 18 13 22 9"></polyline>'
        }
    ];

    if (isAdmin) {
        NAV_ITEMS.push({
            href: "/users",
            title: "User Management",
            svg: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path>'
        });
    }

    function renderSidebar() {
        // Apply saved theme immediately
        const savedTheme = localStorage.getItem('oi-pro-theme') || 'dark';
        if (savedTheme === 'dark') {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark');
        }

        const currentPath = window.location.pathname;

        const toggleTheme = () => {
            const isDark = document.documentElement.classList.contains('dark');
            if (isDark) {
                document.documentElement.classList.remove('dark');
                localStorage.setItem('oi-pro-theme', 'light');
                window.dispatchEvent(new Event('themeToggled'));
            } else {
                document.documentElement.classList.add('dark');
                localStorage.setItem('oi-pro-theme', 'dark');
                window.dispatchEvent(new Event('themeToggled'));
            }
            renderSidebar(); // Re-render to update icon
        };

        // Inject Styles
        if (!document.getElementById('sidebar-styles')) {
            const style = document.createElement('style');
            style.id = 'sidebar-styles';
            style.innerHTML = `
                :root {
                    --background: #ffffff;
                    --foreground: #020817;
                    --card: #ffffff;
                    --card-foreground: #020817;
                    --popover: #ffffff;
                    --popover-foreground: #020817;
                    --primary: #020817;
                    --primary-foreground: #f8fafc;
                    --secondary: #f8fafc;
                    --secondary-foreground: #1e293b;
                    --muted: #f1f5f9;
                    --muted-foreground: #64748b;
                    --accent: #f1f5f9;
                    --accent-foreground: #020817;
                    --destructive: #ef4444;
                    --destructive-foreground: #f8fafc;
                    --border: #e2e8f0;
                    --input: #e2e8f0;
                    --ring: #020817;
                    --radius: 0.5rem;
                }

                .dark {
                    --background: #020817;
                    --foreground: #f8fafc;
                    --card: #0f172a;
                    --card-foreground: #f8fafc;
                    --popover: #020817;
                    --popover-foreground: #f8fafc;
                    --primary: #f8fafc;
                    --primary-foreground: #020817;
                    --secondary: #1e293b;
                    --secondary-foreground: #f8fafc;
                    --muted: #1e293b;
                    --muted-foreground: #94a3b8;
                    --accent: #1e293b;
                    --accent-foreground: #f8fafc;
                    --destructive: #ef4444;
                    --destructive-foreground: #f8fafc;
                    --border: #334155;
                    --input: #334155;
                    --ring: #f8fafc;
                }

                .sidebar-root {
                    font-family: 'Inter', sans-serif;
                }
                .sidebar {
                    position: fixed;
                    left: 0;
                    top: 0;
                    height: 100%;
                    width: 5.5rem;
                    background-color: var(--card);
                    border-right: 1px solid var(--border);
                    display: flex;
                    flex-direction: column;
                    padding: 1rem 0;
                    z-index: 1000;
                    overflow-y: auto;
                    overflow-x: hidden;
                    transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1), background-color 0.3s, border-color 0.3s;
                    scrollbar-width: none; /* Firefox */
                }
                .sidebar::-webkit-scrollbar {
                    display: none; /* Chrome, Safari, Opera */
                }
                .sidebar:hover {
                    width: 16rem;
                }
                .nav-text {
                    opacity: 0;
                    margin-left: 0.75rem;
                    font-weight: 500;
                    white-space: nowrap;
                    transition: opacity 0.2s, color 0.2s;
                    display: none; /* Hidden by default */
                }
                .sidebar:hover .nav-text {
                    opacity: 1;
                    display: block; /* Show on hover */
                }
                
                .nav-item {
                    position: relative;
                    display: flex;
                    align-items: center;
                    padding: 0.75rem 0;
                    margin: 0.25rem 0.75rem;
                    border-radius: 0.5rem;
                    color: var(--muted-foreground);
                    text-decoration: none;
                    transition: all 0.2s;
                    justify-content: center;
                }
                
                .sidebar:hover .nav-item {
                    justify-content: flex-start;
                    padding-left: 1rem;
                }

                .nav-item:hover {
                    background-color: var(--accent);
                    color: var(--foreground);
                }

                .nav-item.active {
                    background-color: var(--accent);
                    color: var(--foreground);
                    font-weight: 600;
                }

                /* Active indicator line */
                .nav-item.active::before {
                    content: '';
                    position: absolute;
                    left: 0;
                    top: 15%;
                    height: 70%;
                    width: 3px;
                    background-color: var(--foreground);
                    border-radius: 0 4px 4px 0;
                }

                /* Scrollbar hiding for sidebar content */
                .sidebar-content::-webkit-scrollbar {
                    display: none;
                }
                .sidebar-content {
                    -ms-overflow-style: none;
                    scrollbar-width: none;
                }

                /* Mobile Bottom Nav */
                @media (max-width: 768px) {
                    .sidebar {
                        width: 100%;
                        height: 4rem;
                        top: auto;
                        bottom: 0;
                        border-right: none;
                        border-top: 1px solid var(--border);
                        flex-direction: row;
                        padding: 0;
                    }
                    .sidebar:hover {
                        width: 100%;
                    }
                    .nav-text {
                        display: none !important;
                    }
                    .nav-item {
                        flex: 1;
                        justify-content: center !important;
                        margin: 0;
                        border-radius: 0;
                        padding: 0;
                    }
                    .nav-item.active::before {
                        top: 0;
                        left: 15%;
                        width: 70%;
                        height: 3px;
                        border-radius: 0 0 4px 4px;
                    }
                }

                /* Global Clock Styles */
                #oi-pro-global-clock {
                    position: fixed;
                    top: 0;
                    right: 2.5rem;
                    background: var(--card);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border: 1px solid var(--border);
                    border-top: none;
                    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
                    color: var(--muted-foreground);
                    font-size: 0.725rem;
                    font-weight: 600;
                    letter-spacing: 0.5px;
                    padding: 0.35rem 0.85rem 0.4rem 0.85rem;
                    border-radius: 0 0 0.5rem 0.5rem;
                    z-index: 9999;
                    pointer-events: none;
                    user-select: none;
                    font-family: inherit;
                    display: flex;
                    align-items: center;
                    gap: 0.4rem;
                }
            `;
            document.head.appendChild(style);
        }

        const isDark = document.documentElement.classList.contains('dark');

        // Build nav HTML
        // Derive user display info from JWT payload
        const userEmail = (payload && payload.sub) ? payload.sub : 'Unknown';
        const emailPrefix = userEmail.split('@')[0];
        const userInitials = emailPrefix.slice(0, 2).toUpperCase();
        const userDisplayName = userEmail.length > 22 ? userEmail.slice(0, 20) + '…' : userEmail;
        // Deterministic color derived from email string (stable across sessions)
        const AVATAR_COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#14b8a6'];
        const colorIdx = emailPrefix.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0) % AVATAR_COLORS.length;
        const userAvatarColor = AVATAR_COLORS[colorIdx];

        const navItemsHtml = NAV_ITEMS.map(function (item) {
            const isActive = item.href === "/"
                ? currentPath === "/"
                : currentPath === item.href || currentPath.startsWith(item.href + "/");

            return `<a href="${item.href}" class="nav-item ${isActive ? 'active' : ''}">` +
                `<div class="w-5 h-5 flex items-center justify-center shrink-0">` +
                `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">` +
                item.svg +
                `</svg>` +
                `</div>` +
                `<span class="nav-text">${item.title}</span>` +
                `</a>`;
        }).join('\n');

        const navHTML = `
            <nav class="sidebar">
                <div class="flex items-center justify-center h-12 mb-6 cursor-default">
                    <div class="w-8 h-8 rounded-lg bg-foreground flex items-center justify-center text-background font-bold text-lg shadow-md shrink-0">
                        OI
                    </div>
                    <span class="nav-text text-lg font-bold tracking-tight text-foreground">Pro Analytics</span>
                </div>

                <div class="sidebar-content flex-1 overflow-y-auto">
                    ${navItemsHtml}
                </div>

                <div class="mt-auto px-3 border-t border-border pt-4 flex flex-col gap-2">
                    <!-- User Identity Card -->
                    <div class="flex items-center gap-2.5 px-2 py-2 rounded-lg bg-muted/40 border border-border/50 mb-1 min-w-0 overflow-hidden" title="${payload && payload.sub ? payload.sub : 'Unknown'}">
                        <div class="w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-bold text-white" style="background:${userAvatarColor}">
                            ${userInitials}
                        </div>
                        <div class="nav-text flex flex-col min-w-0 flex-1">
                            <span class="text-xs font-medium text-foreground truncate leading-tight">${userDisplayName}</span>
                            <span class="text-[10px] px-1.5 py-0.5 rounded mt-0.5 inline-flex w-fit font-semibold ${isAdmin ? 'bg-amber-500/20 text-amber-400' : 'bg-blue-500/20 text-blue-400'}">${isAdmin ? 'Admin' : 'User'}</span>
                        </div>
                    </div>

                    <!-- Theme Toggle -->
                    <button id="theme-toggle" class="nav-item relative w-full group focus:outline-none">
                        <div class="w-5 h-5 flex items-center justify-center shrink-0">
                            ${isDark ?
                `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>`
                :
                `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`
            }
                        </div>
                        <span class="nav-text">${isDark ? 'Light Mode' : 'Dark Mode'}</span>
                    </button>

                    <button id="oi-pro-logout" class="nav-item relative w-full group text-destructive hover:text-destructive-foreground hover:bg-destructive/10 focus:outline-none">
                        <div class="w-5 h-5 flex items-center justify-center shrink-0">
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line>
                            </svg>
                        </div>
                        <span class="nav-text">Logout</span>
                    </button>
                </div>
            </nav>
        `;

        const root = document.getElementById('sidebar-root');
        if (root) {
            root.innerHTML = navHTML;
        } else {
            const div = document.createElement('div');
            div.className = 'sidebar-root'; // Add class for styling
            div.innerHTML = navHTML;
            document.body.insertBefore(div.firstChild, document.body.firstChild);
        }

        // Bind logout event
        const logoutBtn = document.getElementById('oi-pro-logout');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', function (e) {
                e.preventDefault();
                localStorage.removeItem('oi_pro_jwt');
                window.location.href = '/login';
            });
        }

        // Add event listener to the theme toggle button
        const themeToggleBtn = document.getElementById('theme-toggle');
        if (themeToggleBtn) {
            themeToggleBtn.addEventListener('click', toggleTheme);
        }
    }

    function initGlobalClock() {
        if (document.getElementById('oi-pro-global-clock')) return;

        const clockDiv = document.createElement('div');
        clockDiv.id = 'oi-pro-global-clock';
        // Add a small clock icon SVG internally
        const iconSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>';

        document.body.appendChild(clockDiv);

        function updateClock() {
            const now = new Date();
            const options = {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            };
            const timeStr = now.toLocaleDateString('en-GB', options).replace(',', '');
            clockDiv.innerHTML = iconSvg + '<span>' + timeStr + '</span>';
        }

        updateClock();
        setInterval(updateClock, 1000);
    }




    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            renderSidebar();
            initGlobalClock();
        });
    } else {
        renderSidebar();
        initGlobalClock();
    }
})();
