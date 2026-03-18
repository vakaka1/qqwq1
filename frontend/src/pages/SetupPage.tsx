import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../api/http";
import { useAuth } from "../features/auth/AuthProvider";

function generateUsername() {
  const randomPart = Math.random().toString(36).slice(2, 7);
  return `owner-${randomPart}`;
}

export function SetupPage() {
  const navigate = useNavigate();
  const { completeSetup } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    setUsername(generateUsername());
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await completeSetup(username, password, passwordConfirm);
      navigate("/");
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Не удалось завершить настройку";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-layout">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>Первичная настройка</h1>
        <label>
          <span>Логин</span>
          <div className="input-with-action">
            <input value={username} onChange={(event) => setUsername(event.target.value)} required />
            <button
              className="secondary-button"
              onClick={() => setUsername(generateUsername())}
              type="button"
            >
              Новый
            </button>
          </div>
        </label>
        <label>
          <span>Пароль</span>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            minLength={8}
            required
          />
        </label>
        <label>
          <span>Повтор пароля</span>
          <input
            value={passwordConfirm}
            onChange={(event) => setPasswordConfirm(event.target.value)}
            type="password"
            minLength={8}
            required
          />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <button className="primary-button" disabled={isSubmitting} type="submit">
          {isSubmitting ? "Сохраняем..." : "Сохранить и войти"}
        </button>
      </form>
    </div>
  );
}
