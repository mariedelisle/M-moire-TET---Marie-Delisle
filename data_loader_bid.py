from pathlib import Path

import pandas as pd


# ==============================================================
# CONSTANTES METIER
# ==============================================================

# Volumes minimaux des reservoirs (10^3 m3)
MINIMUM_VOLUME_FABREGES_RESERVOIR = 135
MINIMUM_VOLUME_BIOUS_RESERVOIR = 218
MINIMUM_VOLUME_ARTOUSTE_RESERVOIR = 0

# Niveaux maximaux des reservoirs (m)
MAXIMUM_LEVEL_FABREGES_RESERVOIR = 1240
MAXIMUM_LEVEL_BIOUS_RESERVOIR = 1416
MAXIMUM_LEVEL_ARTOUSTE_RESERVOIR = 1990.2

# Puissances de Miegebat (MW)
MAXIMUM_POWER_MIEGEBAT_TURBINE = 74
MINIMUM_POWER_MIEGEBAT_TURBINE = 2

# Debit reserve de Miegebat (m3/s)
INSTREAM_FLOW_MIEGEBAT_TURBINE = 0.5

# Feuilles indispensables
REQUIRED_SHEETS = {
    "Horaire",
    "Inflows_data",
    "Hdx_data",
}


# ==============================================================
# OUTILS GENERIQUES
# ==============================================================

def _empty_timeseries():
    """Retourne une serie temporelle vide au format attendu."""

    empty_index = pd.DatetimeIndex([], name="datetime")
    return pd.DataFrame(
        {"valeur": pd.Series(dtype="float64")},
        index=empty_index,
    )


def _prepare_timeseries(df):
    """
    Normalise une serie temporelle :
    - dates valides ;
    - valeurs numeriques float64 ;
    - index trie ;
    - dates dupliquees supprimees.
    """

    if df.empty:
        return _empty_timeseries()

    result = df.copy()
    result["datetime"] = pd.to_datetime(
        result["datetime"],
        errors="coerce",
    )
    result["valeur"] = pd.to_numeric(
        result["valeur"],
        errors="coerce",
    ).astype("float64")

    result = result.dropna(subset=["datetime"])
    result = result.drop_duplicates(
        subset=["datetime"],
        keep="last",
    )
    result = result.sort_values("datetime")
    result.set_index("datetime", inplace=True)
    result.index.name = "datetime"

    return result[["valeur"]]


def _build_hourly_timeseries(
    values,
    date_depart,
    date_fin,
):
    """
    Transforme une ligne Excel en serie horaire.

    La position de chaque cellule determine son heure :
    date_depart + i heures.
    """

    records = []

    for position, raw_value in enumerate(values):
        current_date = date_depart + pd.Timedelta(
            hours=position
        )

        if current_date > date_fin:
            break

        numeric_value = pd.to_numeric(
            raw_value,
            errors="coerce",
        )

        # On conserve uniquement les valeurs effectivement renseignees,
        # comme dans la version initiale du chargeur.
        if pd.isna(numeric_value):
            continue

        records.append(
            {
                "datetime": current_date,
                "valeur": numeric_value,
            }
        )

    return _prepare_timeseries(
        pd.DataFrame(records)
    )


def _load_reservoir_level(
    dataframe,
    row_index,
):
    """
    Charge les niveaux d'un reservoir depuis Inflows_data.

    Les dates/heures sont lues sur la ligne 101 Excel
    (index Python 100), conformement au comportement existant.
    """

    hours = dataframe.iloc[100, 27:51]
    values = dataframe.iloc[row_index, 27:51]

    records = []

    for hour_value, level_value in zip(
        hours,
        values,
    ):
        date_value = pd.to_datetime(
            hour_value,
            errors="coerce",
        )
        numeric_level = pd.to_numeric(
            level_value,
            errors="coerce",
        )

        if pd.isna(date_value):
            continue

        records.append(
            {
                "datetime": date_value,
                "valeur": numeric_level,
            }
        )

    return _prepare_timeseries(
        pd.DataFrame(records)
    )


def _load_unavailability(
    dataframe,
    datetime_column,
    value_column,
    date_depart,
    date_fin,
):
    """
    Charge une serie d'indisponibilite depuis Hdx_data.

    Convention metier attendue ensuite par le modele :
    0 = disponible ; 1 = indisponible.
    """

    dates = pd.to_datetime(
        dataframe.iloc[7:200, datetime_column],
        errors="coerce",
    )
    values = pd.to_numeric(
        dataframe.iloc[7:200, value_column],
        errors="coerce",
    )

    result = pd.DataFrame(
        {
            "datetime": dates,
            "valeur": values,
        }
    )

    result = result.dropna(
        subset=["datetime", "valeur"]
    )
    result = result[
        (result["datetime"] >= date_depart)
        & (result["datetime"] <= date_fin)
    ]

    return _prepare_timeseries(result)


def _validate_excel_path(filepath):
    """Valide et retourne le chemin absolu du fichier Excel."""

    path = Path(filepath).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(
            f"Le fichier Excel n'existe pas : {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Le chemin ne correspond pas a un fichier : {path}"
        )

    if path.suffix.lower() not in {
        ".xlsx",
        ".xlsm",
        ".xls",
    }:
        raise ValueError(
            "Le fichier doit etre au format .xlsx, .xlsm ou .xls."
        )

    return path


# ==============================================================
# CHARGEMENT PRINCIPAL
# ==============================================================

def load_timeseries(filepath):
    """
    Charge toutes les series temporelles necessaires au modele.

    Parameters
    ----------
    filepath : str ou pathlib.Path
        Chemin du fichier Excel selectionne dans Main_bid.py.

    Returns
    -------
    dict
        Donnees temporelles et dates de l'horizon de simulation.
    """

    excel_path = _validate_excel_path(filepath)

    # Lecture de toutes les feuilles. Pour un .xlsm, pandas/openpyxl
    # lit les valeurs sans modifier ni enregistrer le classeur.
    workbook_data = pd.read_excel(
        excel_path,
        sheet_name=None,
        header=None,
        engine="openpyxl" if excel_path.suffix.lower() in {".xlsx", ".xlsm"} else None,
    )

    missing_sheets = sorted(
        REQUIRED_SHEETS.difference(workbook_data.keys())
    )

    if missing_sheets:
        raise KeyError(
            "Feuilles Excel manquantes : "
            + ", ".join(missing_sheets)
        )

    # ==========================================================
    # FEUILLE HORAIRE
    # ==========================================================

    df_horaire = workbook_data["Horaire"]

    try:
        date_depart = pd.to_datetime(
            df_horaire.iloc[2, 8],
            errors="raise",
        )
        date_fin = pd.to_datetime(
            df_horaire.iloc[2, 103],
            errors="raise",
        )
    except (IndexError, ValueError, TypeError) as error:
        raise ValueError(
            "Impossible de lire date_depart en I3 ou date_fin en CZ3 "
            "dans la feuille 'Horaire'."
        ) from error

    if pd.isna(date_depart) or pd.isna(date_fin):
        raise ValueError(
            "La date de depart ou la date de fin est manquante."
        )

    if date_fin < date_depart:
        raise ValueError(
            "La date de fin est anterieure a la date de depart."
        )

    # Lignes horaires, colonnes I a CZ incluses.
    hourly_rows = {
        "power_artouste_turbine": df_horaire.iloc[9, 8:104],
        "power_pont_de_camps_turbine": df_horaire.iloc[10, 8:104],
        "power_bious_turbine": df_horaire.iloc[11, 8:104],
        "power_fabreges_turbine": df_horaire.iloc[12, 8:104],
        "natural_inflows_bious_reservoir": df_horaire.iloc[26, 8:104],
        "natural_inflows_fabreges_reservoir": df_horaire.iloc[27, 8:104],
        "natural_inflows_allias_reservoir": df_horaire.iloc[28, 8:104],
        "natural_inflows_hourat_reservoir": df_horaire.iloc[29, 8:104],
        "natural_inflows_castet_reservoir": df_horaire.iloc[30, 8:104],
        "inflows_vanne_fabreges": df_horaire.iloc[42, 8:104],
    }

    hourly_timeseries = {
        key: _build_hourly_timeseries(
            values=values,
            date_depart=date_depart,
            date_fin=date_fin,
        )
        for key, values in hourly_rows.items()
    }

    # ==========================================================
    # FEUILLE INFLOWS_DATA : NIVEAUX DES RESERVOIRS
    # ==========================================================

    df_inflows = workbook_data["Inflows_data"]

    level_artouste_reservoir = _load_reservoir_level(
        dataframe=df_inflows,
        row_index=110,
    )
    level_bious_reservoir = _load_reservoir_level(
        dataframe=df_inflows,
        row_index=119,
    )
    level_fabreges_reservoir = _load_reservoir_level(
        dataframe=df_inflows,
        row_index=118,
    )

    # ==========================================================
    # FEUILLE HDX_DATA : INDISPONIBILITES
    # ==========================================================

    df_hdx = workbook_data["Hdx_data"]

    unavailability_miegebat_turbine = _load_unavailability(
        dataframe=df_hdx,
        datetime_column=56,
        value_column=57,
        date_depart=date_depart,
        date_fin=date_fin,
    )
    unavailability_hourat_turbine = _load_unavailability(
        dataframe=df_hdx,
        datetime_column=58,
        value_column=59,
        date_depart=date_depart,
        date_fin=date_fin,
    )
    unavailability_geteu_turbine = _load_unavailability(
        dataframe=df_hdx,
        datetime_column=60,
        value_column=61,
        date_depart=date_depart,
        date_fin=date_fin,
    )
    unavailability_castet_turbine = _load_unavailability(
        dataframe=df_hdx,
        datetime_column=62,
        value_column=63,
        date_depart=date_depart,
        date_fin=date_fin,
    )

    print("date_depart :", date_depart)
    print("date_fin :", date_fin)

    # ==========================================================
    # RESULTAT FINAL
    # ==========================================================

    return {
        "source_file": str(excel_path),
        "date_depart": date_depart,
        "date_fin": date_fin,
        "natural_inflows_allias_reservoir": hourly_timeseries[
            "natural_inflows_allias_reservoir"
        ],
        "natural_inflows_bious_reservoir": hourly_timeseries[
            "natural_inflows_bious_reservoir"
        ],
        "natural_inflows_fabreges_reservoir": hourly_timeseries[
            "natural_inflows_fabreges_reservoir"
        ],
        "natural_inflows_hourat_reservoir": hourly_timeseries[
            "natural_inflows_hourat_reservoir"
        ],
        "natural_inflows_castet_reservoir": hourly_timeseries[
            "natural_inflows_castet_reservoir"
        ],
        "inflows_vanne_fabreges": hourly_timeseries[
            "inflows_vanne_fabreges"
        ],
        "power_artouste_turbine": hourly_timeseries[
            "power_artouste_turbine"
        ],
        "power_bious_turbine": hourly_timeseries[
            "power_bious_turbine"
        ],
        "power_fabreges_turbine": hourly_timeseries[
            "power_fabreges_turbine"
        ],
        "power_pont_de_camps_turbine": hourly_timeseries[
            "power_pont_de_camps_turbine"
        ],
        "level_artouste_reservoir": level_artouste_reservoir,
        "level_bious_reservoir": level_bious_reservoir,
        "level_fabreges_reservoir": level_fabreges_reservoir,
        "unavailability_miegebat_turbine": (
            unavailability_miegebat_turbine
        ),
        "unavailability_hourat_turbine": (
            unavailability_hourat_turbine
        ),
        "unavailability_geteu_turbine": (
            unavailability_geteu_turbine
        ),
        "unavailability_castet_turbine": (
            unavailability_castet_turbine
        ),
    }
