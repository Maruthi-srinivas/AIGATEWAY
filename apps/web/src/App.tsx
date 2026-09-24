import { Route, Routes } from "react-router-dom";

import { Shell } from "./layout/Shell";
import { AuditPage } from "./pages/AuditPage";
import { ChatPage } from "./pages/ChatPage";
import { ConversationsPage } from "./pages/ConversationsPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { FailuresPage } from "./pages/FailuresPage";
import { FlowPage } from "./pages/FlowPage";
import { MapPage } from "./pages/MapPage";
import { PolicyPage } from "./pages/PolicyPage";
import { ReadyPage } from "./pages/ReadyPage";

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<MapPage />} />
        <Route path="flow" element={<FlowPage />} />
        <Route path="failures" element={<FailuresPage />} />
        <Route path="try" element={<ChatPage />} />
        <Route path="try/conversations" element={<ConversationsPage />} />
        <Route path="try/documents" element={<DocumentsPage />} />
        <Route path="try/policy" element={<PolicyPage />} />
        <Route path="try/audit" element={<AuditPage />} />
        <Route path="try/ready" element={<ReadyPage />} />
      </Route>
    </Routes>
  );
}
