import itertools

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx
from streamlit.web.server.websocket_headers import _get_websocket_headers
from streamlit import runtime
from streamlit_geolocation import streamlit_geolocation

import plotly.express as px
import plotly.graph_objects as go
from statsmodels.tsa.seasonal import MSTL
from statsmodels.tsa.api import ExponentialSmoothing
import pandas as pd

import reverse_geocoder as rg
import geocoder
import geopy

are_term = 'Influenza, COVID-19 und RSV-Infektionen'
ili_term = 'Fieber mit Husten oder Halsschmerzen'
percentage_infected_term = 'Erkrankte Bevölkerung in %'
location = {}

st.set_page_config(
    page_title="VirusRadar",
    page_icon="🦠",
    layout="wide",
)

def get_forwarded_ip() -> str | None:
    """
    Get the IP address from the X-Forwarded-For header.
    This is useful when the app is behind a reverse proxy or load balancer.
    """
    headers = st.context.headers
    # Example: "X-Forwarded-For': '13.51.91.225, 162.158.90.188'"
    if 'X-Forwarded-For' in headers:
        x_forwarded_for = headers['X-Forwarded-For']
        first_ip = x_forwarded_for.split(', ')[0]

        return first_ip
    else:
        return None


# map admin2 to short name e.g. 'bavaria' to 'BY'
province2short = {
    'Baden-Württemberg': 'BW',
    'Bavaria': 'BY',
    'Berlin': 'BE',
    'Brandenburg': 'BB',
    'Bremen': 'HB',
    'Hamburg': 'HH',
    'Hessen': 'HE',
    'Mecklenburg-Vorpommern': 'MV',
    'Niedersachsen': 'NI',
    'Nordrhein-Westfalen': 'NW',
    'Rheinland-Pfalz': 'RP',
    'Saarland': 'SL',
    'Sachsen': 'SN',
    'Sachsen-Anhalt': 'ST',
    'Schleswig-Holstein': 'SH',
    'Thüringen': 'TH'
}

# check that all short provinces are in province2short
for province in ['BB', 'BE', 'BW', 'BY', 'HB', 'HE', 'HH', 'MV', 'NI', 'NW', 'RP', 'SH', 'SL', 'SN', 'ST', 'TH']:
    assert province in province2short.values()

# map admin2 to ['Mitte (West)', 'Norden (West)', 'Osten', 'Sueden']
province2region = {
    'BW': 'Sueden',
    'BY': 'Sueden',
    'BE': 'Mitte (West)',
    'BB': 'Osten',
    'HB': 'Norden (West)',
    'HH': 'Norden (West)',
    'HE': 'Mitte (West)',
    'MV': 'Osten',
    'NI': 'Norden (West)',
    'NW': 'Mitte (West)',
    'RP': 'Mitte (West)',
    'SL': 'Mitte (West)',
    'SN': 'Osten',
    'ST': 'Osten',
    'SH': 'Norden (West)',
    'TH': 'Osten'
}

# check that all short provinces are in province2region
for province in ['BB', 'BE', 'BW', 'BY', 'HB', 'HE', 'HH', 'MV', 'NI', 'NW', 'RP', 'SH', 'SL', 'SN', 'ST', 'TH']:
    assert province in province2region.keys(), f'{province} not in province2region'


# get ip address
ip_address = get_forwarded_ip()

if ip_address:
    geocoder_result = geocoder.ipinfo(ip_address)
    if geocoder_result.error is False:
        location['city'] = geocoder_result.current_result.city
        location['country'] = geocoder_result.current_result.country
        location['province'] = geocoder_result.current_result.province
        location['latitude'] = geocoder_result.current_result.lat
        location['longitude'] = geocoder_result.current_result.lng
    else:
        st.write("Error getting location from IP address, please allow location access in your browser.")
        location_result = streamlit_geolocation()
        location['latitude'] = location_result['latitude']
        location['longitude'] = location_result['longitude']

if 'latitude' in location and 'longitude' in location and not 'province' in location:
    # get the coordinates from the location
    coordinates = (location['latitude'], location['longitude'])
    geocode = rg.search(coordinates, mode=1)
    # transform administrative area to bundesland, bavaria to BY
    location['province'] = geocode[0]['admin1']

# now we should have the province
location['province_short'] = province2short[location['province']]
location['region'] = province2region[location['province_short']]


def add_forecasts(df: pd.DataFrame, columns_to_forecast: list, facet_col, prediction_horizon: int = 24, periods: int = 52):
    """
    For each column in columns_to_forecast, this function fits an Exponential Smoothing model,
    generates a forecast for prediction_horizon time steps, and adds the fitted values and forecast
    as a new column named '{original_column}_forecast' to the dataframe.
    """
    forecast_dfs = []
    # df = df.asfreq('W-FRI')

    for col in columns_to_forecast:
        # Filter the dataframe for the current illness
        for illness in df[facet_col].unique():
            df_illness = df[df[facet_col] == illness]

            # Fit the Exponential Smoothing model for the current column
            model = ExponentialSmoothing(
                df_illness[col],
                seasonal_periods=periods,
                trend="add",
                seasonal="add",
                use_boxcox=False,
                initialization_method="estimated"
            ).fit()

            # Generate forecast for the defined prediction horizon
            forecast = model.forecast(prediction_horizon)

            # Create a new DataFrame from the forecasted series and set facet_col to illness
            forecast_df = pd.DataFrame(forecast, columns=[col + '_forecast'])
            forecast_df[facet_col] = illness
            forecast_dfs.append(forecast_df)

    # Concatenate all forecast dataframes with the original dataframe
    df = pd.concat([df] + forecast_dfs, join='outer')
    return df


def plot_forecast(figure, dataframe, facet):
    """
    Adds forecast traces to the provided Plotly figure based on forecast columns in the dataframe.
    It groups the data by the given facet and looks for a column ending with '_forecast' to plot.
    """
    forecast_cols = [col for col in dataframe.columns if col.endswith('_forecast')]
    if not forecast_cols:
        return figure
    forecast_col = forecast_cols[0]

    colors = itertools.cycle(px.colors.qualitative.Plotly)

    for group in sorted(dataframe[facet].unique()):
        df_temp = dataframe[dataframe[facet] == group]
        color = next(colors)
        figure.add_trace(
            go.Scatter(
                x=df_temp.index,
                y=df_temp[forecast_col],
                mode='lines',
                line=dict(color=color, dash='dash'),
                name=f'{group} forecast'
            )
        )

    return figure


def decompose_and_plot(df: pd.DataFrame, illness: str, infected_column: str):
    """
    Decomposes the time series for the specified illness and plots the result.
    """
    series = df[df['Erkrankung'] == illness][infected_column]
    decomposed = MSTL(series).fit()
    fig = decomposed.plot()
    fig.suptitle(f'Decomposition {illness}')
    return fig


def find_closest_klaerwerk(df, coordinates):
    """
    Finds the closest wastewater treatment plant (Klärwerk) to the given coordinates.
    """
    # add latitude and longitude to the dataframe
    # apply geopy to get the coordinates of the location
    return 'München'
    # FIXME: this is not working
    # df['coordinates'] = df.apply(lambda x: service.geocode(x['standort'] + ', ' + x['bundesland']), axis=1)
    df['latitude'] = df['coordinates'].apply(lambda x: x.latitude)
    df['longitude'] = df['coordinates'].apply(lambda x: x.longitude)
    df['distance'] = ((df['latitude'] - coordinates[0]) ** 2 + (df['longitude'] - coordinates[1]) ** 2) ** 0.5
    closest_klaerwerk = df.loc[df['distance'].idxmin()]
    return closest_klaerwerk


st.title('Virus Radar')

st.expander('Informationen', expanded=True).markdown(
    """
 Virus Radar aggregiert, prädiziert und visualisiert Virusinfektionen in Deutschland.

 *Nutzer können:*

 Aktuelle Infektionszahlen für verschiedene Viren in ihrer Region einsehen.
 Trends analysieren und prognostische Modelle nutzen, um zukünftige Entwicklungen abzuschätzen.

 *Ziel:*

 Nutzer sollen fundierte Entscheidungen treffen können, ob sie ins Büro pendeln, Menschenmassen meiden oder ihre Kinder in den Kindergarten schicken.
 
 *Zielgruppen:*

 Allgemeinbevölkerung: Jeder, der sich über die aktuelle Gesundheitslage informieren möchte.
 Eltern und Familien: Entscheidungen über den Schul- und Kindergartenbesuch ihrer Kinder.
 Arbeitgeber und Unternehmen: Planung von Arbeitsabläufen und Home-Office-Regelungen.
 Gesundheitsbehörden und Entscheidungsträger: Unterstützung bei der Entwicklung und Implementierung von Gesundheitsstrategien.
 Bildungseinrichtungen: Information für die Organisation des Schulbetriebs.
    """
)

land_index = 0
region_index = 0
klaerwerk_index = 0

tab1, tab2,  = st.tabs(["Grippeweb", "Abwasser"])

with tab2:
    # Load the abwasser data
    abwasser = pd.read_csv('data/Abwassersurveillance_AMELAG/amelag_einzelstandorte.tsv', sep='\t')

    distinct_province_short = sorted(abwasser['bundesland'].dropna().unique())
    if 'province_short' in location:
        if location['province_short'] in distinct_province_short:
            land_index = distinct_province_short.index(location['province_short'])

    selected_bundesland = st.selectbox('Bundesland', distinct_province_short, index=land_index)

    closest_klaerwerk= find_closest_klaerwerk(abwasser, location)
    distinct_standorte = sorted(
        abwasser[abwasser['bundesland'] == selected_bundesland]['standort'].dropna().unique()
    )

    klaerwerk_index = distinct_standorte.index(closest_klaerwerk)

    standort = st.selectbox('Klärwerk', distinct_standorte, index=klaerwerk_index)

    abwasser = abwasser[abwasser['standort'] == standort]
    abwasser = abwasser[abwasser['typ'] != "Influenza A+B"]
    abwasser.set_index('datum', inplace=True)

    # forecast needs at least 2 yrs of data
    # abwasser = add_forecasts(abwasser, ['loess_vorhersage'], facet_col='typ', periods=365)

    fig_abwasser = px.area(abwasser, y='loess_vorhersage', color='typ', title=f'Geglättete Abwasserwerte {standort}', labels={'datum': '', 'loess_vorhersage': 'Loess geglättete Werte', 'typ': 'Virus'})
    # fig_abwasser = plot_forecast(fig_abwasser, abwasser, 'typ')

    st.plotly_chart(fig_abwasser, use_container_width=True)

with tab1:
    # Load the grippeweb data
    grippeweb = pd.read_csv('data/GrippeWeb_Daten_des_Wochenberichts/GrippeWeb_Daten_des_Wochenberichts.tsv', sep='\t')

    regions = sorted(grippeweb['Region'].unique())

    if 'region' in location:
        # if region is in the list of regions, set it as default
        if location['region'] in regions:
            region_index = regions.index(location['region'])
        else:
            region_index = 0
    region = st.selectbox('Region', regions, key='region', index=region_index)

    grippeweb[['Jahr', 'Woche']] = grippeweb['Kalenderwoche'].str.split('-W', expand=True)
    grippeweb['Datum'] = pd.to_datetime(grippeweb['Jahr'] + grippeweb['Woche'].add('-5'), format='%G%V-%u')
    grippeweb.set_index('Datum', inplace=True)

    grippeweb[percentage_infected_term] = (grippeweb['Inzidenz'] / 100000) * 100

    # By focus area
    grippeweb_region = grippeweb[grippeweb['Region'] == region]
    grippeweb_region['Erkrankung'] = grippeweb_region['Erkrankung'].replace({'ILI': ili_term, 'ARE': are_term})

    grippeweb_region = add_forecasts(grippeweb_region, [percentage_infected_term], facet_col='Erkrankung')
    fig_by_focus_area = px.area(grippeweb_region, y=percentage_infected_term, color='Erkrankung', title=f'Region {region}', labels={'index': ''})
    fig_by_focus_area = plot_forecast(fig_by_focus_area, grippeweb_region, 'Erkrankung')

    # Age groups only exist for bundesweite data
    bundesweit = grippeweb[grippeweb['Region'] == "Bundesweit"]

    altersgruppen = st.multiselect('Altersgruppen', ['0-4', '5-14', '15-34', '35-59', '60+'], default=['0-4', '5-14'])
    bundesweit = bundesweit[bundesweit['Altersgruppe'].isin(altersgruppen)]

    # Akute respiratorischer Erkrankungen (ARE)
    bundesweit_are = bundesweit[bundesweit['Erkrankung'] == "ARE"]
    bundesweit_are = add_forecasts(bundesweit_are, [percentage_infected_term], facet_col='Altersgruppe')
    are_by_age_groups = px.line(bundesweit_are, y=percentage_infected_term, color='Altersgruppe', title=f'{are_term} nach Altersgruppen', labels={'index': ''})
    are_by_age_groups = plot_forecast(are_by_age_groups, bundesweit_are, 'Altersgruppe')

    # Grippeähnliche Erkrankungen (ILI)
    bundesweit_ili = bundesweit[bundesweit['Erkrankung'] == "ILI"]
    bundesweit_ili = add_forecasts(bundesweit_ili, [percentage_infected_term], facet_col='Altersgruppe')
    ili_by_age_groups = px.line(bundesweit_ili, y=percentage_infected_term, color='Altersgruppe', title=f'{ili_term} nach Altersgruppen', labels={'index': ''})
    ili_by_age_groups = plot_forecast(ili_by_age_groups, bundesweit_ili, 'Altersgruppe')

    st.plotly_chart(fig_by_focus_area, use_container_width=True)
    st.plotly_chart(are_by_age_groups, use_container_width=True)
    st.plotly_chart(ili_by_age_groups, use_container_width=True)
