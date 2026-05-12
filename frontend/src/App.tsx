import { Route, Routes } from "react-router-dom";

import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";
import AlertsPage from "@/pages/AlertsPage";
import CalendarPage from "@/pages/CalendarPage";
import HomePage from "@/pages/HomePage";
import InstitutionalDetailPage from "@/pages/InstitutionalDetailPage";
import InstitutionalsPage from "@/pages/InstitutionalsPage";
import LoginPage from "@/pages/LoginPage";
import MarketDetailPage from "@/pages/MarketDetailPage";
import SectorDetailPage from "@/pages/SectorDetailPage";
import SectorsOverviewPage from "@/pages/SectorsOverviewPage";
import SettingsPage from "@/pages/SettingsPage";
import StockDetailPage from "@/pages/StockDetailPage";
import StocksBrowserPage from "@/pages/StocksBrowserPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<HomePage />} />
        {/* /sectors took the slot previously held by /watchlists.
            The watchlist feature (custom rule overrides on user-curated
            stock lists) was removed in May 2026 — see CLAUDE.md. The
            slot is now a hub page listing every sector + sub-sector
            with aggregate data, and each sector tile drills down into
            the existing /sectors/:name detail page. */}
        <Route path="/sectors" element={<SectorsOverviewPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/stocks" element={<StocksBrowserPage />} />
        <Route path="/stocks/:ticker" element={<StockDetailPage />} />
        <Route path="/markets/:symbol" element={<MarketDetailPage />} />
        <Route path="/sectors/:name" element={<SectorDetailPage />} />
        <Route path="/institutionals" element={<InstitutionalsPage />} />
        <Route path="/institutionals/:slug" element={<InstitutionalDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        {/* /rules removed: rules now live in the AlertsPage right sidebar
            (RulesPanel) since they're tightly coupled with the alerts they
            produce. */}
      </Route>
      <Route path="*" element={<div className="p-8">404</div>} />
    </Routes>
  );
}
