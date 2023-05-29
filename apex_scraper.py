import csv
import json
import os.path
import time

import selenium
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome import service

chrome_driver_path = "path to chrome webdriver executable"
APEX_URL="https://apex.prosperousuniverse.com/#/"
APEX_LOGIN="your email"
APEX_USERNAME="your apex username"
APEX_PASSWORD="your apex password"

class ApexUtils:
    def __init__(self, driver):
        self.driver = driver
        self.__login()

    def __login(self):
        self.driver.get(APEX_URL)
        loginElement = self.driver.find_element(By.NAME, "login")
        loginElement.send_keys(APEX_LOGIN)
        passwordElement = self.driver.find_element(By.NAME, "password")
        passwordElement.send_keys(APEX_PASSWORD)
        self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
    def saveBuffers(self):
        self.savedBuffers = self.driver.find_elements(By.CLASS_NAME, "Window__window___dAtRTy4")

    def openNewBuffer(self, command):
        self.saveBuffers()
        self.driver.find_element(By.ID, "TOUR_TARGET_BUTTON_BUFFER_NEW").click()
        buf = self.findNewBuffer()
        cmdField = buf.find_element(By.XPATH, ".//input[@placeholder='Enter content command']")
        cmdField.send_keys(command)
        cmdField.send_keys(Keys.ENTER)
        cmdField.send_keys(Keys.ENTER)
        return buf

    def findNewBuffer(self):
        for elem in self.driver.find_elements(By.CLASS_NAME, "Window__window___dAtRTy4"):
            if elem in self.savedBuffers:
                continue
            return elem

    def closeBuffer(self, buffer):
        buffer.find_element(By.XPATH, ".//div[@title='close']").click()

    def scrollDownBuffer(self, buffer):
        scrollbar = buffer.find_element(By.XPATH, ".//div[contains (@class, 'ScrollView__thumb-vertical')]")
        scrollarea = buffer.find_element(By.XPATH, ".//div[contains (@class, 'ScrollView__track-vertical')]")
        scrolldelta = scrollarea.rect["height"] - scrollbar.rect["height"]
        ActionChains(self.driver).drag_and_drop_by_offset(
            scrollbar, 0, scrolldelta).perform()

def main():
    options = webdriver.ChromeOptions()
    #doesn't work well in headless mode...
    #options.add_argument("--headless")
    #options.add_argument("window-size=1920,1080")
    driver = webdriver.Chrome(chrome_driver_path, options=options)
    try:
        print("Logging in...")
        driver.implicitly_wait(10)
        apex = ApexUtils(driver)

        print("Opening BS buffer")
        BSBuffer = apex.openNewBuffer("BS")
        apex.saveBuffers()

        baseButtons = BSBuffer.find_elements(By.XPATH, ".//button[text()='view base']")
        baseInventories = {}
        for btn in baseButtons:
            try:
                btn.click()
            except selenium.common.exceptions.ElementClickInterceptedException:
                #button is not visible - scroll the buffer down and try again
                apex.scrollDownBuffer(BSBuffer)
                btn.click()
            base = apex.findNewBuffer()
            apex.saveBuffers()
            baseName = base.find_element(By.XPATH, ".//div[contains (@class, 'TileFrame__title')]").text.split(":")[1].strip()
            baseID = base.find_element(By.XPATH, ".//div[contains (@class, 'TileFrame__cmd')]").text.split(" ")[1]
            print("Fetching inventory from", baseName)
            base.find_element(By.XPATH, ".//button[text()='Inventory']").click()
            inventory = apex.findNewBuffer()
            items = inventory.find_elements(By.XPATH, ".//div[contains (@class, 'MaterialIcon__container')]")
            baseInventories[baseID] = {}
            baseInventories[baseID]["name"] = baseName or baseID
            baseInventories[baseID]["tickers"] = {}
            for i in items:
                ticker = i.find_element(By.XPATH, ".//span[contains (@class, 'ColoredIcon__label')]").text
                amount_str = i.find_element(By.XPATH, ".//div[contains (@class, 'MaterialIcon__indicator_')]").text
                amount = int(amount_str) if amount_str else 0
                if not ticker:
                    continue
                baseInventories[baseID]["tickers"][ticker] = amount
                #print(ticker, ":", amount)
            apex.closeBuffer(inventory)
            apex.closeBuffer(base)
        with open(os.path.join(os.path.dirname(__file__), "baseinv.json"), "w") as jsonFile:
            json.dump(baseInventories, jsonFile)
            print("Saved to", os.path.abspath(jsonFile.name))

        with open(os.path.join(os.path.dirname(__file__), "baseinv.csv"), "w", newline='') as csvFile:
            writer = csv.DictWriter(csvFile, fieldnames=["Username","NaturalId","Name","StorageType","Ticker","Amount"])
            writer.writeheader()
            for b in baseInventories.keys():
                for t in baseInventories[b]["tickers"].keys():
                    writer.writerow({"Username": APEX_USERNAME, "NaturalId": baseInventories[b]["name"], "Name": b, "StorageType": "STORE", "Ticker": t, "Amount": str(baseInventories[b]["tickers"][t])})
            print("Saved to", os.path.abspath(csvFile.name))
            
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
