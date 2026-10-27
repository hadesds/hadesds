import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { getToken, setToken } from "./api";
import Dashboard from "./pages/Dashboard";
import Deliveries from "./pages/Deliveries";
import Login from "./pages/Login";
import News from "./pages/News";
import ScriptDetail from "./pages/ScriptDetail";
import Scripts from "./pages/Scripts";
import SettingsPage from "./pages/Settings";
import Sources from "./pages/Sources";

const NAV = [
  ["/", "Painel"], ["/fontes", "Fontes"], ["/noticias", "Notícias"], ["/roteiros", "Roteiros"],
  ["/entregas", "Entregas"], ["/configuracoes", "Configurações"],
] as const;

export default function App() {
  const [authed, setAuthed] = useState(Boolean(getToken()));
  useEffect(() => {
    const onLogout = () => setAuthed(false);
    window.addEventListener("devpulse:logout", onLogout);
    return () => window.removeEventListener("devpulse:logout", onLogout);
  }, []);

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;
  return (
    <div className="layout">
      <header className="topbar">
        <span className="brand">DevPulse <strong>AI</strong></span>
        <nav>
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
          ))}
        </nav>
        <button className="link" onClick={() => { setToken(null); setAuthed(false); }}>Sair</button>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/fontes" element={<Sources />} />
          <Route path="/noticias" element={<News />} />
          <Route path="/roteiros" element={<Scripts />} />
          <Route path="/roteiros/:id" element={<ScriptDetail />} />
          <Route path="/entregas" element={<Deliveries />} />
          <Route path="/configuracoes" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}
