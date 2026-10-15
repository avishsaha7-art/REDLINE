"use client";

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export interface NavItem {
  name: string;
  href: string;
  icon: string;
  badge?: string;
}

export const NAV_SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "CORE WORKFLOW",
    items: [
      { name: "New Task", href: "/", icon: "⚡", badge: "Intake" },
      { name: "Mission Control", href: "/sessions", icon: "🛰️", badge: "Live" },
      { name: "Run Results", href: "/results", icon: "📊", badge: "Verdicts" },
      { name: "Evidence & Diffs", href: "/evidence", icon: "🛡️", badge: "Audit" },
    ]
  },
  {
    title: "OVERVIEW & AUDIT",
    items: [
      { name: "Dashboard", href: "/dashboard", icon: "📈" },
      { name: "Session History", href: "/history", icon: "📜" },
      { name: "Projects", href: "/projects", icon: "📁", badge: "Demo" },
      { name: "Repositories", href: "/repositories", icon: "🗄️", badge: "Ref" },
    ]
  },
  {
    title: "PLATFORM & ENGINE",
    items: [
      { name: "Agents", href: "/agents", icon: "🤖", badge: "Specs" },
      { name: "Playground", href: "/playground", icon: "🧪", badge: "Lab" },
      { name: "Models", href: "/models", icon: "🧠", badge: "Specs" },
      { name: "Settings", href: "/settings", icon: "⚙️", badge: "Config" },
    ]
  }
];

// High-fidelity SVG icons tailored to security & developer operations
const NavIconSvg: React.FC<{ href: string; className?: string }> = ({ href, className = "w-4 h-4" }) => {
  switch (href) {
    case '/':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
        </svg>
      );
    case '/sessions':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <circle cx="12" cy="12" r="9" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 7v5l3 3" />
        </svg>
      );
    case '/results':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      );
    case '/evidence':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      );
    case '/dashboard':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
      );
    case '/history':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    case '/projects':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
        </svg>
      );
    case '/repositories':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      );
    case '/agents':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
        </svg>
      );
    case '/playground':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
        </svg>
      );
    case '/models':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
        </svg>
      );
    case '/settings':
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      );
    default:
      return null;
  }
};

export const NavigationSidebar: React.FC = () => {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Close mobile drawer on escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMobileOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const isActive = (href: string) => {
    if (href === '/') {
      return pathname === '/';
    }
    // Nested run result route handling
    if (href === '/results' && pathname.startsWith('/runs')) {
      return true;
    }
    return pathname.startsWith(href);
  };

  const navContent = (
    <div className="flex flex-col h-full bg-[#0d0e12] border-r border-[#222430] text-[#a1a1aa] select-none">
      {/* Brand Header */}
      <div className="p-4 border-b border-[#222430] bg-[#0d0e12]">
        <Link 
          href="/" 
          className="flex items-center gap-3 group focus-visible:ring-2 focus-visible:ring-[#ef4444] rounded p-1.5 -m-1.5 focus-visible:outline-none"
          onClick={() => setMobileOpen(false)}
        >
          <div className="w-8 h-8 rounded bg-gradient-to-br from-[#ef4444] via-[#dc2626] to-[#7f1d1d] flex items-center justify-center font-black text-white text-base shadow-[0_0_12px_rgba(239,68,68,0.35)] group-hover:shadow-[0_0_18px_rgba(239,68,68,0.5)] border border-[#ef4444]/40 transition-shadow">
            R
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5">
              <span className="font-black text-lg tracking-wider text-[#f4f4f5]">REDLINE</span>
              <span className="text-[9px] font-mono font-bold text-[#fca5a5] bg-[#ef4444]/15 px-1.5 py-0.5 rounded border border-[#ef4444]/30">
                v1.1
              </span>
            </div>
            <p className="text-[10px] text-[#71717a] font-mono tracking-tight">
              Adversarial Verification
            </p>
          </div>
        </Link>
      </div>

      {/* Nav List */}
      <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-5" aria-label="Main Navigation">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title} className="space-y-1">
            <h2 className="px-2.5 text-[10px] font-mono font-bold tracking-wider text-[#71717a] uppercase flex items-center gap-1.5">
              <span className="w-1 h-1 rounded-sm bg-[#ef4444]/60"></span>
              {section.title}
            </h2>
            <ul className="space-y-0.5" role="list">
              {section.items.map((item) => {
                const active = isActive(item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={() => setMobileOpen(false)}
                      aria-current={active ? "page" : undefined}
                      className={`flex items-center justify-between px-2.5 py-2 rounded text-xs font-medium transition-all ${
                        active
                          ? 'bg-[#13141b] text-white border border-[#222430] border-l-2 border-l-[#ef4444] shadow-[0_0_12px_rgba(239,68,68,0.18)]'
                          : 'text-[#a1a1aa] hover:text-[#f4f4f5] hover:bg-[#13141b]/80 border border-transparent hover:border-[#222430]/60'
                      } focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none`}
                    >
                      <div className="flex items-center gap-2.5">
                        <span className={`${active ? 'text-[#ef4444]' : 'text-[#71717a] group-hover:text-[#a1a1aa]'} transition-colors`}>
                          <NavIconSvg href={item.href} />
                        </span>
                        <span className={active ? 'font-semibold text-white' : 'text-[#a1a1aa]'}>
                          {item.name}
                        </span>
                      </div>
                      {item.badge && (
                        <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded font-semibold ${
                          active
                            ? 'bg-[#ef4444]/15 text-[#fca5a5] border border-[#ef4444]/30 shadow-sm'
                            : 'bg-[#13141b] text-[#71717a] border border-[#222430]'
                        }`}>
                          {item.badge}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Authority & Security Policy Footer */}
      <div className="p-3.5 pb-5 border-t border-[#222430] bg-[#09090b] space-y-1.5 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[#10b981] motion-safe:animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.3)]"></span>
          <span className="text-[10px] font-mono font-semibold text-[#a1a1aa]">BACKEND ORCHESTRATOR</span>
        </div>
        <p className="text-[10px] text-[#71717a] leading-tight">
          Deterministic verifier is sole authority. AI-generated code is guilty until proven safe.
        </p>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile Top Navbar with Hamburger */}
      <div className="lg:hidden sticky top-0 z-40 bg-[#0d0e12] border-b border-[#222430] px-4 py-2.5 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-7 h-7 rounded bg-[#ef4444] flex items-center justify-center font-black text-white text-xs shadow-sm">
            R
          </div>
          <div className="flex items-center gap-1.5">
            <span className="font-black text-base tracking-wider text-[#f4f4f5]">REDLINE</span>
            <span className="text-[9px] font-mono text-[#fca5a5] bg-[#ef4444]/15 px-1 py-0.5 rounded border border-[#ef4444]/30">
              v1.1
            </span>
          </div>
        </Link>

        <button
          type="button"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-expanded={mobileOpen}
          aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
          className="p-2 rounded bg-[#13141b] text-[#f4f4f5] hover:text-white border border-[#222430] focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none"
        >
          {mobileOpen ? (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          )}
        </button>
      </div>

      {/* Mobile Drawer Backdrop */}
      {mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-black/80 backdrop-blur-sm transition-opacity"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Mobile Drawer Panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Mobile Navigation Menu"
        className={`lg:hidden fixed top-0 left-0 bottom-0 z-50 w-64 transform transition-transform duration-200 ease-in-out shadow-2xl ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {navContent}
      </div>

      {/* Desktop Persistent Sidebar */}
      <aside className="hidden lg:block w-64 flex-shrink-0 h-screen sticky top-0">
        {navContent}
      </aside>
    </>
  );
};

