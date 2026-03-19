import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { apiRequest, ApiError } from "../api/http";
import { Badge } from "../components/Badge";
import { Modal } from "../components/Modal";
import { useToast } from "../components/ToastProvider";
import { useAuth } from "../features/auth/AuthProvider";
import type {
  ManagedBot,
  Site,
  SiteConnectionProbeResult,
  SiteDeleteResult,
  SiteDeploymentPlan,
  SitePreviewResult,
  SiteTemplate
} from "../lib/types";

type AccessMode = "root" | "sudo";
type PublishMode = "ip" | "domain" | "cloudflare_tunnel";
type WizardStep = 1 | 2 | 3 | 4;

interface ConnectionState {
  access_mode: AccessMode;
  host: string;
  port: string;
  username: string;
  password: string;
}

interface SettingsState {
  name: string;
  managed_bot_id: string;
  publish_mode: PublishMode;
  domain: string;
  proxy_port: string;
}

interface TemplateState {
  key: string;
}

const stepLabels: Record<WizardStep, string> = {
  1: "Сервер",
  2: "Сайт",
  3: "Шаблон",
  4: "Запуск"
};

const stepDescriptions: Record<WizardStep, string> = {
  1: "Укажите SSH-доступ к серверу и проверьте подключение.",
  2: "Задайте основные параметры сайта и способ публикации.",
  3: "Выберите шаблон. Предпросмотр можно открыть только при необходимости.",
  4: "Проверьте итоговые параметры и запустите развертывание."
};

const emptyConnection: ConnectionState = {
  access_mode: "root",
  host: "",
  port: "22",
  username: "root",
  password: ""
};

const emptySettings: SettingsState = {
  name: "",
  managed_bot_id: "",
  publish_mode: "ip",
  domain: "",
  proxy_port: "5000"
};

const emptyTemplate: TemplateState = {
  key: ""
};

function normalizeHost(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  try {
    return new URL(trimmed).hostname;
  } catch {
    const withoutPath = trimmed.split("/")[0];
    if (withoutPath.startsWith("[") || withoutPath.split(":").length > 2) {
      return withoutPath;
    }
    return withoutPath.split(":")[0];
  }
}

function normalizeDomain(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  try {
    return new URL(trimmed).hostname.toLowerCase();
  } catch {
    return trimmed.split("/")[0].split(":")[0].replace(/\.$/, "").toLowerCase();
  }
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

function getStatusTone(status: string) {
  if (status === "deployed") {
    return "success" as const;
  }
  if (status === "error") {
    return "danger" as const;
  }
  return "warning" as const;
}

function getStatusLabel(status: string) {
  if (status === "deployed") {
    return "развернут";
  }
  if (status === "error") {
    return "ошибка";
  }
  return "черновик";
}

function getSslLabel(mode: string) {
  if (mode === "cloudflare") {
    return "Cloudflare edge HTTPS";
  }
  return mode === "letsencrypt" ? "Let's Encrypt" : "self-signed";
}

function getPublishModeLabel(mode: string) {
  if (mode === "domain") {
    return "Свой домен";
  }
  if (mode === "cloudflare_tunnel") {
    return "Cloudflare Tunnel";
  }
  return "По IP";
}

function getPublishModeHint(mode: PublishMode) {
  if (mode === "domain") {
    return "HTTPS на вашем домене.";
  }
  if (mode === "cloudflare_tunnel") {
    return "HTTPS без домена через trycloudflare.com.";
  }
  return "Быстрый запуск прямо по IP сервера.";
}

function getSnapshotWarnings(snapshot: Record<string, unknown>) {
  const warnings = snapshot.warnings;
  if (!Array.isArray(warnings)) {
    return [] as string[];
  }
  return warnings.filter((item): item is string => typeof item === "string");
}

export function SitesPage() {
  const { token } = useAuth();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState<WizardStep>(1);
  const [connection, setConnection] = useState<ConnectionState>(emptyConnection);
  const [settings, setSettings] = useState<SettingsState>(emptySettings);
  const [template, setTemplate] = useState<TemplateState>(emptyTemplate);
  const [probeResult, setProbeResult] = useState<SiteConnectionProbeResult | null>(null);
  const [preview, setPreview] = useState<SitePreviewResult | null>(null);
  const previewWindowRef = useRef<Window | null>(null);

  const { data: siteData, isLoading } = useQuery({
    queryKey: ["sites"],
    queryFn: () => apiRequest<Site[]>("/sites/", {}, token)
  });
  const { data: botData } = useQuery({
    queryKey: ["bots"],
    queryFn: () => apiRequest<ManagedBot[]>("/bots/", {}, token)
  });
  const { data: templateData } = useQuery({
    queryKey: ["site-templates"],
    queryFn: () => apiRequest<SiteTemplate[]>("/sites/templates", {}, token)
  });

  const sites = siteData ?? [];
  const bots = botData ?? [];
  const templates = templateData ?? [];
  const activeBots = bots.filter((item) => item.is_active);
  const publicBots = activeBots.filter((item) => Boolean(item.telegram_bot_username));
  const deployedCount = sites.filter((site) => site.deployment_status === "deployed").length;
  const errorCount = sites.filter((site) => site.deployment_status === "error").length;
  const activeTemplate = templates.find((item) => item.key === template.key) ?? null;
  const selectedBot = publicBots.find((item) => item.id === settings.managed_bot_id) ?? null;
  const normalizedHost = normalizeHost(connection.host);
  const normalizedDomain = normalizeDomain(settings.domain);
  const canCheckConnection = Boolean(
    normalizedHost &&
      connection.username.trim() &&
      connection.password &&
      Number(connection.port) >= 1 &&
      Number(connection.port) <= 65535
  );
  const previewAddress =
    settings.publish_mode === "domain" && normalizedDomain
      ? `https://${normalizedDomain}`
      : settings.publish_mode === "cloudflare_tunnel"
        ? "https://<случайный>.trycloudflare.com"
        : normalizedHost
          ? `https://${normalizedHost}`
          : "Будет определен после проверки";

  useEffect(() => {
    if (!template.key && templates.length > 0) {
      setTemplate({ key: templates[0].key });
    }
  }, [template.key, templates]);

  const resetWizard = () => {
    setCurrentStep(1);
    setConnection(emptyConnection);
    setSettings(emptySettings);
    setTemplate(templates.length > 0 ? { key: templates[0].key } : emptyTemplate);
    setProbeResult(null);
    setPreview(null);
    planMutation.reset();
  };

  const closeModal = () => {
    setIsModalOpen(false);
    resetWizard();
  };

  const buildPayload = () => ({
    connection: {
      access_mode: connection.access_mode,
      host: normalizedHost,
      port: Number(connection.port),
      username: connection.username.trim(),
      password: connection.password
    },
    settings: {
      name: settings.name.trim(),
      managed_bot_id: settings.managed_bot_id,
      publish_mode: settings.publish_mode,
      domain: settings.publish_mode === "domain" ? normalizedDomain || null : null,
      proxy_port: Number(settings.proxy_port)
    },
    template: {
      key: template.key
    }
  });

  const openPreviewWindow = (html: string) => {
    const currentWindow = previewWindowRef.current;
    const previewWindow =
      currentWindow && !currentWindow.closed
        ? currentWindow
        : window.open("", "site-template-preview", "width=1280,height=860,resizable=yes,scrollbars=yes");

    if (!previewWindow) {
      throw new Error("Браузер заблокировал окно предпросмотра. Разрешите pop-up для этой страницы.");
    }

    previewWindowRef.current = previewWindow;
    previewWindow.document.open();
    previewWindow.document.write(html);
    previewWindow.document.close();
    previewWindow.focus();
  };

  const openPreviewLoadingWindow = () => {
    const currentWindow = previewWindowRef.current;
    const previewWindow =
      currentWindow && !currentWindow.closed
        ? currentWindow
        : window.open("", "site-template-preview", "width=1280,height=860,resizable=yes,scrollbars=yes");

    if (!previewWindow) {
      throw new Error("Браузер заблокировал окно предпросмотра. Разрешите pop-up для этой страницы.");
    }

    previewWindowRef.current = previewWindow;
    previewWindow.document.open();
    previewWindow.document.write(`<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Предпросмотр сайта</title>
    <style>
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: linear-gradient(180deg, #f8fafc, #ffffff);
        color: #0f172a;
        font: 16px/1.5 system-ui, sans-serif;
      }
      .preview-loader {
        display: grid;
        gap: 12px;
        width: min(420px, calc(100vw - 32px));
        padding: 24px;
        border: 1px solid rgba(203, 213, 225, 0.9);
        border-radius: 24px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 24px 60px rgba(15, 23, 42, 0.12);
      }
      .preview-loader strong {
        font-size: 18px;
      }
      .preview-loader span {
        color: #64748b;
      }
    </style>
  </head>
  <body>
    <div class="preview-loader">
      <strong>Собираем предпросмотр</strong>
      <span>Окно обновится автоматически, когда HTML будет готов.</span>
    </div>
  </body>
</html>`);
    previewWindow.document.close();
    previewWindow.focus();
  };

  const probeMutation = useMutation({
    mutationFn: () =>
      apiRequest<SiteConnectionProbeResult>(
        "/sites/probe-connection",
        {
          method: "POST",
          body: JSON.stringify(buildPayload().connection)
        },
        token
      ),
    onSuccess: (result) => {
      setProbeResult(result);
      pushToast(result.message, "success");
      setCurrentStep(2);
    },
    onError: (error) => {
      setProbeResult(null);
      pushToast(error instanceof ApiError ? error.message : "Не удалось проверить сервер", "danger");
    }
  });

  const previewMutation = useMutation({
    mutationFn: () =>
      apiRequest<SitePreviewResult>(
        "/sites/preview",
        {
          method: "POST",
          body: JSON.stringify(buildPayload())
        },
        token
      ),
    onError: (error) => {
      setPreview(null);
      pushToast(error instanceof ApiError ? error.message : "Не удалось собрать предпросмотр", "danger");
    }
  });

  const planMutation = useMutation({
    mutationFn: () =>
      apiRequest<SiteDeploymentPlan>(
        "/sites/plan",
        {
          method: "POST",
          body: JSON.stringify(buildPayload())
        },
        token
      ),
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось собрать итоговый план", "danger");
    }
  });

  const createMutation = useMutation({
    mutationFn: () =>
      apiRequest<Site>(
        "/sites/",
        {
          method: "POST",
          body: JSON.stringify(buildPayload())
        },
        token
      ),
    onSuccess: async () => {
      pushToast("Сайт развернут", "success");
      closeModal();
      await queryClient.invalidateQueries({ queryKey: ["sites"] });
    },
    onError: async (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось развернуть сайт", "danger");
      await queryClient.invalidateQueries({ queryKey: ["sites"] });
    }
  });

  const redeployMutation = useMutation({
    mutationFn: (siteId: string) =>
      apiRequest<Site>(`/sites/${siteId}/deploy`, { method: "POST" }, token),
    onSuccess: async () => {
      pushToast("Сайт развернут повторно", "success");
      await queryClient.invalidateQueries({ queryKey: ["sites"] });
    },
    onError: async (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось повторно развернуть сайт", "danger");
      await queryClient.invalidateQueries({ queryKey: ["sites"] });
    }
  });

  const refreshCloudflareUrlMutation = useMutation({
    mutationFn: (siteId: string) =>
      apiRequest<Site>(`/sites/${siteId}/refresh-cloudflare-url`, { method: "POST" }, token),
    onSuccess: async (site) => {
      pushToast(`URL туннеля для ${site.name} обновлен`, "success");
      await queryClient.invalidateQueries({ queryKey: ["sites"] });
    },
    onError: async (error) => {
      pushToast(
        error instanceof ApiError ? error.message : "Не удалось обновить URL Cloudflare Tunnel",
        "danger"
      );
      await queryClient.invalidateQueries({ queryKey: ["sites"] });
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (siteId: string) =>
      apiRequest<SiteDeleteResult>(`/sites/${siteId}`, { method: "DELETE" }, token),
    onSuccess: async (result) => {
      pushToast(
        result.deleted_from_server
          ? `Сайт ${result.site_name} удален`
          : `Сайт ${result.site_name} удален только из админки`,
        result.deleted_from_server ? "success" : "warning"
      );
      result.warnings.forEach((warning) => pushToast(warning, "warning"));
      await queryClient.invalidateQueries({ queryKey: ["sites"] });
    },
    onError: async (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось удалить сайт", "danger");
      await queryClient.invalidateQueries({ queryKey: ["sites"] });
    }
  });

  const canProceedFromSettings = Boolean(
    settings.name.trim() &&
      settings.managed_bot_id &&
      (settings.publish_mode !== "domain" || normalizedDomain) &&
      Number(settings.proxy_port) >= 1025 &&
      Number(settings.proxy_port) <= 65535
  );

  return (
    <div className="page-content">
      <header className="page-titlebar">
        <div>
          <h1>Сайты</h1>
        </div>
        <button
          className="primary-button"
          onClick={() => {
            resetWizard();
            setIsModalOpen(true);
          }}
          type="button"
        >
          Добавить сайт
        </button>
      </header>

      <div className="summary-strip">
        <section className="summary-card">
          <span>Всего</span>
          <strong>{sites.length}</strong>
        </section>
        <section className="summary-card">
          <span>Развернуты</span>
          <strong>{deployedCount}</strong>
        </section>
        <section className="summary-card">
          <span>С ошибкой</span>
          <strong>{errorCount}</strong>
        </section>
      </div>

      <section className="entity-grid">
        {isLoading ? (
          <div className="panel">Загрузка...</div>
        ) : sites.length === 0 ? (
          <div className="panel">Сайты еще не добавлены.</div>
        ) : (
          sites.map((site) => {
            const warnings = getSnapshotWarnings(site.deployment_snapshot);
            const isCloudflareTunnel = site.publish_mode === "cloudflare_tunnel";
            return (
              <article key={site.id} className="entity-card">
                <div className="entity-card__header">
                  <div>
                    <h3>{site.name}</h3>
                    <p className="table-subtitle">{site.public_url ?? site.domain ?? site.server_host}</p>
                  </div>
                  <Badge tone={getStatusTone(site.deployment_status)}>{getStatusLabel(site.deployment_status)}</Badge>
                </div>

                <dl className="meta-list">
                  <div>
                    <dt>Публикация</dt>
                    <dd>{getPublishModeLabel(site.publish_mode)}</dd>
                  </div>
                  <div>
                    <dt>Домен</dt>
                    <dd>{site.domain ?? (site.publish_mode === "cloudflare_tunnel" ? "не нужен" : "не указан")}</dd>
                  </div>
                  <div>
                    <dt>Сервер</dt>
                    <dd>{`${site.server_host}:${site.server_port}`}</dd>
                  </div>
                  <div>
                    <dt>Порт приложения</dt>
                    <dd>{site.proxy_port}</dd>
                  </div>
                  <div>
                    <dt>Доступ</dt>
                    <dd>{site.server_access_mode === "root" ? "root" : "sudo"}</dd>
                  </div>
                  <div>
                    <dt>Бот</dt>
                    <dd>{site.managed_bot.name}</dd>
                  </div>
                  <div>
                    <dt>Шаблон</dt>
                    <dd>{site.template_name}</dd>
                  </div>
                  <div>
                    <dt>SSL</dt>
                    <dd>{getSslLabel(site.ssl_mode)}</dd>
                  </div>
                  {typeof site.deployment_snapshot.backend_base_url === "string" ? (
                    <div>
                      <dt>Backend API</dt>
                      <dd>{site.deployment_snapshot.backend_base_url}</dd>
                    </div>
                  ) : null}
                  <div>
                    <dt>Служба</dt>
                    <dd>{String(site.deployment_snapshot.service_name ?? site.code)}</dd>
                  </div>
                  <div>
                    <dt>Развернут</dt>
                    <dd>{formatDate(site.last_deployed_at)}</dd>
                  </div>
                </dl>

                {warnings.length > 0 ? (
                  <div className="inline-note">
                    {warnings.map((warning) => (
                      <div key={warning}>{warning}</div>
                    ))}
                  </div>
                ) : null}

                {isCloudflareTunnel ? (
                  <div className="inline-note">
                    Если ссылка отвечает `530`, значит сохраненный `trycloudflare` URL устарел после рестарта
                    туннеля. Используйте кнопку ниже, чтобы перечитать актуальный адрес с сервера.
                  </div>
                ) : null}

                {site.last_error ? <p className="server-card__error">{site.last_error}</p> : null}

                <div className="table-actions">
                  {site.public_url ? (
                    <button
                      className="ghost-button"
                      onClick={() => window.open(site.public_url ?? "", "_blank", "noopener,noreferrer")}
                      type="button"
                    >
                      Открыть
                    </button>
                  ) : null}
                  {isCloudflareTunnel ? (
                    <button
                      className="ghost-button"
                      disabled={refreshCloudflareUrlMutation.isPending}
                      onClick={() => refreshCloudflareUrlMutation.mutate(site.id)}
                      type="button"
                    >
                      {refreshCloudflareUrlMutation.isPending
                        ? "Обновляем URL..."
                        : "Обновить URL туннеля"}
                    </button>
                  ) : null}
                  <button
                    className="ghost-button"
                    disabled={redeployMutation.isPending}
                    onClick={() => redeployMutation.mutate(site.id)}
                    type="button"
                  >
                    {redeployMutation.isPending ? "Разворачиваем..." : "Развернуть заново"}
                  </button>
                  <button
                    className="ghost-button"
                    disabled={deleteMutation.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Удалить сайт ${site.name}? Система сначала попытается подключиться к серверу и зачистить его, а если не сможет, удалит только запись из админки.`
                        )
                      ) {
                        deleteMutation.mutate(site.id);
                      }
                    }}
                    type="button"
                  >
                    {deleteMutation.isPending ? "Удаляем..." : "Удалить"}
                  </button>
                </div>
              </article>
            );
          })
        )}
      </section>

      {isModalOpen ? (
        <Modal title="Создание сайта" onClose={closeModal}>
          <div className="wizard-stepper">
            {(Object.keys(stepLabels) as Array<keyof typeof stepLabels>).map((stepKey) => {
              const step = Number(stepKey) as WizardStep;
              return (
                <div
                  key={step}
                  className={`wizard-step${step === currentStep ? " wizard-step--active" : ""}${step < currentStep ? " wizard-step--done" : ""}`}
                >
                  <span className="wizard-step__index">{step}</span>
                  <span>{stepLabels[step]}</span>
                </div>
              );
            })}
          </div>
          <p className="site-builder-intro">{stepDescriptions[currentStep]}</p>

          {currentStep === 1 ? (
            <div className="page-content">
              <form
                className="form-grid"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (canCheckConnection) {
                    probeMutation.mutate();
                  }
                }}
              >
                <div className="full-width choice-grid">
                  <button
                    className={`choice-card${connection.access_mode === "root" ? " choice-card--active" : ""}`}
                    onClick={() => {
                      setProbeResult(null);
                      setConnection((current) => ({ ...current, access_mode: "root", username: "root" }));
                    }}
                    type="button"
                  >
                    <strong>Root</strong>
                    <span>Прямое подключение с полными правами.</span>
                  </button>
                  <button
                    className={`choice-card${connection.access_mode === "sudo" ? " choice-card--active" : ""}`}
                    onClick={() => {
                      setProbeResult(null);
                      setConnection((current) => ({
                        ...current,
                        access_mode: "sudo",
                        username: current.username === "root" ? "" : current.username
                      }));
                    }}
                    type="button"
                  >
                    <strong>Sudo-пользователь</strong>
                    <span>Подключение под обычным пользователем с правами sudo.</span>
                  </button>
                </div>

                <label>
                  <span>IP или хост</span>
                  <input
                    value={connection.host}
                    onChange={(event) => {
                      setProbeResult(null);
                      setConnection({ ...connection, host: event.target.value });
                    }}
                    placeholder="1.2.3.4"
                    required
                  />
                </label>

                <label>
                  <span>Порт SSH</span>
                  <input
                    inputMode="numeric"
                    min="1"
                    max="65535"
                    type="number"
                    value={connection.port}
                    onChange={(event) => {
                      setProbeResult(null);
                      setConnection({ ...connection, port: event.target.value });
                    }}
                    required
                  />
                </label>

                <label>
                  <span>Пользователь</span>
                  <input
                    value={connection.username}
                    onChange={(event) => {
                      setProbeResult(null);
                      setConnection({ ...connection, username: event.target.value });
                    }}
                    placeholder={connection.access_mode === "root" ? "root" : "deploy"}
                    required
                  />
                </label>

                <label>
                  <span>Пароль</span>
                  <input
                    type="password"
                    value={connection.password}
                    onChange={(event) => {
                      setProbeResult(null);
                      setConnection({ ...connection, password: event.target.value });
                    }}
                    required
                  />
                </label>

                {probeResult ? (
                  <div className="full-width site-success-card">
                    <strong>Подключение подтверждено</strong>
                    <div className="muted">{probeResult.hostname}</div>
                    <div className="site-server-facts">
                      <span>{probeResult.os_name}</span>
                      <span>{probeResult.os_version ?? probeResult.kernel}</span>
                      <span>{probeResult.python_version ? `Python ${probeResult.python_version}` : "Python не найден"}</span>
                      <span>{connection.access_mode === "root" ? "Доступ: root" : `Пользователь: ${probeResult.current_user}`}</span>
                    </div>
                  </div>
                ) : null}

                <div className="modal-footer">
                  <button className="secondary-button" onClick={closeModal} type="button">
                    Отмена
                  </button>
                  <button className="primary-button" disabled={!canCheckConnection || probeMutation.isPending} type="submit">
                    {probeMutation.isPending ? "Проверяем..." : "Проверить и продолжить"}
                  </button>
                </div>
              </form>
            </div>
          ) : null}

          {currentStep === 2 ? (
            <div className="page-content">
              <form
                className="form-grid"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (canProceedFromSettings) {
                    setCurrentStep(3);
                  }
                }}
              >
                <label className="full-width">
                  <span>Имя сайта</span>
                  <input
                    value={settings.name}
                    onChange={(event) => {
                      setPreview(null);
                      planMutation.reset();
                      setSettings({ ...settings, name: event.target.value });
                    }}
                    placeholder="Например, VLESS Start"
                    required
                  />
                </label>

                <label>
                  <span>Привязанный бот</span>
                  <select
                    value={settings.managed_bot_id}
                    onChange={(event) => {
                      setPreview(null);
                      planMutation.reset();
                      setSettings({ ...settings, managed_bot_id: event.target.value });
                    }}
                    required
                  >
                    <option value="">{publicBots.length > 0 ? "Выберите бота" : "Нет готовых ботов"}</option>
                    {publicBots.map((bot) => (
                      <option key={bot.id} value={bot.id}>
                        {bot.name}
                        {bot.telegram_bot_username ? ` · @${bot.telegram_bot_username}` : ""}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="full-width">
                  <span>Как публиковать сайт</span>
                  <div className="choice-grid">
                    <button
                      className={`choice-card${settings.publish_mode === "ip" ? " choice-card--active" : ""}`}
                      onClick={() => {
                        setPreview(null);
                        planMutation.reset();
                        setSettings({ ...settings, publish_mode: "ip", domain: "" });
                      }}
                      type="button"
                    >
                      <strong>По IP</strong>
                      <span>{getPublishModeHint("ip")}</span>
                    </button>
                    <button
                      className={`choice-card${settings.publish_mode === "domain" ? " choice-card--active" : ""}`}
                      onClick={() => {
                        setPreview(null);
                        planMutation.reset();
                        setSettings({ ...settings, publish_mode: "domain" });
                      }}
                      type="button"
                    >
                      <strong>Свой домен</strong>
                      <span>{getPublishModeHint("domain")}</span>
                    </button>
                    <button
                      className={`choice-card${settings.publish_mode === "cloudflare_tunnel" ? " choice-card--active" : ""}`}
                      onClick={() => {
                        setPreview(null);
                        planMutation.reset();
                        setSettings({ ...settings, publish_mode: "cloudflare_tunnel", domain: "" });
                      }}
                      type="button"
                    >
                      <strong>Cloudflare Tunnel</strong>
                      <span>{getPublishModeHint("cloudflare_tunnel")}</span>
                    </button>
                  </div>
                </div>

                {settings.publish_mode === "domain" ? (
                  <label className="full-width">
                    <span>Домен</span>
                    <input
                      value={settings.domain}
                      onChange={(event) => {
                        setPreview(null);
                        planMutation.reset();
                        setSettings({ ...settings, domain: event.target.value });
                      }}
                      placeholder="example.com"
                      required
                    />
                  </label>
                ) : null}

                <div className="full-width inline-note">
                  {settings.publish_mode === "domain"
                    ? "Домен должен уже смотреть на этот сервер, иначе HTTPS не выпустится автоматически."
                    : settings.publish_mode === "cloudflare_tunnel"
                      ? "Адрес будет выдан автоматически и может измениться после перезапуска туннеля."
                      : "Сайт будет доступен по IP сервера. Браузер может показать предупреждение о сертификате."}
                </div>

                <details className="full-width site-advanced">
                  <summary>Дополнительно</summary>
                  <div className="site-advanced__body">
                    <label>
                      <span>Внутренний порт сайта</span>
                      <input
                        type="number"
                        min="1025"
                        max="65535"
                        value={settings.proxy_port}
                        onChange={(event) => {
                          setPreview(null);
                          planMutation.reset();
                          setSettings({ ...settings, proxy_port: event.target.value });
                        }}
                        required
                      />
                    </label>
                    <small className="form-help">Если не уверены, оставьте `5000`. Порт должен быть свободен на сервере.</small>
                  </div>
                </details>

                {publicBots.length === 0 ? (
                  <div className="full-width inline-note">
                    Сначала подготовьте активного бота с `@username`, чтобы кнопки на сайте вели в Telegram.
                  </div>
                ) : null}

                <div className="modal-footer">
                  <button className="secondary-button" onClick={() => setCurrentStep(1)} type="button">
                    Назад
                  </button>
                  <button className="primary-button" disabled={!canProceedFromSettings} type="submit">
                    Дальше
                  </button>
                </div>
              </form>
            </div>
          ) : null}

          {currentStep === 3 ? (
            <div className="page-content">
              <div className="choice-grid">
                {templates.map((item) => (
                  <button
                    key={item.key}
                    className={`choice-card${item.key === template.key ? " choice-card--active" : ""}`}
                    onClick={() => {
                      setPreview(null);
                      planMutation.reset();
                      setTemplate({ key: item.key });
                    }}
                    type="button"
                  >
                    <strong>{item.name}</strong>
                    <span>{item.description}</span>
                    {item.is_default ? <small>Шаблон по умолчанию</small> : null}
                  </button>
                ))}
              </div>

              {activeTemplate ? (
                <div className="inline-note">Выбран шаблон: {activeTemplate.name}</div>
              ) : null}

              <div className="site-preview-toolbar">
                <div className="site-preview-toolbar__copy">
                  <strong>Предпросмотр</strong>
                  <span>
                    {preview
                      ? "Последний предпросмотр открыт в отдельном окне. Можно обновить его после изменений."
                      : "Нажмите кнопку, и браузер откроет отдельное окно предпросмотра."}
                  </span>
                </div>
                <button
                  className="secondary-button"
                  disabled={!template.key || previewMutation.isPending}
                  onClick={() => {
                    try {
                      openPreviewLoadingWindow();
                    } catch (error) {
                      pushToast(error instanceof Error ? error.message : "Не удалось открыть окно предпросмотра", "danger");
                      return;
                    }
                    previewMutation.mutate(undefined, {
                      onSuccess: (result) => {
                        setPreview(result);
                        try {
                          openPreviewWindow(result.html);
                          pushToast("Предпросмотр открыт в отдельном окне", "success");
                        } catch (error) {
                          pushToast(
                            error instanceof Error ? error.message : "Не удалось открыть окно предпросмотра",
                            "danger"
                          );
                        }
                      }
                    });
                  }}
                  type="button"
                >
                  {previewMutation.isPending ? "Собираем..." : preview ? "Обновить предпросмотр" : "Открыть предпросмотр"}
                </button>
              </div>

              {preview?.warnings.length ? (
                <div className="inline-note">
                  {preview.warnings.map((warning) => (
                    <div key={warning}>{warning}</div>
                  ))}
                </div>
              ) : null}

              <div className="modal-footer">
                <button className="secondary-button" onClick={() => setCurrentStep(2)} type="button">
                  Назад
                </button>
                <button
                  className="primary-button"
                  disabled={!template.key || planMutation.isPending}
                  onClick={() =>
                    planMutation.mutate(undefined, {
                      onSuccess: () => setCurrentStep(4)
                    })
                  }
                  type="button"
                >
                  {planMutation.isPending ? "Проверяем..." : "К запуску"}
                </button>
              </div>
            </div>
          ) : null}

          {currentStep === 4 ? (
            <div className="page-content">
              {planMutation.data ? (
                <>
                  <div className="site-review-grid">
                    <div className="site-review-card">
                      <span>Сайт</span>
                      <strong>{settings.name.trim()}</strong>
                    </div>
                    <div className="site-review-card">
                      <span>Публикация</span>
                      <strong>{getPublishModeLabel(planMutation.data.publish_mode)}</strong>
                    </div>
                    <div className="site-review-card">
                      <span>Адрес</span>
                      <strong>{planMutation.data.public_url || previewAddress}</strong>
                    </div>
                    <div className="site-review-card">
                      <span>Сервер</span>
                      <strong>{probeResult?.hostname ?? normalizedHost}</strong>
                    </div>
                    <div className="site-review-card">
                      <span>Бот</span>
                      <strong>{selectedBot ? `${selectedBot.name}${selectedBot.telegram_bot_username ? ` · @${selectedBot.telegram_bot_username}` : ""}` : "Не выбран"}</strong>
                    </div>
                    <div className="site-review-card">
                      <span>Шаблон</span>
                      <strong>{activeTemplate?.name ?? "Не выбран"}</strong>
                    </div>
                  </div>

                  {planMutation.data.warnings.length > 0 ? (
                    <div className="inline-note">
                      {planMutation.data.warnings.map((warning) => (
                        <div key={warning}>{warning}</div>
                      ))}
                    </div>
                  ) : null}

                  <div className="panel panel--compact">
                    <strong>Что будет сделано</strong>
                    <ol className="site-plan-list">
                      {planMutation.data.deploy_steps.map((step) => (
                        <li key={step}>{step}</li>
                      ))}
                    </ol>
                  </div>

                  <details className="site-advanced">
                    <summary>Технические детали</summary>
                    <div className="site-advanced__body">
                      <dl className="meta-list">
                        <div>
                          <dt>SSL</dt>
                          <dd>{getSslLabel(planMutation.data.ssl_mode)}</dd>
                        </div>
                        <div>
                          <dt>Внутренний порт</dt>
                          <dd>{planMutation.data.proxy_port}</dd>
                        </div>
                        <div>
                          <dt>Служба</dt>
                          <dd>{planMutation.data.service_name}</dd>
                        </div>
                        <div>
                          <dt>Systemd unit</dt>
                          <dd>{planMutation.data.systemd_unit_path}</dd>
                        </div>
                        {planMutation.data.nginx_config_path ? (
                          <div>
                            <dt>Nginx конфиг</dt>
                            <dd>{planMutation.data.nginx_config_path}</dd>
                          </div>
                        ) : null}
                        {planMutation.data.cloudflare_unit_path ? (
                          <div>
                            <dt>Cloudflared unit</dt>
                            <dd>{planMutation.data.cloudflare_unit_path}</dd>
                          </div>
                        ) : null}
                      </dl>
                    </div>
                  </details>
                </>
              ) : (
                <div className="panel">Не удалось собрать итоговый план.</div>
              )}

              <div className="modal-footer">
                <button className="secondary-button" onClick={() => setCurrentStep(3)} type="button">
                  Назад
                </button>
                <button
                  className="primary-button"
                  disabled={!planMutation.data || createMutation.isPending}
                  onClick={() => createMutation.mutate()}
                  type="button"
                >
                  {createMutation.isPending ? "Разворачиваем..." : "Развернуть сайт"}
                </button>
              </div>
            </div>
          ) : null}
        </Modal>
      ) : null}
    </div>
  );
}
