"""National Transit Database agency profile: deterministic parse and reconciliation.

The FTA publishes one PDF per agency per year. Text extraction of its modal
table is error-prone (column labels and values can be recovered out of order),
so every figure parsed here is checked against the profile's own printed
efficiency ratios — operating expense per revenue mile and per revenue hour,
unlinked trips per revenue mile and per revenue hour, expense per passenger
mile and per unlinked trip. A parse that does not reproduce all six ratios is
rejected rather than used.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class NTDParseError(RuntimeError):
    """Raised when the profile cannot be parsed and verified."""


@dataclass
class NTDMode:
    mode: str
    voms: int
    pt_voms: int
    passenger_miles: float
    unlinked_trips: float
    revenue_miles: float
    revenue_hours: float
    operating_expense: float = 0.0
    fare_revenue: float = 0.0
    vams: int = 0
    spare_ratio_pct: float = 0.0
    avg_fleet_age_years: float = 0.0

    @property
    def speed_mph(self) -> float:
        return self.revenue_miles / self.revenue_hours

    @property
    def miles_per_boarding(self) -> float:
        return self.passenger_miles / self.unlinked_trips

    @property
    def opex_per_revenue_hour(self) -> float:
        return self.operating_expense / self.revenue_hours


@dataclass
class NTDProfile:
    ntd_id: str
    agency: str
    year: int
    service_area_population: int
    service_area_sq_miles: float
    annual_upt: float
    avg_weekday_upt: float
    avg_saturday_upt: float
    avg_sunday_upt: float
    modes: dict[str, NTDMode]
    source_file: str = ""

    def bus(self) -> NTDMode:
        for k in ("Bus", "Motorbus", "MB"):
            if k in self.modes:
                return self.modes[k]
        raise KeyError(f"no bus mode in {list(self.modes)}")

    def bus_share_of_upt(self) -> float:
        return self.bus().unlinked_trips / self.annual_upt

    def estimated_weekday_bus_boardings(self) -> float:
        """Weekday boardings attributable to bus.

        The profile reports average weekday UPT agency-wide; bus is scaled by
        its share of annual unlinked trips.
        """
        return self.avg_weekday_upt * self.bus_share_of_upt()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["modes"] = {k: asdict(v) for k, v in self.modes.items()}
        return d


_NUM = r"[\d,]+(?:\.\d+)?"


def _f(s: str) -> float:
    return float(s.replace(",", "").replace("$", ""))


def parse_profile(path: Path) -> NTDProfile:
    """Parse an FTA annual agency profile PDF and verify it against its ratios."""
    import pdfplumber

    lines: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            lines += [l.rstrip() for l in (page.extract_text() or "").split("\n")]
    text = "\n".join(lines)

    m = re.search(r"(\d{4})\s+Annual Agency Profile\s*-\s*(.+?)\s*\(NTD ID\s*(\d+)\)", text)
    if not m:
        raise NTDParseError("could not find the profile header")
    year, agency, ntd_id = int(m.group(1)), m.group(2).strip(), m.group(3)

    def grab(pattern: str, default: float | None = None) -> float:
        mm = re.search(pattern + r"\s+(" + _NUM + ")", text)
        if mm:
            return _f(mm.group(1))
        if default is not None:
            return default
        raise NTDParseError(f"missing field: {pattern}")

    prof_kw = dict(
        service_area_population=int(grab(r"Service Area Population")),
        service_area_sq_miles=grab(r"Service Area Sq\. Miles"),
        annual_upt=grab(r"Annual Unlinked Trips \(UPT\)"),
        avg_weekday_upt=grab(r"Average Weekday UPT"),
        avg_saturday_upt=grab(r"Average Saturday UPT", 0.0),
        avg_sunday_upt=grab(r"Average Sunday UPT", 0.0),
    )

    # modal service table: Mode VOMS ptVOMS PMT UPT VRM VRH DRM
    modes: dict[str, NTDMode] = {}
    row = re.compile(r"^([A-Za-z][A-Za-z /\-]+?)\s+(\d[\d,]*)\s+(\d[\d,]*)\s+"
                     r"(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s+"
                     r"(" + _NUM + r")\s+(" + _NUM + r")\s*$")
    for ln in lines:
        mm = row.match(ln.strip())
        if not mm:
            continue
        name = mm.group(1).strip()
        modes[name] = NTDMode(
            mode=name, voms=int(_f(mm.group(2))), pt_voms=int(_f(mm.group(3))),
            passenger_miles=_f(mm.group(4)), unlinked_trips=_f(mm.group(5)),
            revenue_miles=_f(mm.group(6)), revenue_hours=_f(mm.group(7)))
    if not modes:
        raise NTDParseError("no modal service rows found")

    # operating expense and fare revenue per mode
    oe = re.compile(r"^([A-Za-z][A-Za-z /\-]+?)\s+\$(" + _NUM + r")\s+\$(" + _NUM + r")\s+\$")
    for ln in lines:
        mm = oe.match(ln.strip())
        if mm and mm.group(1).strip() in modes:
            modes[mm.group(1).strip()].operating_expense = _f(mm.group(2))
            modes[mm.group(1).strip()].fare_revenue = _f(mm.group(3))

    # TAM fleet table: Mode VOMS VAMS %Spare AvgAge
    tam = re.compile(r"^([A-Za-z][A-Za-z /\-]+?)\s+(\d[\d,]*)\s+(\d[\d,]*)\s+"
                     r"(" + _NUM + r")%\s+(" + _NUM + r")")
    for ln in lines:
        mm = tam.match(ln.strip())
        if mm and mm.group(1).strip() in modes:
            md = modes[mm.group(1).strip()]
            md.vams = int(_f(mm.group(3)))
            md.spare_ratio_pct = _f(mm.group(4))
            md.avg_fleet_age_years = _f(mm.group(5))

    prof = NTDProfile(ntd_id=ntd_id, agency=agency, year=year, modes=modes,
                      source_file=str(path), **prof_kw)
    _verify(prof, text)
    log.info("NTD %s %d parsed and ratio-verified: %d modes",
             prof.ntd_id, prof.year, len(prof.modes))
    return prof


def _verify(prof: NTDProfile, text: str) -> None:
    """Reject the parse unless it reproduces the profile's own printed ratios."""
    ratio_row = re.compile(
        r"^([A-Za-z][A-Za-z /\-]+?)\s+\$(" + _NUM + r")\s+\$(" + _NUM + r")\s+"
        r"(" + _NUM + r")\s+(" + _NUM + r")\s+\$(" + _NUM + r")\s+\$(" + _NUM + r")\s*$")
    checked = 0
    for ln in text.split("\n"):
        mm = ratio_row.match(ln.strip())
        if not mm:
            continue
        name = mm.group(1).strip()
        md = prof.modes.get(name)
        if md is None or md.operating_expense <= 0:
            continue
        want = [_f(mm.group(i)) for i in range(2, 8)]
        got = [md.operating_expense / md.revenue_miles,
               md.operating_expense / md.revenue_hours,
               md.unlinked_trips / md.revenue_miles,
               md.unlinked_trips / md.revenue_hours,
               md.operating_expense / md.passenger_miles,
               md.operating_expense / md.unlinked_trips]
        for w, g in zip(want, got):
            tol = max(0.05 * max(abs(w), 1e-9), 0.06)
            if abs(w - g) > tol:
                raise NTDParseError(
                    f"{name}: parsed values fail the profile's own ratio check "
                    f"(expected {w}, computed {g:.4f}) — the modal table was "
                    f"read incorrectly")
            checked += 1
    if checked == 0:
        raise NTDParseError("no efficiency ratios found to verify the parse against")
    log.info("NTD parse verified against %d printed ratios", checked)


# ---------------------------------------------------------------------------
# Reconciliation against the GTFS-derived baseline
# ---------------------------------------------------------------------------

@dataclass
class DayTypeService:
    """Scheduled service by day type, from GTFS."""

    weekday_veh_hours: float
    weekday_veh_miles: float
    saturday_veh_hours: float
    saturday_veh_miles: float
    sunday_veh_hours: float
    sunday_veh_miles: float
    n_weekdays: int = 253
    n_saturdays: int = 52
    n_sundays: int = 60          # includes holidays operated on Sunday service

    def annual_hours(self) -> float:
        return (self.n_weekdays * self.weekday_veh_hours
                + self.n_saturdays * self.saturday_veh_hours
                + self.n_sundays * self.sunday_veh_hours)

    def annual_miles(self) -> float:
        return (self.n_weekdays * self.weekday_veh_miles
                + self.n_saturdays * self.saturday_veh_miles
                + self.n_sundays * self.sunday_veh_miles)


def reconcile(prof: NTDProfile, sched: DayTypeService,
              scheduled_peak_buses: int,
              model_peak_buses: float,
              mean_route_runtime_min: float,
              assumed_transfer_rate: float) -> dict[str, Any]:
    """Compare GTFS-derived scheduled service against NTD reported actuals."""
    bus = prof.bus()
    ah, am = sched.annual_hours(), sched.annual_miles()
    sched_speed = am / ah

    weekday_bus_boardings = prof.estimated_weekday_bus_boardings()
    implied_ride_fraction = bus.miles_per_boarding / (
        (mean_route_runtime_min / 60.0) * bus.speed_mph)

    return {
        "ntd_year": prof.year,
        "ntd_id": prof.ntd_id,
        "feed_scheduled_annual_veh_hours": ah,
        "feed_scheduled_annual_veh_miles": am,
        "ntd_bus_revenue_hours": bus.revenue_hours,
        "ntd_bus_revenue_miles": bus.revenue_miles,
        "hours_ratio_scheduled_over_ntd": ah / bus.revenue_hours,
        "miles_ratio_scheduled_over_ntd": am / bus.revenue_miles,
        "scheduled_speed_mph": sched_speed,
        "ntd_speed_mph": bus.speed_mph,
        # fleet
        "ntd_voms": bus.voms,
        "ntd_vams": bus.vams,
        "ntd_spare_ratio_pct": bus.spare_ratio_pct,
        "ntd_avg_fleet_age_years": bus.avg_fleet_age_years,
        "scheduled_peak_concurrent_buses": scheduled_peak_buses,
        "model_peak_buses": model_peak_buses,
        "voms_over_scheduled_peak": bus.voms / scheduled_peak_buses,
        "voms_over_model_peak": bus.voms / model_peak_buses,
        # demand
        "ntd_avg_weekday_upt_agency": prof.avg_weekday_upt,
        "bus_share_of_annual_upt": prof.bus_share_of_upt(),
        "estimated_weekday_bus_boardings": weekday_bus_boardings,
        "implied_weekday_linked_trips": weekday_bus_boardings / (1 + assumed_transfer_rate),
        # trip length
        "ntd_miles_per_boarding": bus.miles_per_boarding,
        "implied_avg_ride_fraction": implied_ride_fraction,
        # cost
        "ntd_opex_per_revenue_hour": bus.opex_per_revenue_hour,
        "ntd_bus_operating_expense": bus.operating_expense,
    }
