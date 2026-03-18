import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiRequest, ApiError } from "../api/http";
import { Badge } from "../components/Badge";
import { Modal } from "../components/Modal";
import { useToast } from "../components/ToastProvider";
import { useAuth } from "../features/auth/AuthProvider";
import type { Access, AccessConfig, ManagedBot, Server } from "../lib/types";

interface AccessFormState {
  telegram_user_id: string;
  username: string;
  first_name: string;
  last_name: string;
  managed_bot_id: string;
  server_id: string;
  access_type: string;
  duration_hours: string;
  device_limit: string;
}

const emptyForm: AccessFormState = {
  telegram_user_id: "",
  username: "",
  first_name: "",
  last_name: "",
  managed_bot_id: "",
  server_id: "",
  access_type: "paid",
  duration_hours: "720",
  device_limit: "1"
};

function getStatusTone(status: string) {
  if (status === "active") {
    return "success" as const;
  }
  if (status === "expired") {
    return "warning" as const;
  }
  if (status === "disabled") {
    return "danger" as const;
  }
  return "neutral" as const;
}

function getStatusLabel(status: string) {
  if (status === "active") {
    return "активен";
  }
  if (status === "expired") {
    return "истек";
  }
  if (status === "disabled") {
    return "отключен";
  }
  if (status === "deleted") {
    return "удален";
  }
  return status;
}

function getTypeLabel(type: string) {
  if (type === "test") {
    return "тестовый";
  }
  if (type === "paid") {
    return "платный";
  }
  return type;
}

function normalizeUsername(value: string) {
  return value.trim().replace(/^@+/, "");
}

export function AccessesPage() {
  const { token } = useAuth();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [serverFilter, setServerFilter] = useState("");
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [form, setForm] = useState<AccessFormState>(emptyForm);
  const [config, setConfig] = useState<AccessConfig | null>(null);
  const [extendAccess, setExtendAccess] = useState<Access | null>(null);
  const [extendHours, setExtendHours] = useState("720");

  const { data: servers } = useQuery({
    queryKey: ["servers"],
    queryFn: () => apiRequest<Server[]>("/servers/", {}, token)
  });

  const { data: bots } = useQuery({
    queryKey: ["bots"],
    queryFn: () => apiRequest<ManagedBot[]>("/bots/", {}, token)
  });

  const { data: accesses, isLoading } = useQuery({
    queryKey: ["accesses", statusFilter, typeFilter, serverFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (typeFilter) params.set("access_type", typeFilter);
      if (serverFilter) params.set("server_id", serverFilter);
      return apiRequest<Access[]>(`/accesses/?${params.toString()}`, {}, token);
    }
  });

  const accessItems = accesses ?? [];
  const activeCount = accessItems.filter((item) => item.status === "active").length;
  const testCount = accessItems.filter((item) => item.access_type === "test").length;

  const closeCreateModal = () => {
    setIsCreateOpen(false);
    setForm(emptyForm);
  };

  const createMutation = useMutation({
    mutationFn: () => {
      if (form.telegram_user_id && !form.managed_bot_id) {
        throw new ApiError("Выберите бота для Telegram-доступа", 422);
      }
      return apiRequest<Access>(
        "/accesses/",
        {
          method: "POST",
          body: JSON.stringify({
            telegram_user_id: form.telegram_user_id ? Number(form.telegram_user_id) : null,
            username: normalizeUsername(form.username) || null,
            first_name: form.first_name.trim() || null,
            last_name: form.last_name.trim() || null,
            language_code: "ru",
            managed_bot_id: form.managed_bot_id || null,
            server_id: form.server_id,
            access_type: form.access_type,
            duration_hours: Number(form.duration_hours),
            device_limit: Number(form.device_limit),
            client_flow: null
          })
        },
        token
      );
    },
    onSuccess: async () => {
      closeCreateModal();
      pushToast("Доступ создан", "success");
      await queryClient.invalidateQueries({ queryKey: ["accesses"] });
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось создать доступ", "danger");
    }
  });

  const actionMutation = useMutation({
    mutationFn: async ({
      accessId,
      action,
      durationHours
    }: {
      accessId: string;
      action: "disable" | "delete" | "extend";
      durationHours?: number;
    }) => {
      if (action === "disable") {
        return apiRequest<Access>(`/accesses/${accessId}/disable`, { method: "POST" }, token);
      }
      if (action === "delete") {
        return apiRequest<{ message: string }>(`/accesses/${accessId}`, { method: "DELETE" }, token);
      }
      return apiRequest<Access>(
        `/accesses/${accessId}/extend`,
        { method: "POST", body: JSON.stringify({ duration_hours: durationHours }) },
        token
      );
    },
    onSuccess: async () => {
      setExtendAccess(null);
      setExtendHours("720");
      await queryClient.invalidateQueries({ queryKey: ["accesses"] });
      pushToast("Операция выполнена", "success");
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось выполнить операцию", "danger");
    }
  });

  const configMutation = useMutation({
    mutationFn: (accessId: string) => apiRequest<AccessConfig>(`/accesses/${accessId}/config`, {}, token),
    onSuccess: (payload) => setConfig(payload)
  });

  return (
    <div className="page-content">
      <header className="page-titlebar">
        <div>
          <h1>Доступы</h1>
        </div>
        <button
          className="primary-button"
          onClick={() => {
            setForm({
              ...emptyForm,
              server_id: servers?.[0]?.id ?? "",
              managed_bot_id: bots?.[0]?.id ?? ""
            });
            setIsCreateOpen(true);
          }}
          type="button"
        >
          Создать доступ
        </button>
      </header>

      <div className="summary-strip">
        <section className="summary-card">
          <span>Всего</span>
          <strong>{accessItems.length}</strong>
        </section>
        <section className="summary-card">
          <span>Активные</span>
          <strong>{activeCount}</strong>
        </section>
        <section className="summary-card">
          <span>Тестовые</span>
          <strong>{testCount}</strong>
        </section>
      </div>

      <section className="panel filter-bar">
        <label>
          <span>Статус</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">Все</option>
            <option value="active">Активные</option>
            <option value="expired">Истекшие</option>
            <option value="disabled">Отключенные</option>
            <option value="deleted">Удаленные</option>
          </select>
        </label>
        <label>
          <span>Тип</span>
          <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
            <option value="">Все</option>
            <option value="test">Тестовый</option>
            <option value="paid">Платный</option>
          </select>
        </label>
        <label>
          <span>Сервер</span>
          <select value={serverFilter} onChange={(event) => setServerFilter(event.target.value)}>
            <option value="">Все</option>
            {(servers ?? []).map((server) => (
              <option key={server.id} value={server.id}>
                {server.name}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="panel">
        {isLoading ? (
          <p>Загрузка...</p>
        ) : accessItems.length === 0 ? (
          <p>Доступы пока не созданы.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Клиент</th>
                  <th>Сервер</th>
                  <th>Тип</th>
                  <th>Статус</th>
                  <th>Окончание</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {accessItems.map((access) => (
                  <tr key={access.id}>
                    <td>
                      <strong>{access.client_email}</strong>
                      <div className="table-subtitle">
                        {access.telegram_user ? `Telegram ${access.telegram_user.telegram_user_id}` : "без Telegram"}
                        {access.managed_bot ? ` • ${access.managed_bot.name}` : ""}
                      </div>
                    </td>
                    <td>{access.server.name}</td>
                    <td>{getTypeLabel(access.access_type)}</td>
                    <td>
                      <Badge tone={getStatusTone(access.status)}>{getStatusLabel(access.status)}</Badge>
                    </td>
                    <td>{new Date(access.expiry_at).toLocaleString("ru-RU")}</td>
                    <td className="table-actions">
                      <button
                        className="ghost-button"
                        onClick={() => {
                          setExtendAccess(access);
                          setExtendHours("720");
                        }}
                        type="button"
                      >
                        Продлить
                      </button>
                      <button className="ghost-button" onClick={() => configMutation.mutate(access.id)} type="button">
                        Конфиг
                      </button>
                      <button
                        className="ghost-button"
                        onClick={() => actionMutation.mutate({ accessId: access.id, action: "disable" })}
                        type="button"
                      >
                        Отключить
                      </button>
                      <button
                        className="ghost-button danger-button"
                        onClick={() => actionMutation.mutate({ accessId: access.id, action: "delete" })}
                        type="button"
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {isCreateOpen ? (
        <Modal title="Создать доступ" onClose={closeCreateModal}>
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              createMutation.mutate();
            }}
          >
            <div className="full-width inline-note">
              Для Telegram-доступа выберите конкретного бота. Тогда доступ будет виден только в нем.
            </div>

            <label>
              <span>Telegram ID</span>
              <input
                inputMode="numeric"
                onChange={(event) => setForm({ ...form, telegram_user_id: event.target.value })}
                placeholder="5577591390"
                type="number"
                value={form.telegram_user_id}
              />
            </label>

            <label>
              <span>Юзернейм</span>
              <input
                value={form.username}
                onChange={(event) => setForm({ ...form, username: event.target.value })}
                placeholder="@username"
              />
            </label>

            <label>
              <span>Имя</span>
              <input value={form.first_name} onChange={(event) => setForm({ ...form, first_name: event.target.value })} />
            </label>

            <label>
              <span>Фамилия</span>
              <input value={form.last_name} onChange={(event) => setForm({ ...form, last_name: event.target.value })} />
            </label>

            <label>
              <span>Бот</span>
              <select
                value={form.managed_bot_id}
                onChange={(event) => setForm({ ...form, managed_bot_id: event.target.value })}
              >
                <option value="">Без бота</option>
                {(bots ?? [])
                  .filter((bot) => bot.is_active)
                  .map((bot) => (
                    <option key={bot.id} value={bot.id}>
                      {bot.name}
                    </option>
                  ))}
              </select>
            </label>

            <label>
              <span>Сервер</span>
              <select value={form.server_id} onChange={(event) => setForm({ ...form, server_id: event.target.value })} required>
                <option value="">Выберите сервер</option>
                {(servers ?? []).map((server) => (
                  <option key={server.id} value={server.id}>
                    {server.name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>Тип доступа</span>
              <select value={form.access_type} onChange={(event) => setForm({ ...form, access_type: event.target.value })}>
                <option value="paid">Платный</option>
                <option value="test">Тестовый</option>
              </select>
            </label>

            <label>
              <span>Срок, часов</span>
              <input
                inputMode="numeric"
                min="1"
                onChange={(event) => setForm({ ...form, duration_hours: event.target.value })}
                type="number"
                value={form.duration_hours}
                required
              />
            </label>

            <label>
              <span>Устройств</span>
              <input
                inputMode="numeric"
                min="1"
                onChange={(event) => setForm({ ...form, device_limit: event.target.value })}
                type="number"
                value={form.device_limit}
                required
              />
            </label>

            <div className="modal-footer">
              <button className="secondary-button" onClick={closeCreateModal} type="button">
                Отмена
              </button>
              <button className="primary-button" disabled={createMutation.isPending} type="submit">
                {createMutation.isPending ? "Создаем..." : "Создать"}
              </button>
            </div>
          </form>
        </Modal>
      ) : null}

      {extendAccess ? (
        <Modal title="Продлить доступ" onClose={() => setExtendAccess(null)}>
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              actionMutation.mutate({
                accessId: extendAccess.id,
                action: "extend",
                durationHours: Number(extendHours)
              });
            }}
          >
            <div className="full-width inline-note">{extendAccess.client_email}</div>
            <label>
              <span>Часов</span>
              <input
                inputMode="numeric"
                min="1"
                onChange={(event) => setExtendHours(event.target.value)}
                type="number"
                value={extendHours}
                required
              />
            </label>
            <div className="modal-footer">
              <button className="secondary-button" onClick={() => setExtendAccess(null)} type="button">
                Отмена
              </button>
              <button className="primary-button" disabled={actionMutation.isPending} type="submit">
                {actionMutation.isPending ? "Сохраняем..." : "Продлить"}
              </button>
            </div>
          </form>
        </Modal>
      ) : null}

      {config ? (
        <Modal title="Конфигурация доступа" onClose={() => setConfig(null)}>
          <div className="config-preview">
            <p className="muted">Доступ ID: {config.access_id}</p>
            <p className="muted">Истекает: {new Date(config.expires_at).toLocaleString("ru-RU")}</p>
            <textarea readOnly rows={6} value={config.config_text} />
            <textarea readOnly rows={6} value={config.config_uri} />
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
