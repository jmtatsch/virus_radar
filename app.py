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

from geocode import Geocoder

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
    
    for col in columns_to_forecast:
        # Filter the dataframe for the current illness
        for illness in df[facet_col].unique():
            df_illness = df[df[facet_col] == illness]
            # set frequency to weekly Friday
            df_illness = df_illness.asfreq('W-FRI')

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
    Adds forecast traces to the provided Plotly figure.
    It looks for _forecast columns in the dataframe, groups the data by the given facet and adds the traces to the plot.
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
    # Add a vertical line for today
    today = pd.to_datetime('today')
    figure.add_vline(x=today, line_width=1, line_dash="dash", line_color="red")
    figure.add_annotation(
        x=today,
        y=figure.layout.yaxis.range[1] if figure.layout.yaxis.range else 15,
        text="Today",
        showarrow=False,
        xanchor="right",
        yanchor="top"
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


def find_closest_klaerwerk(df, user_location) -> str:
    """
    Finds the closest wastewater treatment plant (Klärwerk) to the given coordinates.
    """
    local_geocoder = Geocoder()
    # get distinct standort
    distinct_standorte = sorted(df['standort'].dropna().unique())
    import pandas as pd
    distinct_standorte = pd.DataFrame(distinct_standorte, columns=['standort'])
    distinct_standorte['coordinates'] = distinct_standorte.apply(lambda x: local_geocoder.geocode(city=x['standort'], country='DE'), axis=1)
    distinct_standorte['latitude'] = distinct_standorte['coordinates'].apply(lambda x: x[0])
    distinct_standorte['longitude'] = distinct_standorte['coordinates'].apply(lambda x: x[1])
    distinct_standorte['distance'] = ((distinct_standorte['latitude'] - user_location['latitude']) ** 2 + (distinct_standorte['longitude'] - user_location['longitude']) ** 2) ** 0.5
    closest_klaerwerk = distinct_standorte.loc[distinct_standorte['distance'].idxmin()]
    return closest_klaerwerk['standort']


st.title('Virus Radar 🦠')

st.expander('Über', expanded=False).markdown(
    """
 Virus Radar aggregiert, prädiziert und visualisiert Virusinfektionen in Deutschland.
 Nutzer können aktuelle Infektionszahlen für verschiedene Viren in ihrer Region einsehen und prädiktive Modelle nutzen, um zukünftige Entwicklungen abzuschätzen.
 Ziel ist es, dass Nutzer fundierte Entscheidungen treffen können, ob sie z.B. 
 * gefahrenlos ins Büro können oder besser im Homeoffice bleiben sollten
 * Menschenmassen besser meiden sollten
 * ihre Kinder in den Kindergarten schicken oder besser ein paar Tage zuhause lassen sollten
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

    closest_klaerwerk = find_closest_klaerwerk(abwasser, location)
    distinct_standorte = sorted(
        abwasser[abwasser['bundesland'] == selected_bundesland]['standort'].dropna().unique()
    )

    klaerwerk_index = distinct_standorte.index(closest_klaerwerk)

    standort = st.selectbox('Klärwerk', distinct_standorte, index=klaerwerk_index)

    abwasser = abwasser[abwasser['standort'] == standort]
    abwasser = abwasser[abwasser['typ'] != "Influenza A+B"]
    abwasser.set_index('datum', inplace=True)

    # forecast would need at least 2 yrs of data so not active for now
    # abwasser = add_forecasts(abwasser, ['loess_vorhersage'], facet_col='typ', periods=365)
    last_updated = pd.to_datetime(abwasser.index.max()).date()
    # start date is last update - 2 years
    start_date = last_updated - pd.DateOffset(years=1)

    fig_abwasser = px.area(abwasser, y='loess_vorhersage', color='typ', title=f'Geglättete Abwasserwerte {standort}', labels={'datum': '', 'loess_vorhersage': 'Loess geglättete Werte', 'typ': 'Virus'})
    # fig_abwasser = plot_forecast(fig_abwasser, abwasser, 'typ')
    fig_abwasser.update_xaxes(type="date", range=[start_date, last_updated])

    st.plotly_chart(fig_abwasser, use_container_width=True)
    st.write("Last data update: ", last_updated)


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
    grippeweb_region = grippeweb[grippeweb['Region'] == region].copy()
    grippeweb_region['Erkrankung'] = grippeweb_region['Erkrankung'].replace({'ILI': ili_term, 'ARE': are_term})
    last_updated = pd.to_datetime(grippeweb_region.index.max())
    start_date = last_updated - pd.DateOffset(years=2)

    grippeweb_region = add_forecasts(grippeweb_region, [percentage_infected_term], facet_col='Erkrankung')
    end_date = pd.to_datetime(grippeweb_region.index.max())
    are_ili_by_region = px.area(grippeweb_region, y=percentage_infected_term, color='Erkrankung', title=f'Region {region}', labels={'index': ''})
    are_ili_by_region = plot_forecast(are_ili_by_region, grippeweb_region, 'Erkrankung')
    are_ili_by_region.update_xaxes(type="date", range=[start_date, end_date])


    # Age groups only exist for bundesweite data
    bundesweit = grippeweb[grippeweb['Region'] == "Bundesweit"]

    altersgruppen = st.multiselect('Altersgruppen', ['0-4', '5-14', '15-34', '35-59', '60+'], default=['0-4', '5-14'])
    bundesweit = bundesweit[bundesweit['Altersgruppe'].isin(altersgruppen)]

    # Akute respiratorische Erkrankungen (ARE)
    bundesweit_are = bundesweit[bundesweit['Erkrankung'] == "ARE"]
    bundesweit_are = add_forecasts(bundesweit_are, [percentage_infected_term], facet_col='Altersgruppe')
    are_by_age_groups = px.line(bundesweit_are, y=percentage_infected_term, color='Altersgruppe', title=f'{are_term} nach Altersgruppen', labels={'index': ''})
    are_by_age_groups = plot_forecast(are_by_age_groups, bundesweit_are, 'Altersgruppe')
    are_by_age_groups.update_xaxes(type="date", range=[start_date, end_date])


    # Grippeähnliche Erkrankungen (ILI)
    bundesweit_ili = bundesweit[bundesweit['Erkrankung'] == "ILI"]
    bundesweit_ili = add_forecasts(bundesweit_ili, [percentage_infected_term], facet_col='Altersgruppe')
    ili_by_age_groups = px.line(bundesweit_ili, y=percentage_infected_term, color='Altersgruppe', title=f'{ili_term} nach Altersgruppen', labels={'index': ''})
    ili_by_age_groups = plot_forecast(ili_by_age_groups, bundesweit_ili, 'Altersgruppe')
    ili_by_age_groups.update_xaxes(type="date", range=[start_date, end_date])


    st.plotly_chart(are_ili_by_region, use_container_width=True)
    st.plotly_chart(are_by_age_groups, use_container_width=True)
    st.plotly_chart(ili_by_age_groups, use_container_width=True)
    st.write("Last data update: ", last_updated)
