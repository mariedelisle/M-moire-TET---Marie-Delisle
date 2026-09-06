from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TurbineLimits:
    """Limites techniques d'une turbine amont, en MW."""

    minimum_power: float
    maximum_power: float
    dispatch_step: float = 0.1

    def __post_init__(self):
        minimum_power = float(self.minimum_power)
        maximum_power = float(self.maximum_power)
        dispatch_step = float(self.dispatch_step)

        if minimum_power < 0:
            raise ValueError("La puissance minimale ne peut pas etre negative.")
        if maximum_power <= 0:
            raise ValueError("La puissance maximale doit etre strictement positive.")
        if minimum_power > maximum_power:
            raise ValueError("La puissance minimale ne peut pas depasser la puissance maximale.")
        if dispatch_step <= 0:
            raise ValueError("Le pas de reglage doit etre strictement positif.")


@dataclass(frozen=True)
class UpstreamLimits:
    artouste: TurbineLimits
    bious: TurbineLimits
    fabreges: TurbineLimits


@dataclass(frozen=True)
class WaterValues:
    """Valeurs de l'eau en EUR/MWh."""

    artouste: float
    bious: float
    fabreges: float

    def __post_init__(self):
        for name, value in {
            "Artouste": self.artouste,
            "Bious": self.bious,
            "Fabreges": self.fabreges,
        }.items():
            value = float(value)
            if pd.isna(value):
                raise ValueError(f"La valeur de l'eau de {name} ne peut pas etre manquante.")
            if value < 0:
                raise ValueError(f"La valeur de l'eau de {name} ne peut pas etre negative.")


@dataclass(frozen=True)
class ProductionRequest:
    target_date: pd.Timestamp
    target_power: float
    tolerance: float

    def __post_init__(self):
        target_date = pd.Timestamp(self.target_date)
        target_power = float(self.target_power)
        tolerance = float(self.tolerance)

        if pd.isna(target_date):
            raise ValueError("La date cible ne peut pas etre manquante.")
        if pd.isna(target_power) or target_power < 0:
            raise ValueError("La production demandee doit etre positive ou nulle.")
        if pd.isna(tolerance) or tolerance < 0:
            raise ValueError("La tolerance doit etre positive ou nulle.")

        object.__setattr__(self, "target_date", target_date)
        object.__setattr__(self, "target_power", target_power)
        object.__setattr__(self, "tolerance", tolerance)


@dataclass(frozen=True)
class UpstreamDispatch:
    artouste: float
    bious: float
    fabreges: float

    def __post_init__(self):
        for name, power in {
            "Artouste": self.artouste,
            "Bious": self.bious,
            "Fabreges": self.fabreges,
        }.items():
            power = float(power)
            if pd.isna(power):
                raise ValueError(f"La puissance de {name} ne peut pas etre manquante.")
            if power < 0:
                raise ValueError(f"La puissance de {name} ne peut pas etre negative.")


def default_upstream_limits():
    return UpstreamLimits(
        artouste=TurbineLimits(0.5, 22.0, 0.1),
        bious=TurbineLimits(2.0, 14.0, 0.1),
        fabreges=TurbineLimits(0.5, 8.4, 0.1),
    )


def round_to_dispatch_step(power, dispatch_step):
    power = float(power)
    dispatch_step = float(dispatch_step)
    return round(round(power / dispatch_step) * dispatch_step, 10)


def validate_turbine_power(turbine_name, power, limits):
    power = float(power)

    if pd.isna(power):
        raise ValueError(f"La puissance de {turbine_name} ne peut pas etre manquante.")
    if power < 0:
        raise ValueError(f"La puissance de {turbine_name} ne peut pas etre negative.")
    if abs(power) <= 1e-9:
        return 0.0
    if power < limits.minimum_power:
        raise ValueError(
            f"Puissance invalide pour {turbine_name}: {power:.1f} MW. "
            f"La turbine doit etre arretee ou fonctionner entre "
            f"{limits.minimum_power:.1f} et {limits.maximum_power:.1f} MW."
        )
    if power > limits.maximum_power:
        raise ValueError(
            f"Puissance invalide pour {turbine_name}: {power:.1f} MW. "
            f"Maximum autorise: {limits.maximum_power:.1f} MW."
        )

    rounded = round_to_dispatch_step(power, limits.dispatch_step)
    if abs(power - rounded) > 1e-8:
        raise ValueError(
            f"La puissance de {turbine_name} doit respecter un pas de "
            f"{limits.dispatch_step:.1f} MW."
        )
    return rounded


def validate_dispatch(dispatch, limits):
    return UpstreamDispatch(
        artouste=validate_turbine_power("Artouste", dispatch.artouste, limits.artouste),
        bious=validate_turbine_power("Bious", dispatch.bious, limits.bious),
        fabreges=validate_turbine_power("Fabreges", dispatch.fabreges, limits.fabreges),
    )


def calculate_water_cost(dispatch, water_values, duration_hours=1.0):
    duration_hours = float(duration_hours)
    if duration_hours <= 0:
        raise ValueError("La duree doit etre strictement positive.")

    artouste_cost = dispatch.artouste * duration_hours * water_values.artouste
    bious_cost = dispatch.bious * duration_hours * water_values.bious
    fabreges_cost = dispatch.fabreges * duration_hours * water_values.fabreges
    total_cost = artouste_cost + bious_cost + fabreges_cost

    return {
        "artouste_cost": round(artouste_cost, 2),
        "bious_cost": round(bious_cost, 2),
        "fabreges_cost": round(fabreges_cost, 2),
        "total_cost": round(total_cost, 2),
        "total_cost_raw": total_cost,
    }


def evaluate_production_target(total_power, production_request):
    total_power = float(total_power)
    lower_bound = production_request.target_power - production_request.tolerance
    upper_bound = production_request.target_power + production_request.tolerance
    gap = total_power - production_request.target_power
    shortage = max(lower_bound - total_power, 0.0)
    excess = max(total_power - upper_bound, 0.0)
    feasible = lower_bound <= total_power <= upper_bound

    if feasible:
        status = "FEASIBLE"
    elif total_power < lower_bound:
        status = "BELOW_TARGET"
    else:
        status = "ABOVE_TARGET"

    return {
        "lower_bound": round(lower_bound, 1),
        "upper_bound": round(upper_bound, 1),
        "production_gap": round(gap, 1),
        "production_gap_raw": gap,
        "shortage": round(shortage, 1),
        "shortage_raw": shortage,
        "excess": round(excess, 1),
        "excess_raw": excess,
        "feasible": feasible,
        "status": status,
    }


def evaluate_dispatch(
    data,
    production_request,
    dispatch,
    water_values,
    limits,
    simulation_function,
):
    validated_dispatch = validate_dispatch(dispatch, limits)

    simulation_result = simulation_function(
        data=data,
        target_date=production_request.target_date,
        power_artouste=validated_dispatch.artouste,
        power_bious=validated_dispatch.bious,
        power_fabreges=validated_dispatch.fabreges,
    )

    target = evaluate_production_target(
        simulation_result["total_power"], production_request
    )
    costs = calculate_water_cost(validated_dispatch, water_values, 1.0)
    started_turbines = sum(
        power > 0
        for power in (
            validated_dispatch.artouste,
            validated_dispatch.bious,
            validated_dispatch.fabreges,
        )
    )

    return {
        "target_date": production_request.target_date,
        "target_power": production_request.target_power,
        "tolerance": production_request.tolerance,
        "lower_bound": target["lower_bound"],
        "upper_bound": target["upper_bound"],
        "artouste": validated_dispatch.artouste,
        "bious": validated_dispatch.bious,
        "fabreges": validated_dispatch.fabreges,
        "miegebat": simulation_result["miegebat"],
        "hourat": simulation_result["hourat"],
        "geteu": simulation_result["geteu"],
        "castet": simulation_result["castet"],
        "upstream_total": simulation_result["upstream_total"],
        "downstream_total": simulation_result["downstream_total"],
        "total_power": simulation_result["total_power"],
        "total_power_raw": simulation_result["total_power_raw"],
        "production_gap": target["production_gap"],
        "production_gap_raw": target["production_gap_raw"],
        "shortage": target["shortage"],
        "shortage_raw": target["shortage_raw"],
        "excess": target["excess"],
        "excess_raw": target["excess_raw"],
        "feasible": target["feasible"],
        "status": target["status"],
        "artouste_cost": costs["artouste_cost"],
        "bious_cost": costs["bious_cost"],
        "fabreges_cost": costs["fabreges_cost"],
        "total_cost": costs["total_cost"],
        "total_cost_raw": costs["total_cost_raw"],
        "started_turbines": started_turbines,
        "history": simulation_result["history"],
    }


def display_upstream_limits(limits):
    print("\n" + "=" * 70)
    print("LIMITES DES TURBINES AMONT")
    print("=" * 70)
    for name, obj in {
        "Artouste": limits.artouste,
        "Bious": limits.bious,
        "Fabreges": limits.fabreges,
    }.items():
        print(f"\n{name}")
        print("  Arret              : 0.0 MW")
        print(f"  Puissance minimale : {obj.minimum_power:.1f} MW")
        print(f"  Puissance maximale : {obj.maximum_power:.1f} MW")
        print(f"  Pas de reglage     : {obj.dispatch_step:.1f} MW")
    print("\n" + "=" * 70)


def ask_float(message, default=None, minimum=None, strictly_positive=False):
    while True:
        suffix = f" [{default}] : " if default is not None else " : "
        raw = input(message + suffix).strip()
        if raw == "" and default is not None:
            value = float(default)
        else:
            try:
                value = float(raw.replace(",", "."))
            except ValueError:
                print("Valeur invalide. Entre un nombre.")
                continue

        if pd.isna(value):
            print("La valeur ne peut pas etre manquante.")
            continue
        if minimum is not None and value < minimum:
            print(f"La valeur doit etre superieure ou egale a {minimum}.")
            continue
        if strictly_positive and value <= 0:
            print("La valeur doit etre strictement positive.")
            continue
        return value


def ask_yes_no(message, default=True):
    label = "O/n" if default else "o/N"
    while True:
        answer = input(f"{message} [{label}] : ").strip().lower()
        if answer == "":
            return default
        if answer in ("o", "oui", "y", "yes"):
            return True
        if answer in ("n", "non", "no"):
            return False
        print("Reponse invalide. Entre O pour oui ou N pour non.")


def ask_turbine_limits(turbine_name, current_limits):
    print(f"\nModification des limites de {turbine_name}")
    print("-" * 70)
    minimum_power = ask_float(
        "Puissance minimale en MW", current_limits.minimum_power, minimum=0.0
    )
    maximum_power = ask_float(
        "Puissance maximale en MW",
        current_limits.maximum_power,
        strictly_positive=True,
    )
    dispatch_step = ask_float(
        "Pas de reglage en MW", current_limits.dispatch_step, strictly_positive=True
    )
    return TurbineLimits(minimum_power, maximum_power, dispatch_step)


def confirm_or_modify_limits(default_limits=None):
    if default_limits is None:
        default_limits = default_upstream_limits()

    display_upstream_limits(default_limits)
    if ask_yes_no("Conserver ces limites techniques", default=True):
        return default_limits

    modified = UpstreamLimits(
        artouste=ask_turbine_limits("Artouste", default_limits.artouste),
        bious=ask_turbine_limits("Bious", default_limits.bious),
        fabreges=ask_turbine_limits("Fabreges", default_limits.fabreges),
    )
    display_upstream_limits(modified)
    return modified


def display_dispatch_evaluation(result):
    print("\n" + "=" * 75)
    print("EVALUATION DU PLAN DE PRODUCTION")
    print("=" * 75)
    print(f"Date cible            : {result['target_date']}")
    print(f"Demande               : {result['target_power']:.1f} MW")
    print(f"Tolerance             : +/- {result['tolerance']:.1f} MW")
    print(f"Intervalle            : [{result['lower_bound']:.1f}; {result['upper_bound']:.1f}] MW")
    print("\nHAUT DE VALLEE")
    print(f"Artouste              : {result['artouste']:.1f} MW | {result['artouste_cost']:.2f} EUR")
    print(f"Bious                 : {result['bious']:.1f} MW | {result['bious_cost']:.2f} EUR")
    print(f"Fabreges              : {result['fabreges']:.1f} MW | {result['fabreges_cost']:.2f} EUR")
    print(f"Total amont           : {result['upstream_total']:.1f} MW")
    print("\nBAS DE VALLEE")
    print(f"Miegebat              : {result['miegebat']:.1f} MW")
    print(f"Hourat                : {result['hourat']:.1f} MW")
    print(f"Geteu                 : {result['geteu']:.1f} MW")
    print(f"Castet                : {result['castet']:.1f} MW")
    print(f"Total aval            : {result['downstream_total']:.1f} MW")
    print("\nRESULTAT")
    print(f"Production totale     : {result['total_power']:.1f} MW")
    print(f"Ecart                 : {result['production_gap']:+.1f} MW")
    print(f"Cout total            : {result['total_cost']:.2f} EUR")
    print(f"Turbines demarrees    : {result['started_turbines']}")
    print(f"Statut                : {result['status']}")
    print("=" * 75)
