import pandas as pd
from openpyxl import load_workbook

from data_loader_Hautdevallée import load_timeseries

from M_data_classes_Hautdevallée import (
    ArtousteReservoir, BiousReservoir, FabregesReservoir,
    ArtousteTurbine, BiousTurbine, FabregesTurbine,
    PontDeCampsTurbine,
    MiegebatTurbine,
    HouratTurbine,
    GeteuTurbine,
    CastetTurbine,
    FabregesValve,
    MiegebatNode, HouratNode
)

def build_system(data):

    # ===============================
    # RESERVOIRS
    # ===============================

    artouste_reservoir = ArtousteReservoir(
        name="artouste",
        level_df=data["level_artouste_reservoir"],
        minimum_volume=0, # (103m3)
        maximum_level=1990.2 # (m)
    )

    bious_reservoir = BiousReservoir(
        name="bious",
        level_df=data["level_bious_reservoir"],
        natural_inflows_df=data["natural_inflows_bious_reservoir"],
        minimum_volume=218, # (103m3)
        maximum_level=1416 # (m)
    )

    fabreges_reservoir = FabregesReservoir(
        name="fabreges",
        level_df=data["level_fabreges_reservoir"],
        natural_inflows_df=data["natural_inflows_fabreges_reservoir"],
        minimum_volume=135, # (103m3)
        maximum_level=1240 # (m)
    )

    # ===============================
    # VALVE
    # ===============================

    fabreges_valve = FabregesValve(
        name="fabreges_valve",
        natural_inflows=data["inflows_vanne_fabreges"]
    )

    fabreges_reservoir.valve = fabreges_valve

    # ===============================
    # TURBINES
    # ===============================

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

    # ===============================
    # LIENS RESERVOIR ↔ TURBINES
    # ===============================

    bious_reservoir.turbine = bious_turbine

    fabreges_reservoir.fabreges_turbine = fabreges_turbine
    fabreges_reservoir.pont_de_camps_turbine = pont_de_camps_turbine

    # ===============================
    # NODE
    # ===============================

    miegebat_node = MiegebatNode(name="miegebat")
    hourat_node = HouratNode(name="hourat")

    miegebat_node.artouste = artouste_turbine
    miegebat_node.bious = bious_turbine
    miegebat_node.fabreges = fabreges_turbine
    miegebat_node.natural_inflows_allias_df = (
        data["natural_inflows_allias_reservoir"]
    )

    hourat_node.miegebat_node = miegebat_node

    hourat_node.natural_inflows_hourat_df = (
        data["natural_inflows_hourat_reservoir"]
    )

    # ===============================
    # TURBINES AU FIL DE L'EAU
    # ===============================

    miegebat_turbine = MiegebatTurbine(
        name="miegebat",
        maximum_power=74,
        minimum_power=2,
        instream_flow=0.5,
        unavailability_df=data["unavailability_miegebat_turbine"],
        node=miegebat_node,
        start_date=data["date_depart"]
    )


    hourat_turbine = HouratTurbine(
        name="miegebat",
        maximum_power=48.5,
        minimum_power=2.5,
        instream_flow=0.5,
        unavailability_df=data["unavailability_hourat_turbine"],
        node=hourat_node,
        start_date=data["date_depart"]
    )

    geteu_turbine = GeteuTurbine(
        name="geteu",
        maximum_power=9.9,
        minimum_power=0.5,
        unavailability_df=data["unavailability_geteu_turbine"],
        hourat_turbine=hourat_turbine,
        start_date=data["date_depart"]
    )

    castet_turbine = CastetTurbine(
        name="castet",
        maximum_power=1.5,
        minimum_power=0.2,
        instream_flow=0.5,
        reference_maximum_inflows_from_pmax=28,
        unavailability_df=data["unavailability_castet_turbine"],
        start_date=data["date_depart"]
    )

    return {
        "miegebat": miegebat_turbine,
        "hourat": hourat_turbine,
        "geteu": geteu_turbine,
        "castet": castet_turbine,
        "timeline": data["natural_inflows_allias_reservoir"].index
    }

if __name__ == "__main__":

    path = (
        r"C:\Users\MX6740\OneDrive - ENGIE\Documents"
        r"\sauvegarde_ours_ossau\Ossau_v4.92_29.07.2026.xlsm"
    )

    all_results = {}

    for scenario_number in range(1, 6):

        print(
            f"\n===== SCENARIO {scenario_number} ====="
        )

        data = load_timeseries(
            path,
            scenario_number=scenario_number
        )

        system = build_system(data)

        miegebat_turbine = system["miegebat"]
        hourat_turbine = system["hourat"]
        geteu_turbine = system["geteu"]
        castet_turbine = system["castet"]

        timeline = system["timeline"]

        scenario_results = {
            "miegebat": [],
            "hourat": [],
            "geteu": [],
            "castet": []
        }

        for i, date in enumerate(timeline):

            if i < len(timeline) - 1:
                next_date = timeline[i + 1]
            else:
                next_date = date

            miegebat_power = miegebat_turbine.compute_power(
                date,
                next_date
            )

            hourat_power = hourat_turbine.compute_power(
                date,
                next_date
            )

            geteu_power = geteu_turbine.compute_power(
                date,
                next_date
            )

            castet_power = castet_turbine.compute_power(
                date,
                next_date
            )

            scenario_results["miegebat"].append(
                miegebat_power
            )

            scenario_results["hourat"].append(
                hourat_power
            )

            scenario_results["geteu"].append(
                geteu_power
            )

            scenario_results["castet"].append(
                castet_power
            )

        all_results[scenario_number] = (
            scenario_results
        )

        print(
            f"{date}"
            f" | Miegebat = {miegebat_power:.2f} MW"
            f" | Hourat = {hourat_power:.2f} MW"
            f" | Geteu = {geteu_power:.2f} MW"
            f" | Castet = {castet_power:.2f} MW"
        )

    wb = load_workbook(
        r"C:\Users\MX6740\OneDrive - ENGIE\Documents\Hautdevallée\Haut de vallée.xlsx"
    )

    ws = wb["Results"]

    result_rows = {
        1: [5, 6, 7, 8],
        2: [35, 36, 37, 38],
        3: [65, 66, 67, 68],
        4: [95, 96, 97, 98],
        5: [125, 126, 127, 128]
    }

    print(
        "Nombre de valeurs scénario 1 :",
        len(all_results[1]["miegebat"])
    )

    for scenario_number in range(1, 6):

        row_miegebat, row_hourat, row_geteu, row_castet = (
            result_rows[scenario_number]
        )

        for h in range(24):

            ws.cell(
                row=row_miegebat,
                column=3 + h
            ).value = (
                all_results[scenario_number]["miegebat"][24 + h]
            )

            ws.cell(
                row=row_hourat,
                column=3 + h
            ).value = (
                all_results[scenario_number]["hourat"][24 + h]
            )

            ws.cell(
                row=row_geteu,
                column=3 + h
            ).value = (
                all_results[scenario_number]["geteu"][24 + h]
            )

            ws.cell(
                row=row_castet,
                column=3 + h
            ).value = (
                all_results[scenario_number]["castet"][24 + h]
            )

    wb.save(
        r"C:\Users\MX6740\OneDrive - ENGIE\Documents\Hautdevallée\Haut de vallée.xlsx"
    )

    print(
        "Résultats enregistrés dans l'Excel."
    )