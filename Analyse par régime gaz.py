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
df["hour"] = df["datetime"].dt.hour
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

print("\nQuantiles gaz naturel (MW) - STORM")
print(df["nat_gas_fr_storm"].quantile([0,1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]).round(0))

def build_gas_regime(series):
    q10, q20, q30, q40, q50, q60, q70, q80, q90 = series.quantile([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])

    def regime(x):
        if x <= q10:
            return "Q0-10"
        elif x <= q20:
            return "Q10-20"
        elif x <= q30:
            return "Q20-30"
        elif x <= q40:
            return "Q30-40"
        elif x <= q50:
            return "Q40-50"
        elif x <= q60:
            return "Q50-60"
        elif x <= q70:
            return "Q60-70"
        elif x <= q80:
            return "Q70-80"
        elif x <= q90:
            return "Q80-90"
        else:
            return "Q90-100"

    return series.apply(regime)

df["gas_regime_storm"]  = build_gas_regime(df["nat_gas_fr_storm"])

# ============================================================
# ÉTAPE 2 — ANALYSE HORAIRE
# ============================================================

# SUR L'ENSEMBLE DES HEURES étudiées du 25 octobre 2025 et le 4 avril 2026

def print_regime_stats(df, regime_col, title):

    stats = (
        df.groupby([regime_col])
          .agg(
              mean_spread=("spread_id_da", "mean"),
              median_spread=("spread_id_da", "median"),
              prob_spread_positive=("spread_positive", "mean"),
              std_spread=("spread_id_da", "std"),
              #nb_obs=("spread_id_da", "count"),
          )
          .round(2)
    )

    stats["prob_spread_positive"] *= 100

    print(f"\n=== STATISTIQUES SPREAD ID–DA PAR RÉGIME DE GAZ ET HEURE — {title} ===")
    print(stats)

print_regime_stats(df, "gas_regime_storm", "STORM")

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
                #nb_obs=("spread_id_da", "count"),
            )
            .round(2)
        )

        stats["prob_spread_positive"] *= 100

        print(f"\n=== STATISTIQUES SPREAD ID–DA PAR RÉGIME DE GAZ — {model_name} — {season} ===")
        print(stats)

print_regime_stats_by_season(df, "gas_regime_storm", "STORM")

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
                #nb_obs=("spread_id_da", "count"),
            )
            .round(2)
        )

        stats["prob_spread_positive"] *= 100

        print(f"\n=== STATISTIQUES SPREAD ID–DA PAR RÉGIME DE GAZ — {model_name} — {day_type} ===")
        print(stats)

df["gas_regime_storm"] = build_gas_regime(df["nat_gas_fr_storm"])
print_regime_stats_by_daytype(df, "gas_regime_storm", "STORM")

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
                f"\n=== STATISTIQUES SPREAD ID–DA PAR RÉGIME DE GAZ — "
                f"{model_name} — {season} — {day_type} ==="
            )
            print(stats)

print_regime_stats_by_season_daytype(df, "gas_regime_storm", "STORM")
df["gas_regime_storm"] = build_gas_regime(df["nat_gas_fr_storm"])



# Scatter plot

corr = df["nat_gas_fr_storm"].corr(
    df["spread_id_da"]
)

plt.figure(figsize=(12,6))

sns.regplot(
    data=df,
    x="nat_gas_fr_storm",
    y="spread_id_da",
    scatter_kws={"alpha": 0.25},
    line_kws={"color": "red"}
)

plt.title(
    f"Forecast Gaz (STORM) vs Spread ID-DA\n"
    f"Corrélation = {corr:.3f}"
)

plt.xlabel("Forecast Gaz FR STORM (MW)")
plt.ylabel("Spread ID-DA")

plt.grid(True)

plt.show()

print(f"Corrélation : {corr:.4f}")

# ============================================================
# SCATTER PLOT — FORECAST GAZ VS SPREAD ID-DA
# ============================================================

plt.figure(figsize=(10, 6))

sns.scatterplot(
    data=df,
    x="nat_gas_fr_storm",
    y="spread_id_da",
    alpha=0.4
)

plt.axhline(0, linestyle="--", linewidth=1)

plt.title(
    f"Forecast Gaz (STORM) vs Spread ID-DA\n"
    f"Corrélation = {corr:.3f}"
)
plt.xlabel("Forecast Gaz FR STORM (MW)")
plt.ylabel("Spread ID-DA (€/MWh)")

plt.grid(True, alpha=0.3)
plt.tight_layout()

plt.show()