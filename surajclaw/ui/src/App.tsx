import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useAuth } from "@/context/AuthContext";
import { Shell } from "@/components/layout/Shell";

import Dashboard from "@/pages/Dashboard";
import Pipeline from "@/pages/Pipeline";
import Memory from "@/pages/Memory";
import Tasks from "@/pages/Tasks";
import Integrations from "@/pages/Integrations";
import Chat from "@/pages/Chat";
import Login from "@/pages/Login";

function FullScreenLoading() {
  return (
    <div className="min-h-screen flex items-center justify-center text-ink-dim">
      <span className="font-mono text-xs label-mono animate-pulseDot">
        BOOTING OPERATOR CONSOLE…
      </span>
    </div>
  );
}

function ProtectedShell() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullScreenLoading />;
  if (!user) {
    return (
      <Navigate to="/login" replace state={{ from: location.pathname }} />
    );
  }
  return <Shell />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedShell />}>
        <Route index element={<Dashboard />} />
        <Route path="pipeline" element={<Pipeline />} />
        <Route path="memory" element={<Memory />} />
        <Route path="tasks" element={<Tasks />} />
        <Route path="chat" element={<Chat />} />
        <Route path="integrations" element={<Integrations />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
