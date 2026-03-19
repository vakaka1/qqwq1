import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { apiRequest } from "../api/http";
import { useAuth } from "../features/auth/AuthProvider";
import type { SystemSettings } from "../lib/types";

const navItems = [
  { to: "/", label: "Обзор" },
  { to: "/servers", label: "Серверы" },
  { to: "/sites", label: "Сайты" },
  { to: "/accesses", label: "Доступы" },
  { to: "/bots", label: "Боты" },
  { to: "/users", label: "Пользователи" },
  { to: "/admins", label: "Администраторы" },
  { to: "/monetization", label: "Монетизация" },
  { to: "/settings", label: "Настройки" },
  { to: "/logs", label: "Журнал" }
];

export function AppShell() {
  const { admin, logout, token } = useAuth();
  const location = useLocation();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const { data: systemSettings } = useQuery({
    queryKey: ["system-settings"],
    queryFn: () => apiRequest<SystemSettings>("/system-settings/", {}, token),
    enabled: Boolean(token),
    staleTime: 30000
  });
  const appName = systemSettings?.app_name ?? "Панель управления";

  useEffect(() => {
    setIsSidebarOpen(false);
  }, [location.pathname]);

  return (
    <div className={`app-shell${isSidebarOpen ? " app-shell--menu-open" : ""}`}>
      <button
        className={`sidebar-backdrop${isSidebarOpen ? " sidebar-backdrop--visible" : ""}`}
        onClick={() => setIsSidebarOpen(false)}
        type="button"
        aria-label="Закрыть меню"
      />
      <aside className={`sidebar${isSidebarOpen ? " sidebar--open" : ""}`}>
        <div className="sidebar-main">
          <div className="brand-block">
            <span className="brand-mark" aria-hidden="true">
              <span />
            </span>
            <h1>{appName}</h1>
          </div>
          <nav className="nav-list">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) => `nav-item${isActive ? " nav-item--active" : ""}`}
                onClick={() => setIsSidebarOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <div className="sidebar-footer">
          <div className="sidebar-usercard">
            <span className="sidebar-user-label">Текущий администратор</span>
            <strong className="sidebar-user">{admin?.username}</strong>
          </div>
          <button className="secondary-button" onClick={logout} type="button">
            Выйти
          </button>
        </div>
      </aside>
      <main className="page-shell">
        <div className="mobile-toolbar">
          <button
            className="mobile-menu-button"
            onClick={() => setIsSidebarOpen((current) => !current)}
            type="button"
            aria-expanded={isSidebarOpen}
            aria-label="Открыть меню"
          >
            <span />
            <span />
            <span />
          </button>
          <div className="mobile-toolbar__title">
            <strong>{appName}</strong>
            <span>{admin?.username}</span>
          </div>
        </div>
        <div className="page-shell__inner">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
