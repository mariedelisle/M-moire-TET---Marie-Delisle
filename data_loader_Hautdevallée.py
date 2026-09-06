import pandas as pd
from openpyxl import load_workbook

# on crée la path jusqu'à l'OURS Cockpit d'OSSAU
path_ours_ossau = r"C:\Users\MX6740\OneDrive - ENGIE\Documents\sauvegarde_ours_ossau\Ossau_v4.92_11.08.2026.xlsm"

# on crée le path jusqu'à l'excel de test des scenarios
path_scenarios = (
    r"C:\Users\MX6740\OneDrive - ENGIE\Documents\Hautdevallée\Haut de vallée.xlsx"
)

# AJOUTER INFLOWS VANNE FABREGES

# ===============================
# CONSTANTES
# ===============================

# minimum allowable volume for the reservoir
minimum_volume_fabreges_reservoir = 135  # (103m3)
minimum_volume_bious_reservoir = 218  # (103m3)
minimum_volume_artouste_reservoir = 0  # (103m3)

# maximum allowable level for the reservoir
maximum_level_fabreges_reservoir = 1240  # (m)
maximum_level_bious_reservoir = 1416  # (m)
maximum_level_artouste_reservoir = 1990.2  # (m)

# maximum allowable power for the turbine
maximum_power_miegebat_turbine = 74  # (MW)

# minimum allowable power for the turbine
minimum_power_miegebat_turbine = 2  # (MW)

# instream flow mandatory for the turbine
instream_flow_miegebat_turbine = 0.5  # (103m3)


# je récupère dans l'OURS d'OSSAU original les données horaires nécessaires
# aux calculs de puissances du jour 1 au jour 4
def load_timeseries(
        filepath,
        scenario_number=1
):

    # lecture de toutes les feuilles
    data = pd.read_excel(filepath, sheet_name=None, header=None)

    # Lecture de la feuille "Horaire"
    df_horaire = data["Horaire"]

    # date du jour 1 sur lequel on réalise le plan de production
    date_depart = pd.to_datetime(df_horaire.iloc[2, 8])  # I3

    # date du dernier jour sur lequel on réalise le plan de production
    date_fin = pd.to_datetime(df_horaire.iloc[2, 55])  # BD3

    # Réservoir de Bious natural inflows
    natural_inflows_bious_reservoir = df_horaire.iloc[26, 8:56]

    # Réservoir de Fabreges natural inflows
    natural_inflows_fabreges_reservoir = df_horaire.iloc[27, 8:56]

    # Réservoir des Allias natural inflows
    natural_inflows_allias_reservoir = df_horaire.iloc[28, 8:56]

    # Réservoir d'Hourat natural inflows
    natural_inflows_hourat_reservoir = df_horaire.iloc[29, 8:56]

    # Réservoir de Castet natural inflows
    natural_inflows_castet_reservoir = df_horaire.iloc[30, 8:56]

    # Debit de la vanne de Fabreges (m3/s)
    inflows_vanne_fabreges = df_horaire.iloc[42, 8:56]

    wb_scenarios = load_workbook(
        path_scenarios,
        data_only=True
    )

    ws_scenarios = wb_scenarios["Scenarios"]

    def read_scenario_row(row_number):

        values = []

        for row in ws_scenarios[
            f"C{row_number}:Z{row_number}"
        ]:

            for cell in row:

                value = cell.value

                if value is None:
                    value = 0

                values.append(float(value))

        return values

    pont_de_camps_rows = {
        1: 5,
        2: 6,
        3: 7,
        4: 8,
        5: 9
    }

    bious_rows = {
        1: 37,
        2: 38,
        3: 39,
        4: 40,
        5: 41
    }

    artouste_rows = {
        1: 69,
        2: 70,
        3: 71,
        4: 72,
        5: 73
    }

    fabreges_rows = {
        1: 101,
        2: 102,
        3: 103,
        4: 104,
        5: 105
    }

    power_artouste_turbine_j0 = (
        df_horaire.iloc[9, 8:32].tolist()
    )

    power_bious_turbine_j0 = (
        df_horaire.iloc[11, 8:32].tolist()
    )

    power_fabreges_turbine_j0 = (
        df_horaire.iloc[12, 8:32].tolist()
    )

    power_pont_de_camps_turbine_j0 = (
        df_horaire.iloc[10, 8:32].tolist()
    )

    power_artouste_turbine_j1 = read_scenario_row(
        artouste_rows[scenario_number]
    )

    power_bious_turbine_j1 = read_scenario_row(
        bious_rows[scenario_number]
    )

    power_fabreges_turbine_j1 = read_scenario_row(
        fabreges_rows[scenario_number]
    )

    power_pont_de_camps_turbine_j1 = read_scenario_row(
        pont_de_camps_rows[scenario_number]
    )

    power_artouste_turbine = (
            power_artouste_turbine_j0
            + power_artouste_turbine_j1
    )

    power_bious_turbine = (
            power_bious_turbine_j0
            + power_bious_turbine_j1
    )

    power_fabreges_turbine = (
            power_fabreges_turbine_j0
            + power_fabreges_turbine_j1
    )

    power_pont_de_camps_turbine = (
            power_pont_de_camps_turbine_j0
            + power_pont_de_camps_turbine_j1
    )

    # ==========================================
    # Fonction générique ligne → datetime
    # ==========================================
    def build_timeseries(ligne_valeurs):
        data_tmp = []

        for i, val in enumerate(ligne_valeurs):
            if pd.isna(val):
                continue

            dt = date_depart + pd.Timedelta(hours=i)

            if dt <= date_fin:
                data_tmp.append({
                    "datetime": dt,
                    "valeur": val
                })

        df_tmp = pd.DataFrame(data_tmp)

        if df_tmp.empty:
            return pd.DataFrame(columns=["valeur"])

        df_tmp.set_index("datetime", inplace=True)

        return df_tmp

    # ==========================================
    # transformation en séries temporelles
    # ==========================================

    df_natural_inflows_bious_reservoir = build_timeseries(
        natural_inflows_bious_reservoir
    )

    df_natural_inflows_fabreges_reservoir = build_timeseries(
        natural_inflows_fabreges_reservoir
    )

    df_natural_inflows_hourat_reservoir = build_timeseries(
        natural_inflows_hourat_reservoir
    )

    df_natural_inflows_allias_reservoir = build_timeseries(
        natural_inflows_allias_reservoir
    )

    df_natural_inflows_castet_reservoir = build_timeseries(
        natural_inflows_castet_reservoir
    )

    df_inflows_vanne_fabreges = build_timeseries(
        inflows_vanne_fabreges
    )

    df_power_artouste_turbine = build_timeseries(
        power_artouste_turbine
    )

    df_power_bious_turbine = build_timeseries(
        power_bious_turbine
    )

    df_power_fabreges_turbine = build_timeseries(
        power_fabreges_turbine
    )

    df_power_pont_de_camps_turbine = build_timeseries(
        power_pont_de_camps_turbine
    )

    # ==========================================
    # Lecture de la feuille "Inflows_data"
    # ==========================================
    df_inflows = data["Inflows_data"]

    def load_reservoir_level(df, row_value):

        # ligne 100 Excel -> iloc 99
        dates = df.iloc[99, 27:51]

        # ligne 101 Excel -> iloc 100
        hours = df.iloc[100, 27:51]

        values = df.iloc[row_value, 27:51]

        data_tmp = []

        for date_value, hour_value, level_value in zip(
                dates,
                hours,
                values
        ):

            try:

                dt = pd.to_datetime(hour_value)

                # conversion en nombre
                # si ce n'est pas numérique -> NaN
                level_value = pd.to_numeric(level_value, errors="coerce")

                data_tmp.append({
                    "datetime": dt,
                    "valeur": level_value
                })

            except Exception as e:
                print("hour_value =", repr(hour_value))
                print("ERREUR :", e)


        df_level = pd.DataFrame(data_tmp)

        if df_level.empty:
            return pd.DataFrame(columns=["valeur"])

        df_level.set_index("datetime", inplace=True)

        #print(df_level.head())
        #print(df_level.shape)

        return df_level

    # Excel ligne 111
    level_artouste_reservoir = load_reservoir_level(
        df_inflows,
        110
    )

    # Excel ligne 120
    level_bious_reservoir = load_reservoir_level(
        df_inflows,
        119
    )

    # Excel ligne 119
    level_fabreges_reservoir = load_reservoir_level(
        df_inflows,
        118
    )

    # ==========================================
    # Lecture de la feuille "Hdx_data"
    # ==========================================
    df_hdx = data["Hdx_data"]

    def load_unavailability_miegebat(df):

        # colonne BE = datetime
        dates = df.iloc[7:200, 56]

        # colonne BF = coefficient
        valeurs = df.iloc[7:200, 57]

        df_unavail = pd.DataFrame({
            "datetime": pd.to_datetime(dates),
            "valeur": valeurs
        })

        df_unavail = df_unavail.dropna()

        df_unavail = df_unavail[
            (df_unavail["datetime"] >= date_depart) &
            (df_unavail["datetime"] <= date_fin)
        ]

        df_unavail.set_index("datetime", inplace=True)

        return df_unavail

    unavailability_miegebat_turbine = load_unavailability_miegebat(df_hdx)

    def load_unavailability_hourat(df):

        # colonne BG = datetime
        dates = df.iloc[7:200, 58]

        # colonne BH = coefficient
        valeurs = df.iloc[7:200, 59]

        df_unavail = pd.DataFrame({
            "datetime": pd.to_datetime(dates),
            "valeur": valeurs
        })

        df_unavail = df_unavail.dropna()

        df_unavail = df_unavail[
            (df_unavail["datetime"] >= date_depart) &
            (df_unavail["datetime"] <= date_fin)
        ]

        df_unavail.set_index("datetime", inplace=True)

        return df_unavail

    def load_unavailability_geteu(df):

        # colonne BG = datetime
        dates = df.iloc[7:200, 60]

        # colonne BH = coefficient
        valeurs = df.iloc[7:200, 61]

        df_unavail = pd.DataFrame({
            "datetime": pd.to_datetime(dates),
            "valeur": valeurs
        })

        df_unavail = df_unavail.dropna()

        df_unavail = df_unavail[
            (df_unavail["datetime"] >= date_depart) &
            (df_unavail["datetime"] <= date_fin)
        ]

        df_unavail.set_index("datetime", inplace=True)

        return df_unavail

    def load_unavailability_castet(df):

        # colonne BI = datetime
        dates = df.iloc[7:200, 62]

        # colonne BJ = coefficient
        valeurs = df.iloc[7:200, 63]

        df_unavail = pd.DataFrame({
            "datetime": pd.to_datetime(dates),
            "valeur": valeurs
        })

        df_unavail = df_unavail.dropna()

        df_unavail = df_unavail[
            (df_unavail["datetime"] >= date_depart) &
            (df_unavail["datetime"] <= date_fin)
        ]

        df_unavail.set_index("datetime", inplace=True)

        return df_unavail

    unavailability_miegebat_turbine = load_unavailability_miegebat(df_hdx)
    unavailability_hourat_turbine = load_unavailability_hourat(df_hdx)
    unavailability_geteu_turbine = load_unavailability_geteu(df_hdx)
    unavailability_castet_turbine = load_unavailability_castet(df_hdx)
    #print("Artouste :", level_artouste_reservoir.shape)
    #print("Bious :", level_bious_reservoir.shape)
    #print("Fabreges :", level_fabreges_reservoir.shape)

    print("date_depart :", date_depart)
    print("date_fin :", date_fin)

    # ==========================================
    # RÉSULTAT FINAL
    # ==========================================
    return {
        "date_depart": date_depart,
        "date_fin": date_fin,
        "natural_inflows_allias_reservoir": df_natural_inflows_allias_reservoir,
        "natural_inflows_bious_reservoir": df_natural_inflows_bious_reservoir,
        "natural_inflows_fabreges_reservoir": df_natural_inflows_fabreges_reservoir,
        "natural_inflows_hourat_reservoir": df_natural_inflows_hourat_reservoir,
        "natural_inflows_castet_reservoir": df_natural_inflows_castet_reservoir,
        "inflows_vanne_fabreges": df_inflows_vanne_fabreges,
        "power_artouste_turbine": df_power_artouste_turbine,
        "power_bious_turbine": df_power_bious_turbine,
        "power_fabreges_turbine": df_power_fabreges_turbine,
        "power_pont_de_camps_turbine": df_power_pont_de_camps_turbine,
        "level_artouste_reservoir": level_artouste_reservoir,
        "level_bious_reservoir": level_bious_reservoir,
        "level_fabreges_reservoir": level_fabreges_reservoir,
        "unavailability_miegebat_turbine": unavailability_miegebat_turbine,
        "unavailability_hourat_turbine": unavailability_hourat_turbine,
        "unavailability_geteu_turbine": unavailability_geteu_turbine,
        "unavailability_castet_turbine": unavailability_castet_turbine
    }


