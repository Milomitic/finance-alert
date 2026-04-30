import { useParams } from "react-router-dom";

export default function WatchlistDetailPage() {
  const { id } = useParams();
  return (
    <div>
      <h2 className="text-2xl font-semibold">{id ? `Watchlist #${id}` : "Nuova watchlist"}</h2>
      <p className="text-sm text-muted-foreground mt-2">
        Pagina in costruzione (Task I2/I3).
      </p>
    </div>
  );
}
