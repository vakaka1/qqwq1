import { useQuery } from "@tanstack/react-query";

import { apiRequest } from "../api/http";
import { Badge } from "../components/Badge";
import { useAuth } from "../features/auth/AuthProvider";
import type { TelegramUser } from "../lib/types";

export function UsersPage() {
  const { token } = useAuth();
  const { data, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => apiRequest<TelegramUser[]>("/users/", {}, token)
  });

  const users = data ?? [];
  const activeCount = users.filter((user) => user.status === "active").length;
  const expiredCount = users.filter((user) => user.status === "expired").length;

  return (
    <div className="page-content">
      <header className="page-titlebar">
        <h1>Пользователи</h1>
      </header>

      <div className="summary-strip">
        <section className="summary-card">
          <span>Всего</span>
          <strong>{users.length}</strong>
        </section>
        <section className="summary-card">
          <span>Активные</span>
          <strong>{activeCount}</strong>
        </section>
        <section className="summary-card">
          <span>Истекшие</span>
          <strong>{expiredCount}</strong>
        </section>
      </div>

      <section className="panel">
        {isLoading ? (
          <p>Загрузка...</p>
        ) : users.length === 0 ? (
          <p>Пользователей пока нет.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Username</th>
                  <th>Статус</th>
                  <th>Тест</th>
                  <th>Окончание теста</th>
                  <th>Регистрация</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>{user.telegram_user_id}</td>
                    <td>{user.username ?? "без username"}</td>
                    <td>
                      <Badge
                        tone={
                          user.status === "active"
                            ? "success"
                            : user.status === "expired"
                              ? "warning"
                              : "neutral"
                        }
                      >
                        {user.status}
                      </Badge>
                    </td>
                    <td>{user.trial_used ? "Да" : "Нет"}</td>
                    <td>{user.trial_ends_at ? new Date(user.trial_ends_at).toLocaleString("ru-RU") : "—"}</td>
                    <td>{new Date(user.registered_at).toLocaleString("ru-RU")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
