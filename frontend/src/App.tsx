import { lazy, Suspense } from "react";
import { Loader2 } from "lucide-react";
import { Route, Routes } from "react-router-dom";

import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";

// Route components are code-split via React.lazy so the heavy, page-specific
// dependencies (notably lightweight-charts on the stock/market detail pages)
// ship in their own chunks instead of the initial bundle. Behavior is
// unchanged — each page still mounts exactly as before, just fetched on
// demand the first time its route is visited.
const AlertsPage = lazy(() => import("@/pages/AlertsPage"));
const CalendarPage = lazy(() => import("@/pages/CalendarPage"));
const HomePage = lazy(() => import("@/pages/HomePage"));
const InstitutionalDetailPage = lazy(() => import("@/pages/InstitutionalDetailPage"));
const InstitutionalsPage = lazy(() => import("@/pages/InstitutionalsPage"));
const LoginPage = lazy(() => import("@/pages/LoginPage"));
const MacroDetailPage = lazy(() => import("@/pages/MacroDetailPage"));
const PlatformHealthPage = lazy(() => import("@/pages/PlatformHealthPage"));
const MarketDetailPage = lazy(() => import("@/pages/MarketDetailPage"));
const SectorDetailPage = lazy(() => import("@/pages/SectorDetailPage"));
const SectorsOverviewPage = lazy(() => import("@/pages/SectorsOverviewPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const StockDetailPage = lazy(() => import("@/pages/StockDetailPage"));
const StocksBrowserPage = lazy(() => import("@/pages/StocksBrowserPage"));

/** Centered spinner shown while a lazily-loaded route chunk is fetched.
 *  Matches the existing Loader2 + animate-spin pattern used across pages. */
function RouteFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
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
          <Route path="/health" element={<PlatformHealthPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/macro/:seriesId" element={<MacroDetailPage />} />
          <Route path="/stocks" element={<StocksBrowserPage />} />
          <Route path="/stocks/:ticker" element={<StockDetailPage />} />
          <Route path="/markets/:symbol" element={<MarketDetailPage />} />
          <Route path="/sectors/:name" element={<SectorDetailPage />} />
          <Route path="/institutionals" element={<InstitutionalsPage />} />
          <Route path="/institutionals/:slug" element={<InstitutionalDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          {/* /rules removed: rule engine deleted backend-side; alerts are signals-only. */}
        </Route>
        <Route path="*" element={<div className="p-8">404</div>} />
      </Routes>
    </Suspense>
  );
}
