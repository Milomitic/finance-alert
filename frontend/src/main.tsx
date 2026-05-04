import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import App from "./App";
import { queryClient } from "@/lib/query-client";
import "./index.css";

// `delayDuration={150}` matches the snappy feel users expect from custom
// tooltips while still avoiding flicker on accidental hover. `skipDelayDuration`
// (default 300ms) means once one tooltip has shown, hovering a sibling shows
// instantly — important for valuation-row hover scanning where the user is
// reading multiple cells in a row.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <TooltipProvider delayDuration={150}>
          <App />
        </TooltipProvider>
        <Toaster richColors position="top-right" />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>
);
