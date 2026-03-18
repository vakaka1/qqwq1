import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiRequest, ApiError } from "../api/http";
import { Badge } from "../components/Badge";
import { Modal } from "../components/Modal";
import { useToast } from "../components/ToastProvider";
import { useAuth } from "../features/auth/AuthProvider";
import type { Server, ServerCountryLookupResponse, ServerTestResult } from "../lib/types";

interface ServerFormState {
  name: string;
  country: string;
  host: string;
  scheme: string;
  port: string;
  panel_path: string;
  username: string;
  password: string;
}

const emptyForm: ServerFormState = {
  name: "",
  country: "",
  host: "",
  scheme: "http",
  port: "2053",
  panel_path: "",
  username: "",
  password: ""
};

function toForm(server: Server): ServerFormState {
  return {
    name: server.name,
    country: server.country,
    host: server.host,
    scheme: server.scheme,
    port: String(server.port),
    panel_path: server.panel_path,
    username: server.username ?? "",
    password: ""
  };
}

function normalizePanelPath(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }

  let normalized = trimmed;
  if (normalized.includes("://")) {
    try {
      normalized = new URL(normalized).pathname;
    } catch {
      normalized = trimmed;
    }
  }

  normalized = normalized.replace(/\/panel\/?$/i, "");
  if (normalized && !normalized.startsWith("/")) {
    normalized = `/${normalized}`;
  }
  normalized = normalized.replace(/\/+$/g, "");
  return normalized;
}

function buildPanelAddress(scheme: string, host: string, port: string | number, panelPath: string) {
  const normalizedHost = host.trim();
  const normalizedPort = String(port).trim();
  if (!normalizedHost || !normalizedPort) {
    return "—";
  }
  return `${scheme}://${normalizedHost}:${normalizedPort}${normalizePanelPath(panelPath)}/panel`;
}

function getHealthTone(status: string) {
  if (status === "healthy") {
    return "success" as const;
  }
  if (status === "error") {
    return "danger" as const;
  }
  return "neutral" as const;
}

function getHealthLabel(status: string) {
  if (status === "healthy") {
    return "готов";
  }
  if (status === "error") {
    return "ошибка";
  }
  return "не проверен";
}

export function ServersPage() {
  const { token } = useAuth();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingServer, setEditingServer] = useState<Server | null>(null);
  const [form, setForm] = useState<ServerFormState>(emptyForm);
  const [countryLookupResult, setCountryLookupResult] = useState<ServerCountryLookupResponse | null>(null);

  const { data: servers, isLoading } = useQuery({
    queryKey: ["servers"],
    queryFn: () => apiRequest<Server[]>("/servers/", {}, token)
  });

  const serverItems = servers ?? [];
  const healthyCount = serverItems.filter((server) => server.health_status === "healthy").length;
  const activeCount = serverItems.filter((server) => server.is_active).length;

  const resetModalState = () => {
    setEditingServer(null);
    setForm(emptyForm);
    setCountryLookupResult(null);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    resetModalState();
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name: form.name.trim(),
        country: form.country.trim(),
        region: null,
        host: form.host.trim(),
        public_host: null,
        scheme: form.scheme,
        port: Number(form.port),
        public_port: null,
        panel_path: normalizePanelPath(form.panel_path),
        username: form.username.trim(),
        password: form.password || undefined,
        inbound_id: null,
        client_flow: null,
        is_active: editingServer?.is_active ?? true,
        is_trial_enabled: editingServer?.is_trial_enabled ?? true,
        weight: editingServer?.weight ?? 1,
        notes: null,
        auto_configure: true
      };

      if (editingServer) {
        return apiRequest<Server>(
          `/servers/${editingServer.id}`,
          { method: "PUT", body: JSON.stringify(payload) },
          token
        );
      }

      return apiRequest<Server>("/servers/", { method: "POST", body: JSON.stringify(payload) }, token);
    },
    onSuccess: async () => {
      closeModal();
      pushToast("Сервер сохранен", "success");
      await queryClient.invalidateQueries({ queryKey: ["servers"] });
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось сохранить сервер", "danger");
    }
  });

  const lookupCountryMutation = useMutation({
    mutationFn: () =>
      apiRequest<ServerCountryLookupResponse>(
        "/servers/lookup-country",
        {
          method: "POST",
          body: JSON.stringify({ host: form.host.trim() })
        },
        token
      ),
    onSuccess: (result) => {
      setCountryLookupResult(result);
      setForm((current) => ({ ...current, country: result.country }));
      pushToast(`Страна определена: ${result.country}`, "success");
    },
    onError: (error) => {
      setCountryLookupResult(null);
      pushToast(error instanceof ApiError ? error.message : "Не удалось определить страну", "danger");
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (serverId: string) =>
      apiRequest<{ message: string }>(`/servers/${serverId}`, { method: "DELETE" }, token),
    onSuccess: async () => {
      pushToast("Сервер удален", "success");
      await queryClient.invalidateQueries({ queryKey: ["servers"] });
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось удалить сервер", "danger");
    }
  });

  const testMutation = useMutation({
    mutationFn: (serverId: string) =>
      apiRequest<ServerTestResult>(`/servers/${serverId}/test`, { method: "POST" }, token),
    onSuccess: async (result) => {
      const detail = [result.message, result.version ? `Xray ${result.version}` : null, `inbound: ${result.inbounds.length}`]
        .filter(Boolean)
        .join(" • ");
      pushToast(detail, result.ok ? "success" : "warning");
      await queryClient.invalidateQueries({ queryKey: ["servers"] });
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Проверка завершилась ошибкой", "danger");
    }
  });

  return (
    <div className="page-content">
      <header className="page-titlebar">
        <div>
          <h1>Серверы</h1>
        </div>
        <button
          className="primary-button"
          onClick={() => {
            resetModalState();
            setIsModalOpen(true);
          }}
          type="button"
        >
          Добавить сервер
        </button>
      </header>

      <div className="summary-strip">
        <section className="summary-card">
          <span>Всего</span>
          <strong>{serverItems.length}</strong>
        </section>
        <section className="summary-card">
          <span>Активные</span>
          <strong>{activeCount}</strong>
        </section>
        <section className="summary-card">
          <span>Подключены</span>
          <strong>{healthyCount}</strong>
        </section>
      </div>

      <section className="server-grid">
        {isLoading ? (
          <div className="panel">Загрузка...</div>
        ) : serverItems.length === 0 ? (
          <div className="panel">Серверы пока не добавлены.</div>
        ) : (
          serverItems.map((server) => (
            <article key={server.id} className="server-card">
              <div className="server-card__header">
                <div>
                  <h3>{server.name}</h3>
                  <p className="table-subtitle">{server.country}</p>
                </div>
                <Badge tone={getHealthTone(server.health_status)}>{getHealthLabel(server.health_status)}</Badge>
              </div>

              <dl className="meta-list">
                <div>
                  <dt>Адрес панели</dt>
                  <dd>{buildPanelAddress(server.scheme, server.host, server.port, server.panel_path)}</dd>
                </div>
                <div>
                  <dt>IP или домен</dt>
                  <dd>{server.host}</dd>
                </div>
                <div>
                  <dt>Путь панели</dt>
                  <dd>{normalizePanelPath(server.panel_path) || "стандартный"}</dd>
                </div>
                <div>
                  <dt>Логин</dt>
                  <dd>{server.username || "—"}</dd>
                </div>
                <div>
                  <dt>Статус</dt>
                  <dd>{server.is_active ? "включен" : "отключен"}</dd>
                </div>
                <div>
                  <dt>Проверен</dt>
                  <dd>{server.last_checked_at ? new Date(server.last_checked_at).toLocaleString("ru-RU") : "—"}</dd>
                </div>
              </dl>

              {server.last_error ? <p className="server-card__error">{server.last_error}</p> : null}

              <div className="table-actions">
                <button className="ghost-button" onClick={() => testMutation.mutate(server.id)} type="button">
                  Проверить
                </button>
                <button
                  className="ghost-button"
                  onClick={() => {
                    setEditingServer(server);
                    setForm(toForm(server));
                    setCountryLookupResult(null);
                    setIsModalOpen(true);
                  }}
                  type="button"
                >
                  Редактировать
                </button>
                <button
                  className="ghost-button danger-button"
                  onClick={() => deleteMutation.mutate(server.id)}
                  type="button"
                >
                  Удалить
                </button>
              </div>
            </article>
          ))
        )}
      </section>

      {isModalOpen ? (
        <Modal title={editingServer ? "Редактировать сервер" : "Новый сервер"} onClose={closeModal}>
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              saveMutation.mutate();
            }}
          >
            <label>
              <span>Название</span>
              <input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="Например, Германия 1"
                required
              />
            </label>

            <label>
              <span>Протокол</span>
              <select value={form.scheme} onChange={(event) => setForm({ ...form, scheme: event.target.value })}>
                <option value="http">HTTP</option>
                <option value="https">HTTPS</option>
              </select>
            </label>

            <label>
              <span>IP или домен</span>
              <input
                value={form.host}
                onChange={(event) => {
                  setCountryLookupResult(null);
                  setForm({ ...form, host: event.target.value });
                }}
                placeholder="1.2.3.4 или panel.example.com"
                required
              />
            </label>

            <label className="full-width">
              <span>Страна</span>
              <div className="input-with-action">
                <input
                  value={form.country}
                  onChange={(event) => setForm({ ...form, country: event.target.value })}
                  placeholder="Россия"
                  required
                />
                <button
                  className="secondary-button"
                  disabled={!form.host.trim() || lookupCountryMutation.isPending}
                  onClick={() => lookupCountryMutation.mutate()}
                  type="button"
                >
                  {lookupCountryMutation.isPending ? "Проверяем..." : "Проверить"}
                </button>
              </div>
              {countryLookupResult ? <span className="form-help">Определено по IP {countryLookupResult.resolved_ip}</span> : null}
            </label>

            <label>
              <span>Порт панели</span>
              <input
                inputMode="numeric"
                min="1"
                onChange={(event) => setForm({ ...form, port: event.target.value })}
                placeholder="2053"
                type="number"
                value={form.port}
                required
              />
            </label>

            <label>
              <span>Путь панели</span>
              <input
                value={form.panel_path}
                onChange={(event) => setForm({ ...form, panel_path: event.target.value })}
                placeholder="/secret"
              />
            </label>

            <div className="full-width inline-note">
              Если панель открывается по стандартному адресу, оставьте поле пустым. Если адрес вида
              {" "}
              <strong>https://host:2053/secret/panel</strong>
              , здесь нужно указать
              {" "}
              <strong>/secret</strong>
              .
            </div>

            <label>
              <span>Логин</span>
              <input
                value={form.username}
                onChange={(event) => setForm({ ...form, username: event.target.value })}
                required
              />
            </label>

            <label>
              <span>Пароль</span>
              <input
                value={form.password}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
                type="password"
                placeholder={editingServer?.has_password ? "Оставьте пустым, чтобы не менять" : ""}
                required={!editingServer}
              />
            </label>

            <div className="modal-footer">
              <button className="secondary-button" onClick={closeModal} type="button">
                Отмена
              </button>
              <button className="primary-button" disabled={saveMutation.isPending} type="submit">
                {saveMutation.isPending ? "Сохраняем..." : "Сохранить"}
              </button>
            </div>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
