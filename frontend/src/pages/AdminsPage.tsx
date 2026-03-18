import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { apiRequest, ApiError } from "../api/http";
import { Badge } from "../components/Badge";
import { Modal } from "../components/Modal";
import { useToast } from "../components/ToastProvider";
import { useAuth } from "../features/auth/AuthProvider";
import type { Admin } from "../lib/types";

interface AdminFormState {
  username: string;
  password: string;
  password_confirm: string;
  is_active: boolean;
}

const emptyForm: AdminFormState = {
  username: "",
  password: "",
  password_confirm: "",
  is_active: true
};

function toForm(admin: Admin): AdminFormState {
  return {
    username: admin.username,
    password: "",
    password_confirm: "",
    is_active: admin.is_active
  };
}

export function AdminsPage() {
  const { token, admin: currentAdmin } = useAuth();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingAdmin, setEditingAdmin] = useState<Admin | null>(null);
  const [form, setForm] = useState<AdminFormState>(emptyForm);
  const shouldUpdatePassword = Boolean(form.password || form.password_confirm);

  const { data: admins, isLoading } = useQuery({
    queryKey: ["admins"],
    queryFn: () => apiRequest<Admin[]>("/admins/", {}, token)
  });

  const adminItems = admins ?? [];
  const activeCount = adminItems.filter((item) => item.is_active).length;
  const selfItem = adminItems.find((item) => item.id === currentAdmin?.id) ?? null;

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingAdmin(null);
    setForm(emptyForm);
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        username: form.username,
        is_active: form.is_active,
        ...(shouldUpdatePassword
          ? {
              password: form.password,
              password_confirm: form.password_confirm
            }
          : {})
      };
      if (editingAdmin) {
        return apiRequest<Admin>(
          `/admins/${editingAdmin.id}`,
          { method: "PUT", body: JSON.stringify(payload) },
          token
        );
      }
      return apiRequest<Admin>("/admins/", { method: "POST", body: JSON.stringify(payload) }, token);
    },
    onSuccess: async () => {
      pushToast(editingAdmin ? "Администратор обновлен" : "Администратор добавлен", "success");
      setIsModalOpen(false);
      setEditingAdmin(null);
      setForm(emptyForm);
      await queryClient.invalidateQueries({ queryKey: ["admins"] });
    },
    onError: (error) => {
      pushToast(
        error instanceof ApiError ? error.message : "Не удалось сохранить администратора",
        "danger"
      );
    }
  });

  return (
    <div className="page-content">
      <header className="page-titlebar">
        <div>
          <h1>Администраторы</h1>
        </div>
        <button
          className="primary-button"
          onClick={() => {
            setEditingAdmin(null);
            setForm(emptyForm);
            setIsModalOpen(true);
          }}
          type="button"
        >
          Добавить
        </button>
      </header>

      <div className="summary-strip">
        <section className="summary-card">
          <span>Всего</span>
          <strong>{adminItems.length}</strong>
        </section>
        <section className="summary-card">
          <span>Активные</span>
          <strong>{activeCount}</strong>
        </section>
        <section className="summary-card">
          <span>Вы редактируете</span>
          <strong>{selfItem ? "только себя" : "—"}</strong>
        </section>
      </div>

      <section className="entity-grid">
        {isLoading ? (
          <div className="panel">Загрузка...</div>
        ) : adminItems.length === 0 ? (
          <div className="panel">Администраторы пока не добавлены.</div>
        ) : (
          adminItems.map((item) => (
            <article key={item.id} className="entity-card">
              <div className="entity-card__header">
                <div>
                  <h3>{item.username}</h3>
                  <p className="table-subtitle">
                    {currentAdmin?.id === item.id ? "Текущая учетная запись" : "Администратор"}
                  </p>
                </div>
                <Badge tone={item.is_active ? "success" : "warning"}>
                  {item.is_active ? "активен" : "отключен"}
                </Badge>
              </div>
              <dl className="meta-list">
                <div>
                  <dt>Последний вход</dt>
                  <dd>{item.last_login_at ? new Date(item.last_login_at).toLocaleString("ru-RU") : "—"}</dd>
                </div>
                <div>
                  <dt>Создан</dt>
                  <dd>{new Date(item.created_at).toLocaleString("ru-RU")}</dd>
                </div>
              </dl>
              <div className="table-actions">
                {currentAdmin?.id === item.id ? (
                  <button
                    className="ghost-button"
                    onClick={() => {
                      setEditingAdmin(item);
                      setForm(toForm(item));
                      setIsModalOpen(true);
                    }}
                    type="button"
                  >
                    Редактировать
                  </button>
                ) : (
                  <span className="muted">Редактирование недоступно</span>
                )}
              </div>
            </article>
          ))
        )}
      </section>

      {isModalOpen ? (
        <Modal title={editingAdmin ? "Редактировать администратора" : "Новый администратор"} onClose={closeModal}>
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              saveMutation.mutate();
            }}
          >
            <label>
              <span>Логин</span>
              <input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} required />
            </label>
            <label className="checkbox-field">
              <input
                checked={form.is_active}
                onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
                type="checkbox"
              />
              <span>Активен</span>
            </label>
            <label>
              <span>{editingAdmin ? "Новый пароль" : "Пароль"}</span>
              <input
                type="password"
                value={form.password}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
                minLength={shouldUpdatePassword ? 8 : undefined}
                required={!editingAdmin}
                placeholder={editingAdmin ? "Оставьте пустым, чтобы не менять" : ""}
              />
            </label>
            <label>
              <span>Повтор пароля</span>
              <input
                type="password"
                value={form.password_confirm}
                onChange={(event) => setForm({ ...form, password_confirm: event.target.value })}
                minLength={shouldUpdatePassword ? 8 : undefined}
                required={!editingAdmin}
                placeholder={editingAdmin ? "Заполняется только при смене пароля" : ""}
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
