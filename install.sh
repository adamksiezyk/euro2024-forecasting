#!/usr/bin/env bash

[ -d ./bin] || mkdir ./bin

# Download headless-chrome biary
[ -d ./bin/chrome-headless-shell-linux64 ] \
	|| echo "Installing chrome-headless-shell" \
    && wget -qq -O ./bin/chrome-headless-shell-linux64.zip https://storage.googleapis.com/chrome-for-testing-public/126.0.6478.61/linux64/chrome-headless-shell-linux64.zip \
    && unzip -q ./bin/chrome-headless-shell-linux64.zip -d ./bin \
    && rm ./bin/chrome-headless-shell-linux64.zip \
	&& echo "Done"

# Download chromedriver binary
[ -d ../bin/chromedriver-linux64 ] \
	|| echo "Installing chromedriver" \
    && wget -qq -O ./bin/chromedriver-linux64.zip https://storage.googleapis.com/chrome-for-testing-public/126.0.6478.61/linux64/chromedriver-linux64.zip \
    && unzip -q ./bin/chromedriver-linux64.zip -d ./bin \
    && rm ./bin/chromedriver-linux64.zip \
	&& echo "Done"
