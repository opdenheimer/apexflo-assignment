import pytest
from digital_twin.simulator import DemandGenerator
from digital_twin.report import DigitalTwinRunner

def test_demand_generator_intermission_spike():
    """Verify that the arrival rate function peaks during intermission (progress = 0.5)."""
    gen = DemandGenerator(num_screens=4, patrons_per_screen=100)
    
    rate_baseline = gen.get_arrival_rate(progress_ratio=0.8)
    rate_intermission = gen.get_arrival_rate(progress_ratio=0.5)

    # Intermission rate must be significantly higher than regular viewing period
    assert rate_intermission > rate_baseline * 2.5

def test_demand_generator_schedule_generation():
    """Verify that generated timestamps are sorted and within the duration bound."""
    gen = DemandGenerator()
    duration = 5.0
    schedule = gen.generate_order_schedule(simulation_duration_seconds=duration, total_requests=40)
    
    assert len(schedule) == 40
    assert all(0 <= t <= duration for t in schedule)
    # Monotonically non-decreasing
    assert schedule == sorted(schedule)
