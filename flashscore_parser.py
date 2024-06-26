import asyncio
import json
import logging
import os
import re
from typing import Any

import bs4
import click
import httpx
import pandas as pd
from pandas.core.tools.datetimes import DateParseError
import pycountry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%H:%M:%S",
    filename="./data/logs/flashscore_parser.log",
    filemode='a',
)

PLAYERS_PER_TEAM = 11
LINEUPS_SUFFIX = "?t=lineups"
STATISTICS_SUFFIX = "?t=match-statistics"
TEAM_PATTERN = re.compile(r"\[(\w+)\]")
ASSISTANT_PATTERN = re.compile(r"\(([\w\.\s]+)\)")

########### FlashScore HTML parse functions ###################################


def parse_teams(soup: bs4.BeautifulSoup) -> tuple[str, str]:
    teams = [t.strip().lower() for t in soup.find("h3").text.split('-')]
    assert len(teams) == 2
    return teams[0], teams[1]


def parse_summary(teams: tuple[str, str], summary: bs4.BeautifulSoup) -> tuple[dict[str, Any], dict[str, Any]]:
    teams_codes = (
        pycountry.countries.get(name=teams[0]),
        pycountry.countries.get(name=teams[1]),
        # pycountry.countries.search_fuzzy(teams[0])[0].alpha_3.lower(),
        # pycountry.countries.search_fuzzy(teams[1])[0].alpha_3.lower(),
    )
    teams_codes = tuple(c.alpha_3.lower() if c else None for c in teams_codes)
    first_team = {
        'goals': [],
        'substitutions': [],
        'yellow_cards': [],
        'red_cards': [],
    }
    second_team = {
        'goals': [],
        'substitutions': [],
        'yellow_cards': [],
        'red_cards': [],
    }

    for incident in summary.find_all(class_="incident soccer"):
        time = incident.find(class_="time")
        if time is None:
            # Parse extra time
            time = incident.find(class_="time-wide").text.removesuffix("'").split('+')
            assert len(time) == 2
            time = int(time[0]) + int(time[1])
        else:
            time = int(time.text.removesuffix("'"))
        text = incident.find_all(string=True, recursive=False)[-1]
        team = TEAM_PATTERN.findall(text)
        assert team
        team = team[0].strip().lower()
        if teams[0].startswith(team) or teams_codes[0] == team:
            current_team = first_team
        elif teams[1].startswith(team) or teams_codes[1] == team:
            current_team = second_team
        else:
            raise RuntimeError(f"Team {team!r} not foung among {teams!r} nor {teams_codes!r}")

        if incident.find(class_="i-field icon ball"):
            scorer = ASSISTANT_PATTERN.sub('', TEAM_PATTERN.sub('', text)).strip().lower()
            if assistant := ASSISTANT_PATTERN.findall(text):
                assistant = assistant[0].strip().lower()
            else:
                assistant = None
            current_team['goals'].append((time, scorer, assistant))
        elif incident.find(class_="i-field icon substitution"):
            sub_in = incident.find_all(string=True, recursive=False)[0].strip().lower()
            sub_out = incident.find(class_="substitution-out").text.removeprefix('(').removesuffix(')').strip().lower()
            current_team['substitutions'].append((time, sub_in, sub_out))
        elif incident.find(class_="i-field icon y-card"):
            player = TEAM_PATTERN.sub('', text).strip().lower()
            current_team['yellow_cards'].append((time, player))
        elif incident.find(class_="i-field icon r-card"):
            player = TEAM_PATTERN.sub('', text).strip().lower()
            current_team['red_cards'].append((time, player))

    return first_team, second_team


def parse_lineup_table(table: bs4.BeautifulSoup) -> list[str]:
    players = table.find_all("td", class_=None)
    return [p.text.lower().removesuffix('(g)').strip() for p in players]


def parse_statistics_row(row: bs4.BeautifulSoup) -> tuple[str, tuple[float, float]]:
    values = [col.text for col in row.find_next().children]
    assert len(values) == 3
    first_value = float(values[0].removesuffix('%'))
    name = values[1].lower().removesuffix('(xg)').strip().replace(' ', '_')
    second_value = float(values[2].removesuffix('%'))
    return name, (first_value, second_value)


########### Async fetch functions #############################################


async def fetch_summary(match_url: str) -> dict:
    if not match_url.endswith('/'):
        match_url += '/'

    async with httpx.AsyncClient() as client:
        res = await client.get(match_url)
    soup = bs4.BeautifulSoup(res.text, "html.parser")

    teams = parse_teams(soup)
    details = soup.find_all(class_="detail")
    try:
        datetime = pd.to_datetime(details[2].text, dayfirst=True)
    except DateParseError:
        # Additional info in details, parse next entry
        datetime = pd.to_datetime(details[3].text, dayfirst=True)
    first_team, second_team = parse_summary(teams, soup)
    return {
        'teams': list(teams),
        'datetime': datetime.isoformat(),
        teams[0]: first_team,
        teams[1]: second_team,
    }


async def fetch_lineups(match_url: str) -> pd.DataFrame:
    if not match_url.endswith(LINEUPS_SUFFIX):
        match_url = f"{match_url.removesuffix('/')}/{LINEUPS_SUFFIX}"

    async with httpx.AsyncClient() as client:
        res = await client.get(match_url)
    soup = bs4.BeautifulSoup(res.text, "html.parser")
    teams = parse_teams(soup)
    container = soup.find(id="detail-tab-content")
    lineups = soup.find_all(class_="lineup")
    # Assert all exist: team 1, bench 1, team 2, bench 2
    assert len(lineups) == 4
    # Parse only teams
    lineups = list(map(parse_lineup_table, lineups[::2]))
    for players in lineups:
        assert len(players) == PLAYERS_PER_TEAM

    cols = [f"player_{i}" for i in range(1, PLAYERS_PER_TEAM + 1)]
    return pd.DataFrame(lineups, columns=cols, index=teams)


async def fetch_statistics(match_url: str) -> pd.DataFrame:
    if not match_url.endswith(STATISTICS_SUFFIX):
        match_url = f"{match_url.removesuffix('/')}/{STATISTICS_SUFFIX}"

    async with httpx.AsyncClient() as client:
        res = await client.get(match_url)
    soup = bs4.BeautifulSoup(res.text, "html.parser")

    teams = parse_teams(soup)
    statistics_rows = soup.find(id="statistics-mobi").find_all("div", class_="statisticsMobi")
    statistics = dict(map(parse_statistics_row, statistics_rows))
    goals = [int(g) for g in soup.find(class_="detail").find('b').text.split(':')]
    df = pd.DataFrame(statistics, index=teams)
    df['goals'] = goals
    return df


########### ETL ###############################################################


async def etl(match_url: str, output_path: str) -> None:
    # Fetch data
    summary, df_lineups, df_statistics = await asyncio.gather(
        fetch_summary(match_url),
        fetch_lineups(match_url),
        fetch_statistics(match_url),
    )

    # Concatenate tables
    df_match_data = pd.concat([df_lineups, df_statistics], axis=1)

    # Create output dir
    dir = '_'.join(summary["teams"]) + '-' + summary["datetime"].split('T')[0]
    path = os.path.join(output_path, dir)
    if not os.path.isdir(path):
        print(f"Output directory doesn't exist. Creating {path!r}")
        os.makedirs(path)

    # Save JSON summary
    summary_path = os.path.join(path, "summary.json")
    print(f"Saving summary to {summary_path!r}")
    with open(summary_path, 'w') as f:
        json.dump(summary, f)

    # Save match data table
    match_data_path = os.path.join(path, "match_data.csv")
    print(f"Saving match data to {match_data_path!r}")
    df_match_data.to_csv(match_data_path)


########### Main program ######################################################


@click.command()
@click.option("-O", "--output", default="./data/raw", help="Output directory.")
@click.argument("match-url")
def main(match_url: str, output: str):
    """
    Fetches match details from provided MATCH_URL and outputs them to OUTPUT.

    MATCH_URL to FlashScore match mobile website. E.g. 'https://www.flashscore.mobi/match/f3eqDO5s'.
    """
    if not os.path.isdir(output):
        print(f"Output directory doesn't exist. Creating {output!r}")
        os.makedirs(output)

    print(f"Fetching match from {match_url!r}")
    asyncio.run(etl(match_url, output))


if __name__ == "__main__":
    main()
