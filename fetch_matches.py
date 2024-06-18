import asyncio
import datetime as dt
import glob
import logging
import os

import pandas as pd
from tqdm.asyncio import tqdm_asyncio

from flashscore_parser import etl as fs_parse
from flashscore_scraper import etl as fs_scrape

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%H:%M:%S",
    filename="./data/logs/fetch_matches.log",
    filemode='a',
)


def fetch_matches() -> None:
    input_dir = "./data/squads"
    output_dir = "./data/matches"
    print("Scraping matchs")
    for team_file in os.listdir(input_dir):
        with open(os.path.join(input_dir, team_file), 'r') as f:
            lines = f.readlines()
        url = lines[2].strip()
        team = os.path.splitext(team_file)[0]
        output_path = os.path.join(output_dir, team + ".csv")

        if os.path.isfile(output_path):
            print(f"File {output_path!r} already existss, skipping")
            continue

        print(f"Scraping matches for {team}")
        try:
            fs_scrape(url, output_path=output_path)
        except Exception as e:
            print(f"Failed with: {str(e)}, skipping")


sem = asyncio.Semaphore(10)


async def limit_fs_parse(*args, **kwargs):
    async with sem:  # semaphore limits num of simultaneous downloads
        return await fs_parse(*args, **kwargs)


async def fetch_matches_details() -> None:
    input_dir = "./data/matches"
    output_dir = "./data/raw"

    df = pd.concat(
        [pd.read_csv(fp, parse_dates=['datetime']) for fp in glob.glob(os.path.join(input_dir, "*.csv"))],
        ignore_index=True,
    ).drop(columns="Unnamed: 0")
    total = len(df)
    print(f"Found {total} total matches")
    df = df[df['datetime'] < dt.datetime.now()]
    print(f"Dropping {total - len(df)} matches, that are not yet finished")

    futures = [asyncio.ensure_future(limit_fs_parse(match['url'], output_dir)) for _, match in df.iterrows()]
    await tqdm_asyncio.gather(*futures, ncols=120, desc="Parsing matches")


if __name__ == "__main__":
    # fetch_matches()
    asyncio.run(fetch_matches_details())
