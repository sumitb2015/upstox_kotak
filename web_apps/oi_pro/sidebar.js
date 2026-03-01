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
        const currentPath = window.location.pathname;

        // Inject Styles
        if (!document.getElementById('sidebar-styles')) {
            const style = document.createElement('style');
            style.id = 'sidebar-styles';
            style.innerHTML = `
                .oi-pro-sidebar {
                    position: fixed;
                    left: 0;
                    top: 0;
                    height: 100%;
                    width: 5.5rem;
                    background: #0b0f1a;
                    border-right: 1px solid rgba(51, 65, 85, 0.4);
                    display: flex;
                    flex-direction: column;
                    align-items: flex-start;
                    padding: 1.5rem 0.75rem;
                    gap: 1.25rem;
                    z-index: 1000;
                    overflow-y: auto;
                    overflow-x: hidden;
                    transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1), background 0.3s;
                    scrollbar-width: thin;
                    scrollbar-color: #1e293b transparent;
                }

                .oi-pro-sidebar:hover {
                    width: 18rem;
                    background: #0f172a;
                    box-shadow: 20px 0 50px rgba(0,0,0,0.5);
                }

                .nav-item {
                    display: flex;
                    align-items: center;
                    width: 100%;
                    min-height: 3rem;
                    padding: 0 0.85rem;
                    border-radius: 0.75rem;
                    text-decoration: none;
                    transition: all 0.2s ease;
                    white-space: nowrap;
                    overflow: hidden;
                    gap: 1.25rem;
                }

                .nav-item-icon {
                    flex-shrink: 0;
                    width: 2.5rem;
                    height: 2.5rem;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: 0.625rem;
                    transition: transform 0.2s;
                }

                .nav-label {
                    opacity: 0;
                    transform: translateX(-15px);
                    transition: opacity 0.2s ease 0.1s, transform 0.2s ease 0.1s;
                    font-size: 0.9rem;
                    font-weight: 600;
                    color: #94a3b8;
                }

                .oi-pro-sidebar:hover .nav-label {
                    opacity: 1;
                    transform: translateX(0);
                }

                .nav-item.active .nav-label {
                    color: white;
                }
                
                .nav-item:hover .nav-label {
                    color: #10b981;
                }
                
                .nav-item:hover .nav-item-icon {
                    transform: scale(1.05);
                }

                /* Active/Inactive states */
                .nav-item.active .nav-item-icon {
                    background: #10b981;
                    box-shadow: 0 0 15px rgba(16,185,129,0.4);
                    color: white;
                }
                
                .nav-item.inactive .nav-item-icon {
                    background: rgba(30, 41, 59, 0.5);
                    color: #64748b;
                }
                
                .nav-item.inactive:hover .nav-item-icon {
                    background: rgba(16,185,129,0.15);
                    color: #10b981;
                }

                /* Hide scrollbar */
                .oi-pro-sidebar::-webkit-scrollbar { width: 4px; }
                .oi-pro-sidebar::-webkit-scrollbar-track { background: transparent; }
                .oi-pro-sidebar::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 10px; }

                /* Global Clock Styles */
                #oi-pro-global-clock {
                    position: fixed;
                    top: 0;
                    right: 2.5rem;
                    background: rgba(15, 23, 42, 0.9);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border: 1px solid rgba(51, 65, 85, 0.6);
                    border-top: none;
                    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
                    color: #94a3b8;
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

        // Build nav HTML
        const itemsHTML = NAV_ITEMS.map(function (item) {
            const isActive = item.href === "/"
                ? currentPath === "/"
                : currentPath === item.href || currentPath.startsWith(item.href + "/");

            const strokeColor = isActive ? "white" : "currentColor";

            return '<a href="' + item.href + '" class="nav-item ' + (isActive ? 'active' : 'inactive') + '">' +
                '<div class="nav-item-icon">' +
                '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="' + strokeColor + '" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
                item.svg +
                '</svg>' +
                '</div>' +
                '<span class="nav-label">' + item.title + '</span>' +
                '</a>';
        }).join('\n');

        const logoutHTML = '<a href="#" id="oi-pro-logout" class="nav-item inactive mt-auto" style="margin-top: auto; border-top: 1px solid rgba(51, 65, 85, 0.4); border-radius: 0; padding-top: 1.25rem;">' +
            '<div class="nav-item-icon">' +
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line>' +
            '</svg>' +
            '</div>' +
            '<span class="nav-label" style="color: #ef4444;">Logout</span>' +
            '</a>';

        const navHTML = '<nav class="oi-pro-sidebar">' +
            itemsHTML +
            logoutHTML +
            '</nav>';

        const root = document.getElementById('sidebar-root');
        if (root) {
            root.innerHTML = navHTML;
        } else {
            const div = document.createElement('div');
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
