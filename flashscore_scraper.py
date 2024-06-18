import contextlib
import datetime as dt
import logging
import os
import time
import urllib.parse
from typing import Generator

import bs4
import click
import pandas as pd
from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver

LOGGING_PATH = "./data/logs"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%H:%M:%S",
    filename=os.path.join(LOGGING_PATH, "flashscore_scraper.log"),
    filemode='a',
)

DEFAULT_CHROME_PATH = "./bin/chrome-headless-shell-linux64/chrome-headless-shell"
DEFAULT_CHROMEDRIVER_PATH = "./bin/chromedriver-linux64/chromedriver"


@contextlib.contextmanager
def _create_chrome_driver(browser_location: str, driver_location: str) -> Generator[webdriver.Chrome, None, None]:
    options = webdriver.ChromeOptions()
    options.binary_location = browser_location
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    service = webdriver.ChromeService(executable_path=driver_location)
    with webdriver.Chrome(service=service, options=options) as driver:
        yield driver


def fetch_website_with_js_loaded(driver: WebDriver, url: str) -> bs4.BeautifulSoup:
    driver.get(url)
    time.sleep(5)  # Let JS load
    return bs4.BeautifulSoup(driver.page_source, "html.parser")


def parse_match(match: bs4.BeautifulSoup) -> tuple[pd.Timestamp | None, str, str, str]:
    # If penalties, remove suffix
    datetime = match.find(class_="event__time")
    # Check if match just recently finished (time unavailable)
    if datetime is not None:
        datetime = datetime.text.lower().removesuffix("pen").split()
        # Check if date-only
        if len(datetime) == 1:
            datetime = pd.to_datetime(datetime[0], dayfirst=True)
        else:
            date, time = datetime
            date = date.split('.')
            # Check if year is present
            if not date[2]:
                date[2] = str(dt.date.today().year)
            datetime = pd.to_datetime('.'.join(date) + ' ' + time, dayfirst=True)

    home_participant = match.find(class_="event__homeParticipant")
    home_participant = (home_participant.find("strong") or home_participant.find("span")).text.lower().strip()
    away_participant = match.find(class_="event__awayParticipant")
    away_participant = (away_participant.find("strong") or away_participant.find("span")).text.lower().strip()

    href = match.find("a").get("href")
    url = urllib.parse.urlparse(href)
    url = url._replace(netloc="m.flashscore.com", fragment='')
    new_href = url.geturl()

    return datetime, home_participant, away_participant, new_href


def fetch_matches(driver: WebDriver, team_url: str) -> pd.DataFrame:
    soup = fetch_website_with_js_loaded(driver, team_url)
    matches = soup.find_all(class_="event__match")
    logging.info(f"Found {len(matches)} matches")
    return pd.DataFrame([parse_match(m) for m in matches], columns=["datetime", "home_team", "away_team", "url"])


def etl(
    team_url: str,
    output_path: str,
    chrome_path=DEFAULT_CHROME_PATH,
    chromedriver_path=DEFAULT_CHROMEDRIVER_PATH
) -> None:
    with _create_chrome_driver(chrome_path, chromedriver_path) as driver:
        try:
            df_matches = fetch_matches(driver, team_url)
        except Exception as e:
            logging.error(f"Failed to fetch matches for {team_url!r}: {str(e)}")
            # if logging.root.level == logging.DEBUG:
            #     logging.debug(f"Dumping page source to file debug_{team_url}.html")
            #     with open(os.path.join(LOGGING_PATH, f"debug_{team_url}.html"), 'w') as f:
            #         f.write(driver.page_source)
            raise e

    if not len(df_matches):
        logging.warn("DataFrame is empty")
    df_matches.to_csv(output_path)


@click.command()
@click.option("--chromedriver-path", default=DEFAULT_CHROMEDRIVER_PATH, help="Chromedriver binary path.")
@click.option("--chrome-path", default=DEFAULT_CHROME_PATH, help="Chrome binary path. Can be also headless shell path.")
@click.option("-O", "--output", default="./data/matches", help="Output directory.")
@click.argument("team-url")
def main(team_url: str, output: str, chrome_path: str, chromedriver_path: str) -> None:
    """
    Fetches all matches played by the team under TEAM_URL and outputs them to OUTPUT.

    TEAM_URL to FlashScore team website. E.g. 'https://www.flashscore.com/team/germany/ptQide1O/results/'.
    """

    team = urllib.parse.urlparse(team_url).path.split('/')[2]
    output_path = os.path.join(output, team + ".csv")
    if not os.path.isdir(output):
        print(f"Output directory doesn't exist. Creating {output!r}")
        os.makedirs(output)
    elif os.path.isfile(output_path):
        print(f"File for team {team!r} already exists. Overriding.")

    print(f"Fetching matches from {team_url!r}")
    etl(team_url, output_path, chrome_path, chromedriver_path)


if __name__ == "__main__":
    main()
