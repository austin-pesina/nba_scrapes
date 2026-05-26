# %%
import time
import datetime
import os

import requests
from bs4 import BeautifulSoup
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas
from dotenv import load_dotenv


# %%
load_dotenv()
season = '2026'

# %%
def playoff_teams(year: str) -> list:
    url = f'https://www.basketball-reference.com/playoffs/NBA_{year}.html'
    response = requests.get(url)
    print(response.status_code)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    teams = set()
    table = soup.find('table', {'id': 'per_game-team'})

    teams = set()
    if table:
        for row in table.tbody.find_all('tr'):
            team_cell = row.find('td', {'data-stat': 'team'})
            if team_cell:
                team_link = team_cell.find('a')
                if team_link:
                    team_name = team_link.get_text(strip=True)
                    team_abbr = team_link['href'].split('/')[2]
                    teams.add(team_abbr)

    return list(teams)

# %%
teams = playoff_teams(season)
teams = teams.sort()

# %%
def player_list(year: str) -> dict:

    players = {}

    for team in teams:
        players[team] = {}
        url = f'https://www.basketball-reference.com/teams/{team}/{year}.html'
        print(url)
        response = requests.get(url)
        print(response.status_code)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'id': 'roster'})

        if table is None:
            print(f'No roster table found for team: {team}')
            continue

        for row in table.tbody.find_all('tr'):
            player_cell = row.find('td', {'data-stat': 'player'})
            if player_cell:
                player_link = player_cell.find('a')
                if player_link:
                    player_name = player_link.get_text(strip=True)
                    player_href = player_link['href']
                    player_id = player_href.split('/')[-1].replace('.html', '')
                    players[team][player_name] = player_id
        print(f'Finished team: {team}')
        time.sleep(1)

    return players


# %%
def stats_scrape(player_id: str, 
                 year: str) -> pd.DataFrame:
    url = f'https://www.basketball-reference.com/players/{player_id[0]}/{player_id}/gamelog/{year}/#all_player_game_log_post'
    response = requests.get(url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    stats_table = soup.find('table', {'id': 'player_game_log_post'})

    if stats_table is None:
        print(f'No stats table found for player: {player_id}')
        return pd.DataFrame()  

    game_logs = []

    for row in stats_table.tbody.find_all('tr'):
        # Skip repeated header rows
        if 'thead' in row.get('class', []):
            continue
        game = {}
        for cell in row.find_all(['th', 'td']):
            stat_name = cell.get('data-stat')
            stat_value = cell.get_text(strip=True)
            if stat_name:
                game[stat_name] = stat_value
        if game:
            game_logs.append(game)

    game_logs_df = pd.DataFrame(game_logs)
    
    if game_logs_df.empty or "mp" not in game_logs_df.columns:
        return pd.DataFrame()

    game_logs_df = game_logs_df[game_logs_df["mp"].notna()]
    game_logs_df = game_logs_df[game_logs_df["ranker"] != '']
    game_logs_df['player_id'] = player_id
    
    return game_logs_df


# %%
def all_player_stats(players_dict: dict, 
                     year: str) -> pd.DataFrame:
    all_game_logs = []
    
    for team, roster in players_dict.items():
        print(f"\n Starting team: {team} \n")

        for player_name, player_id in roster.items():
            # print(f"Scraping: {player_name}")
            try:
                player_df = stats_scrape(
                    player_id = player_id,
                    year = year
                )
                print(f"Finished scraping: {player_name}")
                time.sleep(8)
                if not player_df.empty:
                    player_df["player_name"] = player_name
                    all_game_logs.append(player_df)
                    time.sleep(5)

            except Exception as e:
                print(f"Error scraping {player_name}: {e}")

    if not all_game_logs:
        print("No game logs were scraped.")
        return pd.DataFrame()

    final_df = pd.concat(all_game_logs, ignore_index=True)

    return final_df


# %%
def sf_connect():
    cnx = snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
        database=os.getenv('SNOWFLAKE_DATABASE'),
        schema=os.getenv('SNOWFLAKE_SCHEMA'),
        role=os.getenv('SNOWFLAKE_ROLE')
    )
    return cnx

# %%
roster = player_list(season)
print('Roster scraping complete.')


# %%
player_stats = all_player_stats(roster, season)
player_stats['last_updated'] = datetime.datetime.now().isoformat()
print('Player stats scraping complete.')


# %%
with sf_connect() as conn:
    write_pandas(
        conn=conn,
        df=player_stats,
        table_name='PLAYER_STATS_PLAYOFFS',
        schema='RAW',
        database='NBA',
        auto_create_table=False,
        quote_identifiers=False
    )



# %%
player_stats.to_csv(f'data/player_stats_{season}_playoffs.csv', index=False)
player_stats_table = pa.Table.from_pandas(player_stats)
pq.write_table(player_stats_table, f'data/player_stats_{season}_playoffs.parquet')

# %%

