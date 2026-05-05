import { Route, Routes } from "react-router-dom";

import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";
import AlertsPage from "@/pages/AlertsPage";
import CalendarPage from "@/pages/CalendarPage";
import HomePage from "@/pages/HomePage";
import LoginPage from "@/pages/LoginPage";
import StockDetailPage from "@/pages/StockDetailPage";
import StocksBrowserPage from "@/pages/StocksBrowserPage";
import WatchlistDetailPage from "@/pages/WatchlistDetailPage";
import WatchlistListPage from "@/pages/WatchlistListPage";

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
        <Route path="/watchlists" element={<WatchlistListPage />} />
        <Route path="/watchlists/new" element={<WatchlistDetailPage />} />
        <Route path="/watchlists/:id" element={<WatchlistDetailPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/stocks" element={<StocksBrowserPage />} />
        <Route path="/stocks/:ticker" element={<StockDetailPage />} />
        {/* /rules removed: rules now live in the AlertsPage right sidebar
            (RulesPanel) since they're tightly coupled with the alerts they
            produce. */}
      </Route>
      <Route path="*" element={<div className="p-8">404</div>} />
    </Routes>
  );
}
