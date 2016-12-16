import datetime
import json
import time
import tweepy
import os.path
from enum import Enum
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary

CONIFG_FILENAME = "config.json"
#Vanitra Richards

class DriverType(Enum):
    driver = 0
    firefox = 1
    chrome = 2

class Config(object):

    with open(CONIFG_FILENAME, "r") as j:
        config = json.load(j)

        # set download, upload, isp, twitter api data, and other defaults in config.json

        download = float(config["bandwidth"]["download"])
        upload = float(config["bandwidth"]["upload"])
        margin = float(config["margin"])
        isp = config["isp"]

        twitter_token = config["twitter"]["twitter_token"]
        twitter_token_secret = config["twitter"]["twitter_token_secret"]
        twitter_consomer_key = config["twitter"]["twitter_consumer_key"]
        twitter_consumer_secret = config["twitter"]["twitter_consumer_secret"]

        log = config["log"]["name"]

        driver_type = None
        binary_path = None

        # Check the configuration file for existence of a 'driver' field
        if DriverType.driver.name in config:
            # If the driver indicated is "firefox", set for that
            if config[DriverType.driver.name]["type"] == DriverType.firefox.name:
                driver_type = DriverType.firefox
                binary_path = config[DriverType.driver.name]["binary"]
                # Check if the provided binary path is valid
                if len(binary_path) > 0 and not os.path.isfile(binary_path):
                    # Invalid binary path, try to use the default
                    driver_type = None
                    binary_path = None
            # Check for "chrome", no binary path needed
            elif config[DriverType.driver.name]["type"] == DriverType.chrome.name:
                driver_type = DriverType.chrome
            # No driver, or other missing, try the default (which is Firefox right now)

        date = ("Data logged: {:%Y-%b-%d %H:%M:%S}".format(datetime.datetime.now()))


class Log(object):

    config = Config()

    def write_to_log(self, input):
        with open(self.config.log, "a") as f:
            f.write(input)


class SpeedTest(object):

    def __init__(self, config:Config):
        self.download = ""
        self.upload = ""
        self.latency = ""
        self.jitter = ""
        self.log = Log()
        self.config = config

        self.driver = None
        self.wait = None
        try:
            # Check for specific driver configured
            if self.config.driver_type is not None:
                # Create a Firefox driver
                if self.config.driver_type == DriverType.firefox:
                    # Point to a configured binary for FF
                    if self.config.binary_path is not None:
                        self.driver = webdriver.Firefox(firefox_binary=FirefoxBinary(config.binary_path))
                    else:
                        self.driver = webdriver.Firefox()
                # Create a Chrome driver (no specific executable needed)
                elif self.config.driver_type == DriverType.chrome:
                        self.driver = webdriver.Chrome()
            # No specific driver configured, try to use Firefox
            else:
                self.driver = webdriver.Firefox()
            self.wait = WebDriverWait(self.driver, 5)
        except WebDriverException as e:
            self.log.write_to_log("Driver creation failed {:%Y-%b-%d %H:%M:%S}\n".format(datetime.datetime.now()))
            self.log.write_to_log(str(e))

    def valid_driver(self):
        return self.driver is not None

    def run_test(self):
        if self.driver is None or self.wait is None:
            return

        self.driver.get("https://www.measurementlab.net/p/ndt-ws.html")

        try:
            button = self.wait.until(EC.element_to_be_clickable(
                (By.ID, "start-button")))
            button.click()

        except TimeoutException:
            self.log.write_to_log("-- Button not found --")

    def store_test_values(self):
        if self.driver is None:
            return

        try:
            self.upload = str(self.driver.find_element_by_id("upload-speed").text)
            self.download = str(self.driver.find_element_by_id("download-speed").text)
            self.latency = self.driver.find_element_by_id("latency").text
            self.jitter = self.driver.find_element_by_id("jitter").text
        except TimeoutException:
            self.log.write_to_log("-- could not find test values --")

    def __del__(self):
        if self.driver is not None:
            self.driver.quit()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver is not None:
            self.driver.quit()


class Twitter(object):

    def __init__(self):
        self.config = Config()
        self.log = Log()
        auth = tweepy.OAuthHandler(self.config.twitter_consomer_key,
                                   self.config.twitter_consumer_secret)
        auth.set_access_token(self.config.twitter_token,
                              self.config.twitter_token_secret)

        try:
            self.api = tweepy.API(auth)
        except:
            self.log.write_to_log("-- " + self.config.date + " --\n"
                                  "Twitter Auth failed \n"
                                  "-------------------- \n")

class Output(object):
    def __init__(self, config:Config, speedtest:SpeedTest, twitter:Twitter):
        self.config = config
        self.log = Log()
        self.twitter = twitter
        self.speedtest = speedtest
        self.config_download = self.config.download
        self.config_upload = self.config.upload
        self.margin = self.config.margin
        self.isp = self.config.isp
        self.speedtest_download = self.speedtest.download
        self.speedtest_upload = self.speedtest.upload

    def test_results(self):

        # If the driver creation failed, these will be empty strings
        if self.speedtest_download == "" or self.speedtest_upload == "":
            self.log.write_to_log("Speed test values invalid\n")
            self.log.write_to_log("Down {} : Up {}\n".format(self.speedtest_download, self.speedtest_upload))
            return

        if (float(self.speedtest_download) < self.config_download * self.margin or
                float(self.speedtest_upload) < self.config_upload * self.margin):

                try:

                    self.twitter.api.update_status(self.isp + " Hey what gives!  I pay for " +
                                           str(self.config_download) + " Mbps download and " +
                                           str(self.config_upload) + " Mbps upload. Why am I only getting " +
                                           self.speedtest_download + " Mbps down and " +
                                           self.speedtest_upload + " Mbps up?")

                    self.log.write_to_log("-- " + self.config.date + " --\n"
                                          "- ERROR: Bandwidth not in spec - \n"
                                          "Download: " + self.speedtest_download + " Mbps \n"
                                          "Upload: " + self.speedtest_upload + " Mbps \n"
                                          "Latency: " + self.speedtest.latency + " msec round trip time \n"
                                          "Jitter: " + self.speedtest.jitter + " msec \n"
                                          "-------------------- \n")

                except:
                    self.log.write_to_log("-- " + self.config.date + " --\n"
                                          "Twitter post / logging failed \n"
                                          "-------------------- \n")

        else:
            self.log.write_to_log("-- " + self.config.date + " --\n"
                                  "- Bandwidth in spec - \n"
                                  "Download: " + self.speedtest_download + " Mbps \n"
                                  "Upload: " + self.speedtest_upload + " Mbps \n"
                                  "Latency: " + self.speedtest.latency + " msec round trip time \n"
                                  "Jitter: " + self.speedtest.jitter + "\n"
                                  "-------------------- \n")


if __name__ == "__main__":
    # Parse the configuration JSON file
    config_data = Config()
    # Create SpeedTest
    speedtest = SpeedTest(config_data)
    # Run test
    speedtest.run_test()
    if speedtest.valid_driver():
        time.sleep(35)
    # Store speed test values
    speedtest.store_test_values()
    # Create Twitter object
    twitter = Twitter()
    # Create Output
    output = Output(config_data, speedtest, twitter)
    # Tweet/log results
    output.test_results()
