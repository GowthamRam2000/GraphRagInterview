"use client";

import { Activity, Bot, Home, Info, MessageSquare } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const nav = [
  { href: "/", label: "Home", icon: Home },
  { href: "/about", label: "About", icon: Info },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/trace", label: "Trace", icon: Activity }
] as const;

export function AppNav() {
  const pathname = usePathname();
  return (
    <header className="app-nav">
      <Link className="brand-mark" href="/">
        <Bot size={18} />
        <span>CognizInterview Graph RAG</span>
      </Link>
      <nav className="nav-links" aria-label="Primary">
        {nav.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              className={active ? "nav-link active" : "nav-link"}
              href={item.href}
            >
              <Icon size={15} />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
