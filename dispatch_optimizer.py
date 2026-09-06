from dataclasses import dataclass
from itertools import product

from scipy.optimize import differential_evolution

from optimization_config import (
    UpstreamDispatch,
    evaluate_dispatch,
    round_to_dispatch_step,
)


@dataclass(frozen=True)
class OptimizerParameters:
    maxiter: int = 80
    popsize: int = 12
    seed: int = 42
    shortage_penalty: float = 10_000_000.0
    excess_penalty: float = 10_000_000.0
    local_radius_steps: int = 3

    def __post_init__(self):
        if self.maxiter <= 0:
            raise ValueError("maxiter doit etre strictement positif.")
        if self.popsize <= 0:
            raise ValueError("popsize doit etre strictement positif.")
        if self.shortage_penalty <= 0 or self.excess_penalty <= 0:
            raise ValueError("Les penalites doivent etre strictement positives.")
        if self.local_radius_steps < 0:
            raise ValueError("local_radius_steps ne peut pas etre negatif.")


START_CONFIGURATIONS = {
    "all_off": (False, False, False),
    "artouste_only": (True, False, False),
    "bious_only": (False, True, False),
    "fabreges_only": (False, False, True),
    "artouste_bious": (True, True, False),
    "artouste_fabreges": (True, False, True),
    "bious_fabreges": (False, True, True),
    "all_on": (True, True, True),
}

TURBINE_NAMES = ("artouste", "bious", "fabreges")


def get_configuration_name(result):
    """
    Retourne un nom lisible selon les turbines amont démarrées.
    """

    artouste_started = float(
        result["artouste"]
    ) > 0

    bious_started = float(
        result["bious"]
    ) > 0

    fabreges_started = float(
        result["fabreges"]
    ) > 0

    configuration_names = {
        (
            False,
            False,
            False
        ): "Toutes les turbines arrêtées",

        (
            True,
            False,
            False
        ): "Artouste seule",

        (
            False,
            True,
            False
        ): "Bious seule",

        (
            False,
            False,
            True
        ): "Fabrèges seule",

        (
            True,
            True,
            False
        ): "Artouste + Bious",

        (
            True,
            False,
            True
        ): "Artouste + Fabrèges",

        (
            False,
            True,
            True
        ): "Bious + Fabrèges",

        (
            True,
            True,
            True
        ): "Artouste + Bious + Fabrèges"
    }

    configuration_key = (
        artouste_started,
        bious_started,
        fabreges_started
    )

    return configuration_names[
        configuration_key]

class EvaluationCache:
    def __init__(self):
        self._results = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def build_key(dispatch):
        return (
            round(float(dispatch.artouste), 1),
            round(float(dispatch.bious), 1),
            round(float(dispatch.fabreges), 1),
        )

    def get(self, dispatch):
        result = self._results.get(self.build_key(dispatch))
        if result is not None:
            self.hits += 1
        return result

    def store(self, dispatch, result):
        self._results[self.build_key(dispatch)] = result
        self.misses += 1

    @property
    def size(self):
        return len(self._results)

    def all_results(self):
        return list(self._results.values())


def build_dispatch_from_active_powers(active_turbines, active_powers, limits):
    values = {"artouste": 0.0, "bious": 0.0, "fabreges": 0.0}
    for turbine_name, proposed_power in zip(active_turbines, active_powers):
        turbine_limits = getattr(limits, turbine_name)
        rounded = round_to_dispatch_step(proposed_power, turbine_limits.dispatch_step)
        rounded = max(turbine_limits.minimum_power, rounded)
        rounded = min(turbine_limits.maximum_power, rounded)
        values[turbine_name] = round(float(rounded), 1)

    return UpstreamDispatch(
        artouste=values["artouste"],
        bious=values["bious"],
        fabreges=values["fabreges"],
    )


def evaluate_with_cache(
    cache,
    data,
    production_request,
    dispatch,
    water_values,
    limits,
    simulation_function,
):
    cached = cache.get(dispatch)
    if cached is not None:
        return cached

    result = evaluate_dispatch(
        data=data,
        production_request=production_request,
        dispatch=dispatch,
        water_values=water_values,
        limits=limits,
        simulation_function=simulation_function,
    )
    cache.store(dispatch, result)
    return result


def calculate_optimization_score(result, production_request, parameters):
    total_power = float(result["total_power"])
    lower_bound = production_request.target_power - production_request.tolerance
    upper_bound = production_request.target_power + production_request.tolerance
    shortage = max(lower_bound - total_power, 0.0)
    excess = max(total_power - upper_bound, 0.0)
    penalty = (
        parameters.shortage_penalty * shortage**2
        + parameters.excess_penalty * excess**2
    )
    tiebreaker = max(float(result["production_gap_raw"]), 0.0) * 1e-4 if result["feasible"] else 0.0
    return penalty + float(result["total_cost_raw"]) + tiebreaker


def feasible_sort_key(result):
    return (
        float(result["total_cost_raw"]),
        max(float(result["production_gap_raw"]), 0.0),
        int(result["started_turbines"]),
        abs(float(result["production_gap_raw"])),
    )


def infeasible_sort_key(result):
    if result["status"] == "BELOW_TARGET":
        distance = float(result.get("shortage_raw", result["shortage"]))
    elif result["status"] == "ABOVE_TARGET":
        distance = float(result.get("excess_raw", result["excess"]))
    else:
        distance = abs(float(result["production_gap_raw"]))
    return distance, float(result["total_cost_raw"]), int(result["started_turbines"])


def build_local_values(central_power, turbine_limits, radius_steps):
    values = []
    for offset in range(-radius_steps, radius_steps + 1):
        candidate = central_power + offset * turbine_limits.dispatch_step
        candidate = round_to_dispatch_step(candidate, turbine_limits.dispatch_step)
        if turbine_limits.minimum_power <= candidate <= turbine_limits.maximum_power:
            values.append(round(float(candidate), 1))
    return sorted(set(values))


def refine_solution_locally(
    initial_result,
    active_turbines,
    cache,
    data,
    production_request,
    water_values,
    limits,
    simulation_function,
    parameters,
):
    if not active_turbines:
        return initial_result

    initial_powers = {
        "artouste": initial_result["artouste"],
        "bious": initial_result["bious"],
        "fabreges": initial_result["fabreges"],
    }
    local_lists = [
        build_local_values(
            initial_powers[name], getattr(limits, name), parameters.local_radius_steps
        )
        for name in active_turbines
    ]

    evaluated = [initial_result]
    for powers in product(*local_lists):
        dispatch = build_dispatch_from_active_powers(active_turbines, powers, limits)
        evaluated.append(
            evaluate_with_cache(
                cache,
                data,
                production_request,
                dispatch,
                water_values,
                limits,
                simulation_function,
            )
        )

    feasible = [result for result in evaluated if result["feasible"]]
    return min(feasible, key=feasible_sort_key) if feasible else min(evaluated, key=infeasible_sort_key)


def optimize_start_configuration(
    configuration_name,
    start_configuration,
    cache,
    data,
    production_request,
    water_values,
    limits,
    simulation_function,
    parameters,
):
    active_turbines = [
        name
        for name, started in zip(TURBINE_NAMES, start_configuration)
        if started
    ]

    if not active_turbines:
        result = evaluate_with_cache(
            cache,
            data,
            production_request,
            UpstreamDispatch(0.0, 0.0, 0.0),
            water_values,
            limits,
            simulation_function,
        ).copy()
        result.update(
            configuration_name=configuration_name,
            optimizer_success=True,
            optimizer_message="Configuration sans variable.",
            optimizer_iterations=0,
            optimizer_function_evaluations=1,
        )
        return result

    bounds = [
        (getattr(limits, name).minimum_power, getattr(limits, name).maximum_power)
        for name in active_turbines
    ]

    def objective(active_powers):
        dispatch = build_dispatch_from_active_powers(active_turbines, active_powers, limits)
        result = evaluate_with_cache(
            cache,
            data,
            production_request,
            dispatch,
            water_values,
            limits,
            simulation_function,
        )
        return calculate_optimization_score(result, production_request, parameters)

    scipy_result = differential_evolution(
        func=objective,
        bounds=bounds,
        strategy="best1bin",
        maxiter=parameters.maxiter,
        popsize=parameters.popsize,
        tol=1e-7,
        atol=1e-7,
        mutation=(0.5, 1.0),
        recombination=0.7,
        polish=False,
        seed=parameters.seed,
        workers=1,
        updating="immediate",
    )

    initial_dispatch = build_dispatch_from_active_powers(
        active_turbines, scipy_result.x, limits
    )
    initial_result = evaluate_with_cache(
        cache,
        data,
        production_request,
        initial_dispatch,
        water_values,
        limits,
        simulation_function,
    )
    refined = refine_solution_locally(
        initial_result,
        active_turbines,
        cache,
        data,
        production_request,
        water_values,
        limits,
        simulation_function,
        parameters,
    ).copy()
    refined.update(
        configuration_name=configuration_name,
        optimizer_success=bool(scipy_result.success),
        optimizer_message=str(scipy_result.message),
        optimizer_iterations=int(scipy_result.nit),
        optimizer_function_evaluations=int(scipy_result.nfev),
    )
    return refined


def select_best_below_target(evaluated_results, production_request):
    lower_bound = production_request.target_power - production_request.tolerance
    results = [r for r in evaluated_results if float(r["total_power"]) < lower_bound]
    if not results:
        return None
    return min(
        results,
        key=lambda r: (
            lower_bound - float(r["total_power"]),
            float(r["total_cost_raw"]),
            int(r["started_turbines"]),
            float(r["upstream_total"]),
        ),
    )


def select_best_above_target(evaluated_results, production_request):
    upper_bound = production_request.target_power + production_request.tolerance
    results = [r for r in evaluated_results if float(r["total_power"]) > upper_bound]
    if not results:
        return None
    return min(
        results,
        key=lambda r: (
            float(r["total_power"]) - upper_bound,
            float(r["total_cost_raw"]),
            int(r["started_turbines"]),
            float(r["upstream_total"]),
        ),
    )


def select_maximum_production_result(evaluated_results):
    return max(
        evaluated_results,
        key=lambda r: (float(r["total_power_raw"]), -float(r["total_cost_raw"])),
    ) if evaluated_results else None


def select_minimum_production_result(evaluated_results):
    return min(
        evaluated_results,
        key=lambda r: (float(r["total_power_raw"]), float(r["total_cost_raw"])),
    ) if evaluated_results else None


def distance_to_target_interval(result, production_request):
    lower = production_request.target_power - production_request.tolerance
    upper = production_request.target_power + production_request.tolerance
    total = float(result["total_power"])
    if total < lower:
        return lower - total
    if total > upper:
        return total - upper
    return 0.0


def optimize_dispatch(
    data,
    production_request,
    water_values,
    limits,
    simulation_function,
    parameters=None,
):
    if parameters is None:
        parameters = OptimizerParameters()

    cache = EvaluationCache()
    configuration_results = []

    for configuration_name, start_configuration in START_CONFIGURATIONS.items():
        print(f"Optimisation de la configuration : {configuration_name}")
        result = optimize_start_configuration(
            configuration_name,
            start_configuration,
            cache,
            data,
            production_request,
            water_values,
            limits,
            simulation_function,
            parameters,
        )
        configuration_results.append(result)
        print(
            f"  Total = {result['total_power']:.1f} MW"
            f" | Cout = {result['total_cost']:.2f} EUR"
            f" | Statut = {result['status']}"
        )

    all_results = cache.all_results()
    if not all_results:
        raise RuntimeError("L'optimiseur n'a evalue aucun scenario.")

    feasible_results = [r for r in all_results if r["feasible"]]
    if feasible_results:
        best_result = min(feasible_results, key=feasible_sort_key)
        global_status = "OPTIMAL_FEASIBLE"
        message = "Une solution respectant la production demandee dans la tolerance a ete trouvee."
    else:
        best_result = None
        global_status = "NO_FEASIBLE_SOLUTION"
        message = "Aucune solution respectant la tolerance n'a ete trouvee parmi les scenarios evalues."

    best_below = select_best_below_target(all_results, production_request)
    best_above = select_best_above_target(all_results, production_request)
    maximum_result = select_maximum_production_result(all_results)
    minimum_result = select_minimum_production_result(all_results)

    if best_result is None:
        alternatives = [r for r in (best_below, best_above) if r is not None]
        if not alternatives:
            raise RuntimeError("Aucun plan alternatif n'a ete trouve.")
        best_result = min(
            alternatives,
            key=lambda r: (
                distance_to_target_interval(r, production_request),
                float(r["total_cost_raw"]),
                int(r["started_turbines"]),
            ),
        )

    lower = production_request.target_power - production_request.tolerance
    upper = production_request.target_power + production_request.tolerance
    maximum_available_power = float(maximum_result["total_power"])
    minimum_available_power = float(minimum_result["total_power"])
    capacity_shortage = max(lower - maximum_available_power, 0.0)
    minimum_overproduction = max(minimum_available_power - upper, 0.0)

    if feasible_results:
        reason = None
    elif capacity_shortage > 0:
        reason = "TARGET_ABOVE_MAXIMUM_CAPACITY"
    elif minimum_overproduction > 0:
        reason = "TARGET_BELOW_MINIMUM_PRODUCTION"
    else:
        reason = "DISCRETE_PRODUCTION_GAP"

    for result in all_results:

        if "configuration_name" not in result:
            result["configuration_name"] = (
                get_configuration_name(result))

    return {
        "status": global_status,
        "message": message,
        "best_result": best_result,
        "configuration_results": configuration_results,
        "all_evaluated_results": all_results,
        "feasible_results": feasible_results,
        "best_below": best_below,
        "best_above": best_above,
        "maximum_result": maximum_result,
        "minimum_result": minimum_result,
        "maximum_available_power": maximum_available_power,
        "minimum_available_power": minimum_available_power,
        "capacity_shortage": capacity_shortage,
        "minimum_overproduction": minimum_overproduction,
        "impossibility_reason": reason,
        "cache_size": cache.size,
        "cache_hits": cache.hits,
        "cache_misses": cache.misses,
        "parameters": parameters,
    }


def display_optimizer_result_line(result):
    name = result.get("configuration_name", "candidate")
    print(
        f"{name:<22}"
        f" | A={result['artouste']:4.1f}"
        f" | B={result['bious']:4.1f}"
        f" | F={result['fabreges']:4.1f}"
        f" | Amont={result['upstream_total']:5.1f}"
        f" | Aval={result['downstream_total']:5.1f}"
        f" | Total={result['total_power']:5.1f}"
        f" | Cout={result['total_cost']:9.2f}"
        f" | {result['status']}"
    )


def display_infeasible_analysis(optimization):
    if optimization["status"] != "NO_FEASIBLE_SOLUTION":
        return

    print("\n" + "=" * 125)
    print("ANALYSE DE LA DEMANDE IMPOSSIBLE")
    print("=" * 125)
    reason = optimization["impossibility_reason"]

    if reason == "TARGET_ABOVE_MAXIMUM_CAPACITY":
        print("Cause : la demande depasse la capacite maximale trouvee.")
        print(f"Capacite maximale : {optimization['maximum_available_power']:.1f} MW")
        print(f"Deficit : {optimization['capacity_shortage']:.1f} MW")
    elif reason == "TARGET_BELOW_MINIMUM_PRODUCTION":
        print("Cause : la demande est inferieure a la production minimale trouvee.")
        print(f"Production minimale : {optimization['minimum_available_power']:.1f} MW")
        print(f"Surproduction minimale : {optimization['minimum_overproduction']:.1f} MW")
    else:
        print("Cause : aucune combinaison evaluee au pas autorise ne respecte la tolerance.")

    if optimization["best_below"] is not None:
        print("\nMEILLEURE SOLUTION SOUS LA DEMANDE")
        display_optimizer_result_line(optimization["best_below"])
    if optimization["best_above"] is not None:
        print("\nMEILLEURE SOLUTION AU-DESSUS")
        display_optimizer_result_line(optimization["best_above"])

    print("\nPLAN DE CAPACITE MAXIMALE")
    display_optimizer_result_line(optimization["maximum_result"])
    print("\nPLAN DE PRODUCTION MINIMALE")
    display_optimizer_result_line(optimization["minimum_result"])
    print("=" * 125)


def display_optimization_result(optimization):
    print("\n" + "=" * 125)
    print("RESULTATS DE L'OPTIMISATION")
    print("=" * 125)
    print("\nMEILLEURE SOLUTION PAR CONFIGURATION")
    print("-" * 125)
    for result in optimization["configuration_results"]:
        display_optimizer_result_line(result)
    print("-" * 125)
    print(f"\nStatut global : {optimization['status']}")
    print(f"Message       : {optimization['message']}")

    best = optimization["best_result"]
    print("\n" + "=" * 75)
    print("PLAN OPTIMAL RETENU" if optimization["status"] == "OPTIMAL_FEASIBLE" else "MEILLEUR PLAN ALTERNATIF RETENU")
    print("=" * 75)
    print(f"Configuration          : {best.get('configuration_name', 'candidate')}")
    print("\nHAUT DE VALLEE")
    print(f"Artouste              : {best['artouste']:.1f} MW | Cout : {best['artouste_cost']:.2f} EUR")
    print(f"Bious                 : {best['bious']:.1f} MW | Cout : {best['bious_cost']:.2f} EUR")
    print(f"Fabreges              : {best['fabreges']:.1f} MW | Cout : {best['fabreges_cost']:.2f} EUR")
    print(f"Total amont           : {best['upstream_total']:.1f} MW")
    print("\nBAS DE VALLEE")
    print(f"Miegebat              : {best['miegebat']:.1f} MW")
    print(f"Hourat                : {best['hourat']:.1f} MW")
    print(f"Geteu                 : {best['geteu']:.1f} MW")
    print(f"Castet                : {best['castet']:.1f} MW")
    print(f"Total aval            : {best['downstream_total']:.1f} MW")
    print("\nBILAN")
    print(f"Demande               : {best['target_power']:.1f} MW")
    print(f"Production totale     : {best['total_power']:.1f} MW")
    print(f"Ecart                 : {best['production_gap']:+.1f} MW")
    print(f"Cout total            : {best['total_cost']:.2f} EUR")
    print(f"Turbines demarrees    : {best['started_turbines']}")
    print(f"Statut                : {best['status']}")
    print("\nSTATISTIQUES")
    print(f"Scenarios uniques simules : {optimization['cache_size']}")
    print(f"Utilisations du cache     : {optimization['cache_hits']}")
    print(f"Nouvelles simulations     : {optimization['cache_misses']}")
    print("=" * 75)
    display_infeasible_analysis(optimization)
