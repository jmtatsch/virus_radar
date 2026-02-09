import logging
from typing import List

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from statsmodels.tsa.seasonal import MSTL
from statsmodels.tsa.api import ExponentialSmoothing
import pandas as pd
from plotly.graph_objs import Figure

from geocode import Geocoder
from location_manager import LocationManager

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Technical terms with explanations
are_term = "Influenza, COVID-19 und RSV-Infektionen"
are_tooltip = "ARE (Akute Respiratorische Erkrankungen): Akute Atemwegserkrankungen wie Influenza, COVID-19 und RSV"

ili_term = "Fieber mit Husten oder Halsschmerzen"
ili_tooltip = "ILI (Influenza-like Illness): Grippeähnliche Erkrankungen mit Fieber und Atemwegssymptomen"

percentage_infected_term = "Erkrankte Bevölkerung in %"


def get_traffic_light_status(
    dataframe: pd.DataFrame, y_column: str, facet_col: str = None
) -> dict:
    """
    Calculate traffic light status for today's values based on quintiles.
    Uses forecast data if today's date falls in the forecast period.

    Args:
        dataframe: Data containing the values
        y_column: Column name with the values to analyze
        facet_col: Column name to group by (e.g., 'typ', 'Erkrankung', 'Altersgruppe')

    Returns:
        Dictionary mapping series names to colors ('🔴', '🟡', '🟢')
    """
    status = {}
    today = pd.Timestamp.today().normalize()

    # Check if there's a forecast column
    forecast_col = y_column + "_forecast"
    has_forecast = forecast_col in dataframe.columns

    if facet_col and facet_col in dataframe.columns:
        # Calculate per series
        for series_name in dataframe[facet_col].unique():
            series_data = dataframe[dataframe[facet_col] == series_name]
            values = series_data[y_column].dropna()

            if len(values) == 0:
                continue

            # Try to get today's value (from actual data or forecast)
            current_value = None
            if today in series_data.index:
                # Check forecast first, then actual data
                if has_forecast and pd.notna(series_data.loc[today, forecast_col]):
                    current_value = series_data.loc[today, forecast_col]
                elif pd.notna(series_data.loc[today, y_column]):
                    current_value = series_data.loc[today, y_column]

            # If no value for today, use most recent available value
            if current_value is None:
                if has_forecast:
                    # Try forecast column first
                    forecast_values = series_data[forecast_col].dropna()
                    if len(forecast_values) > 0:
                        current_value = forecast_values.iloc[-1]
                    else:
                        current_value = values.iloc[-1]
                else:
                    current_value = values.iloc[-1]

            # Calculate quintile boundaries from historical data only
            q40 = values.quantile(0.4)
            q60 = values.quantile(0.6)

            # Determine color
            if current_value >= q60:
                status[series_name] = "🔴"  # Red: upper two quintiles
            elif current_value >= q40:
                status[series_name] = "🟡"  # Yellow: middle quintile
            else:
                status[series_name] = "🟢"  # Green: lower two quintiles
    else:
        # Calculate for entire dataset
        values = dataframe[y_column].dropna()

        if len(values) > 0:
            # Try to get today's value
            current_value = None
            if today in dataframe.index:
                if has_forecast and pd.notna(dataframe.loc[today, forecast_col]):
                    current_value = dataframe.loc[today, forecast_col]
                elif pd.notna(dataframe.loc[today, y_column]):
                    current_value = dataframe.loc[today, y_column]

            # If no value for today, use most recent
            if current_value is None:
                if has_forecast:
                    forecast_values = dataframe[forecast_col].dropna()
                    if len(forecast_values) > 0:
                        current_value = forecast_values.iloc[-1]
                    else:
                        current_value = values.iloc[-1]
                else:
                    current_value = values.iloc[-1]

            q40 = values.quantile(0.4)
            q60 = values.quantile(0.6)

            if current_value >= q60:
                status["overall"] = "🔴"
            elif current_value >= q40:
                status["overall"] = "🟡"
            else:
                status["overall"] = "🟢"

    return status


st.set_page_config(
    page_title="VirusRadar",
    page_icon="🦠",
    layout="wide",
)


hide_decoration_bar_style = """
    <style>
        header {visibility: hidden;}
    </style>
"""
st.markdown(hide_decoration_bar_style, unsafe_allow_html=True)

location_manager = LocationManager()


def add_forecasts(
    df: pd.DataFrame,
    columns_to_forecast: List[str],
    facet_col: str,
    prediction_horizon: int = 12,
    periods: int = 52,
) -> pd.DataFrame:
    """
    For each column in columns_to_forecast, this function fits an Exponential Smoothing model,
    generates a forecast for prediction_horizon time steps, and adds the fitted values and forecast
    as a new column named '{original_column}_forecast' to the dataframe.
    """
    logger.info("Adding forecasts for columns: %s", columns_to_forecast)
    forecast_dfs = []

    for col in columns_to_forecast:
        # Filter the dataframe for the current illness
        for illness in df[facet_col].unique():
            df_illness = df[df[facet_col] == illness].copy()

            # Ensure index is DatetimeIndex for resampling
            if not isinstance(df_illness.index, pd.DatetimeIndex):
                logger.info("Converting index to DatetimeIndex for %s", illness)
                df_illness.index = pd.to_datetime(df_illness.index)

            # Check if we have enough data points before processing
            non_null_data = df_illness[col].dropna()
            if len(non_null_data) < periods * 2:
                logger.warning(
                    "Skipping forecast for %s - insufficient data (%d points)",
                    illness,
                    len(non_null_data),
                )
                continue

            # Select only the column to forecast and resample to weekly frequency
            # Use last() instead of mean() to preserve the most recent value in each week
            df_illness_col = df_illness[[col]].resample("W-FRI").last()

            # Forward fill gaps - be more lenient (up to 12 weeks for sparse data)
            df_illness_col = df_illness_col.ffill(limit=12)

            # Backward fill any leading NaNs
            df_illness_col = df_illness_col.bfill(limit=2)

            # Drop any remaining NaN values
            df_illness_col = df_illness_col.dropna(subset=[col])

            # Final check for sufficient data (at least 1 year of weekly data)
            # Reduced from 2 years to handle sparse datasets like RSV
            min_weeks_required = periods  # 52 weeks = 1 year
            if len(df_illness_col) < min_weeks_required:
                logger.warning(
                    "Skipping forecast for %s - insufficient non-NaN data after processing (%d points after resampling, need %d)",
                    illness,
                    len(df_illness_col),
                    min_weeks_required,
                )
                continue

            try:
                # Fit the Exponential Smoothing model for the current column
                model = ExponentialSmoothing(
                    df_illness_col[col],
                    seasonal_periods=periods,
                    trend="add",
                    seasonal="add",
                    use_boxcox=False,
                    initialization_method="estimated",
                ).fit()

                # Generate forecast for the defined prediction horizon
                forecast = model.forecast(prediction_horizon)

                # Create a new DataFrame from the forecasted series
                forecast_df = pd.DataFrame(forecast, columns=[col + "_forecast"])

                # Ensure the forecast index is DatetimeIndex
                if not isinstance(forecast_df.index, pd.DatetimeIndex):
                    forecast_df.index = pd.to_datetime(forecast_df.index)
                forecast_df.loc[:, facet_col] = illness
                forecast_dfs.append(forecast_df)
                logger.info("Successfully created forecast for %s", illness)
            except Exception as e:
                logger.warning("Failed to create forecast for %s: %s", illness, str(e))
                continue

    # Concatenate all forecast dataframes with the original dataframe
    if forecast_dfs:
        df = pd.concat([df] + forecast_dfs, join="outer")
        # Ensure index is properly sorted and typed as DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df = df.sort_index()
    return df


def plot_forecast(figure: Figure, dataframe: pd.DataFrame, facet: str) -> Figure:
    """
    Adds forecast traces to the provided Plotly figure.
    It looks for _forecast columns in the dataframe, groups the data by the given facet and adds the traces to the plot.
    Ensures forecast lines use the same color as their corresponding historical data.
    """
    logger.info("Plotting forecast for facet: %s", facet)
    logger.info("Available columns: %s", list(dataframe.columns))
    forecast_cols = [col for col in dataframe.columns if col.endswith("_forecast")]
    logger.info("Found forecast columns: %s", forecast_cols)
    if not forecast_cols:
        logger.warning("No forecast columns found in dataframe")
        return figure
    forecast_col = forecast_cols[0]

    # Get the colors from the existing traces
    color_map = {}
    for trace in figure.data:
        if trace.name in dataframe[facet].unique():
            # For area charts, get color from fillcolor or line.color
            if hasattr(trace, "fillcolor") and trace.fillcolor:
                color_map[trace.name] = trace.fillcolor
            elif hasattr(trace, "line") and hasattr(trace.line, "color"):
                color_map[trace.name] = trace.line.color

    for group in sorted(dataframe[facet].unique()):
        df_temp = dataframe[dataframe[facet] == group]
        # Filter to only forecast data (non-NaN)
        df_forecast = df_temp[df_temp[forecast_col].notna()]

        logger.info("Group %s: %d forecast points", group, len(df_forecast))

        if len(df_forecast) == 0:
            logger.warning("No forecast data for group: %s", group)
            continue

        # Get the original column name (remove _forecast suffix)
        original_col = forecast_col.replace("_forecast", "")

        # Find the last actual data point to connect the forecast line
        df_actual = df_temp[df_temp[original_col].notna()]
        if len(df_actual) > 0:
            last_actual_date = df_actual.index[-1]
            last_actual_value = df_actual[original_col].iloc[-1]

            # Prepend the last actual point to create visual continuity
            x_values = [last_actual_date] + list(df_forecast.index)
            y_values = [last_actual_value] + list(df_forecast[forecast_col])
        else:
            x_values = list(df_forecast.index)
            y_values = list(df_forecast[forecast_col])

        # Use the same color as the original trace
        color = color_map.get(group)
        logger.info("Adding forecast trace for %s with color %s", group, color)
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines",
                line=dict(color=color, dash="dash", width=2),
                name=f"{group} Vorhersage",
                showlegend=True,
            )
        )
    # Add a vertical line for today
    today = pd.to_datetime("today")
    figure.add_vline(x=today, line_width=1, line_dash="dash", line_color="red")
    figure.add_annotation(
        x=today,
        y=1,
        yref="paper",
        text="Heute",
        showarrow=False,
        xanchor="right",
        yanchor="top",
    )
    return figure


def add_quintile_bands(
    fig: Figure,
    dataframe: pd.DataFrame,
    y_column: str,
    facet_col: str = None,
    show_regions: bool = True,
    show_lines: bool = True,
) -> Figure:
    """
    Add quintile visualization to plotly figure.
    Shades top quintile in red and bottom quintile in green.

    Args:
        fig: Plotly figure object
        dataframe: Data containing the values
        y_column: Column name with the values to analyze
        facet_col: Column name to group by (e.g., 'typ', 'Erkrankung', 'Altersgruppe')
        show_regions: Whether to show shaded regions
        show_lines: Whether to show reference lines
    """
    if facet_col and facet_col in dataframe.columns:
        # Calculate quintiles per series
        for series_name in dataframe[facet_col].unique():
            series_data = dataframe[dataframe[facet_col] == series_name]
            values = series_data[y_column].dropna()

            if len(values) == 0:
                continue

            quintiles = values.quantile([0.2, 0.8])

            # For multi-series, only show reference lines (not regions to avoid overlap)
            if show_lines:
                # Get color from existing traces if possible
                trace_color = None
                for trace in fig.data:
                    if hasattr(trace, "name") and trace.name == series_name:
                        if hasattr(trace, "line") and hasattr(trace.line, "color"):
                            trace_color = trace.line.color
                        elif hasattr(trace, "marker") and hasattr(
                            trace.marker, "color"
                        ):
                            trace_color = trace.marker.color
                        break

                # Top quintile line (80th percentile)
                fig.add_hline(
                    y=quintiles[0.8],
                    line_dash="dot",
                    line_color=trace_color if trace_color else "rgba(255, 69, 58, 0.4)",
                    line_width=1,
                    annotation_text=f"{series_name} P80",
                    annotation_position="right",
                    annotation=dict(
                        font_size=8,
                        font_color=(
                            trace_color if trace_color else "rgba(255, 69, 58, 0.8)"
                        ),
                    ),
                )

                # Bottom quintile line (20th percentile)
                fig.add_hline(
                    y=quintiles[0.2],
                    line_dash="dot",
                    line_color=trace_color if trace_color else "rgba(52, 199, 89, 0.4)",
                    line_width=1,
                    annotation_text=f"{series_name} P20",
                    annotation_position="right",
                    annotation=dict(
                        font_size=8,
                        font_color=(
                            trace_color if trace_color else "rgba(52, 199, 89, 0.8)"
                        ),
                    ),
                )
    else:
        # Single series - use global bands
        values = dataframe[y_column].dropna()
        if len(values) == 0:
            logger.warning("No values found for quintile calculation")
            return fig

        quintiles = values.quantile([0.2, 0.8])

        if show_regions:
            # Top quintile (red/warning)
            fig.add_hrect(
                y0=quintiles[0.8],
                y1=values.max(),
                fillcolor="rgba(255, 69, 58, 0.1)",
                line_width=0,
                annotation_text="Hohe Werte (Top 20%)",
                annotation_position="top right",
                annotation=dict(font_size=10, font_color="rgba(255, 69, 58, 0.8)"),
            )

            # Bottom quintile (traffic light green)
            fig.add_hrect(
                y0=values.min(),
                y1=quintiles[0.2],
                fillcolor="rgba(52, 199, 89, 0.1)",
                line_width=0,
                annotation_text="Niedrige Werte (Bottom 20%)",
                annotation_position="bottom right",
                annotation=dict(font_size=10, font_color="rgba(52, 199, 89, 0.8)"),
            )

        if show_lines:
            fig.add_hline(
                y=quintiles[0.8],
                line_dash="dash",
                line_color="rgba(255, 69, 58, 0.5)",
                line_width=1,
            )
            fig.add_hline(
                y=quintiles[0.2],
                line_dash="dash",
                line_color="rgba(52, 199, 89, 0.5)",
                line_width=1,
            )

    return fig


def decompose_and_plot(df: pd.DataFrame, illness: str, infected_column: str) -> Figure:
    """
    Decomposes the time series for the specified illness and plots the result.
    """
    logger.info("Decomposing time series for illness: %s", illness)
    series = df[df["Erkrankung"] == illness][infected_column]
    decomposed = MSTL(series).fit()
    fig = decomposed.plot()
    fig.suptitle(f"Decomposition {illness}")
    return fig


def find_closest_klaerwerk(df: pd.DataFrame, user_location: dict) -> str:
    """
    Finds the closest wastewater treatment plant (Klärwerk) to the given coordinates.
    """
    logger.info("Finding closest Klärwerk to location: %s", user_location)
    local_geocoder = Geocoder()
    # get distinct standorte
    distinct_standorte = sorted(df["standort"].dropna().unique())
    distinct_standorte = pd.DataFrame(distinct_standorte, columns=["standort"]).copy()
    # add coordinates for each standort
    coordinates = distinct_standorte["standort"].apply(
        lambda x: local_geocoder.geocode(city=x, country="DE")
    )
    distinct_standorte.loc[:, "latitude"] = coordinates.apply(
        lambda x: x[0] if x[0] is not None else 0.0
    )
    distinct_standorte.loc[:, "longitude"] = coordinates.apply(
        lambda x: x[1] if x[1] is not None else 0.0
    )
    distinct_standorte.loc[:, "distance"] = (
        (distinct_standorte["latitude"] - user_location["latitude"]) ** 2
        + (distinct_standorte["longitude"] - user_location["longitude"]) ** 2
    ) ** 0.5
    closest_klaerwerk = distinct_standorte.loc[distinct_standorte["distance"].idxmin()]
    return str(closest_klaerwerk["standort"])


st.title("Virus Radar 🦠")

st.markdown(
    """
 Virus Radar aggregiert, prädiziert und visualisiert Virusinfektionen in Deutschland.
 Nutzer können aktuelle Infektionszahlen für verschiedene Viren in ihrer Region einsehen und prädiktive Modelle nutzen, um zukünftige Entwicklungen abzuschätzen.
 Ziel ist es, dass Nutzer fundierte Entscheidungen treffen, ob sie z.B. 
 * ohne erhöhtes Erkrankungsrisiko ins Büro können oder besser im Homeoffice bleiben sollten
 * Menschenmengen besser meiden sollten
 * ihre Kinder in den Kindergarten schicken oder besser ein paar Tage zuhause lassen sollten
    """
)

# Explanatory expander for technical terms
with st.expander("ℹ️ Erklärung der Begriffe"):
    st.markdown(
        """
    **ARE (Akute Respiratorische Erkrankungen)**: Akute Atemwegserkrankungen wie Influenza, COVID-19 und RSV-Infektionen.
    
    **ILI (Influenza-like Illness)**: Grippeähnliche Erkrankungen, definiert als Fieber mit Husten oder Halsschmerzen.
    
    **Inzidenz**: Anzahl der Neuerkrankungen pro 100.000 Einwohner.
    """
    )

land_index = 0
region_index = 0
klaerwerk_index = 0

(
    tab1,
    tab2,
) = st.tabs(["Grippeweb", "Abwasser"])

with tab2:
    # Load the abwasser data
    with st.spinner("Lade Abwasserdaten..."):
        logger.info("Loading Abwasser data")
        abwasser = pd.read_csv(
            "data/Abwassersurveillance_AMELAG/amelag_einzelstandorte.tsv",
            sep="\t",
            parse_dates=["datum"],
        )
        distinct_province_short = sorted(abwasser["bundesland"].dropna().unique())
    if "province_short" in location_manager.location:
        if location_manager.location["province_short"] in distinct_province_short:
            land_index = distinct_province_short.index(
                location_manager.location["province_short"]
            )

    selected_bundesland = st.selectbox(
        "Bundesland", distinct_province_short, index=land_index
    )
    distinct_standorte = sorted(
        abwasser[abwasser["bundesland"] == selected_bundesland]["standort"]
        .dropna()
        .unique()
    )

    if (
        location_manager.location["latitude"] is not None
        and location_manager.location["longitude"] is not None
    ):
        with st.spinner("Suche nächstes Klärwerk..."):
            closest_klaerwerk = find_closest_klaerwerk(
                abwasser, location_manager.location
            )
            klaerwerk_index = distinct_standorte.index(closest_klaerwerk)
    else:
        # if no location is available, set the index to 0
        klaerwerk_index = 0

    standort = st.selectbox("Klärwerk", distinct_standorte, index=klaerwerk_index)

    with st.spinner("Erstelle Visualisierung..."):
        abwasser = abwasser[abwasser["standort"] == standort]
        abwasser = abwasser[abwasser["typ"] != "Influenza A+B"]

        # Rename loess_vorhersage to vorhersage for easier reference
        abwasser = abwasser.rename(columns={"loess_vorhersage": "vorhersage"})

        # Set datum as index and ensure it's DatetimeIndex
        abwasser.set_index("datum", inplace=True)
        if not isinstance(abwasser.index, pd.DatetimeIndex):
            abwasser.index = pd.to_datetime(abwasser.index)

        # Store last updated date before adding forecasts
        last_updated = pd.to_datetime(abwasser.index.max()).date()

        # Add forecasts - the add_forecasts function will skip series without enough data
        # (requires at least 1 year / 52 weeks of data after resampling)

        # Log data availability per virus type
        logger.info(
            "Checking data availability for %d virus types",
            len(abwasser["typ"].unique()),
        )
        for typ in abwasser["typ"].unique():
            data_points = len(
                abwasser[abwasser["typ"] == typ].dropna(subset=["vorhersage"])
            )
            logger.info("Virus type '%s' has %d data points", typ, data_points)

        # Always try to add forecasts - the function will skip virus types without enough data
        logger.info("Starting forecast generation for abwasser data")
        abwasser = add_forecasts(
            abwasser,
            ["vorhersage"],
            facet_col="typ",
            periods=52,
            prediction_horizon=12,
        )

        # Check if any forecasts were generated
        has_forecasts = (
            "vorhersage_forecast" in abwasser.columns
            and abwasser["vorhersage_forecast"].notna().any()
        )
        logger.info("Forecast generation complete. Has forecasts: %s", has_forecasts)
        if has_forecasts:
            logger.info("Columns after forecast: %s", list(abwasser.columns))
            logger.info(
                "Forecast data rows: %s",
                len(abwasser[abwasser["vorhersage_forecast"].notna()]),
            )
            # Log forecast counts per virus type
            for typ in abwasser["typ"].unique():
                forecast_count = len(
                    abwasser[
                        (abwasser["typ"] == typ)
                        & (abwasser["vorhersage_forecast"].notna())
                    ]
                )
                logger.info(
                    "Virus type '%s' has %d forecast points", typ, forecast_count
                )

        # start date is last update - 2 years
        start_date = last_updated - pd.DateOffset(years=1)

        # Use 'vorhersage' as y column (correct column name from data)
        fig_abwasser = px.line(
            abwasser,
            y="vorhersage",
            color="typ",
            title=f"Geglättete Abwasserwerte {standort}",
            labels={"datum": "", "vorhersage": "Vorhersage", "typ": "Virus"},
        )

        if has_forecasts:
            fig_abwasser = plot_forecast(fig_abwasser, abwasser, "typ")
        else:
            # Add "today" marker even when there's no forecast
            today = pd.to_datetime("today")
            fig_abwasser.add_vline(
                x=today, line_width=1, line_dash="dash", line_color="red"
            )
            fig_abwasser.add_annotation(
                x=today,
                y=1,
                yref="paper",
                text="Heute",
                showarrow=False,
                xanchor="right",
                yanchor="top",
            )

        fig_abwasser = add_quintile_bands(
            fig_abwasser, abwasser, "vorhersage", facet_col="typ"
        )

        # Adjust x-axis range to include forecast if available
        if has_forecasts:
            # Safely get max date from index
            try:
                max_idx = abwasser.index.max()
                end_date = pd.to_datetime(max_idx).date() if max_idx else last_updated
            except Exception as e:
                logger.warning("Error getting max date from index: %s", e)
                end_date = last_updated
        else:
            end_date = last_updated
        fig_abwasser.update_xaxes(type="date", range=[start_date, end_date])

        # Get traffic light status
        traffic_lights = get_traffic_light_status(
            abwasser, "vorhersage", facet_col="typ"
        )

    # Display traffic lights
    st.markdown("**Aktuelle Lage**")
    if not has_forecasts:
        st.warning(
            "⚠️ Nicht genügend Daten für Prognosen (mindestens 1 Jahr wöchentliche Daten erforderlich)"
        )
    cols = st.columns(len(traffic_lights))
    for idx, (series_name, light) in enumerate(sorted(traffic_lights.items())):
        with cols[idx]:
            st.metric(label=series_name, value=light)

    st.plotly_chart(fig_abwasser, width="stretch")
    st.caption(f"💡 Letzte Datenaktualisierung: {last_updated}")


with tab1:
    # Load the grippeweb data
    with st.spinner("Lade GrippeWeb-Daten..."):
        logger.info("Loading GrippeWeb data")
        grippeweb = pd.read_csv(
            "data/GrippeWeb_Daten_des_Wochenberichts/GrippeWeb_Daten_des_Wochenberichts.tsv",
            sep="\t",
        )

        regions = sorted(grippeweb["Region"].unique())

    if "region" in location_manager.location:
        # if region is in the list of regions, set it as default
        if location_manager.location["region"] in regions:
            region_index = regions.index(location_manager.location["region"])
    else:
        region_index = 4
    region = st.selectbox(
        "Region",
        regions,
        key="region",
        index=region_index,
        help="Wählen Sie Ihre Region aus, um regionale Infektionsdaten zu sehen",
    )

    # Parse calendar week data
    split_data = grippeweb["Kalenderwoche"].str.split("-W", expand=True)
    grippeweb = grippeweb.assign(Jahr=split_data[0], Woche=split_data[1])

    # Create date from Jahr and Woche
    date_str = grippeweb["Jahr"].astype(str) + grippeweb["Woche"].astype(str) + "-5"
    grippeweb = grippeweb.assign(Datum=pd.to_datetime(date_str, format="%G%V-%u"))
    grippeweb.set_index("Datum", inplace=True)

    # Calculate percentage infected
    grippeweb = grippeweb.assign(
        **{percentage_infected_term: (grippeweb["Inzidenz"] / 100000) * 100}
    )

    # By focus area
    with st.spinner("Berechne Prognosen für regionale Daten..."):
        grippeweb_region = grippeweb[grippeweb["Region"] == region].copy()
        grippeweb_region["Erkrankung"] = grippeweb_region["Erkrankung"].replace(
            {"ILI": ili_term, "ARE": are_term}
        )
        last_updated = pd.to_datetime(grippeweb_region.index.max())
        start_date = last_updated - pd.DateOffset(years=2)

        grippeweb_region = add_forecasts(
            grippeweb_region, [percentage_infected_term], facet_col="Erkrankung"
        )
        end_date = pd.to_datetime(grippeweb_region.index.max())
        are_ili_by_region = px.line(
            grippeweb_region,
            y=percentage_infected_term,
            color="Erkrankung",
            title=f"Region {region}",
            labels={"index": ""},
        )
        are_ili_by_region = plot_forecast(
            are_ili_by_region, grippeweb_region, "Erkrankung"
        )
        are_ili_by_region = add_quintile_bands(
            are_ili_by_region,
            grippeweb_region,
            percentage_infected_term,
            facet_col="Erkrankung",
        )
        are_ili_by_region.update_xaxes(type="date", range=[start_date, end_date])

        # Get traffic light status
        traffic_lights_region = get_traffic_light_status(
            grippeweb_region, percentage_infected_term, facet_col="Erkrankung"
        )

    # Age groups only exist for bundesweite data
    bundesweit = grippeweb[grippeweb["Region"] == "Bundesweit"]

    altersgruppen = st.multiselect(
        "Altersgruppen",
        ["0-4", "5-14", "15-34", "35-59", "60+"],
        default=["0-4", "5-14"],
        help="Wählen Sie Altersgruppen aus, um die Infektionsraten für verschiedene Altersgruppen zu vergleichen",
    )
    bundesweit = bundesweit[bundesweit["Altersgruppe"].isin(altersgruppen)]

    with st.spinner("Berechne Prognosen für Altersgruppen..."):
        # Akute respiratorische Erkrankungen (ARE)
        bundesweit_are = bundesweit[bundesweit["Erkrankung"] == "ARE"]
        bundesweit_are = add_forecasts(
            bundesweit_are, [percentage_infected_term], facet_col="Altersgruppe"
        )
        are_by_age_groups = px.line(
            bundesweit_are,
            y=percentage_infected_term,
            color="Altersgruppe",
            title=f"{are_term} nach Altersgruppen",
            labels={"index": ""},
        )
        are_by_age_groups = plot_forecast(
            are_by_age_groups, bundesweit_are, "Altersgruppe"
        )
        are_by_age_groups = add_quintile_bands(
            are_by_age_groups,
            bundesweit_are,
            percentage_infected_term,
            facet_col="Altersgruppe",
        )
        are_by_age_groups.update_xaxes(type="date", range=[start_date, end_date])

        # Get traffic light status
        traffic_lights_are = get_traffic_light_status(
            bundesweit_are, percentage_infected_term, facet_col="Altersgruppe"
        )

        # Grippeähnliche Erkrankungen (ILI)
        bundesweit_ili = bundesweit[bundesweit["Erkrankung"] == "ILI"]
        bundesweit_ili = add_forecasts(
            bundesweit_ili, [percentage_infected_term], facet_col="Altersgruppe"
        )
        ili_by_age_groups = px.line(
            bundesweit_ili,
            y=percentage_infected_term,
            color="Altersgruppe",
            title=f"{ili_term} nach Altersgruppen",
            labels={"index": ""},
        )
        ili_by_age_groups = plot_forecast(
            ili_by_age_groups, bundesweit_ili, "Altersgruppe"
        )
        ili_by_age_groups = add_quintile_bands(
            ili_by_age_groups,
            bundesweit_ili,
            percentage_infected_term,
            facet_col="Altersgruppe",
        )
        ili_by_age_groups.update_xaxes(type="date", range=[start_date, end_date])

        # Get traffic light status
        traffic_lights_ili = get_traffic_light_status(
            bundesweit_ili, percentage_infected_term, facet_col="Altersgruppe"
        )

    # Display regional traffic lights
    st.markdown("**Aktuelle Lage**")
    st.subheader(f"Region {region}")
    cols = st.columns(len(traffic_lights_region))
    for idx, (series_name, light) in enumerate(sorted(traffic_lights_region.items())):
        with cols[idx]:
            st.metric(label=series_name, value=light)

    st.plotly_chart(are_ili_by_region, width="stretch")

    # Display ARE age group traffic lights
    st.markdown("**Aktuelle Lage**")
    st.subheader(f"{are_term} nach Altersgruppen")
    cols = st.columns(len(traffic_lights_are))
    for idx, (series_name, light) in enumerate(sorted(traffic_lights_are.items())):
        with cols[idx]:
            st.metric(label=series_name, value=light)

    st.plotly_chart(are_by_age_groups, width="stretch")

    # Display ILI age group traffic lights
    st.markdown("**Aktuelle Lage**")
    st.subheader(f"{ili_term} nach Altersgruppen")
    cols = st.columns(len(traffic_lights_ili))
    for idx, (series_name, light) in enumerate(sorted(traffic_lights_ili.items())):
        with cols[idx]:
            st.metric(label=series_name, value=light)

    st.plotly_chart(ili_by_age_groups, width="stretch")
    st.caption(f"💡 Letzte Datenaktualisierung: {last_updated}")

text_footer = f"""
    <style>
        footer {{visibility: hidden;}}
    </style>
    <p style="font-size: 0.8em;display:block;text-align:center;">
        &copy;{2025} {"Ceyeborg GmbH"} ·
        <a href="https://ceyeb.org/privacy-policy/"
           style="text-decoration: none; color: #FFFFFF;">
        Privacy Policy
        </a> ·
        <a href="https://ceyeb.org/legal-notice/"
           style="text-decoration: none; color: #FFFFFF;">
        Legal Notice
        </a>
    </p>
    """
st.markdown(text_footer, unsafe_allow_html=True)
