/** @type {import('tailwindcss').Config} */
export default {
    darkMode: ["class"],
    content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
  	extend: {
  		/* Breakpoints for the dashboard's dense list rows.
  		 *
  		 * The stock `lg` (1024px) is a viewport width, and the dashboard does
  		 * not get the viewport: a 255px sidebar sits to its left. At lg the
  		 * content column is ~740px, so a row declared `lg:grid-cols-4` hands
  		 * each card ~180px — and a list row of
  		 * `[minmax(0,1fr) 46px 52px auto]` spends 98px on fixed numeric
  		 * columns before the name gets anything. The name column collapsed to
  		 * 0px and the company name rendered as nothing.
  		 *
  		 * That is why the dashboard looked right on a 4K screen and broken on
  		 * 1080p: 1920 physical at Windows' 150% scaling is a 1280px CSS
  		 * viewport, and every dense row was sized for roughly 1900.
  		 *
  		 * These two are measured, not guessed — a movers card needs ~330px to
  		 * fit ticker + name + price + Δ% + volume, so the breakpoint is that
  		 * width times the column count, plus gaps, plus the sidebar.
  		 */
  		screens: {
  			// Page rows go 2-across. 2×330 + gap + sidebar.
  			'dense-3': '1400px',
  			// Page rows go 4-across. Below this, four dense list cards on one
  			// row give each ~230px, which is less than their fixed numeric
  			// columns alone occupy.
  			'dense-4': '2400px',
  			// The six-column list row (identity + price + Δ% + volume + ×avg +
  			// score) spends 241px on fixed columns and gaps before the name
  			// gets a pixel — measured off the live grid, not estimated. It
  			// needs ~351px per row to leave the name a readable 110px, and
  			// TopMovers/Pre-market split internally into two sub-columns, so
  			// the CARD needs ~710px. On a 2-across page row that arrives here.
  			// Below it the rows drop volume and ×avg and keep the name.
  			'row-full': '1750px',
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		colors: {
  			emerald: {
  				50: '#e6f9ee',
  				100: '#c3f0d6',
  				200: '#8fe3b4',
  				300: '#57d98f',
  				400: '#2ecf74',
  				500: '#1ed760',
  				600: '#17b551',
  				700: '#128f41',
  				800: '#0f7536',
  				900: '#0d5e2d',
  				950: '#06351a'
  			},
  			green: {
  				50: '#e6f9ee',
  				100: '#c3f0d6',
  				200: '#8fe3b4',
  				300: '#57d98f',
  				400: '#2ecf74',
  				500: '#1ed760',
  				600: '#17b551',
  				700: '#128f41',
  				800: '#0f7536',
  				900: '#0d5e2d',
  				950: '#06351a'
  			},
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			}
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
};
