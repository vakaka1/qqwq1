import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { apiRequest } from "../api/http";
import { useAuth } from "../features/auth/AuthProvider";
import type { SystemSettings } from "../lib/types";

function MonetizationOverviewTab() {
  return (
    <section className="panel">
      <div className="inline-note">В разработке.</div>
    </section>
  );
}

function MonetizationSettingsTab({ settings }: { settings: SystemSettings }) {
  const freekassa = settings.freekassa;
  const [provider, setProvider] = useState("freekassa");

  if (!freekassa || provider !== "freekassa") {
    return <div className="panel">Конфигурация FreeKassa недоступна.</div>;
  }

  return (
    <section className="panel monetization-stack">
      <div className="monetization-settings-grid">
        <label className="monetization-settings-field">
          <span>Касса</span>
          <select value={provider} onChange={(event) => setProvider(event.target.value)}>
            <option value="freekassa">FreeKassa</option>
          </select>
        </label>

        <label className="monetization-settings-field">
          <span>URL оповещения</span>
          <input readOnly value={freekassa.endpoints.notification.url} />
        </label>

        <label className="monetization-settings-field">
          <span>URL успешной оплаты</span>
          <input readOnly value={freekassa.endpoints.success.url} />
        </label>

        <label className="monetization-settings-field">
          <span>URL возврата в случае неудачи</span>
          <input readOnly value={freekassa.endpoints.failure.url} />
        </label>
      </div>
    </section>
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
        <div>
          <h1>Монетизация</h1>
          <p className="table-subtitle">Раздел под кассы, платежные ссылки и будущую сводку по доходу.</p>
        </div>
      </header>

      <div className="monetization-tabs">
        <NavLink
          end
          to="/monetization"
          className={({ isActive }) => `monetization-tab${isActive ? " monetization-tab--active" : ""}`}
        >
          <strong>Обзор</strong>
          <span>Сводка по монетизации.</span>
        </NavLink>

        <NavLink
          to="/monetization/settings"
          className={({ isActive }) => `monetization-tab${isActive ? " monetization-tab--active" : ""}`}
        >
          <strong>Настройка</strong>
          <span>Подключение и платежные URL.</span>
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
