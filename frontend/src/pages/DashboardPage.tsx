import { useQuery } from "@tanstack/react-query";

import { apiRequest } from "../api/http";
import { StatCard } from "../components/StatCard";
import { useAuth } from "../features/auth/AuthProvider";
import type { DashboardSummary } from "../lib/types";

export function DashboardPage() {
  const { token } = useAuth();
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => apiRequest<DashboardSummary>("/dashboard/summary", {}, token)
  });

  if (isLoading || !data) {
    return (
      <div className="page-content">
        <header className="page-titlebar">
          <h1>Обзор</h1>
        </header>
        <div className="panel">Загрузка...</div>
      </div>
    );
  }

  return (
    <div className="page-content">
      <header className="page-titlebar">
        <h1>Обзор</h1>
      </header>

      <div className="stat-grid">
        <StatCard label="Серверы" value={data.total_servers} accent="linear-gradient(135deg,#111827,#475569)" />
        <StatCard label="Активные серверы" value={data.active_servers} accent="linear-gradient(135deg,#0f766e,#14b8a6)" />
        <StatCard label="Боты" value={data.total_bots} accent="linear-gradient(135deg,#2563eb,#60a5fa)" />
        <StatCard label="Активные боты" value={data.active_bots} accent="linear-gradient(135deg,#1d4ed8,#93c5fd)" />
        <StatCard label="Активные доступы" value={data.active_clients} accent="linear-gradient(135deg,#0f172a,#64748b)" />
        <StatCard label="Тестовые доступы" value={data.test_clients} accent="linear-gradient(135deg,#b45309,#f59e0b)" />
        <StatCard label="Истекшие" value={data.expired_accesses} accent="linear-gradient(135deg,#991b1b,#ef4444)" />
        <StatCard label="Пользователи" value={data.total_users} accent="linear-gradient(135deg,#334155,#94a3b8)" />
      </div>

      <div className="summary-strip">
        <section className="summary-card">
          <span>Серверы online</span>
          <strong>{data.active_servers}</strong>
        </section>
        <section className="summary-card">
          <span>Активные боты</span>
          <strong>{data.active_bots}</strong>
        </section>
        <section className="summary-card">
          <span>Активные доступы</span>
          <strong>{data.active_clients}</strong>
        </section>
      </div>
    </div>
  );
}
