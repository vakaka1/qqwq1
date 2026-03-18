import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "../components/AppShell";
import { ToastProvider } from "../components/ToastProvider";
import { AuthProvider, useAuth } from "../features/auth/AuthProvider";
import { AccessesPage } from "../pages/AccessesPage";
import { AdminsPage } from "../pages/AdminsPage";
import { BotsPage } from "../pages/BotsPage";
import { DashboardPage } from "../pages/DashboardPage";
import { LoginPage } from "../pages/LoginPage";
import { LogsPage } from "../pages/LogsPage";
import { ServersPage } from "../pages/ServersPage";
import { SetupPage } from "../pages/SetupPage";
import { UsersPage } from "../pages/UsersPage";

const queryClient = new QueryClient();

function ProtectedRoutes() {
  const { token, isReady } = useAuth();
  if (!isReady) {
    return <div className="screen-loader">Проверяем сессию...</div>;
  }
  if (!token) {
    return <Navigate replace to="/login" />;
  }
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/bots" element={<BotsPage />} />
        <Route path="/servers" element={<ServersPage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/accesses" element={<AccessesPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/admins" element={<AdminsPage />} />
      </Route>
      <Route path="*" element={<Navigate replace to="/" />} />
    </Routes>
  );
}

function AppRoutes() {
  const { token, isInitialized, isReady } = useAuth();
  if (!isReady || isInitialized === null) {
    return <div className="screen-loader">Проверяем доступ...</div>;
  }
  return (
    <Routes>
      <Route
        path="/login"
        element={token ? <Navigate replace to="/" /> : isInitialized ? <LoginPage /> : <SetupPage />}
      />
      <Route path="/*" element={<ProtectedRoutes />} />
    </Routes>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
