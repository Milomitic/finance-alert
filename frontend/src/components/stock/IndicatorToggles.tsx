interface Props {
  showSma50: boolean;
  showSma200: boolean;
  onToggle: (key: "sma50" | "sma200", value: boolean) => void;
}

export function IndicatorToggles({ showSma50, showSma200, onToggle }: Props) {
  return (
    <div className="inline-flex items-center gap-3 text-xs">
      <label className="inline-flex items-center gap-1 cursor-pointer">
        <input
          type="checkbox"
          checked={showSma50}
          onChange={(e) => onToggle("sma50", e.target.checked)}
          className="cursor-pointer"
        />
        <span style={{ color: "#3b82f6" }}>SMA 50</span>
      </label>
      <label className="inline-flex items-center gap-1 cursor-pointer">
        <input
          type="checkbox"
          checked={showSma200}
          onChange={(e) => onToggle("sma200", e.target.checked)}
          className="cursor-pointer"
        />
        <span style={{ color: "#f59e0b" }}>SMA 200</span>
      </label>
    </div>
  );
}
