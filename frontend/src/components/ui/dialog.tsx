"use client"

import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"

import { cn } from "@/lib/utils"

const Dialog = DialogPrimitive.Root

const DialogTrigger = DialogPrimitive.Trigger

const DialogPortal = DialogPrimitive.Portal

const DialogClose = DialogPrimitive.Close

const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/80  data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className
    )}
    {...props}
  />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

/* ⚠️ Il focus torna a chi ha aperto il dialogo — anche quando Radix non lo fa.
 *
 * Trovato nel collaudo in browser (2026-09-16): dal pulsante «segnale» di un
 * setup il dialogo si apriva, Esc lo chiudeva, e il focus finiva sul BODY, cioe'
 * chi naviga da tastiera ripartiva dall'inizio della pagina. Quasi ogni dialogo
 * dell'app e' aperto da uno STATO (`open={x !== null}`) e non da un
 * `DialogTrigger`, e spesso sparisce del tutto appena lo stato torna nullo: in
 * quel caso il ripristino di Radix non arriva. Risolverlo qui, una volta, vale
 * per tutti; `dialog.focus.test.tsx` lo riproduce.
 *
 * Due strade, perche' il dialogo puo' chiudersi in due modi: chiuso (Radix
 * chiama `onCloseAutoFocus`) o smontato di colpo (resta solo la pulizia
 * dell'effetto). In entrambe il focus si restituisce SOLO se e' rimasto sul
 * BODY: se l'app l'ha gia' mandato altrove, quella scelta vince.
 */
function restituisciFocus(opener: HTMLElement | null) {
  if (!opener) return
  setTimeout(() => {
    const ora = document.activeElement
    // `preventScroll`: chi chiude il dialogo puo' aver chiesto di andare
    // altrove — «Mostra sul grafico» scorre fino al grafico — e riportare la
    // vista sull'apertore annullerebbe proprio quel gesto.
    if (opener.isConnected && (ora === null || ora === document.body)) {
      opener.focus({ preventScroll: true })
    }
  }, 0)
}

const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, onOpenAutoFocus, onCloseAutoFocus, ...props }, ref) => {
  const opener = React.useRef<HTMLElement | null>(null)
  React.useEffect(
    () => () => {
      restituisciFocus(opener.current)
    },
    [],
  )
  return (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      onOpenAutoFocus={(e) => {
        const attivo = document.activeElement
        opener.current =
          attivo instanceof HTMLElement && attivo !== document.body ? attivo : null
        onOpenAutoFocus?.(e)
      }}
      onCloseAutoFocus={(e) => {
        onCloseAutoFocus?.(e)
        if (!e.defaultPrevented) restituisciFocus(opener.current)
        opener.current = null
      }}
      className={cn(
        "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg",
        className
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground">
        <X className="h-4 w-4" />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPortal>
  )
})
DialogContent.displayName = DialogPrimitive.Content.displayName

const DialogHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col space-y-1.5 text-center sm:text-left",
      className
    )}
    {...props}
  />
)
DialogHeader.displayName = "DialogHeader"

const DialogFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",
      className
    )}
    {...props}
  />
)
DialogFooter.displayName = "DialogFooter"

const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn(
      "text-lg font-semibold leading-none tracking-tight",
      className
    )}
    {...props}
  />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

const DialogDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
))
DialogDescription.displayName = DialogPrimitive.Description.displayName

export {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogTrigger,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
}
