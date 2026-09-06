from copy import deepcopy
from pathlib import Path
import pandas as pd

from data_loader_bid import load_timeseries

from data_classes_bid import (
    ArtousteReservoir,
    BiousReservoir,
    FabregesReservoir,
    ArtousteTurbine,
    BiousTurbine,
    FabregesTurbine,
    PontDeCampsTurbine,
    MiegebatTurbine,
    HouratTurbine,
    GeteuTurbine,
    CastetTurbine,
    FabregesValve,
    MiegebatNode,
    HouratNode
)

from optimization_config import (
    WaterValues,
    ProductionRequest,
    default_upstream_limits,
    confirm_or_modify_limits,
    ask_float
)

from feasibility_analysis import (
    analyze_feasibility,
    display_feasibility_analysis
)

from dispatch_optimizer import (
    OptimizerParameters,
    optimize_dispatch,
    display_optimization_result
)

from solution_validator import (
    validate_optimization_solution,
    display_solution_validation
)

# ==============================================================
# CONSTRUCTION DU SYSTEME HYDRAULIQUE
# ==============================================================

def build_system(data):
    """
    Construit l'ensemble du système hydraulique de la vallée
    à partir des séries temporelles chargées depuis l'Excel.
    """

    # ==========================================================
    # RESERVOIRS
    # ==========================================================

    artouste_reservoir = ArtousteReservoir(
        name="artouste",
        level_df=data["level_artouste_reservoir"],
        minimum_volume=0,
        maximum_level=1990.2
    )

    bious_reservoir = BiousReservoir(
        name="bious",
        level_df=data["level_bious_reservoir"],
        natural_inflows_df=data[
            "natural_inflows_bious_reservoir"
        ],
        minimum_volume=218,
        maximum_level=1416
    )

    fabreges_reservoir = FabregesReservoir(
        name="fabreges",
        level_df=data["level_fabreges_reservoir"],
        natural_inflows_df=data[
            "natural_inflows_fabreges_reservoir"
        ],
        minimum_volume=135,
        maximum_level=1240
    )

    # ==========================================================
    # VANNE DE FABREGES
    # ==========================================================

    fabreges_valve = FabregesValve(
        name="fabreges_valve",
        natural_inflows=data[
            "inflows_vanne_fabreges"
        ]
    )

    fabreges_reservoir.valve = fabreges_valve

    # ==========================================================
    # TURBINES AMONT
    # ==========================================================

    artouste_turbine = ArtousteTurbine(
        name="artouste",
        power=data["power_artouste_turbine"],
        reservoir=artouste_reservoir
    )

    bious_turbine = BiousTurbine(
        name="bious",
        power=data["power_bious_turbine"],
        reservoir=bious_reservoir
    )

    fabreges_turbine = FabregesTurbine(
        name="fabreges",
        power=data["power_fabreges_turbine"],
        reservoir=fabreges_reservoir
    )

    pont_de_camps_turbine = PontDeCampsTurbine(
        name="pont_de_camps",
        power=data["power_pont_de_camps_turbine"],
        reservoir=artouste_reservoir
    )

    # ==========================================================
    # LIENS RESERVOIRS / TURBINES
    # ==========================================================

    bious_reservoir.turbine = bious_turbine

    fabreges_reservoir.fabreges_turbine = (
        fabreges_turbine
    )

    fabreges_reservoir.pont_de_camps_turbine = (
        pont_de_camps_turbine
    )

    # ==========================================================
    # NOEUDS HYDRAULIQUES
    # ==========================================================

    miegebat_node = MiegebatNode(
        name="miegebat"
    )

    hourat_node = HouratNode(
        name="hourat"
    )

    # Connexions du nœud de Miégebat

    miegebat_node.artouste = artouste_turbine
    miegebat_node.bious = bious_turbine
    miegebat_node.fabreges = fabreges_turbine

    miegebat_node.natural_inflows_allias_df = (
        data["natural_inflows_allias_reservoir"]
    )

    # Connexions du nœud d'Hourat

    hourat_node.miegebat_node = miegebat_node

    hourat_node.natural_inflows_hourat_df = (
        data["natural_inflows_hourat_reservoir"]
    )

    # ==========================================================
    # TURBINES AVAL
    # ==========================================================

    miegebat_turbine = MiegebatTurbine(
        name="miegebat",
        maximum_power=74,
        minimum_power=2,
        instream_flow=0.5,
        unavailability_df=data[
            "unavailability_miegebat_turbine"
        ],
        node=miegebat_node,
        start_date=data["date_depart"]
    )

    hourat_turbine = HouratTurbine(
        name="hourat",
        maximum_power=48.5,
        minimum_power=2.5,
        instream_flow=0.5,
        unavailability_df=data[
            "unavailability_hourat_turbine"
        ],
        node=hourat_node,
        start_date=data["date_depart"]
    )

    geteu_turbine = GeteuTurbine(
        name="geteu",
        maximum_power=9.9,
        minimum_power=0.5,
        unavailability_df=data[
            "unavailability_geteu_turbine"
        ],
        hourat_turbine=hourat_turbine,
        start_date=data["date_depart"]
    )

    castet_turbine = CastetTurbine(
        name="castet",
        maximum_power=1.5,
        minimum_power=0.2,
        instream_flow=0.5,
        reference_maximum_inflows_from_pmax=28,
        unavailability_df=data[
            "unavailability_castet_turbine"
        ],
        natural_inflows_df=data[
            "natural_inflows_castet_reservoir"
        ],
        hourat_turbine=hourat_turbine,
        start_date=data["date_depart"]
    )

    # ==========================================================
    # CONTROLES DE CONSTRUCTION
    # ==========================================================

    required_objects = {
        "artouste_turbine": artouste_turbine,
        "bious_turbine": bious_turbine,
        "fabreges_turbine": fabreges_turbine,
        "pont_de_camps_turbine": pont_de_camps_turbine,
        "miegebat_turbine": miegebat_turbine,
        "hourat_turbine": hourat_turbine,
        "geteu_turbine": geteu_turbine,
        "castet_turbine": castet_turbine,
        "miegebat_node": miegebat_node,
        "hourat_node": hourat_node,
        "artouste_reservoir": artouste_reservoir,
        "bious_reservoir": bious_reservoir,
        "fabreges_reservoir": fabreges_reservoir,
        "fabreges_valve": fabreges_valve
    }

    for object_name, hydraulic_object in required_objects.items():

        if hydraulic_object is None:
            raise RuntimeError(
                f"L'objet {object_name} n'a pas été construit."
            )

    if castet_turbine.hourat_turbine is None:
        raise RuntimeError(
            "La turbine de Castet n'est pas reliée "
            "à la turbine d'Hourat."
        )

    if castet_turbine.natural_inflows_df is None:
        raise RuntimeError(
            "Les apports naturels de Castet "
            "ne sont pas renseignés."
        )

    if miegebat_turbine.node is None:
        raise RuntimeError(
            "La turbine de Miégebat n'est pas reliée "
            "à son nœud hydraulique."
        )

    if hourat_turbine.node is None:
        raise RuntimeError(
            "La turbine d'Hourat n'est pas reliée "
            "à son nœud hydraulique."
        )

    if geteu_turbine.hourat_turbine is None:
        raise RuntimeError(
            "La turbine de Gétêu n'est pas reliée "
            "à la turbine d'Hourat."
        )

    if miegebat_node.artouste is None:
        raise RuntimeError(
            "Le nœud de Miégebat n'est pas relié "
            "à la turbine d'Artouste."
        )

    if miegebat_node.bious is None:
        raise RuntimeError(
            "Le nœud de Miégebat n'est pas relié "
            "à la turbine de Bious."
        )

    if miegebat_node.fabreges is None:
        raise RuntimeError(
            "Le nœud de Miégebat n'est pas relié "
            "à la turbine de Fabrèges."
        )

    if hourat_node.miegebat_node is None:
        raise RuntimeError(
            "Le nœud d'Hourat n'est pas relié "
            "au nœud de Miégebat."
        )

    # ==========================================================
    # CONTROLE DE LA CHRONOLOGIE
    # ==========================================================

    timeline = data[
        "natural_inflows_allias_reservoir"
    ].index

    if timeline.empty:
        raise RuntimeError(
            "La chronologie de simulation est vide."
        )

    if timeline.has_duplicates:
        raise RuntimeError(
            "La chronologie contient des dates dupliquées."
        )

    if not timeline.is_monotonic_increasing:
        timeline = timeline.sort_values()

    # ==========================================================
    # RESULTAT
    # ==========================================================

    return {
        # Turbines amont
        "artouste": artouste_turbine,
        "bious": bious_turbine,
        "fabreges": fabreges_turbine,
        "pont_de_camps": pont_de_camps_turbine,

        # Turbines aval
        "miegebat": miegebat_turbine,
        "hourat": hourat_turbine,
        "geteu": geteu_turbine,
        "castet": castet_turbine,

        # Réservoirs
        "artouste_reservoir": artouste_reservoir,
        "bious_reservoir": bious_reservoir,
        "fabreges_reservoir": fabreges_reservoir,

        # Vanne
        "fabreges_valve": fabreges_valve,

        # Nœuds
        "miegebat_node": miegebat_node,
        "hourat_node": hourat_node,

        # Chronologie
        "timeline": timeline
    }


# ==============================================================
# INJECTION D'UN PLAN DE PRODUCTION AMONT
# ==============================================================

def inject_upstream_dispatch(
    data,
    target_date,
    power_artouste=None,
    power_bious=None,
    power_fabreges=None
):
    """
    Copie les données puis remplace les puissances amont
    uniquement à la date cible.

    Les colonnes de puissance sont converties en float64
    afin d'accepter les puissances décimales proposées
    par l'optimiseur.
    """

    target_date = pd.Timestamp(target_date)

    scenario_data = deepcopy(data)

    replacements = {
        "power_artouste_turbine": power_artouste,
        "power_bious_turbine": power_bious,
        "power_fabreges_turbine": power_fabreges
    }

    for data_key, candidate_power in replacements.items():

        if candidate_power is None:
            continue

        if data_key not in scenario_data:
            raise KeyError(
                f"La série {data_key} n'existe pas "
                f"dans les données chargées."
            )

        power_df = scenario_data[data_key].copy(deep=True)

        if "valeur" not in power_df.columns:
            raise KeyError(
                f"La colonne 'valeur' n'existe pas "
                f"dans la série {data_key}."
            )

        if target_date not in power_df.index:
            raise ValueError(
                f"La date {target_date} n'existe pas "
                f"dans la série {data_key}."
            )

        # ------------------------------------------------------
        # CORRECTION IMPORTANTE
        #
        # Une série Excel contenant uniquement des entiers est
        # chargée par Pandas avec le type int64. L'optimiseur
        # propose des puissances décimales, par exemple 15.4 MW.
        # La colonne doit donc devenir float64 avant l'affectation.
        # ------------------------------------------------------

        power_df = power_df.astype(
            {"valeur": "float64"}
        )

        candidate_power = float(
            candidate_power
        )

        if pd.isna(candidate_power):
            raise ValueError(
                f"La puissance injectée dans {data_key} "
                f"ne peut pas être manquante."
            )

        if candidate_power < 0:
            raise ValueError(
                f"La puissance injectée dans {data_key} "
                f"ne peut pas être négative : "
                f"{candidate_power} MW."
            )

        candidate_power = round(
            candidate_power,
            1
        )

        # À ce stade, la colonne est obligatoirement float64.
        power_df.at[
            target_date,
            "valeur"
        ] = candidate_power

        scenario_data[data_key] = power_df

    return scenario_data


# ==============================================================
# LECTURE D'UNE PUISSANCE AMONT
# ==============================================================

def get_upstream_power(
    system,
    turbine_name,
    date
):
    """
    Récupère la puissance d'une turbine amont.

    Une valeur manquante est remplacée par zéro.
    """

    turbine = system[turbine_name]

    power = turbine.power[
        "valeur"
    ].asof(date)

    if pd.isna(power):
        return 0.0

    return float(power)


# ==============================================================
# SIMULATION JUSQU'A UNE DATE CIBLE
# ==============================================================

def simulate_until_date(
    data,
    target_date,
    power_artouste=None,
    power_bious=None,
    power_fabreges=None
):
    """
    Rejoue le modèle depuis la première heure du fichier Excel
    jusqu'à la date cible incluse.

    Les puissances candidates remplacent les valeurs Excel
    uniquement à la date cible.
    """

    target_date = pd.Timestamp(target_date)

    # ==========================================================
    # VERIFICATION DE LA CHRONOLOGIE
    # ==========================================================

    original_timeline = data[
        "natural_inflows_allias_reservoir"
    ].index

    if original_timeline.empty:
        raise ValueError(
            "La chronologie des données est vide."
        )

    if target_date not in original_timeline:
        raise ValueError(
            f"La date {target_date} n'existe pas dans "
            f"l'horizon de simulation.\n"
            f"Horizon disponible : "
            f"{original_timeline.min()} "
            f"à {original_timeline.max()}."
        )

    target_position = original_timeline.get_loc(
        target_date
    )

    if not isinstance(target_position, int):
        raise ValueError(
            f"La date {target_date} apparaît plusieurs fois "
            f"dans la chronologie."
        )

    if target_position == len(original_timeline) - 1:
        raise ValueError(
            f"La date cible {target_date} est la dernière "
            f"heure disponible dans l'Excel.\n"
            f"Certaines équations utilisent l'heure suivante. "
            f"Choisis une date possédant une heure T+1."
        )

    # ==========================================================
    # CREATION DU SCENARIO
    # ==========================================================

    scenario_data = inject_upstream_dispatch(
        data=data,
        target_date=target_date,
        power_artouste=power_artouste,
        power_bious=power_bious,
        power_fabreges=power_fabreges
    )

    system = build_system(
        scenario_data
    )

    timeline = system["timeline"]

    # ==========================================================
    # SIMULATION CHRONOLOGIQUE
    # ==========================================================

    hourly_results = []
    target_result = None

    for i, current_date in enumerate(timeline):

        if current_date > target_date:
            break

        if i < len(timeline) - 1:
            next_date = timeline[i + 1]

        else:
            next_date = (
                current_date
                + pd.Timedelta(hours=1)
            )

        # ------------------------------------------------------
        # Puissances amont
        # ------------------------------------------------------

        artouste_power = get_upstream_power(
            system=system,
            turbine_name="artouste",
            date=current_date
        )

        bious_power = get_upstream_power(
            system=system,
            turbine_name="bious",
            date=current_date
        )

        fabreges_power = get_upstream_power(
            system=system,
            turbine_name="fabreges",
            date=current_date
        )

        # ------------------------------------------------------
        # Productions aval
        # ------------------------------------------------------

        miegebat_power = float(
            system["miegebat"].compute_power(
                current_date,
                next_date
            )
        )

        hourat_power = float(
            system["hourat"].compute_power(
                current_date,
                next_date
            )
        )

        geteu_power = float(
            system["geteu"].compute_power(
                current_date,
                next_date
            )
        )

        castet_power = float(
            system["castet"].compute_power(
                current_date,
                next_date
            )
        )

        # ------------------------------------------------------
        # Vérification des résultats
        # ------------------------------------------------------

        computed_powers = {
            "Artouste": artouste_power,
            "Bious": bious_power,
            "Fabreges": fabreges_power,
            "Miegebat": miegebat_power,
            "Hourat": hourat_power,
            "Geteu": geteu_power,
            "Castet": castet_power
        }

        for turbine_name, power in computed_powers.items():

            if pd.isna(power):
                raise RuntimeError(
                    f"La puissance de {turbine_name} est "
                    f"manquante à la date {current_date}."
                )

        # ------------------------------------------------------
        # Totaux non arrondis
        # ------------------------------------------------------

        upstream_total_raw = (
            artouste_power
            + bious_power
            + fabreges_power
        )

        downstream_total_raw = (
            miegebat_power
            + hourat_power
            + geteu_power
            + castet_power
        )

        total_power_raw = (
            upstream_total_raw
            + downstream_total_raw
        )

        hourly_result = {
            "date": current_date,
            "next_date": next_date,

            "artouste": round(
                artouste_power,
                1
            ),
            "bious": round(
                bious_power,
                1
            ),
            "fabreges": round(
                fabreges_power,
                1
            ),

            "miegebat": round(
                miegebat_power,
                1
            ),
            "hourat": round(
                hourat_power,
                1
            ),
            "geteu": round(
                geteu_power,
                1
            ),
            "castet": round(
                castet_power,
                1
            ),

            "upstream_total": round(
                upstream_total_raw,
                1
            ),
            "downstream_total": round(
                downstream_total_raw,
                1
            ),
            "total_power": round(
                total_power_raw,
                1
            ),

            "upstream_total_raw": upstream_total_raw,
            "downstream_total_raw": downstream_total_raw,
            "total_power_raw": total_power_raw
        }

        hourly_results.append(
            hourly_result
        )

        if current_date == target_date:
            target_result = hourly_result.copy()

    # ==========================================================
    # CONTROLE FINAL
    # ==========================================================

    if target_result is None:
        raise RuntimeError(
            f"La simulation n'a produit aucun résultat "
            f"pour la date {target_date}."
        )

    history_df = pd.DataFrame(
        hourly_results
    )

    if not history_df.empty:
        history_df.set_index(
            "date",
            inplace=True
        )

    target_result["history"] = history_df

    return target_result


# ==============================================================
# AFFICHAGE DU CONTROLE DE CONSTRUCTION
# ==============================================================

def display_system_control(system):
    """
    Affiche un récapitulatif de la construction du système.
    """

    print()
    print("=" * 70)
    print("CONTROLE DE CONSTRUCTION DU SYSTEME")
    print("=" * 70)

    turbine_names = [
        "artouste",
        "bious",
        "fabreges",
        "pont_de_camps",
        "miegebat",
        "hourat",
        "geteu",
        "castet"
    ]

    for turbine_key in turbine_names:

        turbine = system[turbine_key]

        print(
            f"Turbine {turbine_key:<15} : "
            f"{turbine.name}"
        )

    print("-" * 70)

    print(
        "Castet reliée à Hourat :",
        system["castet"].hourat_turbine.name
    )

    print(
        "Gétêu reliée à Hourat  :",
        system["geteu"].hourat_turbine.name
    )

    print(
        "Nombre d'heures        :",
        len(system["timeline"])
    )

    print(
        "Première date          :",
        system["timeline"].min()
    )

    print(
        "Dernière date          :",
        system["timeline"].max()
    )

    print("=" * 70)


# ==============================================================
# SAISIE D'UNE DATE DISPONIBLE
# ==============================================================

def ask_target_date(timeline):
    """
    Demande une date cible appartenant à la chronologie.
    """

    if len(timeline) < 2:
        raise RuntimeError(
            "L'horizon doit contenir au moins deux heures."
        )

    available_start = timeline.min()
    available_end = timeline.max()

    default_position = min(
        24,
        len(timeline) - 2
    )

    default_date = timeline[
        default_position
    ]

    while True:

        print()
        print(
            f"Horizon disponible : "
            f"{available_start} à {available_end}"
        )

        raw_date = input(
            f"Date et heure cible "
            f"[{default_date}] : "
        ).strip()

        if (
            raw_date != ""
            and len(raw_date) < 10
        ):
            print(
                "La date doit être saisie au format "
                "AAAA-MM-JJ HH:MM."
            )
            continue

        if raw_date == "":
            target_date = default_date

        else:
            try:
                target_date = pd.Timestamp(
                    raw_date
                )

            except Exception:
                print(
                    "Format invalide. Exemple attendu : "
                    "2026-07-30 14:00"
                )
                continue

        if target_date not in timeline:
            print(
                "Cette date n'appartient pas "
                "à l'horizon Excel."
            )
            continue

        target_position = timeline.get_loc(
            target_date
        )

        if not isinstance(target_position, int):
            print(
                "Cette date apparaît plusieurs fois "
                "dans la chronologie."
            )
            continue

        if target_position == len(timeline) - 1:
            print(
                "La dernière heure ne peut pas être utilisée, "
                "car le modèle a besoin de T+1."
            )
            continue

        return target_date


# ==============================================================
# AFFICHAGE DU RECAPITULATIF
# ==============================================================

def display_input_summary(
    path,
    production_request,
    water_values,
    limits
):
    """
    Affiche les données d'entrée de l'optimisation.
    """

    lower_bound = (
        production_request.target_power
        - production_request.tolerance
    )

    upper_bound = (
        production_request.target_power
        + production_request.tolerance
    )

    print()
    print("=" * 75)
    print("RECAPITULATIF DES ENTREES")
    print("=" * 75)

    print(
        f"Fichier Excel           : {path}"
    )

    print(
        f"Date cible              : "
        f"{production_request.target_date}"
    )

    print(
        f"Production demandée     : "
        f"{production_request.target_power:.1f} MW"
    )

    print(
        f"Tolérance               : "
        f"+/- {production_request.tolerance:.1f} MW"
    )

    print(
        f"Intervalle acceptable   : "
        f"[{lower_bound:.1f} ; {upper_bound:.1f}] MW"
    )

    print()
    print("VALEURS DE L'EAU")

    print(
        f"  Artouste              : "
        f"{water_values.artouste:.2f} EUR/MWh"
    )

    print(
        f"  Bious                 : "
        f"{water_values.bious:.2f} EUR/MWh"
    )

    print(
        f"  Fabrèges              : "
        f"{water_values.fabreges:.2f} EUR/MWh"
    )

    print()
    print("LIMITES ACTIVES")

    print(
        f"  Artouste              : "
        f"0 ou [{limits.artouste.minimum_power:.1f} ; "
        f"{limits.artouste.maximum_power:.1f}] MW"
        f" | pas {limits.artouste.dispatch_step:.1f} MW"
    )

    print(
        f"  Bious                 : "
        f"0 ou [{limits.bious.minimum_power:.1f} ; "
        f"{limits.bious.maximum_power:.1f}] MW"
        f" | pas {limits.bious.dispatch_step:.1f} MW"
    )

    print(
        f"  Fabrèges              : "
        f"0 ou [{limits.fabreges.minimum_power:.1f} ; "
        f"{limits.fabreges.maximum_power:.1f}] MW"
        f" | pas {limits.fabreges.dispatch_step:.1f} MW"
    )

    print("=" * 75)


# ==============================================================
# AFFICHAGE DU DIAGNOSTIC DE FAISABILITE
# ==============================================================

def display_feasibility_diagnostic(feasibility):
    """
    Affiche un diagnostic complémentaire après le précontrôle.
    """

    if feasibility["status"] == "TARGET_TOO_HIGH":

        print()
        print("!" * 75)
        print("DEMANDE SUPERIEURE A LA CAPACITE DE REFERENCE")
        print("!" * 75)

        print(
            f"Borne basse de la demande : "
            f"{feasibility['lower_target_bound']:.1f} MW"
        )

        print(
            f"Maximum observé          : "
            f"{feasibility['reference_maximum_power']:.1f} MW"
        )

        print(
            f"Déficit observé          : "
            f"{feasibility['capacity_shortage']:.1f} MW"
        )

        print(
            "L'optimiseur va néanmoins examiner les "
            "puissances intermédiaires."
        )

        print("!" * 75)

    elif feasibility["status"] == "TARGET_TOO_LOW":

        print()
        print("!" * 75)
        print("DEMANDE INFERIEURE A LA PRODUCTION DE REFERENCE")
        print("!" * 75)

        print(
            f"Borne haute de la demande : "
            f"{feasibility['upper_target_bound']:.1f} MW"
        )

        print(
            f"Minimum observé           : "
            f"{feasibility['reference_minimum_power']:.1f} MW"
        )

        print(
            f"Surproduction observée    : "
            f"{feasibility['minimum_overproduction']:.1f} MW"
        )

        print("!" * 75)

    else:

        print()
        print("=" * 75)
        print("DEMANDE POTENTIELLEMENT REALISABLE")
        print("=" * 75)

        print(
            "La demande se trouve dans la plage de référence."
        )

        print(
            "L'optimiseur va rechercher une combinaison "
            "au dixième de MW respectant la tolérance "
            "et minimisant le coût."
        )

        print("=" * 75)

# ==============================================================
# SELECTION DU FICHIER EXCEL
# ==============================================================

def ask_excel_path(
    default_path=None
):
    """
    Demande à l'utilisateur le chemin du fichier Excel
    contenant les données à utiliser pour l'optimisation.

    La fonction :
    - accepte les chemins entourés de guillemets ;
    - développe le dossier utilisateur ;
    - vérifie l'existence du fichier ;
    - vérifie son extension ;
    - vérifie qu'il s'agit bien d'un fichier ;
    - retourne un chemin absolu.
    """

    allowed_extensions = {
        ".xlsx",
        ".xlsm",
        ".xls"
    }

    if default_path is not None:
        default_path = Path(
            default_path
        ).expanduser()

    while True:

        print()
        print("=" * 75)
        print("SELECTION DU FICHIER EXCEL")
        print("=" * 75)

        if default_path is None:

            raw_path = input(
                "Chemin du fichier Excel à optimiser : "
            ).strip()

        else:

            raw_path = input(
                "Chemin du fichier Excel à optimiser "
                f"[{default_path}] : "
            ).strip()

            if raw_path == "":
                excel_path = default_path

            else:
                excel_path = Path(
                    clean_path_input(
                        raw_path
                    )
                ).expanduser()

        if default_path is None:

            if raw_path == "":
                print(
                    "Le chemin du fichier Excel est obligatoire."
                )
                continue

            excel_path = Path(
                clean_path_input(
                    raw_path
                )
            ).expanduser()

        # Résolution en chemin absolu.
        try:
            excel_path = excel_path.resolve()

        except OSError as error:
            print(
                "Le chemin fourni ne peut pas être résolu : "
                f"{error}"
            )
            continue

        if not excel_path.exists():
            print(
                "Le fichier indiqué n'existe pas :"
            )
            print(
                excel_path
            )
            continue

        if not excel_path.is_file():
            print(
                "Le chemin indiqué ne correspond pas "
                "à un fichier :"
            )
            print(
                excel_path
            )
            continue

        extension = excel_path.suffix.lower()

        if extension not in allowed_extensions:
            print(
                "Extension non autorisée : "
                f"{extension}"
            )

            print(
                "Extensions acceptées : "
                ".xlsx, .xlsm et .xls"
            )
            continue

        print()
        print(
            "Fichier Excel sélectionné :"
        )

        print(
            excel_path
        )

        print("=" * 75)

        return excel_path


def clean_path_input(
    raw_path
):
    """
    Nettoie un chemin saisi ou collé par l'utilisateur.

    Les guillemets ajoutés par Windows lors de la copie
    d'un chemin sont supprimés.
    """

    cleaned_path = str(
        raw_path
    ).strip()

    matching_quotes = [
        ('"', '"'),
        ("'", "'")
    ]

    for opening_quote, closing_quote in matching_quotes:

        if (
            cleaned_path.startswith(opening_quote)
            and cleaned_path.endswith(closing_quote)
            and len(cleaned_path) >= 2
        ):
            cleaned_path = cleaned_path[
                1:-1
            ].strip()

    return cleaned_path

# ==============================================================
# CHARGEMENT SECURISE DU FICHIER EXCEL
# ==============================================================

def load_optimization_excel(
    excel_path
):
    """
    Charge le fichier Excel sélectionné.

    En cas d'erreur, l'utilisateur reçoit un message explicite
    plutôt qu'une longue erreur difficile à interpréter.
    """

    excel_path = Path(
        excel_path
    )

    print()
    print("=" * 75)
    print("CHARGEMENT DU FICHIER EXCEL")
    print("=" * 75)

    print(
        f"Fichier : {excel_path}"
    )

    try:
        data = load_timeseries(
            str(excel_path)
        )

    except PermissionError as error:
        raise RuntimeError(
            "Le fichier Excel ne peut pas être lu. "
            "Vérifie qu'il n'est pas verrouillé, que tu disposes "
            "des droits nécessaires et qu'il est bien accessible."
        ) from error

    except FileNotFoundError as error:
        raise RuntimeError(
            "Le fichier Excel sélectionné n'existe plus "
            "ou a été déplacé."
        ) from error

    except ValueError as error:
        raise RuntimeError(
            "Le fichier Excel a été trouvé, mais certaines "
            "données ne peuvent pas être chargées. "
            f"Détail : {error}"
        ) from error

    except KeyError as error:
        raise RuntimeError(
            "Une feuille, une colonne ou une donnée attendue "
            "est absente du fichier Excel. "
            f"Détail : {error}"
        ) from error

    except Exception as error:
        raise RuntimeError(
            "Une erreur inattendue est survenue pendant "
            "le chargement du fichier Excel. "
            f"{type(error).__name__} : {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            "Le chargeur Excel n'a pas retourné "
            "le dictionnaire de données attendu."
        )

    required_data_keys = [
        "date_depart",
        "date_fin",
        "natural_inflows_allias_reservoir",
        "power_artouste_turbine",
        "power_bious_turbine",
        "power_fabreges_turbine"
    ]

    missing_keys = [
        key
        for key in required_data_keys
        if key not in data
    ]

    if missing_keys:
        raise RuntimeError(
            "Le fichier Excel ne contient pas toutes "
            "les données indispensables.\n"
            "Données manquantes : "
            + ", ".join(missing_keys)
        )

    print()
    print(
        "Chargement du fichier Excel : OK"
    )

    print(
        f"Début de l'horizon : "
        f"{data['date_depart']}"
    )

    print(
        f"Fin de l'horizon   : "
        f"{data['date_fin']}"
    )

    print("=" * 75)

    return data

# ==============================================================
# SELECTION ET CHARGEMENT DU FICHIER
# ==============================================================

def ask_and_load_excel(
    default_path=None
):
    """
    Demande un fichier Excel puis tente de le charger.

    Si le chargement échoue, l'utilisateur peut saisir
    un nouveau chemin sans relancer tout le programme.
    """

    current_default = default_path

    while True:

        excel_path = ask_excel_path(
            default_path=current_default
        )

        try:
            data = load_optimization_excel(
                excel_path
            )

        except RuntimeError as error:

            print()
            print("!" * 75)
            print("ERREUR DE CHARGEMENT")
            print("!" * 75)

            print(
                error
            )

            print("!" * 75)

            retry = input(
                "Choisir un autre fichier Excel ? [O/n] : "
            ).strip().lower()

            if retry in (
                "n",
                "non",
                "no"
            ):
                raise

            current_default = None
            continue

        return excel_path, data

# ==============================================================
# CONFIRMATION APRES LE PRECONTROLE
# ==============================================================

def confirm_optimization_after_feasibility(
    feasibility
):
    """
    Demande si l'utilisateur souhaite lancer l'optimiseur
    lorsque le précontrôle indique une impossibilité manifeste.
    """

    if feasibility["status"] == "POTENTIALLY_FEASIBLE":
        return True

    print()
    print("!" * 75)
    print("PRECONTROLE DEFAVORABLE")
    print("!" * 75)

    if feasibility["status"] == "TARGET_TOO_HIGH":

        print(
            "La demande dépasse la capacité maximale "
            "observée pendant le précontrôle."
        )

    elif feasibility["status"] == "TARGET_TOO_LOW":

        print(
            "La demande est inférieure à la production "
            "minimale observée pendant le précontrôle."
        )

    answer = input(
        "Lancer malgré tout l'optimisation complète ? "
        "[o/N] : "
    ).strip().lower()

    return answer in (
        "o",
        "oui",
        "y",
        "yes"
    )

def clean_path_input(raw_path):
    """
    Supprime les guillemets éventuellement ajoutés
    autour d'un chemin Windows.
    """

    cleaned_path = str(raw_path).strip()

    if (
        len(cleaned_path) >= 2
        and cleaned_path[0] == cleaned_path[-1]
        and cleaned_path[0] in ('"', "'")
    ):
        cleaned_path = cleaned_path[1:-1].strip()

    return cleaned_path

# ==============================================================
# POINT D'ENTREE DU PROGRAMME
# ==============================================================

if __name__ == "__main__":

    # ==========================================================
    # 1. SELECTION ET CHARGEMENT DU FICHIER EXCEL
    # ==========================================================

    excel_path, data = ask_and_load_excel(
        default_path=None
    )

    path = str(
        excel_path
    )

    # ==========================================================
    # 2. CONSTRUCTION ET CONTROLE DU SYSTEME
    # ==========================================================

    system = build_system(
        data
    )

    display_system_control(
        system
    )

    timeline = system["timeline"]

    # ==========================================================
    # 3. DATE CIBLE
    # ==========================================================

    target_date = ask_target_date(
        timeline
    )

    # ==========================================================
    # 4. DEMANDE ET TOLERANCE
    # ==========================================================

    target_power = ask_float(
        message="Production totale demandée en MW",
        default=80.0,
        minimum=0.0
    )

    tolerance = ask_float(
        message="Tolérance symétrique en MW",
        default=0.1,
        minimum=0.0
    )

    production_request = ProductionRequest(
        target_date=target_date,
        target_power=target_power,
        tolerance=tolerance
    )

    # ==========================================================
    # 5. VALEURS DE L'EAU
    # ==========================================================

    water_values = WaterValues(
        artouste=ask_float(
            message=(
                "Valeur de l'eau Artouste en EUR/MWh"
            ),
            default=10.0,
            minimum=0.0
        ),
        bious=ask_float(
            message=(
                "Valeur de l'eau Bious en EUR/MWh"
            ),
            default=15.0,
            minimum=0.0
        ),
        fabreges=ask_float(
            message=(
                "Valeur de l'eau Fabrèges en EUR/MWh"
            ),
            default=20.0,
            minimum=0.0
        )
    )

    # ==========================================================
    # 6. LIMITES TECHNIQUES
    # ==========================================================

    limits = confirm_or_modify_limits(
        default_limits=default_upstream_limits()
    )

    # ==========================================================
    # 7. RECAPITULATIF
    # ==========================================================

    display_input_summary(
        path=path,
        production_request=production_request,
        water_values=water_values,
        limits=limits
    )

    # ==========================================================
    # 8. ANALYSE PRELIMINAIRE DE FAISABILITE
    # ==========================================================

    feasibility = analyze_feasibility(
        data=data,
        production_request=production_request,
        water_values=water_values,
        limits=limits,
        simulation_function=simulate_until_date
    )

    display_feasibility_analysis(
        feasibility
    )

    display_feasibility_diagnostic(
        feasibility
    )

    should_optimize = (
        confirm_optimization_after_feasibility(
            feasibility
        )
    )

    if not should_optimize:

        print()
        print(
            "Optimisation complète non lancée."
        )

        print(
            "Le précontrôle de faisabilité a été affiché."
        )

        raise SystemExit(0)

    # ==========================================================
    # 9. PARAMETRES DE L'OPTIMISEUR
    #
    # Commencer avec les paramètres de test.
    # Une fois le fonctionnement validé, utiliser maxiter=80
    # et popsize=12.
    # ==========================================================

    optimizer_parameters = OptimizerParameters(
        maxiter=20,
        popsize=6,
        seed=42,
        shortage_penalty=10_000_000.0,
        excess_penalty=10_000_000.0,
        local_radius_steps=2
    )

    # ==========================================================
    # 10. LANCEMENT DE L'OPTIMISATION
    # ==========================================================

    print()
    print("=" * 75)
    print("LANCEMENT DE L'OPTIMISATION")
    print("=" * 75)

    optimization = optimize_dispatch(
        data=data,
        production_request=production_request,
        water_values=water_values,
        limits=limits,
        simulation_function=simulate_until_date,
        parameters=optimizer_parameters
    )

    # ==========================================================
    # 11. AFFICHAGE DU RESULTAT
    # ==========================================================

    display_optimization_result(
        optimization
    )

    # ==========================================================
    # 12. VALIDATION INDEPENDANTE DU PLAN RETENU
    # ==========================================================

    validation = validate_optimization_solution(
        data=data,
        production_request=production_request,
        water_values=water_values,
        limits=limits,
        optimization=optimization,
        simulation_function=simulate_until_date
    )

    # ==========================================================
    # 13. AFFICHAGE DE LA VALIDATION
    # ==========================================================

    display_solution_validation(
        validation
    )

    # ==========================================================
    # 14. SECURITE FINALE
    # ==========================================================

    if not validation["validated"]:
        raise RuntimeError(
            "La solution produite par l'optimiseur "
            "n'a pas passé la validation indépendante."
        )
