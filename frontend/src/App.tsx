import { lazy, Suspense } from "react";
import { Loader2 } from "lucide-react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

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
const PositionsPage = lazy(() => import("@/pages/PositionsPage"));
const MarketDetailPage = lazy(() => import("@/pages/MarketDetailPage"));
const SectorDetailPage = lazy(() => import("@/pages/SectorDetailPage"));
const SectorsOverviewPage = lazy(() => import("@/pages/SectorsOverviewPage"));
const DiagnosticsPage = lazy(() => import("@/pages/DiagnosticsPage"));
const StockDetailPage = lazy(() => import("@/pages/StockDetailPage"));
const StocksBrowserPage = lazy(() => import("@/pages/StocksBrowserPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));

/** `/setups` e' diventata una scheda di `/alerts` (2026-09-19) e reindirizza
 *  PORTANDOSI DIETRO LA QUERY: i link interni e i segnalibri esistenti
 *  filtravano per titolo (`?ticker=`) e per vista (`?vista=esiti`), e un
 *  redirect che perdesse i parametri li aprirebbe su una lista intera senza
 *  dire che il filtro e' caduto.
 *
 *  ⚠️ `vista=esiti` nel vecchio indirizzo significava «i SETUP chiusi», che
 *  nella pagina nuova e' la sottovista `esiti=setup`: senza la traduzione, il
 *  link «guarda il setup che ha annunciato questo segnale» finirebbe sui
 *  piani risolti, che e' un altro elenco. */
function VaiAllaScheda() {
  const { search } = useLocation();
  const p = new URLSearchParams(search);
  if (p.get("vista") === "esiti") p.set("esiti", "setup");
  else p.set("vista", "formazione");
  return <Navigate to={`/alerts?${p.toString()}`} replace />;
}

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
          {/* Setups: lo stato pre-scatto degli stessi detector. Dal
              2026-09-19 e' una SCHEDA di /alerts — restano due liste distinte
              (un setup e' un'attesa, non una chiamata) dentro una
              destinazione sola, perche' il ciclo di vita e' uno: setup →
              segnale → posizione. La rotta storica reindirizza. */}
          <Route path="/setups" element={<VaiAllaScheda />} />
          {/* Tracked trades (B3-6): playbook entries persisted as positions
              with live P&L + auto stop/target closing. */}
          <Route path="/positions" element={<PositionsPage />} />
          {/* Diagnostica: una destinazione, due schede.
              ⚠️ Le due rotte storiche NON spariscono, reindirizzano — i
              segnalibri esistenti continuano a funzionare, e `replace` evita
              che il tasto indietro rimbalzi sul redirect. */}
          <Route path="/diagnostics" element={<DiagnosticsPage />} />
          <Route
            path="/health"
            element={<Navigate to="/diagnostics?vista=piattaforma" replace />}
          />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/macro/:seriesId" element={<MacroDetailPage />} />
          <Route path="/stocks" element={<StocksBrowserPage />} />
          <Route path="/stocks/:ticker" element={<StockDetailPage />} />
          <Route path="/markets/:symbol" element={<MarketDetailPage />} />
          <Route path="/sectors/:name" element={<SectorDetailPage />} />
          <Route path="/institutionals" element={<InstitutionalsPage />} />
          <Route path="/institutionals/:slug" element={<InstitutionalDetailPage />} />
          <Route
            path="/settings"
            element={<Navigate to="/diagnostics?vista=motore" replace />}
          />
          {/* /rules removed: rule engine deleted backend-side; alerts are signals-only. */}
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
