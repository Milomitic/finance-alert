# Price-units Audit -- 2026-05-08

**Goal:** confirm the IAG.L bug is the LSE pence/pounds mismatch and scope which other tickers are affected.

Read-only walk: latest OHLCV close vs latest live_quote price (post-scaling).

**Catalog size:** 889 stocks total.


## UK / LSE (.L) -- currency `GBp / pounds`

Stocks in catalog: **99**.

| Ticker | DB close | Live price | Ratio | Verdict |
|---|---:|---:|---:|---|
| III.L | 2608.50 | 25.90 | 100.71 | DB in pence, live in pounds (BUG) |
| ADM.L | 3182.00 | 31.72 | 100.32 | DB in pence, live in pounds (BUG) |
| AAF.L | 363.00 | 3.67 | 98.91 | DB in pence, live in pounds (BUG) |
| ALW.L | 1296.00 | 12.94 | 100.15 | DB in pence, live in pounds (BUG) |
| AAL.L | 3864.50 | 38.49 | 100.40 | DB in pence, live in pounds (BUG) |
| ANTO.L | 3894.50 | 38.98 | 99.92 | DB in pence, live in pounds (BUG) |
| ABF.L | 1828.66 | 18.20 | 100.48 | DB in pence, live in pounds (BUG) |
| AZN.L | 13454.00 | 133.44 | 100.82 | DB in pence, live in pounds (BUG) |
| AUTO.L | 519.00 | 5.19 | 100.00 | DB in pence, live in pounds (BUG) |
| AV.L | 624.90 | 6.20 | 100.82 | DB in pence, live in pounds (BUG) |
| BAB.L | 1071.50 | 10.53 | 101.81 | DB in pence, live in pounds (BUG) |
| BA.L | 1964.00 | 19.34 | 101.56 | DB in pence, live in pounds (BUG) |
| BARC.L | 438.18 | 4.35 | 100.73 | DB in pence, live in pounds (BUG) |
| BTRW.L | 265.10 | 2.63 | 100.72 | DB in pence, live in pounds (BUG) |
| BEZ.L | 1278.00 | 12.79 | 99.92 | DB in pence, live in pounds (BUG) |
| BKG.L | 3368.00 | 33.38 | 100.90 | DB in pence, live in pounds (BUG) |
| BP.L | 537.00 | 5.36 | 100.21 | DB in pence, live in pounds (BUG) |
| BATS.L | 4287.00 | 42.67 | 100.47 | DB in pence, live in pounds (BUG) |
| BLND.L | 391.80 | 3.91 | 100.15 | DB in pence, live in pounds (BUG) |
| BNZL.L | 2396.00 | 23.94 | 100.08 | DB in pence, live in pounds (BUG) |
| BRBY.L | 1219.80 | 12.10 | 100.81 | DB in pence, live in pounds (BUG) |
| CNA.L | 200.10 | 2.00 | 99.95 | DB in pence, live in pounds (BUG) |
| CCEP.L | 6930.00 | 69.05 | 100.36 | DB in pence, live in pounds (BUG) |
| CCH.L | 4244.40 | 42.50 | 99.87 | DB in pence, live in pounds (BUG) |
| CPG.L | 29.30 | 29.50 | 0.99 | consistent |
| CTEC.L | 207.80 | 2.05 | 101.27 | DB in pence, live in pounds (BUG) |
| CRDA.L | 2830.00 | 28.45 | 99.47 | DB in pence, live in pounds (BUG) |
| DCC.L | 5770.00 | 57.50 | 100.35 | DB in pence, live in pounds (BUG) |
| DGE.L | 1538.40 | 15.44 | 99.64 | DB in pence, live in pounds (BUG) |
| DPLM.L | 6990.00 | 69.45 | 100.65 | DB in pence, live in pounds (BUG) |
| EDV.L | 4840.00 | 47.97 | 100.90 | DB in pence, live in pounds (BUG) |
| ENT.L | 547.40 | 5.48 | 99.89 | DB in pence, live in pounds (BUG) |
| EXPN.L | 2675.00 | 26.45 | 101.12 | DB in pence, live in pounds (BUG) |
| FCIT.L | 1321.95 | 13.18 | 100.30 | DB in pence, live in pounds (BUG) |
| FRES.L | 3628.00 | 35.72 | 101.57 | DB in pence, live in pounds (BUG) |
| GAW.L | 19630.00 | 196.05 | 100.13 | DB in pence, live in pounds (BUG) |
| GLEN.L | 562.97 | 5.63 | 99.96 | DB in pence, live in pounds (BUG) |
| GSK.L | 1855.50 | 18.43 | 100.68 | DB in pence, live in pounds (BUG) |
| HLN.L | 333.30 | 3.31 | 100.63 | DB in pence, live in pounds (BUG) |
| HLMA.L | 4561.00 | 45.49 | 100.26 | DB in pence, live in pounds (BUG) |
| HSX.L | 1629.00 | 16.24 | 100.31 | DB in pence, live in pounds (BUG) |
| HWDN.L | 789.00 | 7.80 | 101.09 | DB in pence, live in pounds (BUG) |
| HSBA.L | 1320.20 | 13.20 | 100.03 | DB in pence, live in pounds (BUG) |
| ICG.L | 1879.00 | 18.85 | 99.68 | DB in pence, live in pounds (BUG) |
| IGG.L | 1530.50 | 15.28 | 100.16 | DB in pence, live in pounds (BUG) |
| IHG.L | 149.35 | 149.70 | 1.00 | consistent |
| IMI.L | 2802.00 | 27.80 | 100.79 | DB in pence, live in pounds (BUG) |
| IMB.L | 2763.00 | 27.30 | 101.19 | DB in pence, live in pounds (BUG) |
| INF.L | 821.40 | 8.14 | 100.88 | DB in pence, live in pounds (BUG) |
| IAG.L | 391.20 | 3.85 | 101.61 | DB in pence, live in pounds (BUG) |
| ITRK.L | 4924.00 | 49.10 | 100.29 | DB in pence, live in pounds (BUG) |
| JD.L | 75.46 | 0.75 | 100.51 | DB in pence, live in pounds (BUG) |
| BGEO.L | 11280.00 | 110.30 | 102.27 | DB in pence, live in pounds (BUG) |
| KGF.L | 291.10 | 2.88 | 100.94 | DB in pence, live in pounds (BUG) |
| LAND.L | 596.50 | 5.92 | 100.85 | DB in pence, live in pounds (BUG) |
| LGEN.L | 253.40 | 2.51 | 100.82 | DB in pence, live in pounds (BUG) |
| LLOY.L | 99.75 | 0.99 | 100.73 | DB in pence, live in pounds (BUG) |
| LMP.L | 189.80 | 1.89 | 100.53 | DB in pence, live in pounds (BUG) |
| LSEG.L | 9078.00 | 90.38 | 100.44 | DB in pence, live in pounds (BUG) |
| MNG.L | 304.10 | 3.02 | 100.53 | DB in pence, live in pounds (BUG) |
| MKS.L | 332.35 | 3.32 | 100.17 | DB in pence, live in pounds (BUG) |
| MRO.L | 515.40 | 5.11 | 100.78 | DB in pence, live in pounds (BUG) |
| MTLN.L | 37.00 | 36.30 | 1.02 | consistent |
| MNDI.L | 784.20 | 7.81 | 100.36 | DB in pence, live in pounds (BUG) |
| NG.L | 1279.00 | 12.78 | 100.11 | DB in pence, live in pounds (BUG) |
| NWG.L | 581.20 | 5.80 | 100.24 | DB in pence, live in pounds (BUG) |
| NXT.L | 13225.00 | 131.85 | 100.30 | DB in pence, live in pounds (BUG) |
| PSON.L | 1099.00 | 10.92 | 100.64 | DB in pence, live in pounds (BUG) |
| PSH.L | 4150.00 | 41.44 | 100.14 | DB in pence, live in pounds (BUG) |
| PSN.L | 1123.00 | 11.13 | 100.85 | DB in pence, live in pounds (BUG) |
| PCT.L | 656.00 | 6.59 | 99.47 | DB in pence, live in pounds (BUG) |
| PRU.L | 1150.00 | 11.35 | 101.32 | DB in pence, live in pounds (BUG) |
| RKT.L | 4685.00 | 46.71 | 100.30 | DB in pence, live in pounds (BUG) |
| REL.L | 2477.00 | 24.60 | 100.69 | DB in pence, live in pounds (BUG) |
| RTO.L | 486.70 | 4.85 | 100.41 | DB in pence, live in pounds (BUG) |
| RMV.L | 427.70 | 4.22 | 101.25 | DB in pence, live in pounds (BUG) |
| RIO.L | 7705.00 | 77.04 | 100.01 | DB in pence, live in pounds (BUG) |
| RR.L | 1243.20 | 12.20 | 101.92 | DB in pence, live in pounds (BUG) |
| SGE.L | 883.40 | 8.77 | 100.75 | DB in pence, live in pounds (BUG) |
| SBRY.L | 314.70 | 3.14 | 100.32 | DB in pence, live in pounds (BUG) |
| SDR.L | 581.00 | 5.80 | 100.09 | DB in pence, live in pounds (BUG) |
| SMT.L | 1438.50 | 14.33 | 100.38 | DB in pence, live in pounds (BUG) |
| SGRO.L | 717.20 | 7.17 | 100.00 | DB in pence, live in pounds (BUG) |
| SVT.L | 3169.00 | 31.33 | 101.15 | DB in pence, live in pounds (BUG) |
| SHEL.L | 3095.50 | 31.03 | 99.76 | DB in pence, live in pounds (BUG) |
| SMIN.L | 2507.00 | 24.75 | 101.29 | DB in pence, live in pounds (BUG) |
| SN.L | 1108.86 | 10.93 | 101.45 | DB in pence, live in pounds (BUG) |
| SPX.L | 7482.00 | 74.46 | 100.48 | DB in pence, live in pounds (BUG) |
| SSE.L | 2517.00 | 25.07 | 100.40 | DB in pence, live in pounds (BUG) |
| STAN.L | 1887.00 | 18.88 | 99.94 | DB in pence, live in pounds (BUG) |
| SDLF.L | 762.80 | 7.61 | 100.18 | DB in pence, live in pounds (BUG) |
| STJ.L | 1193.00 | 11.82 | 100.89 | DB in pence, live in pounds (BUG) |
| TSCO.L | 466.85 | 4.67 | 99.98 | DB in pence, live in pounds (BUG) |
| BBOX.L | 153.10 | 1.52 | 100.39 | DB in pence, live in pounds (BUG) |
| ULVR.L | 4270.50 | 42.74 | 99.91 | DB in pence, live in pounds (BUG) |
| UU.L | 1408.00 | 13.89 | 101.33 | DB in pence, live in pounds (BUG) |
| VOD.L | 118.67 | 1.19 | 100.02 | DB in pence, live in pounds (BUG) |
| WEIR.L | 2516.00 | 25.00 | 100.64 | DB in pence, live in pounds (BUG) |
| WTB.L | 2316.62 | 24.10 | 96.13 | DB in pence, live in pounds (BUG) |

**Affected tickers in UK / LSE: 96/99 checked (99 total in catalog)**


## South Africa / JSE (.JO)

No stocks in catalog.


## Israel / TASE (.TA)

No stocks in catalog.


## Score staleness

.L stocks with a stock_scores row: **99**. These will have stale composite scores after the migration -- the next scan_alerts run rebuilds them.
