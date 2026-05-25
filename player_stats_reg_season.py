# %%
import time

import requests
from bs4 import BeautifulSoup
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# %%
season = '2026'


# %%
# Get Player List
teams = ['ATL', 'BOS', 'BRK', 'CHI', 'CHO', 'CLE', 'DAL', 'DEN', 'DET', 'GSW', 'HOU', 'IND', 'LAC', 'LAL', 'MEM',
           'MIA', 'MIL', 'MIN', 'NOP', 'NYK', 'OKC', 'ORL', 'PHI', 'PHO', 'POR', 'SAC', 'SAS', 'TOR', 'UTA', 'WAS']


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
    url = f'https://www.basketball-reference.com/players/{player_id[0]}/{player_id}/gamelog/{year}/'
    response = requests.get(url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    stats_table = soup.find('table', {'id': 'player_game_log_reg'})

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
    game_logs_df['player_id'] = player_id
    
    return game_logs_df


# %%
def all_player_stats(players_dict: dict, 
                     year: str) -> pd.DataFrame:
    all_game_logs = []
    
    for team, roster in players_dict.items():
        print(f"Starting team: {team}")

        for player_name, player_id in roster.items():
            print(f"Scraping: {player_name}")
            try:
                player_df = stats_scrape(
                    player_id = player_id,
                    year = year
                )
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
roster = player_list(season)
print('Roster scraping complete.')


# %%
player_stats = all_player_stats(roster, season)
print('Player stats scraping complete.')

# %%
player_stats.to_csv(f'data/player_stats_{season}.csv', index=False)
player_stats_table = pa.Table.from_pandas(player_stats)
pq.write_table(player_stats_table, f'data/player_stats_{season}.parquet')


# %%
rows = []

for team, players in roster.items():
    for player_name, player_id in players.items():
        rows.append({
            "team": team,
            "player_name": player_name,
            "player_id": player_id
        })

roster_df = pd.DataFrame(rows)

# %%
roster_df.to_csv(f'data/player_roster_{season}.csv', index=False)
roster_table = pa.Table.from_pandas(roster_df)
pq.write_table(roster_table, f'data/player_roster_{season}.parquet')
# %%
