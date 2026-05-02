import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "@/components/layout/Layout";
import { RequireAuth } from "@/components/layout/RequireAuth";
import Chat from "@/pages/Chat";
import Dashboard from "@/pages/Dashboard";
import Integrations from "@/pages/Integrations";
import Login from "@/pages/Login";
import Memory from "@/pages/Memory";
import Pipeline from "@/pages/Pipeline";
import Tasks from "@/pages/Tasks";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="chat" element={<Chat />} />
        <Route path="memory" element={<Memory />} />
        <Route path="tasks" element={<Tasks />} />
        <Route path="pipeline" element={<Pipeline />} />
        <Route path="integrations" element={<Integrations />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
