import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiRequest, ApiError } from "../api/http";
import { useAuth } from "../features/auth/AuthProvider";
import type {
  PaymentDomain,
  PaymentDomainConnectionProbeResult,
  PaymentDomainDeleteResult,
  PaymentDomainDeploymentPlan,
  SystemSettings
} from "../lib/types";
import { Badge } from "./Badge";
import { Modal } from "./Modal";
import { useToast } from "./ToastProvider";

type AccessMode = "root" | "sudo";
type WizardStep = 1 | 2 | 3;

const wizardSteps: WizardStep[] = [1, 2, 3];

interface ConnectionState {
  access_mode: AccessMode;
  host: string;
  port: string;
  username: string;
  password: string;
}

interface PaymentDomainSettingsState {
  domain: string;
}

const stepLabels: Record<WizardStep, string> = {
  1: "Сервер",
  2: "Домен",
  3: "Запуск"
};

const stepDescriptions: Record<WizardStep, string> = {
  1: "Проверьте SSH-доступ к серверу, на котором будет жить отдельный платежный домен.",
  2: "Укажите домен, через который бот будет открывать FreeKassa redirect.",
  3: "Проверьте итоговый nginx и SSL план, затем запустите развертывание."
};

const emptyConnection: ConnectionState = {
  access_mode: "root",
  host: "",
  port: "22",
  username: "root",
  password: ""
};

const emptySettings: PaymentDomainSettingsState = {
  domain: ""
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

function getSnapshotWarnings(snapshot: Record<string, unknown>) {
  const warnings = snapshot.warnings;
  if (!Array.isArray(warnings)) {
    return [] as string[];
  }
  return warnings.filter((item): item is string => typeof item === "string");
}

function getSslLabel(mode: string) {
  return mode === "letsencrypt" ? "Let's Encrypt" : mode;
}

export function PaymentDomainManager({ settings }: { settings: SystemSettings }) {
  const { token } = useAuth();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState<WizardStep>(1);
  const [connection, setConnection] = useState<ConnectionState>(emptyConnection);
  const [domainSettings, setDomainSettings] = useState<PaymentDomainSettingsState>(emptySettings);
  const [probeResult, setProbeResult] = useState<PaymentDomainConnectionProbeResult | null>(null);

  const normalizedHost = normalizeHost(connection.host);
  const normalizedDomain = normalizeDomain(domainSettings.domain);
  const activePaymentUrl = (settings.freekassa_public_url || "").trim().replace(/\/$/, "");

  const paymentDomainsQuery = useQuery({
    queryKey: ["payment-domains"],
    queryFn: () => apiRequest<PaymentDomain[]>("/payment-domains/", {}, token),
    enabled: Boolean(token)
  });

  const paymentDomains = paymentDomainsQuery.data ?? [];
  const deployedCount = paymentDomains.filter((item) => item.deployment_status === "deployed").length;
  const errorCount = paymentDomains.filter((item) => item.deployment_status === "error").length;
  const activePaymentDomain = paymentDomains.find(
    (item) => item.public_url && item.public_url.replace(/\/$/, "") === activePaymentUrl
  );

  const probeMutation = useMutation({
    mutationFn: () =>
      apiRequest<PaymentDomainConnectionProbeResult>(
        "/payment-domains/probe-connection",
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

  const planMutation = useMutation({
    mutationFn: () =>
      apiRequest<PaymentDomainDeploymentPlan>(
        "/payment-domains/plan",
        {
          method: "POST",
          body: JSON.stringify(buildPayload())
        },
        token
      ),
    onSuccess: () => {
      setCurrentStep(3);
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось собрать план платежного домена", "danger");
    }
  });

  const createMutation = useMutation({
    mutationFn: () =>
      apiRequest<PaymentDomain>(
        "/payment-domains/",
        {
          method: "POST",
          body: JSON.stringify(buildPayload())
        },
        token
      ),
    onSuccess: async (result) => {
      pushToast(`Платежный домен ${result.domain} развернут`, "success");
      closeModal();
      await queryClient.invalidateQueries({ queryKey: ["payment-domains"] });
      await queryClient.invalidateQueries({ queryKey: ["system-settings"] });
    },
    onError: async (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось развернуть платежный домен", "danger");
      await queryClient.invalidateQueries({ queryKey: ["payment-domains"] });
      await queryClient.invalidateQueries({ queryKey: ["system-settings"] });
    }
  });

  const redeployMutation = useMutation({
    mutationFn: (paymentDomainId: string) =>
      apiRequest<PaymentDomain>(`/payment-domains/${paymentDomainId}/deploy`, { method: "POST" }, token),
    onSuccess: async (result) => {
      pushToast(`Платежный домен ${result.domain} развернут повторно`, "success");
      await queryClient.invalidateQueries({ queryKey: ["payment-domains"] });
      await queryClient.invalidateQueries({ queryKey: ["system-settings"] });
    },
    onError: async (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось повторно развернуть платежный домен", "danger");
      await queryClient.invalidateQueries({ queryKey: ["payment-domains"] });
      await queryClient.invalidateQueries({ queryKey: ["system-settings"] });
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (paymentDomainId: string) =>
      apiRequest<PaymentDomainDeleteResult>(`/payment-domains/${paymentDomainId}`, { method: "DELETE" }, token),
    onSuccess: async (result) => {
      pushToast(
        result.deleted_from_server
          ? `Платежный домен ${result.domain} удален`
          : `Платежный домен ${result.domain} удален только из админки`,
        result.deleted_from_server ? "success" : "warning"
      );
      result.warnings.forEach((warning) => pushToast(warning, "warning"));
      await queryClient.invalidateQueries({ queryKey: ["payment-domains"] });
      await queryClient.invalidateQueries({ queryKey: ["system-settings"] });
    },
    onError: async (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось удалить платежный домен", "danger");
      await queryClient.invalidateQueries({ queryKey: ["payment-domains"] });
      await queryClient.invalidateQueries({ queryKey: ["system-settings"] });
    }
  });

  const resetWizard = () => {
    setCurrentStep(1);
    setConnection(emptyConnection);
    setDomainSettings(emptySettings);
    setProbeResult(null);
    probeMutation.reset();
    planMutation.reset();
    createMutation.reset();
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
      domain: normalizedDomain
    }
  });

  const canCheckConnection = Boolean(
    normalizedHost &&
      connection.username.trim() &&
      connection.password &&
      Number(connection.port) >= 1 &&
      Number(connection.port) <= 65535
  );
  const canBuildPlan = Boolean(normalizedDomain);
  const plan = planMutation.data;

  return (
    <>
      <section className="panel monetization-stack">
        <div className="page-titlebar">
          <div>
            <h2>Платежный домен</h2>
          </div>
          <button
            className="primary-button"
            onClick={() => {
              resetWizard();
              setIsModalOpen(true);
            }}
            type="button"
          >
            Добавить домен
          </button>
        </div>

        <div className="summary-strip">
          <section className="summary-card">
            <span>Всего доменов</span>
            <strong>{paymentDomains.length}</strong>
          </section>
          <section className="summary-card">
            <span>Развернуты</span>
            <strong>{deployedCount}</strong>
          </section>
          <section className="summary-card">
            <span>С ошибкой</span>
            <strong>{errorCount}</strong>
          </section>
          <section className="summary-card">
            <span>Активный URL</span>
            <strong>{activePaymentDomain?.domain ?? (settings.freekassa_public_url || "—")}</strong>
          </section>
        </div>

        {activePaymentDomain ? (
          <div className="inline-note">
            Сейчас `freekassa_public_url` синхронизирован с доменом {activePaymentDomain.domain}. Бот будет отдавать
            пользователю ссылки на этот домен, а не на домен админки.
          </div>
        ) : settings.freekassa_public_url ? (
          <div className="inline-note">Сейчас `freekassa_public_url` задан вручную: {settings.freekassa_public_url}</div>
        ) : (
          <div className="inline-note">
            Отдельный платежный домен еще не настроен. Пока бот будет использовать основной `public_app_url`.
          </div>
        )}
      </section>

      <section className="entity-grid">
        {paymentDomainsQuery.isLoading ? (
          <div className="panel">Загрузка платежных доменов...</div>
        ) : paymentDomains.length === 0 ? (
          <div className="panel">Платежные домены еще не добавлены.</div>
        ) : (
          paymentDomains.map((paymentDomain) => {
            const warnings = getSnapshotWarnings(paymentDomain.deployment_snapshot);
            const isActive = Boolean(
              paymentDomain.public_url && paymentDomain.public_url.replace(/\/$/, "") === activePaymentUrl
            );

            return (
              <article key={paymentDomain.id} className="entity-card">
                <div className="entity-card__header">
                  <div>
                    <h3>{paymentDomain.domain}</h3>
                    <p className="table-subtitle">{paymentDomain.public_url ?? paymentDomain.server_host}</p>
                  </div>
                  <div className="table-actions">
                    {isActive ? <Badge tone="success">активный URL</Badge> : null}
                    <Badge tone={getStatusTone(paymentDomain.deployment_status)}>
                      {getStatusLabel(paymentDomain.deployment_status)}
                    </Badge>
                  </div>
                </div>

                <dl className="meta-list">
                  <div>
                    <dt>Домен</dt>
                    <dd>{paymentDomain.domain}</dd>
                  </div>
                  <div>
                    <dt>Публичный URL</dt>
                    <dd>{paymentDomain.public_url ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>Сервер</dt>
                    <dd>{`${paymentDomain.server_host}:${paymentDomain.server_port}`}</dd>
                  </div>
                  <div>
                    <dt>Доступ</dt>
                    <dd>{paymentDomain.server_access_mode === "root" ? "root" : "sudo"}</dd>
                  </div>
                  <div>
                    <dt>SSL</dt>
                    <dd>{getSslLabel(paymentDomain.ssl_mode)}</dd>
                  </div>
                  <div>
                    <dt>Backend API</dt>
                    <dd>{String(paymentDomain.deployment_snapshot.backend_api_base_url ?? "—")}</dd>
                  </div>
                  <div>
                    <dt>Nginx config</dt>
                    <dd>{String(paymentDomain.deployment_snapshot.nginx_config_path ?? "—")}</dd>
                  </div>
                  <div>
                    <dt>Служба</dt>
                    <dd>{String(paymentDomain.deployment_snapshot.service_name ?? paymentDomain.code)}</dd>
                  </div>
                  <div>
                    <dt>Развернут</dt>
                    <dd>{formatDate(paymentDomain.last_deployed_at)}</dd>
                  </div>
                </dl>

                {warnings.length > 0 ? (
                  <div className="inline-note">
                    {warnings.map((warning) => (
                      <div key={warning}>{warning}</div>
                    ))}
                  </div>
                ) : null}

                {paymentDomain.last_error ? <p className="server-card__error">{paymentDomain.last_error}</p> : null}

                <div className="table-actions">
                  {paymentDomain.public_url ? (
                    <button
                      className="ghost-button"
                      onClick={() => window.open(paymentDomain.public_url ?? "", "_blank", "noopener,noreferrer")}
                      type="button"
                    >
                      Открыть
                    </button>
                  ) : null}
                  <button
                    className="ghost-button"
                    disabled={redeployMutation.isPending}
                    onClick={() => redeployMutation.mutate(paymentDomain.id)}
                    type="button"
                  >
                    {redeployMutation.isPending ? "Разворачиваем..." : "Развернуть заново"}
                  </button>
                  <button
                    className="ghost-button danger-button"
                    disabled={deleteMutation.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Удалить платежный домен ${paymentDomain.domain}? Система сначала попробует очистить nginx и файлы на сервере, а затем удалит запись из админки.`
                        )
                      ) {
                        deleteMutation.mutate(paymentDomain.id);
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
        <Modal title="Создание платежного домена" onClose={closeModal}>
          <div className="wizard-stepper">
            {wizardSteps.map((step) => {
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
                    planMutation.reset();
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
                    planMutation.reset();
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
                    planMutation.reset();
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
                    planMutation.reset();
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
                  {probeMutation.isPending ? "Проверяем..." : "Проверить сервер"}
                </button>
              </div>
            </form>
          ) : null}

          {currentStep === 2 ? (
            <form
              className="form-grid"
              onSubmit={(event) => {
                event.preventDefault();
                if (canBuildPlan) {
                  planMutation.mutate();
                }
              }}
            >
              <label className="full-width">
                <span>Платежный домен</span>
                <input
                  value={domainSettings.domain}
                  onChange={(event) => {
                    planMutation.reset();
                    setDomainSettings({ domain: event.target.value });
                  }}
                  placeholder="pay.example.com"
                  required
                />
              </label>

              <div className="full-width inline-note">
                Перед запуском проверьте, что DNS уже указывает на сервер {normalizedHost || connection.host.trim() || ""}. Иначе
                Let's Encrypt не выпустит сертификат.
              </div>

              <div className="modal-footer">
                <button className="secondary-button" onClick={() => setCurrentStep(1)} type="button">
                  Назад
                </button>
                <button className="primary-button" disabled={!canBuildPlan || planMutation.isPending} type="submit">
                  {planMutation.isPending ? "Собираем план..." : "Продолжить"}
                </button>
              </div>
            </form>
          ) : null}

          {currentStep === 3 && plan ? (
            <div className="form-grid">
              <div className="full-width site-success-card">
                <strong>{plan.public_url}</strong>
                <div className="site-server-facts">
                  <span>{plan.service_name}</span>
                  <span>{plan.ssl_mode}</span>
                  <span>{plan.backend_api_base_url}</span>
                </div>
              </div>

              <label>
                <span>Remote root</span>
                <input readOnly value={plan.remote_root} />
              </label>

              <label>
                <span>Nginx config</span>
                <input readOnly value={plan.nginx_config_path} />
              </label>

              <label className="full-width">
                <span>Публичный URL</span>
                <input readOnly value={plan.public_url} />
              </label>

              <div className="full-width inline-note">
                <strong>Что будет сделано</strong>
                {plan.deploy_steps.map((step) => (
                  <div key={step}>{step}</div>
                ))}
              </div>

              {plan.warnings.length > 0 ? (
                <div className="full-width inline-note">
                  <strong>На что обратить внимание</strong>
                  {plan.warnings.map((warning) => (
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
                  disabled={createMutation.isPending}
                  onClick={() => createMutation.mutate()}
                  type="button"
                >
                  {createMutation.isPending ? "Разворачиваем..." : "Развернуть домен"}
                </button>
              </div>
            </div>
          ) : null}
        </Modal>
      ) : null}
    </>
  );
}
