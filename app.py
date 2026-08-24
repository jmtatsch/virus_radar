import logging
import warnings
from typing import List, Optional

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from statsmodels.tsa.seasonal import MSTL
from statsmodels.tsa.api import ExponentialSmoothing
from statsmodels.tools.sm_exceptions import ConvergenceWarning
import pandas as pd
from plotly.graph_objs import Figure
from geopy.distance import geodesic

from geocode import Geocoder
from location_manager import LocationManager, find_province_index

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

# the weekly grid every forecast is computed on
forecast_freq = "W-FRI"
# a series that would have to be interpolated more than this is not worth fitting
max_interpolated_fraction = 0.25


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

            # Find the value with date closest to today, taking it from the
            # forecast where no observation is available
            observed = series_data[y_column]
            combined = observed
            if has_forecast and forecast_col in series_data.columns:
                combined = observed.combine_first(series_data[forecast_col])

            available = combined.notna()
            all_data_clean = combined[available]
            # positionally aligned with all_data_clean: True where the value that
            # survived came from the forecast rather than from an observation
            from_forecast = observed[available].isna()
            if len(all_data_clean) == 0:
                continue
            
            # Find index closest to today
            time_diff = abs(all_data_clean.index - today)
            closest_idx = time_diff.argmin()
            current_date = all_data_clean.index[closest_idx]
            current_value = all_data_clean.iloc[closest_idx]
            
            # Calculate trend based on last week
            one_week_ago = current_date - pd.Timedelta(days=7)
            time_diff_week = abs(all_data_clean.index - one_week_ago)
            week_ago_idx = time_diff_week.argmin()
            week_ago_value = all_data_clean.iloc[week_ago_idx]
            
            # Determine trend symbol (using 5% threshold to avoid noise)
            percent_change = ((current_value - week_ago_value) / week_ago_value * 100) if week_ago_value != 0 else 0
            if percent_change > 5:
                trend = "↑"
            elif percent_change < -5:
                trend = "↓"
            else:
                trend = "→"

            # Calculate quintile boundaries from historical data only
            q40 = values.quantile(0.4)
            q60 = values.quantile(0.6)
            
            # Calculate percentile rank of current value
            percentile_rank = (values < current_value).sum() / len(values) * 100
            # Express as "top X%" or "bottom X%" for better intuition
            top_percent = 100 - percentile_rank
            if percentile_rank >= 50:
                rank_description = f"top {top_percent:.1f}%"
            else:
                rank_description = f"bottom {percentile_rank:.1f}%"
            
            # Log traffic light information
            logger.info(
                f"Traffic light for {series_name}: value={current_value:.4f}, "
                f"date={current_date}, rank={rank_description}"
            )

            # Determine color
            if current_value >= q60:
                color = "🔴"  # Red: upper two quintiles
            elif current_value >= q40:
                color = "🟡"  # Yellow: middle quintile
            else:
                color = "🟢"  # Green: lower two quintiles
            
            status[series_name] = {
                "color": color,
                "value": current_value,
                "date": current_date,
                "rank": rank_description,
                "trend": trend,
                "is_forecast": bool(from_forecast.iloc[closest_idx]),
            }
    else:
        # Calculate for entire dataset
        values = dataframe[y_column].dropna()

        if len(values) > 0:
            # Find the value with date closest to today, taking it from the
            # forecast where no observation is available
            observed = dataframe[y_column]
            combined = observed
            if has_forecast and forecast_col in dataframe.columns:
                combined = observed.combine_first(dataframe[forecast_col])

            available = combined.notna()
            all_data_clean = combined[available]
            # positionally aligned with all_data_clean: True where the value that
            # survived came from the forecast rather than from an observation
            from_forecast = observed[available].isna()
            if len(all_data_clean) == 0:
                return status
            
            # Find index closest to today
            time_diff = abs(all_data_clean.index - today)
            closest_idx = time_diff.argmin()
            current_date = all_data_clean.index[closest_idx]
            current_value = all_data_clean.iloc[closest_idx]
            
            # Calculate trend based on last week
            one_week_ago = current_date - pd.Timedelta(days=7)
            time_diff_week = abs(all_data_clean.index - one_week_ago)
            week_ago_idx = time_diff_week.argmin()
            week_ago_value = all_data_clean.iloc[week_ago_idx]
            
            # Determine trend symbol (using 5% threshold to avoid noise)
            percent_change = ((current_value - week_ago_value) / week_ago_value * 100) if week_ago_value != 0 else 0
            if percent_change > 5:
                trend = "↑"
            elif percent_change < -5:
                trend = "↓"
            else:
                trend = "→"

            q40 = values.quantile(0.4)
            q60 = values.quantile(0.6)
            
            # Calculate percentile rank of current value
            percentile_rank = (values < current_value).sum() / len(values) * 100
            # Express as "top X%" or "bottom X%" for better intuition
            top_percent = 100 - percentile_rank
            if percentile_rank >= 50:
                rank_description = f"top {top_percent:.1f}%"
            else:
                rank_description = f"bottom {percentile_rank:.1f}%"
            
            # Log traffic light information
            logger.info(
                f"Traffic light for overall: value={current_value:.4f}, "
                f"date={current_date}, rank={rank_description}"
            )

            if current_value >= q60:
                color = "🔴"
            elif current_value >= q40:
                color = "🟡"
            else:
                color = "🟢"
            
            status["overall"] = {
                "color": color,
                "value": current_value,
                "date": current_date,
                "rank": rank_description,
                "trend": trend,
                "is_forecast": bool(from_forecast.iloc[closest_idx]),
            }

    return status


def series_without_forecast(
    dataframe: pd.DataFrame, y_column: str, facet_col: str
) -> List[str]:
    """
    Names of the series that ended up without a forecast, e.g. because their
    history is shorter than the two seasonal cycles the model needs.
    """
    if facet_col not in dataframe.columns:
        return []
    forecast_col = y_column + "_forecast"
    if forecast_col not in dataframe.columns:
        return sorted(str(name) for name in dataframe[facet_col].dropna().unique())
    return sorted(
        str(name)
        for name, group in dataframe.groupby(facet_col)
        if not group[forecast_col].notna().any()
    )


def render_traffic_lights(
    status: dict,
    subheader: Optional[str] = None,
    without_forecast: Optional[List[str]] = None,
) -> None:
    """
    Render the traffic light metrics belonging to one chart.

    Args:
        status: Mapping of series name to the info dict from get_traffic_light_status
        subheader: Optional heading naming the chart the metrics belong to
        without_forecast: Series that have no forecast, named in a notice
    """
    st.markdown("**Aktuelle Lage**")
    if subheader:
        st.subheader(subheader)
    if without_forecast:
        st.info(
            "Zu wenige Daten für eine Prognose: " + ", ".join(without_forecast)
        )
    if not status:
        # st.columns() rejects a column count of zero, which is what an empty
        # selection (e.g. no age group picked) would produce
        st.info("Keine Daten für die aktuelle Auswahl.")
        return
    today = pd.Timestamp.today().normalize()
    cols = st.columns(len(status))
    for idx, (series_name, info) in enumerate(sorted(status.items())):
        with cols[idx]:
            st.metric(label=series_name, value=f"{info['color']} {info['trend']}")
            st.caption(f"Wert: {info['value']:.2f}")
            # say where the number comes from: otherwise one row of "Aktuelle Lage"
            # silently mixes next week's forecast with an observation from two
            # months ago
            date_caption = f"Datum: {info['date'].strftime('%Y-%m-%d')}"
            age_days = (today - pd.Timestamp(info["date"])).days
            if info.get("is_forecast"):
                date_caption += " (Prognose)"
            elif age_days > 14:
                date_caption += f" (vor {age_days} Tagen)"
            st.caption(date_caption)
            st.caption(f"Rang: {info['rank']}")


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


def prepare_weekly_series(
    values: pd.Series, label: str, periods: int
) -> Optional[pd.Series]:
    """
    Put one series onto the gap-free weekly grid a seasonal model can be fitted to.

    Returns None when the series is not suitable for a forecast, having logged why.

    Args:
        values: The observations, indexed by date
        label: Name of the series, for the log messages
        periods: Length of one seasonal cycle in weeks
    """
    # Use last() instead of mean() to preserve the most recent value in each week
    weekly = values.resample(forecast_freq).last()

    first_observed = weekly.first_valid_index()
    last_observed = weekly.last_valid_index()
    if first_observed is None:
        logger.warning("Skipping forecast for %s - no usable data", label)
        return None

    # Trim to the observed span first. Filling forward past the last real
    # observation would append up to 12 flat invented weeks and push the start of
    # the forecast that far beyond the data - one site's forecast began 37 days
    # after its last measurement.
    weekly = weekly.loc[first_observed:last_observed]

    # Forward fill gaps - be more lenient (up to 12 weeks for sparse data)
    weekly = weekly.ffill(limit=12)

    # Backward fill any leading NaNs
    weekly = weekly.bfill(limit=2)

    # ExponentialSmoothing estimates the initial seasonals from two full cycles and
    # raises below that, so anything shorter is skipped here instead of attempted.
    min_weeks_required = periods * 2
    if len(weekly) < min_weeks_required:
        logger.warning(
            "Skipping forecast for %s - %d weeks of data, need %d",
            label,
            len(weekly),
            min_weeks_required,
        )
        return None

    interpolated = int(weekly.isna().sum())
    if interpolated / len(weekly) > max_interpolated_fraction:
        logger.warning(
            "Skipping forecast for %s - %d of %d weeks would have to be interpolated",
            label,
            interpolated,
            len(weekly),
        )
        return None
    if interpolated:
        logger.info("Interpolating %d gap week(s) for %s", interpolated, label)
        weekly = weekly.interpolate()

    return weekly


def add_forecasts(
    df: pd.DataFrame,
    columns_to_forecast: List[str],
    facet_col: str,
    prediction_horizon: int = 12,
    periods: int = 52,
    non_negative: bool = True,
) -> pd.DataFrame:
    """
    For each column in columns_to_forecast, this function fits an Exponential Smoothing model,
    generates a forecast for prediction_horizon time steps, and adds the fitted values and forecast
    as a new column named '{original_column}_forecast' to the dataframe.

    non_negative floors the forecast at zero. Every quantity these data sets
    measure - viral load, share of the population, consultation incidence - is
    non-negative and never observed below zero, while an additive trend
    extrapolates to any value at all: without the floor a third of the wastewater
    series forecast a negative viral load.
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

            weekly = prepare_weekly_series(df_illness[col], str(illness), periods)
            if weekly is None:
                continue

            try:
                # Fit the Exponential Smoothing model for the current column
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    model = ExponentialSmoothing(
                        weekly,
                        seasonal_periods=periods,
                        trend="add",
                        seasonal="add",
                        use_boxcox=False,
                        initialization_method="estimated",
                    ).fit()

                # statsmodels reports a failed optimisation anonymously, which makes
                # it impossible to tell which series the forecast belongs to
                if any(
                    issubclass(entry.category, ConvergenceWarning) for entry in caught
                ):
                    logger.warning(
                        "Fit for %s did not converge, its forecast is less reliable",
                        illness,
                    )

                # Generate forecast for the defined prediction horizon
                forecast = model.forecast(prediction_horizon)
            except Exception as e:
                logger.warning("Failed to create forecast for %s: %s", illness, str(e))
                continue

            if non_negative and (forecast < 0).any():
                logger.warning(
                    "Forecast for %s reached %.1f, flooring it at zero",
                    illness,
                    forecast.min(),
                )
                forecast = forecast.clip(lower=0)

            # Derive the forecast dates from the last observed week rather than
            # trusting the index statsmodels hands back: it falls back to a
            # RangeIndex whenever the input index carries no frequency, and those
            # integers turn into 1970 timestamps when coerced to datetimes.
            forecast_index = pd.date_range(
                start=weekly.index[-1],
                periods=prediction_horizon + 1,
                freq=forecast_freq,
            )[1:]
            forecast_df = pd.DataFrame(
                {col + "_forecast": forecast.to_numpy()}, index=forecast_index
            )
            forecast_df.loc[:, facet_col] = illness
            forecast_dfs.append(forecast_df)
            logger.info("Successfully created forecast for %s", illness)

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


def find_closest_klaerwerk(df: pd.DataFrame, user_location: dict) -> Optional[str]:
    """
    Finds the closest wastewater treatment plant (Klärwerk) to the given coordinates.

    Returns None when not a single Standort could be geocoded, so that the caller
    falls back to its own default instead of pointing at an arbitrary plant.
    """
    logger.info("Finding closest Klärwerk to location: %s", user_location)
    local_geocoder = Geocoder()
    # get distinct standorte
    distinct_standorte = pd.DataFrame(
        sorted(df["standort"].dropna().unique()), columns=["standort"]
    )
    # add coordinates for each standort
    coordinates = distinct_standorte["standort"].apply(
        lambda x: local_geocoder.geocode(city=x, country="DE")
    )
    distinct_standorte["latitude"] = coordinates.apply(lambda x: x[0])
    distinct_standorte["longitude"] = coordinates.apply(lambda x: x[1])

    # drop what could not be geocoded rather than placing it at (0, 0), where it
    # would silently compete for 'closest' with the plants we do have a position for
    located = distinct_standorte.dropna(subset=["latitude", "longitude"])
    unresolved = len(distinct_standorte) - len(located)
    if unresolved:
        logger.warning(
            "Could not geocode %d of %d Standorte",
            unresolved,
            len(distinct_standorte),
        )
    if located.empty:
        logger.error("No Standort could be geocoded, cannot find closest Klärwerk")
        return None

    # geodesic distance instead of euclidean degrees: at German latitudes a degree
    # of longitude covers only ~0.63 of a degree of latitude, so treating the two
    # alike overstates east-west distances by roughly 60 % and can pick the wrong plant
    user_coordinates = (user_location["latitude"], user_location["longitude"])
    distances = located.apply(
        lambda row: geodesic(user_coordinates, (row["latitude"], row["longitude"])).km,
        axis=1,
    )
    closest_klaerwerk = located.loc[distances.idxmin()]
    logger.info(
        "Closest Klärwerk is %s at %.1f km",
        closest_klaerwerk["standort"],
        distances.min(),
    )
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
    tab3,
) = st.tabs(["Grippeweb", "Abwasser", "ARE-Konsultationsinzidenz"])

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
            # Check if closest_klaerwerk is in the filtered list for the selected Bundesland
            if closest_klaerwerk in distinct_standorte:
                klaerwerk_index = distinct_standorte.index(closest_klaerwerk)
            else:
                klaerwerk_index = 0
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
        # AMELAG data: weekly data points with 7-day publication delay
        # Data is usually expected at 15:00 GMT+1
        # Next data point (7 days) + publication delay (7 days) = 14 days total
        next_update_expected = pd.to_datetime(last_updated) + pd.Timedelta(days=14)
        next_update_time = "ca. 15:00 Uhr"

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
    render_traffic_lights(
        traffic_lights,
        without_forecast=series_without_forecast(abwasser, "vorhersage", "typ"),
    )

    st.plotly_chart(fig_abwasser, width="stretch")
    
    # Display update information
    days_since_update_abwasser = (pd.Timestamp.today().normalize() - pd.to_datetime(last_updated)).days
    st.caption(
        f"💡 Datenstand bis **{last_updated}** "
        f"(vor {days_since_update_abwasser} Tag{'en' if days_since_update_abwasser != 1 else ''}) · "
        f"Nächste Aktualisierung erwartet am **{next_update_expected.date()} {next_update_time}** · "
        f"Aktualisierungsrhythmus: wöchentlich"
    )


with tab1:
    # Load the grippeweb data
    with st.spinner("Lade GrippeWeb-Daten..."):
        logger.info("Loading GrippeWeb data")
        grippeweb = pd.read_csv(
            "data/GrippeWeb_Daten_des_Wochenberichts/GrippeWeb_Daten_des_Wochenberichts.tsv",
            sep="\t",
        )

        regions = sorted(grippeweb["Region"].unique())

    # default to the nationwide view when the visitor's region is unknown, rather
    # than to whichever region happens to sit at a hardcoded index
    default_region = "Bundesweit"
    region_index = regions.index(default_region) if default_region in regions else 0
    if location_manager.location["region"] in regions:
        region_index = regions.index(location_manager.location["region"])
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

    # Create date from Jahr and Woche - use Sunday (day 7) as the end of the week
    date_str = grippeweb["Jahr"].astype(str) + grippeweb["Woche"].astype(str) + "-7"
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
        # GrippeWeb data: week ends on Sunday, published ~4 days later (Thursday)
        # Data is usually expected at 10:00 GMT+1
        # Next week + 4 days publication delay = 11 days total
        next_update_expected = last_updated + pd.Timedelta(days=11)
        next_update_time = "ca. 10:00 Uhr"

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
    render_traffic_lights(
        traffic_lights_region,
        f"Region {region}",
        without_forecast=series_without_forecast(
            grippeweb_region, percentage_infected_term, "Erkrankung"
        ),
    )

    st.plotly_chart(are_ili_by_region, width="stretch")

    # Display ARE age group traffic lights
    render_traffic_lights(
        traffic_lights_are,
        f"{are_term} nach Altersgruppen",
        without_forecast=series_without_forecast(
            bundesweit_are, percentage_infected_term, "Altersgruppe"
        ),
    )

    st.plotly_chart(are_by_age_groups, width="stretch")

    # Display ILI age group traffic lights
    render_traffic_lights(
        traffic_lights_ili,
        f"{ili_term} nach Altersgruppen",
        without_forecast=series_without_forecast(
            bundesweit_ili, percentage_infected_term, "Altersgruppe"
        ),
    )

    st.plotly_chart(ili_by_age_groups, width="stretch")
    
    # Display update information
    days_since_update_grippeweb = (pd.Timestamp.today().normalize() - last_updated).days
    st.caption(
        f"💡 Datenstand bis **{last_updated.date()}** "
        f"(vor {days_since_update_grippeweb} Tag{'en' if days_since_update_grippeweb != 1 else ''}) · "
        f"Nächste Aktualisierung erwartet am **{next_update_expected.date()} {next_update_time}** · "
        f"Aktualisierungsrhythmus: wöchentlich (donnerstags)"
    )

with tab3:
    # Load the ARE-Konsultationsinzidenz data
    with st.spinner("Lade ARE-Konsultationsinzidenz-Daten..."):
        logger.info("Loading ARE-Konsultationsinzidenz data")
        are_data = pd.read_csv(
            "data/ARE-Konsultationsinzidenz/ARE-Konsultationsinzidenz.tsv",
            sep="\t",
        )

        bundeslaender = sorted(are_data["Bundesland"].unique())

    # Set default Bundesland: the visitor's own if we know it, else the nationwide
    # view. find_province_index matches through the Bundesland short code, so an
    # English province name from reverse_geocoder still finds the German name used
    # in this data set, and it returns None instead of 0 when nothing matches - so
    # a genuine match on the first entry is no longer mistaken for a failed lookup.
    bundesland_index = find_province_index(
        bundeslaender, location_manager.location.get("province")
    )
    if bundesland_index is None:
        bundesland_index = (
            bundeslaender.index("Bundesweit") if "Bundesweit" in bundeslaender else 0
        )

    selected_bundesland_are = st.selectbox(
        "Bundesland",
        bundeslaender,
        key="bundesland_are",
        index=bundesland_index,
        help="Wählen Sie ein Bundesland aus, um ARE-Konsultationsinzidenzen zu sehen",
    )

    # Parse calendar week data
    split_data = are_data["Kalenderwoche"].str.split("-W", expand=True)
    are_data = are_data.assign(Jahr=split_data[0], Woche=split_data[1])

    # Create date from Jahr and Woche - use Sunday (day 7) as the end of the week
    date_str = are_data["Jahr"].astype(str) + are_data["Woche"].astype(str) + "-7"
    are_data = are_data.assign(Datum=pd.to_datetime(date_str, format="%G%V-%u"))
    are_data.set_index("Datum", inplace=True)

    # Filter by selected Bundesland
    bundesland_data = are_data[are_data["Bundesland"] == selected_bundesland_are].copy()

    # Get last updated date
    last_updated_are = pd.to_datetime(bundesland_data.index.max())
    start_date_are = last_updated_are - pd.DateOffset(years=2)
    # ARE data: weekly data, publication delay similar to GrippeWeb
    next_update_expected_are = last_updated_are + pd.Timedelta(days=11)
    next_update_time_are = "ca. 10:00 Uhr"

    # Age group selection
    available_age_groups = sorted(bundesland_data["Altersgruppe"].unique())
    selected_age_groups = st.multiselect(
        "Altersgruppen",
        available_age_groups,
        default=available_age_groups[:2] if len(available_age_groups) >= 2 else available_age_groups,
        help="Wählen Sie Altersgruppen aus, um die ARE-Konsultationsinzidenzen für verschiedene Altersgruppen zu vergleichen",
    )

    if selected_age_groups:
        bundesland_data = bundesland_data[bundesland_data["Altersgruppe"].isin(selected_age_groups)]

        with st.spinner("Berechne Prognosen für ARE-Konsultationsinzidenz..."):
            # Add forecasts for the ARE consultation incidence
            bundesland_data = add_forecasts(
                bundesland_data, ["ARE_Konsultationsinzidenz"], facet_col="Altersgruppe"
            )
            end_date_are = pd.to_datetime(bundesland_data.index.max())
            
            # Create the line plot
            are_consultation_fig = px.line(
                bundesland_data,
                y="ARE_Konsultationsinzidenz",
                color="Altersgruppe",
                title=f"ARE-Konsultationsinzidenz nach Altersgruppen - {selected_bundesland_are}",
                labels={"index": "", "ARE_Konsultationsinzidenz": "Konsultationsinzidenz (pro 100.000)"},
            )
            are_consultation_fig = plot_forecast(
                are_consultation_fig, bundesland_data, "Altersgruppe"
            )
            are_consultation_fig = add_quintile_bands(
                are_consultation_fig,
                bundesland_data,
                "ARE_Konsultationsinzidenz",
                facet_col="Altersgruppe",
            )
            are_consultation_fig.update_xaxes(type="date", range=[start_date_are, end_date_are])

            # Get traffic light status
            traffic_lights_are_consultation = get_traffic_light_status(
                bundesland_data, "ARE_Konsultationsinzidenz", facet_col="Altersgruppe"
            )

        # Display traffic lights
        render_traffic_lights(
            traffic_lights_are_consultation,
            f"ARE-Konsultationsinzidenz - {selected_bundesland_are}",
            without_forecast=series_without_forecast(
                bundesland_data, "ARE_Konsultationsinzidenz", "Altersgruppe"
            ),
        )

        st.plotly_chart(are_consultation_fig, width="stretch")
        
        # Display update information
        days_since_update_are = (pd.Timestamp.today().normalize() - last_updated_are).days
        st.caption(
            f"💡 Datenstand bis **{last_updated_are.date()}** "
            f"(vor {days_since_update_are} Tag{'en' if days_since_update_are != 1 else ''}) · "
            f"Nächste Aktualisierung erwartet am **{next_update_expected_are.date()} {next_update_time_are}** · "
            f"Aktualisierungsrhythmus: wöchentlich"
        )
    else:
        st.warning("Bitte wählen Sie mindestens eine Altersgruppe aus.")

text_footer = f"""
    <style>
        footer {{visibility: hidden;}}
    </style>
    <p style="font-size: 0.8em;display:block;text-align:center;">
        Datenquelle: <a href="https://github.com/robert-koch-institut/GrippeWeb_Daten_des_Wochenberichts"
           style="text-decoration: none; color: #FFFFFF;">Robert Koch-Institut</a><br>
        &copy;{2026} {"Ceyeborg GmbH"} ·
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
