import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { apiRequest, ApiError } from "../api/http";
import { Modal } from "../components/Modal";
import { PaymentDomainManager } from "../components/PaymentDomainManager";
import { useToast } from "../components/ToastProvider";
import { useAuth } from "../features/auth/AuthProvider";
import type { BillingPlan, ManagedBot, MonetizationSummary, SystemSettings } from "../lib/types";

interface PlanFormState {
  managed_bot_id: string;
  name: string;
  description: string;
  duration_hours: string;
  price_rub: string;
  sort_order: string;
  is_active: boolean;
}

const emptyPlanForm: PlanFormState = {
  managed_bot_id: "",
  name: "",
  description: "",
  duration_hours: "720",
  price_rub: "",
  sort_order: "100",
  is_active: true
};

interface FreeKassaFormState {
  freekassa_shop_id: string;
  freekassa_public_url: string;
  freekassa_secret_word: string;
  freekassa_api_key: string;
  freekassa_secret_word_2: string;
  freekassa_sbp_method_id: string;
}

const emptyFreeKassaForm: FreeKassaFormState = {
  freekassa_shop_id: "",
  freekassa_public_url: "",
  freekassa_secret_word: "",
  freekassa_api_key: "",
  freekassa_secret_word_2: "",
  freekassa_sbp_method_id: "42"
};

const freeKassaMethodOptions = [
  { value: "13", label: "13 - Онлайн банк" },
  { value: "12", label: "12 - МИР" },
  { value: "36", label: "36 - Card RUB API" },
  { value: "42", label: "42 - СБП" },
  { value: "44", label: "44 - СБП (API)" },
  { value: "37", label: "37 - Google Pay" },
  { value: "38", label: "38 - Apple Pay" }
];

function formatMoney(kopecks: number) {
  return `${(kopecks / 100).toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })} ₽`;
}

function formatDuration(hours: number) {
  if (hours % (24 * 30) === 0) {
    return `${hours / (24 * 30)} мес.`;
  }
  if (hours % 24 === 0) {
    return `${hours / 24} дн.`;
  }
  return `${hours} ч`;
}

function parsePriceToKopecks(value: string) {
  const normalized = value.trim().replace(",", ".");
  const amount = Number(normalized);
  if (!Number.isFinite(amount) || amount <= 0) {
    throw new ApiError("Укажите корректную цену", 422);
  }
  return Math.round(amount * 100);
}

function toPlanForm(plan: BillingPlan): PlanFormState {
  return {
    managed_bot_id: plan.managed_bot_id,
    name: plan.name,
    description: plan.description || "",
    duration_hours: String(plan.duration_hours),
    price_rub: (plan.price_kopecks / 100).toFixed(2),
    sort_order: String(plan.sort_order),
    is_active: plan.is_active
  };
}

function toFreeKassaForm(settings: SystemSettings): FreeKassaFormState {
  return {
    freekassa_shop_id: settings.freekassa_shop_id ? String(settings.freekassa_shop_id) : "",
    freekassa_public_url: settings.freekassa_public_url || "",
    freekassa_secret_word: "",
    freekassa_api_key: "",
    freekassa_secret_word_2: "",
    freekassa_sbp_method_id: String(settings.freekassa_sbp_method_id)
  };
}

function MonetizationOverviewTab() {
  const { token } = useAuth();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const [selectedBotId, setSelectedBotId] = useState("");
  const [isPlanModalOpen, setIsPlanModalOpen] = useState(false);
  const [editingPlan, setEditingPlan] = useState<BillingPlan | null>(null);
  const [form, setForm] = useState<PlanFormState>(emptyPlanForm);

  const summaryQuery = useQuery({
    queryKey: ["monetization-summary"],
    queryFn: () => apiRequest<MonetizationSummary>("/monetization/summary", {}, token),
    enabled: Boolean(token)
  });

  const botsQuery = useQuery({
    queryKey: ["bots"],
    queryFn: () => apiRequest<ManagedBot[]>("/bots/", {}, token),
    enabled: Boolean(token)
  });

  const plansQuery = useQuery({
    queryKey: ["monetization-plans"],
    queryFn: () => apiRequest<BillingPlan[]>("/monetization/plans", {}, token),
    enabled: Boolean(token)
  });

  const bots = botsQuery.data ?? [];
  const plans = plansQuery.data ?? [];
  const filteredPlans = useMemo(
    () => (selectedBotId ? plans.filter((plan) => plan.managed_bot_id === selectedBotId) : plans),
    [plans, selectedBotId]
  );

  useEffect(() => {
    if (!form.managed_bot_id && bots.length > 0) {
      setForm((current) => ({ ...current, managed_bot_id: bots[0].id }));
    }
  }, [bots, form.managed_bot_id]);

  const closePlanModal = () => {
    setIsPlanModalOpen(false);
    setEditingPlan(null);
    setForm({ ...emptyPlanForm, managed_bot_id: selectedBotId || bots[0]?.id || "" });
  };

  const savePlanMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        managed_bot_id: form.managed_bot_id,
        name: form.name.trim(),
        description: form.description.trim() || null,
        duration_hours: Number(form.duration_hours),
        price_kopecks: parsePriceToKopecks(form.price_rub),
        sort_order: Number(form.sort_order),
        is_active: form.is_active
      };
      if (editingPlan) {
        return apiRequest<BillingPlan>(
          `/monetization/plans/${editingPlan.id}`,
          {
            method: "PUT",
            body: JSON.stringify({
              name: payload.name,
              description: payload.description,
              duration_hours: payload.duration_hours,
              price_kopecks: payload.price_kopecks,
              sort_order: payload.sort_order,
              is_active: payload.is_active
            })
          },
          token
        );
      }
      return apiRequest<BillingPlan>(
        "/monetization/plans",
        {
          method: "POST",
          body: JSON.stringify(payload)
        },
        token
      );
    },
    onSuccess: async () => {
      closePlanModal();
      await queryClient.invalidateQueries({ queryKey: ["monetization-plans"] });
      await queryClient.invalidateQueries({ queryKey: ["monetization-summary"] });
      pushToast(editingPlan ? "Тариф обновлен" : "Тариф создан", "success");
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось сохранить тариф", "danger");
    }
  });

  const deletePlanMutation = useMutation({
    mutationFn: (planId: string) => apiRequest<{ message: string }>(`/monetization/plans/${planId}`, { method: "DELETE" }, token),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["monetization-plans"] });
      await queryClient.invalidateQueries({ queryKey: ["monetization-summary"] });
      pushToast("Тариф удален", "success");
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось удалить тариф", "danger");
    }
  });

  const botNames = new Map(bots.map((bot) => [bot.id, bot.name]));
  const summary = summaryQuery.data;

  return (
    <>
      <div className="summary-strip">
        <section className="summary-card">
          <span>Активные тарифы</span>
          <strong>{summary?.active_plans ?? "—"}</strong>
        </section>
        <section className="summary-card">
          <span>Оплаченные счета</span>
          <strong>{summary?.paid_payments ?? "—"}</strong>
        </section>
        <section className="summary-card">
          <span>Ожидают оплаты</span>
          <strong>{summary?.pending_payments ?? "—"}</strong>
        </section>
        <section className="summary-card">
          <span>Выручка</span>
          <strong>{summary ? `${summary.paid_total_rub} RUB` : "—"}</strong>
        </section>
      </div>

      <section className="panel">
        <div className="page-titlebar">
          <h2>Прайс-лист</h2>
          <button
            className="primary-button"
            onClick={() => {
              setEditingPlan(null);
              setForm({ ...emptyPlanForm, managed_bot_id: selectedBotId || bots[0]?.id || "" });
              setIsPlanModalOpen(true);
            }}
            type="button"
          >
            Новый тариф
          </button>
        </div>

        <div className="filter-bar">
          <label>
            <span>Бот</span>
            <select value={selectedBotId} onChange={(event) => setSelectedBotId(event.target.value)}>
              <option value="">Все боты</option>
              {bots.map((bot) => (
                <option key={bot.id} value={bot.id}>
                  {bot.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {plansQuery.isLoading ? (
          <p>Загрузка тарифов...</p>
        ) : filteredPlans.length === 0 ? (
          <p>Тарифы пока не настроены.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Бот</th>
                  <th>Тариф</th>
                  <th>Срок</th>
                  <th>Цена</th>
                  <th>Статус</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {filteredPlans.map((plan) => (
                  <tr key={plan.id}>
                    <td>{botNames.get(plan.managed_bot_id) ?? plan.managed_bot_id}</td>
                    <td>
                      <strong>{plan.name}</strong>
                      <div className="table-subtitle">{plan.description || "Без описания"}</div>
                    </td>
                    <td>{formatDuration(plan.duration_hours)}</td>
                    <td>{formatMoney(plan.price_kopecks)}</td>
                    <td>{plan.is_active ? "активен" : "скрыт"}</td>
                    <td className="table-actions">
                      <button
                        className="ghost-button"
                        onClick={() => {
                          setEditingPlan(plan);
                          setForm(toPlanForm(plan));
                          setIsPlanModalOpen(true);
                        }}
                        type="button"
                      >
                        Изменить
                      </button>
                      <button
                        className="ghost-button danger-button"
                        onClick={() => deletePlanMutation.mutate(plan.id)}
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

      <section className="panel">
        <div className="page-titlebar">
          <h2>Последние платежи</h2>
        </div>

        {summaryQuery.isLoading ? (
          <p>Загрузка платежей...</p>
        ) : !summary || summary.recent_payments.length === 0 ? (
          <p>Платежей пока нет.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Заказ</th>
                  <th>Сумма</th>
                  <th>Статус</th>
                  <th>Метод</th>
                  <th>Создан</th>
                </tr>
              </thead>
              <tbody>
                {summary.recent_payments.map((payment) => (
                  <tr key={payment.id}>
                    <td>{payment.merchant_order_id}</td>
                    <td>{formatMoney(payment.amount_kopecks)}</td>
                    <td>{payment.status}</td>
                    <td>{`${payment.provider} / ${payment.payment_method}`}</td>
                    <td>{new Date(payment.created_at).toLocaleString("ru-RU")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

      </section>

      {isPlanModalOpen ? (
        <Modal title={editingPlan ? "Изменить тариф" : "Новый тариф"} onClose={closePlanModal}>
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              savePlanMutation.mutate();
            }}
          >
            <label>
              <span>Бот</span>
              <select
                value={form.managed_bot_id}
                onChange={(event) => setForm({ ...form, managed_bot_id: event.target.value })}
                required
              >
                <option value="">Выберите бота</option>
                {bots.map((bot) => (
                  <option key={bot.id} value={bot.id}>
                    {bot.name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>Название тарифа</span>
              <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
            </label>

            <label>
              <span>Срок, часы</span>
              <input
                type="number"
                min="1"
                max={24 * 365}
                value={form.duration_hours}
                onChange={(event) => setForm({ ...form, duration_hours: event.target.value })}
                required
              />
            </label>

            <label>
              <span>Цена, RUB</span>
              <input
                inputMode="decimal"
                value={form.price_rub}
                onChange={(event) => setForm({ ...form, price_rub: event.target.value })}
                placeholder="199.00"
                required
              />
            </label>

            <label>
              <span>Порядок</span>
              <input
                type="number"
                min="0"
                value={form.sort_order}
                onChange={(event) => setForm({ ...form, sort_order: event.target.value })}
                required
              />
            </label>

            <label className="checkbox-field">
              <input
                checked={form.is_active}
                onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                type="checkbox"
              />
              <span>Показывать в боте</span>
            </label>

            <label className="full-width">
              <span>Описание</span>
              <textarea
                rows={4}
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
                placeholder="Например: базовое продление без смены конфига"
              />
            </label>

            <div className="modal-footer">
              <button className="secondary-button" onClick={closePlanModal} type="button">
                Отмена
              </button>
              <button className="primary-button" disabled={savePlanMutation.isPending} type="submit">
                {savePlanMutation.isPending ? "Сохраняем..." : editingPlan ? "Сохранить" : "Создать"}
              </button>
            </div>
          </form>
        </Modal>
      ) : null}
    </>
  );
}

function MonetizationSettingsTab({ settings }: { settings: SystemSettings }) {
  const { token } = useAuth();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const freekassa = settings.freekassa;
  const [provider, setProvider] = useState("freekassa");
  const [form, setForm] = useState<FreeKassaFormState>(() => toFreeKassaForm(settings));

  useEffect(() => {
    setForm(toFreeKassaForm(settings));
  }, [settings]);

  const saveMutation = useMutation({
    mutationFn: () =>
      apiRequest<SystemSettings>(
        "/system-settings/",
        {
          method: "PUT",
          body: JSON.stringify({
            app_name: settings.app_name,
            public_app_url: settings.public_app_url,
            freekassa_public_url: form.freekassa_public_url.trim() || null,
            trial_duration_hours: settings.trial_duration_hours,
            site_trial_duration_hours: settings.site_trial_duration_hours,
            site_trial_total_gb: settings.site_trial_total_gb,
            scheduler_interval_minutes: settings.scheduler_interval_minutes,
            three_xui_timeout_seconds: settings.three_xui_timeout_seconds,
            three_xui_verify_ssl: settings.three_xui_verify_ssl,
            bot_webhook_base_url: settings.bot_webhook_base_url,
            freekassa_shop_id: form.freekassa_shop_id ? Number(form.freekassa_shop_id) : null,
            freekassa_secret_word: form.freekassa_secret_word.trim() || null,
            freekassa_api_key: form.freekassa_api_key.trim() || null,
            freekassa_secret_word_2: form.freekassa_secret_word_2.trim() || null,
            freekassa_sbp_method_id: Number(form.freekassa_sbp_method_id)
          })
        },
        token
      ),
    onSuccess: async (result) => {
      setForm(toFreeKassaForm(result));
      await queryClient.invalidateQueries({ queryKey: ["system-settings"] });
      pushToast("Настройки FreeKassa сохранены", "success");
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось сохранить FreeKassa", "danger");
    }
  });

  if (!freekassa || provider !== "freekassa") {
    return <div className="panel">Конфигурация FreeKassa недоступна.</div>;
  }

  return (
    <>
      <section className="panel monetization-stack">
        <form
          className="form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            saveMutation.mutate();
          }}
        >
          <label>
            <span>Касса</span>
            <select value={provider} onChange={(event) => setProvider(event.target.value)}>
              <option value="freekassa">FreeKassa</option>
            </select>
          </label>

          <label>
            <span>Shop ID</span>
            <input
              inputMode="numeric"
              type="number"
              min="1"
              value={form.freekassa_shop_id}
              onChange={(event) => setForm({ ...form, freekassa_shop_id: event.target.value })}
            />
          </label>

          <label>
            <span>Публичный URL платежей</span>
            <input
              value={form.freekassa_public_url}
              onChange={(event) => setForm({ ...form, freekassa_public_url: event.target.value })}
              placeholder="https://pay.example.com"
            />
          </label>

          <label>
            <span>Secret Word</span>
            <input
              value={form.freekassa_secret_word}
              onChange={(event) => setForm({ ...form, freekassa_secret_word: event.target.value })}
              placeholder={freekassa.has_secret_word ? "Сохранен" : ""}
            />
          </label>

          <label>
            <span>API ключ</span>
            <input
              value={form.freekassa_api_key}
              onChange={(event) => setForm({ ...form, freekassa_api_key: event.target.value })}
              placeholder={freekassa.has_api_key ? "Сохранен" : ""}
            />
          </label>

          <label>
            <span>Secret Word 2</span>
            <input
              value={form.freekassa_secret_word_2}
              onChange={(event) => setForm({ ...form, freekassa_secret_word_2: event.target.value })}
              placeholder={freekassa.has_secret_word_2 ? "Сохранен" : ""}
            />
          </label>

          <label>
            <span>Метод оплаты FreeKassa</span>
            <select
              value={form.freekassa_sbp_method_id}
              onChange={(event) => setForm({ ...form, freekassa_sbp_method_id: event.target.value })}
            >
              {freeKassaMethodOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <div className="full-width inline-note">
            Сейчас выбран: {freekassa.selected_method_label}. Если СБП уводит в FKwallet, попробуйте 13 (Онлайн банк), 12 (МИР) или 36 (Card RUB API).
          </div>

          {freekassa.notes.length > 0 ? (
            <div className="full-width inline-note">
              {freekassa.notes.map((note) => (
                <div key={note}>{note}</div>
              ))}
            </div>
          ) : null}

          <label>
            <span>URL оповещения</span>
            <input readOnly value={freekassa.endpoints.notification.url} />
          </label>

          <label>
            <span>URL успешной оплаты</span>
            <input readOnly value={freekassa.endpoints.success.url} />
          </label>

          <label>
            <span>URL неудачи</span>
            <input readOnly value={freekassa.endpoints.failure.url} />
          </label>

          <div className="modal-footer">
            <button className="primary-button" disabled={saveMutation.isPending} type="submit">
              {saveMutation.isPending ? "Сохраняем..." : "Сохранить"}
            </button>
          </div>
        </form>
      </section>

      <PaymentDomainManager settings={settings} />
    </>
  );
}

export function MonetizationPage() {
  const { token } = useAuth();
  const location = useLocation();
  const isSettingsTab = location.pathname.startsWith("/monetization/settings");

  const settingsQuery = useQuery({
    queryKey: ["system-settings"],
    queryFn: () => apiRequest<SystemSettings>("/system-settings/", {}, token),
    enabled: Boolean(token)
  });

  const settings = settingsQuery.data;

  return (
    <div className="page-content">
      <header className="page-titlebar">
        <h1>Монетизация</h1>
      </header>

      <div className="monetization-tabs">
        <NavLink
          end
          to="/monetization"
          className={({ isActive }) => `monetization-tab${isActive ? " monetization-tab--active" : ""}`}
        >
          <strong>Обзор</strong>
        </NavLink>

        <NavLink
          to="/monetization/settings"
          className={({ isActive }) => `monetization-tab${isActive ? " monetization-tab--active" : ""}`}
        >
          <strong>FreeKassa</strong>
        </NavLink>
      </div>

      {settingsQuery.isLoading ? (
        <div className="panel">Загрузка...</div>
      ) : settings ? (
        isSettingsTab ? <MonetizationSettingsTab settings={settings} /> : <MonetizationOverviewTab />
      ) : (
        <div className="panel">Не удалось загрузить настройки монетизации.</div>
      )}
    </div>
  );
}
