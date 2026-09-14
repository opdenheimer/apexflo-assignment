"""Minimal digital twin for the cinema ordering path.

Runs a deterministic, faithful in-memory stub of checkout: an atomic stock claim,
a bounded API worker pool, and delayed stock-projection events. It is deliberately
not a dashboard; the output identifies the first operational limit.

Run: python -m digital_twin.simulator --screens 4 --showtimes 2 --popcorn-stock 80
"""
import argparse
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Order:
    at: float
    show: int
    screen: int
    item: str


class DemandGenerator:
    """Compatibility API plus configurable bursty demand generation."""
    def __init__(self, num_screens=4, patrons_per_screen=150, spike_multiplier=1.0, seed=42):
        self.num_screens, self.patrons_per_screen = num_screens, patrons_per_screen
        self.spike_multiplier, self.rng = spike_multiplier, random.Random(seed)

    def get_arrival_rate(self, progress_ratio):
        pre_show = 3 * math.exp(-((progress_ratio - .10) / .05) ** 2 / 2)
        interval = 8 * self.spike_multiplier * math.exp(-((progress_ratio - .50) / .08) ** 2 / 2)
        return .5 + pre_show + interval

    def generate_order_schedule(self, simulation_duration_seconds, total_requests):
        points, ceiling = [], 12 * max(1, self.spike_multiplier)
        while len(points) < total_requests:
            point = self.rng.uniform(0, simulation_duration_seconds)
            if self.rng.uniform(0, ceiling) <= self.get_arrival_rate(point / simulation_duration_seconds):
                points.append(point)
        return sorted(points)

    def orders(self, showtimes, audience, duration, hot_share):
        factor = {"family": .70, "standard": 1.0, "snacker": 1.45}[audience]
        count = round(self.num_screens * self.patrons_per_screen * showtimes * factor)
        schedule = self.generate_order_schedule(duration, count)
        return [Order(t, (i % showtimes) + 1, (i % self.num_screens) + 1,
                      "popcorn" if self.rng.random() < hot_share else "soda")
                for i, t in enumerate(schedule)]


def percentile(values, p):
    return statistics.quantiles(values, n=100)[p - 1] if len(values) >= 2 else (values[0] if values else 0)


def simulate(args):
    demand = DemandGenerator(args.screens, args.patrons_per_screen, args.spike, args.seed)
    orders = demand.orders(args.showtimes, args.audience, args.duration, args.popcorn_share)
    # Equivalent to: UPDATE inventory SET quantity=quantity-1 WHERE quantity >= 1.
    stock = {(show, "popcorn"): args.popcorn_stock for show in range(1, args.showtimes + 1)}
    stock.update({(show, "soda"): args.soda_stock for show in range(1, args.showtimes + 1)})
    workers = [0.0] * args.workers
    latency, queue_depths, sync_lags, statuses = [], [], [], {200: 0, 409: 0}
    sold_out_at, oversells = {}, 0
    for order in orders:
        worker = min(range(args.workers), key=workers.__getitem__)
        start = max(order.at, workers[worker])
        queued = sum(done > order.at for done in workers)
        finish = start + (args.service_ms + queued * args.queue_penalty_ms) / 1000
        workers[worker] = finish
        latency.append((finish - order.at) * 1000)
        queue_depths.append(queued)
        key = (order.show, order.item)
        if stock[key] > 0:
            stock[key] -= 1
            statuses[200] += 1
            sync_lags.append(args.sync_lag_ms + queued * args.sync_queue_penalty_ms)
            if stock[key] == 0 and key not in sold_out_at:
                sold_out_at[key] = finish
        else:
            statuses[409] += 1
        oversells += int(stock[key] < 0)

    p95, max_queue = percentile(latency, 95), max(queue_depths, default=0)
    reasons = []
    if statuses[409]: reasons.append(f"stock exhaustion ({statuses[409]} clean 409s)")
    if max_queue >= args.workers: reasons.append(f"API saturation (queue {max_queue})")
    if percentile(sync_lags, 95) > args.sync_slo_ms: reasons.append("stock-sync SLO breach")
    first = reasons[0] if reasons else "no configured limit reached"
    result = "\n".join([
        "# Digital Twin Result",
        f"Scenario: {args.screens} screens × {args.showtimes} showtimes; {args.audience} audience; intermission spike ×{args.spike}.",
        f"Orders: {len(orders)} | success: {statuses[200]} | stock rejections (409): {statuses[409]}",
        f"p95 checkout latency: {p95:.1f} ms | max queue depth: {max_queue} | worker pool: {args.workers}",
        f"p95 stock-sync lag: {percentile(sync_lags, 95):.1f} ms (SLO {args.sync_slo_ms} ms)",
        f"Oversell events: {oversells} (expected 0: atomic conditional claim)",
        f"Popcorn sell-outs: {len([k for k in sold_out_at if k[1] == 'popcorn'])}/{args.showtimes} showtimes",
        f"First limit: **{first}**.",
        "\nInterpretation: raise per-show popcorn allocation for 409s; add workers/backpressure for queue growth; tune the projection consumer when sync lag misses its SLO.",
    ]) + "\n"
    Path(__file__).with_name("RESULTS.md").write_text(result, encoding="utf-8")
    print(result)


def main():
    parser = argparse.ArgumentParser(description="ApexFlo ordering-path digital twin")
    parser.add_argument("--screens", type=int, default=4); parser.add_argument("--showtimes", type=int, default=2)
    parser.add_argument("--patrons-per-screen", type=int, default=150); parser.add_argument("--audience", choices=["family", "standard", "snacker"], default="snacker")
    parser.add_argument("--duration", type=float, default=300); parser.add_argument("--spike", type=float, default=2.0)
    parser.add_argument("--popcorn-share", type=float, default=.75); parser.add_argument("--popcorn-stock", type=int, default=80); parser.add_argument("--soda-stock", type=int, default=300)
    parser.add_argument("--workers", type=int, default=8); parser.add_argument("--service-ms", type=float, default=35); parser.add_argument("--queue-penalty-ms", type=float, default=2)
    parser.add_argument("--sync-lag-ms", type=float, default=80); parser.add_argument("--sync-queue-penalty-ms", type=float, default=3); parser.add_argument("--sync-slo-ms", type=float, default=250)
    parser.add_argument("--seed", type=int, default=42)
    simulate(parser.parse_args())


if __name__ == "__main__": main()
