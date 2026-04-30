import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";
import LoginPage from "@/pages/LoginPage";
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
        <Route path="/" element={<Navigate to="/watchlists" replace />} />
        <Route path="/watchlists" element={<WatchlistListPage />} />
        <Route path="/watchlists/new" element={<WatchlistDetailPage />} />
        <Route path="/watchlists/:id" element={<WatchlistDetailPage />} />
      </Route>
      <Route path="*" element={<div className="p-8">404</div>} />
    </Routes>
  );
}
