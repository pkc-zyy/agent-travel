import { useState } from "react";
import Layout, { type PageKey } from "./components/Layout";
import ArchitecturePage from "./pages/ArchitecturePage";
import ChatPage from "./pages/ChatPage";
import FeedbackPage from "./pages/FeedbackPage";
import KnowledgePage from "./pages/KnowledgePage";
import MonitorPage from "./pages/MonitorPage";
import OrdersPage from "./pages/OrdersPage";
import PlansPage from "./pages/PlansPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  const [page, setPage] = useState<PageKey>("chat");

  return (
    <Layout page={page} onNavigate={setPage}>
      {page === "chat" && <ChatPage onNavigate={setPage} />}
      {page === "plans" && <PlansPage />}
      {page === "orders" && <OrdersPage />}
      {page === "knowledge" && <KnowledgePage />}
      {page === "feedback" && <FeedbackPage />}
      {page === "monitor" && <MonitorPage />}
      {page === "settings" && <SettingsPage />}
      {page === "architecture" && <ArchitecturePage />}
    </Layout>
  );
}
