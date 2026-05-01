import type { Alert } from "@/api/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface Props {
  alert: Alert | null;
  onClose: () => void;
}

export function AlertDetailDialog({ alert, onClose }: Props) {
  return (
    <Dialog open={alert !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {alert?.ticker} — {alert?.rule_kind}
          </DialogTitle>
        </DialogHeader>
        {alert && (
          <div className="space-y-3 text-sm">
            <div>
              <strong>Triggered at:</strong> {new Date(alert.triggered_at).toLocaleString("it-IT")}
            </div>
            <div>
              <strong>Trigger price:</strong> ${alert.trigger_price}
            </div>
            <div>
              <strong>Snapshot:</strong>
              <pre className="mt-1 p-2 bg-muted rounded text-xs overflow-auto">
                {JSON.stringify(alert.snapshot, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
