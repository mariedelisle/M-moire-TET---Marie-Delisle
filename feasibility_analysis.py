from optimization_config import (
    UpstreamDispatch,
    evaluate_dispatch
)


# ==============================================================
# CONFIGURATIONS DE DEMARRAGE DE REFERENCE
# ==============================================================

def build_reference_dispatches(limits):
    """
    Construit les huit configurations de démarrage possibles.

    Pour cette analyse préliminaire :
    - une turbine arrêtée est placée à 0 MW ;
    - une turbine démarrée est placée à sa puissance maximale.

    Les huit configurations sont :
    000 : toutes arrêtées
    100 : Artouste seule
    010 : Bious seule
    001 : Fabrèges seule
    110 : Artouste + Bious
    101 : Artouste + Fabrèges
    011 : Bious + Fabrèges
    111 : les trois turbines
    """

    return {
        "all_off": UpstreamDispatch(
            artouste=0.0,
            bious=0.0,
            fabreges=0.0
        ),

        "artouste_max": UpstreamDispatch(
            artouste=limits.artouste.maximum_power,
            bious=0.0,
            fabreges=0.0
        ),

        "bious_max": UpstreamDispatch(
            artouste=0.0,
            bious=limits.bious.maximum_power,
            fabreges=0.0
        ),

        "fabreges_max": UpstreamDispatch(
            artouste=0.0,
            bious=0.0,
            fabreges=limits.fabreges.maximum_power
        ),

        "artouste_bious_max": UpstreamDispatch(
            artouste=limits.artouste.maximum_power,
            bious=limits.bious.maximum_power,
            fabreges=0.0
        ),

        "artouste_fabreges_max": UpstreamDispatch(
            artouste=limits.artouste.maximum_power,
            bious=0.0,
            fabreges=limits.fabreges.maximum_power
        ),

        "bious_fabreges_max": UpstreamDispatch(
            artouste=0.0,
            bious=limits.bious.maximum_power,
            fabreges=limits.fabreges.maximum_power
        ),

        "all_max": UpstreamDispatch(
            artouste=limits.artouste.maximum_power,
            bious=limits.bious.maximum_power,
            fabreges=limits.fabreges.maximum_power
        )
    }


# ==============================================================
# EVALUATION DES CONFIGURATIONS DE REFERENCE
# ==============================================================

def evaluate_reference_dispatches(
    data,
    production_request,
    water_values,
    limits,
    simulation_function
):
    """
    Évalue les huit configurations de démarrage de référence.

    Retourne une liste de résultats contenant :
    - le nom de la configuration ;
    - les puissances amont ;
    - les productions aval ;
    - la production totale ;
    - le coût ;
    - le statut par rapport à la demande.
    """

    reference_dispatches = build_reference_dispatches(
        limits=limits
    )

    evaluated_dispatches = []

    for configuration_name, dispatch in (
        reference_dispatches.items()
    ):
        result = evaluate_dispatch(
            data=data,
            production_request=production_request,
            dispatch=dispatch,
            water_values=water_values,
            limits=limits,
            simulation_function=simulation_function
        )

        result["configuration_name"] = (
            configuration_name
        )

        evaluated_dispatches.append(
            result
        )

    return evaluated_dispatches


# ==============================================================
# ANALYSE DE FAISABILITE
# ==============================================================

def analyze_feasibility(
    data,
    production_request,
    water_values,
    limits,
    simulation_function
):
    """
    Réalise une analyse préliminaire de la faisabilité.

    Cette fonction ne remplace pas l'optimiseur. Elle permet
    d'identifier rapidement :

    - la production lorsque toutes les turbines amont sont arrêtées ;
    - la meilleure production observée aux puissances maximales ;
    - une demande clairement trop faible ;
    - une demande clairement trop élevée ;
    - une demande potentiellement accessible.
    """

    evaluated_dispatches = evaluate_reference_dispatches(
        data=data,
        production_request=production_request,
        water_values=water_values,
        limits=limits,
        simulation_function=simulation_function
    )

    if not evaluated_dispatches:
        raise RuntimeError(
            "Aucune configuration de référence "
            "n'a pu être évaluée."
        )

    # ----------------------------------------------------------
    # Scénario toutes turbines arrêtées
    # ----------------------------------------------------------

    all_off_result = next(
        result
        for result in evaluated_dispatches
        if result["configuration_name"] == "all_off"
    )

    # ----------------------------------------------------------
    # Configuration donnant la production totale la plus élevée
    # ----------------------------------------------------------

    maximum_result = max(
        evaluated_dispatches,
        key=lambda result: result["total_power_raw"]
    )

    # ----------------------------------------------------------
    # Configuration donnant la production totale la plus faible
    # ----------------------------------------------------------

    minimum_result = min(
        evaluated_dispatches,
        key=lambda result: result["total_power_raw"]
    )

    lower_target_bound = (
        production_request.target_power
        - production_request.tolerance
    )

    upper_target_bound = (
        production_request.target_power
        + production_request.tolerance
    )

    reference_minimum_power = minimum_result[
        "total_power"
    ]

    reference_maximum_power = maximum_result[
        "total_power"
    ]

    # ----------------------------------------------------------
    # Classement préliminaire de la demande
    # ----------------------------------------------------------

    if upper_target_bound < reference_minimum_power:
        feasibility_status = "TARGET_TOO_LOW"

        message = (
            "La borne haute de la demande est inférieure "
            "à la production minimale observée dans les "
            "configurations de référence."
        )

    elif lower_target_bound > reference_maximum_power:
        feasibility_status = "TARGET_TOO_HIGH"

        message = (
            "La borne basse de la demande est supérieure "
            "à la production maximale observée dans les "
            "configurations de référence."
        )

    else:
        feasibility_status = "POTENTIALLY_FEASIBLE"

        message = (
            "La demande se situe dans la plage de production "
            "observée. L'optimiseur devra vérifier qu'une "
            "combinaison respecte réellement la tolérance."
        )

    # ----------------------------------------------------------
    # Déficit maximal éventuel
    # ----------------------------------------------------------

    capacity_shortage = max(
        lower_target_bound - reference_maximum_power,
        0.0
    )

    # ----------------------------------------------------------
    # Production incompressible éventuelle
    # ----------------------------------------------------------

    minimum_overproduction = max(
        reference_minimum_power - upper_target_bound,
        0.0
    )

    # ----------------------------------------------------------
    # Configurations de référence déjà réalisables
    # ----------------------------------------------------------

    feasible_reference_dispatches = [
        result
        for result in evaluated_dispatches
        if result["feasible"]
    ]

    if feasible_reference_dispatches:
        cheapest_feasible_reference = min(
            feasible_reference_dispatches,
            key=lambda result: (
                result["total_cost_raw"],
                abs(result["production_gap_raw"]),
                result["started_turbines"]
            )
        )

    else:
        cheapest_feasible_reference = None

    return {
        "status": feasibility_status,
        "message": message,

        "target_power": production_request.target_power,
        "tolerance": production_request.tolerance,
        "lower_target_bound": lower_target_bound,
        "upper_target_bound": upper_target_bound,

        "reference_minimum_power": (
            reference_minimum_power
        ),
        "reference_maximum_power": (
            reference_maximum_power
        ),

        "minimum_result": minimum_result,
        "maximum_result": maximum_result,
        "all_off_result": all_off_result,

        "capacity_shortage": capacity_shortage,
        "minimum_overproduction": minimum_overproduction,

        "reference_dispatches": evaluated_dispatches,
        "feasible_reference_dispatches": (
            feasible_reference_dispatches
        ),
        "cheapest_feasible_reference": (
            cheapest_feasible_reference
        )
    }


# ==============================================================
# AFFICHAGE D'UNE CONFIGURATION
# ==============================================================

def display_reference_dispatch_line(result):
    """
    Affiche une ligne résumant une configuration de référence.
    """

    print(
        f"{result['configuration_name']:<24}"
        f" | A = {result['artouste']:4.1f} MW"
        f" | B = {result['bious']:4.1f} MW"
        f" | F = {result['fabreges']:4.1f} MW"
        f" | Amont = {result['upstream_total']:5.1f} MW"
        f" | Aval = {result['downstream_total']:5.1f} MW"
        f" | Total = {result['total_power']:5.1f} MW"
        f" | Cout = {result['total_cost']:8.2f} EUR"
        f" | {result['status']}"
    )


# ==============================================================
# AFFICHAGE DE L'ANALYSE
# ==============================================================

def display_feasibility_analysis(analysis):
    """
    Affiche le résultat de l'analyse préliminaire.
    """

    print()
    print("=" * 135)
    print("ANALYSE PRELIMINAIRE DE FAISABILITE")
    print("=" * 135)

    print(
        f"Production demandee       : "
        f"{analysis['target_power']:.1f} MW"
    )

    print(
        f"Tolerance                 : "
        f"+/- {analysis['tolerance']:.1f} MW"
    )

    print(
        f"Intervalle acceptable     : "
        f"[{analysis['lower_target_bound']:.1f} ; "
        f"{analysis['upper_target_bound']:.1f}] MW"
    )

    print()
    print("CONFIGURATIONS DE REFERENCE")
    print("-" * 135)

    for result in analysis["reference_dispatches"]:
        display_reference_dispatch_line(
            result
        )

    print("-" * 135)

    print()
    print("PLAGE DE REFERENCE")

    print(
        f"Production minimale observee : "
        f"{analysis['reference_minimum_power']:.1f} MW"
    )

    print(
        f"Production maximale observee : "
        f"{analysis['reference_maximum_power']:.1f} MW"
    )

    maximum_result = analysis["maximum_result"]

    print()
    print("CONFIGURATION DE CAPACITE MAXIMALE OBSERVEE")

    print(
        f"Configuration             : "
        f"{maximum_result['configuration_name']}"
    )

    print(
        f"Artouste                 : "
        f"{maximum_result['artouste']:.1f} MW"
    )

    print(
        f"Bious                    : "
        f"{maximum_result['bious']:.1f} MW"
    )

    print(
        f"Fabreges                 : "
        f"{maximum_result['fabreges']:.1f} MW"
    )

    print(
        f"Production amont         : "
        f"{maximum_result['upstream_total']:.1f} MW"
    )

    print(
        f"Production aval          : "
        f"{maximum_result['downstream_total']:.1f} MW"
    )

    print(
        f"Production totale        : "
        f"{maximum_result['total_power']:.1f} MW"
    )

    print()
    print("DIAGNOSTIC")
    print("-" * 135)

    print(
        f"Statut                    : "
        f"{analysis['status']}"
    )

    print(
        f"Message                   : "
        f"{analysis['message']}"
    )

    if analysis["capacity_shortage"] > 0:
        print(
            f"Deficit par rapport a la borne basse : "
            f"{analysis['capacity_shortage']:.1f} MW"
        )

    if analysis["minimum_overproduction"] > 0:
        print(
            f"Surproduction minimale par rapport "
            f"a la borne haute : "
            f"{analysis['minimum_overproduction']:.1f} MW"
        )

    cheapest_reference = analysis[
        "cheapest_feasible_reference"
    ]

    if cheapest_reference is not None:

        print()
        print(
            "Une configuration de reference respecte "
            "deja la tolerance."
        )

        print(
            f"Configuration             : "
            f"{cheapest_reference['configuration_name']}"
        )

        print(
            f"Production totale         : "
            f"{cheapest_reference['total_power']:.1f} MW"
        )

        print(
            f"Cout                       : "
            f"{cheapest_reference['total_cost']:.2f} EUR"
        )

        print(
            "Cette solution n'est pas nécessairement optimale. "
            "L'optimiseur recherchera des puissances intermédiaires."
        )

    else:
        print()
        print(
            "Aucune configuration aux seules bornes maximales "
            "ne respecte directement la tolerance."
        )

        print(
            "Cela ne signifie pas que la demande est impossible : "
            "des puissances intermédiaires peuvent convenir."
        )

    print("=" * 135)