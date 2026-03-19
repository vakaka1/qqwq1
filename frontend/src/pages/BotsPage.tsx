import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiRequest, ApiError } from "../api/http";
import { Badge } from "../components/Badge";
import { Modal } from "../components/Modal";
import { useToast } from "../components/ToastProvider";
import { useAuth } from "../features/auth/AuthProvider";
import type { ManagedBot } from "../lib/types";

interface BotFormState {
  name: string;
  telegram_token: string;
  telegram_bot_username: string;
  welcome_text: string;
  help_text: string;
  is_active: boolean;
}

const emptyForm: BotFormState = {
  name: "",
  telegram_token: "",
  telegram_bot_username: "",
  welcome_text: "",
  help_text: "",
  is_active: true
};

function toForm(bot: ManagedBot): BotFormState {
  return {
    name: bot.name,
    telegram_token: "",
    telegram_bot_username: bot.telegram_bot_username ?? "",
    welcome_text: bot.welcome_text ?? "",
    help_text: bot.help_text ?? "",
    is_active: bot.is_active
  };
}

function normalizeBotUsername(value: string) {
  return value.trim().replace(/^@+/, "");
}

export function BotsPage() {
  const { token } = useAuth();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingBot, setEditingBot] = useState<ManagedBot | null>(null);
  const [form, setForm] = useState<BotFormState>(emptyForm);
  const [isMailingModalOpen, setIsMailingModalOpen] = useState(false);
  const [mailingBot, setMailingBot] = useState<ManagedBot | null>(null);
  const [mailingText, setMailingText] = useState("");
  const [mailingImageFile, setMailingImageFile] = useState<File | null>(null);

  const closeMailingModal = () => {
    setIsMailingModalOpen(false);
    setMailingBot(null);
    setMailingText("");
    setMailingImageFile(null);
  };

  const mailingMutation = useMutation({
    mutationFn: () => {
      const formData = new FormData();
      formData.append("text", mailingText.trim());
      if (mailingImageFile) {
        formData.append("image", mailingImageFile);
      }
      return apiRequest<{ message: string }>(
        `/bots/${mailingBot?.id}/mailing`,
        {
          method: "POST",
          body: formData
        },
        token
      );
    },
    onSuccess: (result) => {
      pushToast(result.message, "success");
      closeMailingModal();
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось отправить рассылку", "danger");
    }
  });

  const { data: bots, isLoading } = useQuery({
    queryKey: ["bots"],
    queryFn: () => apiRequest<ManagedBot[]>("/bots/", {}, token)
  });

  const botItems = bots ?? [];
  const activeCount = botItems.filter((item) => item.is_active).length;

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingBot(null);
    setForm(emptyForm);
  };

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = {
        name: form.name.trim(),
        telegram_bot_username: normalizeBotUsername(form.telegram_bot_username) || null,
        welcome_text: form.welcome_text.trim() || null,
        help_text: form.help_text.trim() || null,
        is_active: form.is_active,
        telegram_token: form.telegram_token || undefined
      };
      if (editingBot) {
        return apiRequest<ManagedBot>(
          `/bots/${editingBot.id}`,
          { method: "PUT", body: JSON.stringify(payload) },
          token
        );
      }
      return apiRequest<ManagedBot>("/bots/", { method: "POST", body: JSON.stringify(payload) }, token);
    },
    onSuccess: async () => {
      pushToast("Бот сохранен", "success");
      closeModal();
      await queryClient.invalidateQueries({ queryKey: ["bots"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось сохранить бота", "danger");
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (botId: string) => apiRequest<{ message: string }>(`/bots/${botId}`, { method: "DELETE" }, token),
    onSuccess: async () => {
      pushToast("Бот удален", "success");
      await queryClient.invalidateQueries({ queryKey: ["bots"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (error) => {
      pushToast(error instanceof ApiError ? error.message : "Не удалось удалить бота", "danger");
    }
  });

  return (
    <div className="page-content">
      <header className="page-titlebar">
        <div>
          <h1>Боты</h1>
        </div>
        <button
          className="primary-button"
          onClick={() => {
            setEditingBot(null);
            setForm(emptyForm);
            setIsModalOpen(true);
          }}
          type="button"
        >
          Добавить бота
        </button>
      </header>

      <div className="summary-strip">
        <section className="summary-card">
          <span>Всего</span>
          <strong>{botItems.length}</strong>
        </section>
        <section className="summary-card">
          <span>Активные</span>
          <strong>{activeCount}</strong>
        </section>
      </div>

      <section className="entity-grid">
        {isLoading ? (
          <div className="panel">Загрузка...</div>
        ) : botItems.length === 0 ? (
          <div className="panel">Боты ещё не добавлены.</div>
        ) : (
          botItems.map((bot) => (
            <article key={bot.id} className="entity-card">
              <div className="entity-card__header">
                <div>
                  <h3>{bot.name}</h3>
                  <p className="table-subtitle">{bot.telegram_bot_username ? `@${bot.telegram_bot_username}` : "Юзернейм не указан"}</p>
                </div>
                <Badge tone={bot.is_active ? "success" : "warning"}>
                  {bot.is_active ? "активен" : "отключен"}
                </Badge>
              </div>
              <dl className="meta-list">
                <div>
                  <dt>Токен</dt>
                  <dd>{bot.has_token ? "сохранен" : "не задан"}</dd>
                </div>
                <div>
                  <dt>Синхронизация</dt>
                  <dd>{bot.last_synced_at ? new Date(bot.last_synced_at).toLocaleString("ru-RU") : "—"}</dd>
                </div>
              </dl>
              <div className="table-actions">
                <button
                  className="ghost-button"
                  onClick={() => {
                    setMailingBot(bot);
                    setMailingText("");
                    setMailingImageFile(null);
                    setIsMailingModalOpen(true);
                  }}
                  type="button"
                >
                  Рассылка
                </button>
                <button
                  className="ghost-button"
                  onClick={() => {
                    setEditingBot(bot);
                    setForm(toForm(bot));
                    setIsModalOpen(true);
                  }}
                  type="button"
                >
                  Редактировать
                </button>
                <button
                  className="ghost-button danger-button"
                  onClick={() => deleteMutation.mutate(bot.id)}
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
        <Modal title={editingBot ? "Редактировать бота" : "Новый бот"} onClose={closeModal}>
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
                placeholder="Например, Основной бот"
                required
              />
            </label>

            <label>
              <span>Юзернейм бота</span>
              <input
                value={form.telegram_bot_username}
                onChange={(event) => setForm({ ...form, telegram_bot_username: event.target.value })}
                placeholder="@my_bot"
              />
            </label>

            <label className="full-width">
              <span>Токен</span>
              <input
                type="password"
                value={form.telegram_token}
                onChange={(event) => setForm({ ...form, telegram_token: event.target.value })}
                placeholder={editingBot?.has_token ? "Оставьте пустым, чтобы не менять" : ""}
                required={!editingBot}
              />
            </label>

            <label className="full-width">
              <span>Приветственное сообщение</span>
              <textarea
                rows={4}
                value={form.welcome_text}
                onChange={(event) => setForm({ ...form, welcome_text: event.target.value })}
                placeholder="Можно оставить пустым."
              />
            </label>

            <label className="full-width">
              <span>Сообщение помощи</span>
              <textarea
                rows={4}
                value={form.help_text}
                onChange={(event) => setForm({ ...form, help_text: event.target.value })}
                placeholder="Можно оставить пустым."
              />
            </label>

            <label className="checkbox-field">
              <input
                checked={form.is_active}
                onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                type="checkbox"
              />
              <span>Активен</span>
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

      {isMailingModalOpen ? (
        <Modal title={`Рассылка: ${mailingBot?.name}`} onClose={closeMailingModal}>
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              mailingMutation.mutate();
            }}
          >
            <label className="full-width">
              <span>Текст сообщения</span>
              <textarea
                rows={6}
                value={mailingText}
                onChange={(event) => setMailingText(event.target.value)}
                placeholder="Текст рассылки..."
                required
              />
              <small className="field-meta">Сообщение будет отправлено всем пользователям этого бота.</small>
            </label>

            <label className="full-width">
              <span>Изображение</span>
              <input
                accept="image/*"
                onChange={(event) => setMailingImageFile(event.target.files?.[0] ?? null)}
                type="file"
              />
              <small className="field-meta">
                {mailingImageFile
                  ? `Выбран файл: ${mailingImageFile.name}`
                  : "Необязательно. Файл будет отправлен в Telegram и не сохраняется в проекте."}
              </small>
            </label>

            <div className="modal-footer">
              <button className="secondary-button" onClick={closeMailingModal} type="button">
                Отмена
              </button>
              <button className="primary-button" disabled={mailingMutation.isPending} type="submit">
                {mailingMutation.isPending ? "Отправляем..." : "Отправить рассылку"}
              </button>
            </div>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
