import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiRequest, ApiError } from "../api/http";
import { useToast } from "../components/ToastProvider";
import { useAuth } from "../features/auth/AuthProvider";
import type { SystemSettings } from "../lib/types";

interface SettingsFormState {
  app_name: string;
  public_app_url: string;
  trial_duration_hours: string;
  site_trial_duration_hours: string;
  site_trial_total_gb: string;
  scheduler_interval_minutes: string;
  three_xui_timeout_seconds: string;
  three_xui_verify_ssl: boolean;
  bot_webhook_base_url: string;
}

const emptyForm: SettingsFormState = {
  app_name: "",
  public_app_url: "",
  trial_duration_hours: "24",
  site_trial_duration_hours: "6",
  site_trial_total_gb: "1",
  scheduler_interval_minutes: "5",
  three_xui_timeout_seconds: "20",
  three_xui_verify_ssl: false,
  bot_webhook_base_url: ""
};

function toForm(settings: SystemSettings): SettingsFormState {
  return {
    app_name: settings.app_name,
    public_app_url: settings.public_app_url,
    trial_duration_hours: String(settings.trial_duration_hours),
    site_trial_duration_hours: String(settings.site_trial_duration_hours),
    site_trial_total_gb: String(settings.site_trial_total_gb),
    scheduler_interval_minutes: String(settings.scheduler_interval_minutes),
    three_xui_timeout_seconds: String(settings.three_xui_timeout_seconds),
    three_xui_verify_ssl: settings.three_xui_verify_ssl,
    bot_webhook_base_url: settings.bot_webhook_base_url || ""
  };
}

function formatSource(source: string | undefined) {
  if (source === "default") {
    return "дефолт";
  }
  return source === "database" ? "панель" : "env";
}

export function SettingsPage() {
  const { token } = useAuth();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<SettingsFormState>(emptyForm);

  const settingsQuery = useQuery({
    queryKey: ["system-settings"],
    queryFn: () => apiRequest<SystemSettings>("/system-settings/", {}, token)
  });

  useEffect(() => {
    if (settingsQuery.data) {
      setForm(toForm(settingsQuery.data));
    }
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      apiRequest<SystemSettings>(
        "/system-settings/",
        {
          method: "PUT",
          body: JSON.stringify({
            app_name: form.app_name.trim(),
            public_app_url: form.public_app_url.trim(),
            trial_duration_hours: Number(form.trial_duration_hours),
            site_trial_duration_hours: Number(form.site_trial_duration_hours),
            site_trial_total_gb: Number(form.site_trial_total_gb),
            scheduler_interval_minutes: Number(form.scheduler_interval_minutes),
            three_xui_timeout_seconds: Number(form.three_xui_timeout_seconds),
            three_xui_verify_ssl: form.three_xui_verify_ssl,
            bot_webhook_base_url: form.bot_webhook_base_url.trim() || null
          })
        },
        token
      ),
    onSuccess: (result) => {
      setForm(toForm(result));
      queryClient.invalidateQueries({ queryKey: ["system-settings"] });
      pushToast("Системные настройки сохранены", "success");
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось сохранить системные настройки", "danger");
    }
  });

  const settings = settingsQuery.data;

  return (
    <div className="page-content">
      <header className="page-titlebar">
        <div>
          <h1>Настройки</h1>
          <p className="table-subtitle">Runtime-настройки панели, выдачи тестов и интеграции с 3x-ui.</p>
        </div>
      </header>

      {settingsQuery.isLoading ? (
        <div className="panel">Загрузка...</div>
      ) : settings ? (
        <>
          <div className="summary-strip">
            <section className="summary-card">
              <span>Telegram тест</span>
              <strong>{`${settings.trial_duration_hours} ч`}</strong>
            </section>
            <section className="summary-card">
              <span>Сайт тест</span>
              <strong>{`${settings.site_trial_duration_hours} ч / ${settings.site_trial_total_gb} ГБ`}</strong>
            </section>
            <section className="summary-card">
              <span>Планировщик</span>
              <strong>{`${settings.scheduler_interval_minutes} мин`}</strong>
            </section>
          </div>

          {settings.warnings.length > 0 ? (
            <div className="inline-note">
              {settings.warnings.map((warning) => (
                <div key={warning}>{warning}</div>
              ))}
            </div>
          ) : null}

          <section className="panel">
            <form
              className="form-grid"
              onSubmit={(event) => {
                event.preventDefault();
                saveMutation.mutate();
              }}
            >
              <label>
                <span>Название панели</span>
                <input
                  value={form.app_name}
                  onChange={(event) => setForm({ ...form, app_name: event.target.value })}
                  required
                />
                <small className="field-meta">{`Источник сейчас: ${formatSource(settings.sources.app_name)}`}</small>
              </label>

              <label>
                <span>Публичный URL админки</span>
                <input
                  value={form.public_app_url}
                  onChange={(event) => setForm({ ...form, public_app_url: event.target.value })}
                  placeholder="https://panel.example.com"
                  required
                />
                <small className="field-meta">{`Источник сейчас: ${formatSource(settings.sources.public_app_url)}`}</small>
              </label>

              <label>
                <span>Длительность Telegram-теста, часы</span>
                <input
                  type="number"
                  min="1"
                  max="720"
                  value={form.trial_duration_hours}
                  onChange={(event) => setForm({ ...form, trial_duration_hours: event.target.value })}
                  required
                />
                <small className="field-meta">{`Источник сейчас: ${formatSource(settings.sources.trial_duration_hours)}`}</small>
              </label>

              <label>
                <span>Длительность site-теста, часы</span>
                <input
                  type="number"
                  min="1"
                  max="168"
                  value={form.site_trial_duration_hours}
                  onChange={(event) => setForm({ ...form, site_trial_duration_hours: event.target.value })}
                  required
                />
                <small className="field-meta">{`Источник сейчас: ${formatSource(settings.sources.site_trial_duration_hours)}`}</small>
              </label>

              <label>
                <span>Лимит трафика site-теста, ГБ</span>
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={form.site_trial_total_gb}
                  onChange={(event) => setForm({ ...form, site_trial_total_gb: event.target.value })}
                  required
                />
                <small className="field-meta">{`Источник сейчас: ${formatSource(settings.sources.site_trial_total_gb)}`}</small>
              </label>

              <label>
                <span>Интервал планировщика, минуты</span>
                <input
                  type="number"
                  min="1"
                  max="1440"
                  value={form.scheduler_interval_minutes}
                  onChange={(event) => setForm({ ...form, scheduler_interval_minutes: event.target.value })}
                  required
                />
                <small className="field-meta">{`Источник сейчас: ${formatSource(settings.sources.scheduler_interval_minutes)}`}</small>
              </label>

              <label>
                <span>Timeout 3x-ui, секунды</span>
                <input
                  type="number"
                  min="1"
                  max="300"
                  value={form.three_xui_timeout_seconds}
                  onChange={(event) => setForm({ ...form, three_xui_timeout_seconds: event.target.value })}
                  required
                />
                <small className="field-meta">{`Источник сейчас: ${formatSource(settings.sources.three_xui_timeout_seconds)}`}</small>
              </label>

              <label className="checkbox-field">
                <input
                  checked={form.three_xui_verify_ssl}
                  onChange={(event) => setForm({ ...form, three_xui_verify_ssl: event.target.checked })}
                  type="checkbox"
                />
                <span>Проверять SSL у 3x-ui</span>
                <small className="field-meta">{`Источник сейчас: ${formatSource(settings.sources.three_xui_verify_ssl)}`}</small>
              </label>

              <label>
                <span>Telegram Webhook Base URL</span>
                <input
                  value={form.bot_webhook_base_url}
                  onChange={(event) => setForm({ ...form, bot_webhook_base_url: event.target.value })}
                  placeholder="https://your-domain.com/webhooks"
                />
                <small className="field-meta">
                  {`Источник сейчас: ${formatSource(settings.sources.bot_webhook_base_url)}`}
                  <br />
                  Если пусто — используется Polling. Путь будет: URL/bot_code
                </small>
              </label>

              <div className="modal-footer">
                <button className="primary-button" disabled={saveMutation.isPending} type="submit">
                  {saveMutation.isPending ? "Сохраняем..." : "Сохранить настройки"}
                </button>
              </div>
            </form>
          </section>
        </>
      ) : (
        <div className="panel">Не удалось загрузить настройки.</div>
      )}
    </div>
  );
}
