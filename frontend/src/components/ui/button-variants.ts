import { cva } from "class-variance-authority"

/* ⚠️ Le varianti stanno in un modulo separato, non accanto al componente.
 *
 * `react-refresh/only-export-components`: un file che esporta un componente
 * E altro rompe il Fast Refresh — modificandolo Vite ricarica la pagina
 * intera invece di sostituire il componente, e lo stato va perso. E' la
 * convenzione shadcn che lo prevede accanto; qui la si e' sciolta perche'
 * `calendar.tsx` le importa davvero, quindi non bastava smettere di
 * esportarle come per `badgeVariants`. */

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow hover:bg-primary/90",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        outline:
          "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
        secondary:
          "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)
