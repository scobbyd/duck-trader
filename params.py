"""Parameters for the day-ahead battery trading algorithm.

Reference configuration: 48 kWh LiFePO4 battery behind a 12 kW hybrid
inverter, traded at 10 kW with 93% round trip (standby excluded as sunk),
0,50 EUR write-off per equivalent full cycle. Adjust to your hardware.
"""
import math
from dataclasses import dataclass, replace

PV_AC = 0.985           # panel-side -> AC (MPPT 0,996 x bridge 0,989)
TZ = "Europe/Amsterdam"

# backtest window of the reference run (post PV-install data only)
WARMUP_START = "2026-03-09"      # forecaster history begins here
BT_FIRST_PLAN = "2026-03-16"     # first 13:00-local plan (7 d ma7 warmup)
BT_LAST_PLAN = "2026-08-14"      # last plan (executes into 08-15)


@dataclass(frozen=True)
class P:
    cap: float = 48.0            # kWh nameplate
    soc_lo: float = 0.10         # fraction of cap
    soc_hi: float = 0.95
    p_kw: float = 10.0           # AC-side charge and discharge cap
    rt: float = 0.93             # round trip at p_kw, standby excluded
    cycle_eur: float = 0.50      # write-off per equivalent full cycle
    fee: float = 0.02            # EUR/kWh supplier fee, each direction
    lam_end_frac: float = 0.90   # terminal SOC value vs trailing median sell
    plan_hour: int = 13          # local hour of the daily re-plan

    @property
    def eta_c(self):
        return math.sqrt(self.rt)

    @property
    def eta_d(self):
        return math.sqrt(self.rt)

    @property
    def soc_min(self):
        return self.soc_lo * self.cap

    @property
    def soc_max(self):
        return self.soc_hi * self.cap

    @property
    def c_deg(self):
        """EUR per kWh discharged (battery side): one EFC costs cycle_eur."""
        return self.cycle_eur / self.cap


# Named sensitivity variants (spec battery-parameter table)
SENS = {
    "primary": P(),
    "rt85": P(rt=0.85),
    "deg0": P(cycle_eur=0.0),
    "deg75": P(cycle_eur=0.75),
    "deg100": P(cycle_eur=1.00),
    "band_reserved": P(soc_lo=0.25, soc_hi=0.90),
    "band_full": P(soc_lo=0.10, soc_hi=1.00),
    "p12": P(p_kw=12.0),
    "fee0": P(fee=0.0),
    "lam_end_low": P(lam_end_frac=0.75),
    "lam_end_high": P(lam_end_frac=1.00),
}


def variant(**kw):
    return replace(P(), **kw)
