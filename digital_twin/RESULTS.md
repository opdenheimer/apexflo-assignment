# Digital Twin Result
Scenario: 40 screens × 2 showtimes; snacker audience; intermission spike ×4.0.
Orders: 72500 | success: 760 | stock rejections (409): 71740
p95 checkout latency: 119975.5 ms | max queue depth: 25 | worker pool: 25
p95 stock-sync lag: 104.0 ms (SLO 250 ms)
Oversell events: 0 (expected 0: atomic conditional claim)
Popcorn sell-outs: 2/2 showtimes
First limit: **stock exhaustion (71740 clean 409s)**.

Interpretation: raise per-show popcorn allocation for 409s; add workers/backpressure for queue growth; tune the projection consumer when sync lag misses its SLO.
