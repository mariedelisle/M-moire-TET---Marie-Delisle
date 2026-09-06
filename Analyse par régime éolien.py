import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# ============================================================
# ETAPE 1 - CHARGEMENT ET PRÉPARATION DES DONNÉES
# ============================================================

file_path = r"C:\Users\marie\Documents\Perso\ENGIE\Data DA ID\Stat descriptives.csv"

df = pd.read_csv(file_path, sep=",", encoding="utf-8-sig")
df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True)
df = df.sort_values("datetime")

df["month"] = df["datetime"].dt.month

df["spread_id_da"] = df["id_vwap_fr"] - df["da_actual_price"]
df["spread_positive"] = (df["spread_id_da"] > 0).astype(int)

def season_from_month(m):
    if m in [10, 11]:
        return "Autumn (Oct–Nov)"
    elif m in [12, 1, 2]:
        return "Winter (Dec–Feb)"
    elif m in [3, 4]:
        return "Spring (Mar–Apr)"
    else:
        return None

df["season"] = df["month"].apply(season_from_month)

df["weekday"] = df["datetime"].dt.weekday

holidays = pd.to_datetime(
    [
        "2025-11-01",
        "2025-11-11",
        "2025-12-25",
        "2026-01-01",
        "2026-04-06",
    ],
    utc=True
)

df["is_holiday"] = df["datetime"].dt.normalize().isin(holidays)

df["day_type"] = "Weekday"
df.loc[(df["weekday"] >= 5) | (df["is_holiday"]), "day_type"] = "Weekend / Holiday"


print("\nQuantiles éoliens (MW) - ARPEGE")
print(df["wind_fr_arpege"].quantile([0.25, 0.5, 0.75]).round(0))

print("\nQuantiles éoliens (MW) - STORM")
print(df["wind_fr_storm"].quantile([0.25, 0.5, 0.75]).round(0))

def build_wind_regime(series):
    q25, q50, q75 = series.quantile([0.25, 0.50, 0.75])

    def regime(x):
        if x <= q25:
            return "Low wind"
        elif x <= q50:
            return "Medium wind"
        elif x <= q75:
            return "High wind"
        else:
            return "Very high wind"

    return series.apply(regime)

df["wind_regime_arpege"] = build_wind_regime(df["wind_fr_arpege"])
df["wind_regime_storm"]  = build_wind_regime(df["wind_fr_storm"])

# ============================================================
# ÉTAPE 2 — ANALYSE HORAIRE
# ============================================================

# SUR L'ENSEMBLE DES HEURES étudiées du 25 octobre 2025 et le 4 avril 2026

def print_regime_stats(df, regime_col, title):

    stats = (
        df.groupby(regime_col)
          .agg(
              mean_spread=("spread_id_da", "mean"),
              median_spread=("spread_id_da", "median"),
              prob_spread_positive=("spread_positive", "mean"),
              std_spread=("spread_id_da", "std"),
              nb_obs=("spread_id_da", "count"),
          )
          .round(2)
    )

    stats["prob_spread_positive"] *= 100

    print(f"\n=== STATISTIQUES SPREAD ID–DA PAR RÉGIME DE VENT — {title} ===")
    print(stats)

print_regime_stats(df, "wind_regime_arpege", "ARPEGE")
print_regime_stats(df, "wind_regime_storm", "STORM")

# PAR SAISON

def print_regime_stats_by_season(df, regime_col, model_name):

    for season in ["Autumn (Oct–Nov)", "Winter (Dec–Feb)", "Spring (Mar–Apr)"]:

        df_season = df[df["season"] == season]

        stats = (
            df_season.groupby(regime_col)
            .agg(
                mean_spread=("spread_id_da", "mean"),
                median_spread=("spread_id_da", "median"),
                prob_spread_positive=("spread_positive", "mean"),
                std_spread=("spread_id_da", "std"),
                nb_obs=("spread_id_da", "count"),
            )
            .round(2)
        )

        stats["prob_spread_positive"] *= 100

        print(f"\n=== STATISTIQUES SPREAD ID–DA PAR RÉGIME DE VENT — {model_name} — {season} ===")
        print(stats)

print_regime_stats_by_season(df, "wind_regime_arpege", "ARPEGE")
print_regime_stats_by_season(df, "wind_regime_storm", "STORM")

# PAR TYPE DE JOUR

def print_regime_stats_by_daytype(df, regime_col, model_name):

    for day_type in ["Weekday", "Weekend / Holiday"]:

        df_day = df[df["day_type"] == day_type]

        stats = (
            df_day.groupby(regime_col)
            .agg(
                mean_spread=("spread_id_da", "mean"),
                median_spread=("spread_id_da", "median"),
                prob_spread_positive=("spread_positive", "mean"),
                std_spread=("spread_id_da", "std"),
                nb_obs=("spread_id_da", "count"),
            )
            .round(2)
        )

        stats["prob_spread_positive"] *= 100

        print(f"\n=== STATISTIQUES SPREAD ID–DA PAR RÉGIME DE VENT — {model_name} — {day_type} ===")
        print(stats)

print_regime_stats_by_daytype(df, "wind_regime_arpege", "ARPEGE")
print_regime_stats_by_daytype(df, "wind_regime_storm", "STORM")

# PAR SAISON × TYPE DE JOUR

def print_regime_stats_by_season_daytype(df, regime_col, model_name):

    seasons = ["Autumn (Oct–Nov)", "Winter (Dec–Feb)", "Spring (Mar–Apr)"]
    day_types = ["Weekday", "Weekend / Holiday"]

    for season in seasons:
        for day_type in day_types:

            df_sub = df[
                (df["season"] == season) &
                (df["day_type"] == day_type)
            ]

            if df_sub.empty:
                continue

            stats = (
                df_sub
                .groupby(regime_col)
                .agg(
                    mean_spread=("spread_id_da", "mean"),
                    median_spread=("spread_id_da", "median"),
                    prob_spread_positive=("spread_positive", "mean"),
                    std_spread=("spread_id_da", "std"),
                    nb_obs=("spread_id_da", "count"),
                )
                .round(2)
            )

            stats["prob_spread_positive"] *= 100

            print(
                f"\n=== STATISTIQUES SPREAD ID–DA PAR RÉGIME DE VENT — "
                f"{model_name} — {season} — {day_type} ==="
            )
            print(stats)

print_regime_stats_by_season_daytype(df, "wind_regime_arpege", "ARPEGE")
print_regime_stats_by_season_daytype(df, "wind_regime_storm", "STORM")

# ============================================================
# SCATTER PLOT — STORM
# ============================================================

corr_storm = df["wind_fr_storm"].corr(df["spread_id_da"])

plt.figure(figsize=(10, 6))

sns.scatterplot(
    data=df,
    x="wind_fr_storm",
    y="spread_id_da",
    alpha=0.3
)

plt.title(
    f"Forecast éolien STORM vs Spread ID-DA\n"
    f"Corrélation de Pearson = {corr_storm:.3f}"
)

plt.xlabel("Forecast éolien FR STORM (MW)")
plt.ylabel("Spread ID-DA (€/MWh)")

plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()


# ============================================================
# SCATTER PLOT — ARPEGE
# ============================================================

corr_arpege = df["wind_fr_arpege"].corr(df["spread_id_da"])

plt.figure(figsize=(10, 6))

sns.scatterplot(
    data=df,
    x="wind_fr_arpege",
    y="spread_id_da",
    alpha=0.3
)

plt.title(
    f"Forecast éolien ARPEGE vs Spread ID-DA\n"
    f"Corrélation de Pearson = {corr_arpege:.3f}"
)

plt.xlabel("Forecast éolien FR ARPEGE (MW)")
plt.ylabel("Spread ID-DA (€/MWh)")

plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()


# ============================================================
# CORRÉLATIONS
# ============================================================

print("\n=== CORRÉLATIONS DE PEARSON AVEC LE SPREAD ID–DA ===")
print(f"STORM   : {corr_storm:.4f}")
print(f"ARPEGE  : {corr_arpege:.4f}")