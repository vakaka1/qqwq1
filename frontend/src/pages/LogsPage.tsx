import { useQuery } from "@tanstack/react-query";

import { apiRequest } from "../api/http";
import { Badge } from "../components/Badge";
import { useAuth } from "../features/auth/AuthProvider";
import type { AuditLog } from "../lib/types";

export function LogsPage() {
  const { token } = useAuth();
  const { data, isLoading } = useQuery({
    queryKey: ["logs"],
    queryFn: () => apiRequest<AuditLog[]>("/logs/", {}, token)
  });

  const logs = data ?? [];
  const errorCount = logs.filter((item) => item.level === "error").length;

  return (
    <div className="page-content">
      <header className="page-titlebar">
        <h1>Журнал</h1>
      </header>

      <div className="summary-strip">
        <section className="summary-card">
          <span>Записей</span>
          <strong>{logs.length}</strong>
        </section>
        <section className="summary-card">
          <span>Ошибки</span>
          <strong>{errorCount}</strong>
        </section>
      </div>

      <section className="panel">
        {isLoading ? (
          <p>Загрузка...</p>
        ) : logs.length === 0 ? (
          <p>Записей пока нет.</p>
        ) : (
          <div className="activity-list">
            {logs.map((log) => (
              <article key={log.id} className="activity-item">
                <div className="activity-item__top">
                  <div>
                    <strong>{log.message}</strong>
                    <p className="table-subtitle">
                      {log.event_type} · {log.actor_type} · {log.entity_type}
                      {log.entity_id ? ` / ${log.entity_id}` : ""}
                    </p>
                  </div>
                  <Badge
                    tone={
                      log.level === "error"
                        ? "danger"
                        : log.level === "warning"
                          ? "warning"
                          : "neutral"
                    }
                  >
                    {log.level}
                  </Badge>
                </div>
                <span className="activity-time">{new Date(log.created_at).toLocaleString("ru-RU")}</span>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
