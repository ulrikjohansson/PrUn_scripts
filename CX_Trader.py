import argparse
import requests

import PySimpleGUI as sg

from operator import attrgetter

materialsDataURL = "https://rest.fnar.net/material/allmaterials"
CXDataUrl = "https://rest.fnar.net/exchange/all"
CXOrdersURLFormat = "https://rest.fnar.net/exchange/{ticker}.{cx}"

def findCXGaps(cxMarket, origin, dest, tm3Capacity):
    gapFormat = "{ticker} at {origin} : {buyPrice} {buyCount} -> sell {sellCount} at {dest} for {sellPrice}"
    gaps = {}
    for ticker, CXPrices in cxMarket.items():
        originPrices = CXPrices[origin]
        destPrices = CXPrices[dest]
        if originPrices.ask and destPrices.bid and originPrices.ask < destPrices.bid:
            print("Processing {ticker}...".format(ticker=ticker))
            gaps[ticker] = Gap(originPrices, destPrices, tm3Capacity)

    return gaps

def printCXGaps(gaps):
    for ticker in getSortedTickers(gaps):
        print(str(gaps[ticker]))

class PriceData:
    def __init__(self, offer, tm3):
        self.ticker = offer["MaterialTicker"]
        self.tm3 = tm3
        self.cx = offer["ExchangeCode"]
        self.mmAsk = offer["MMSell"]
        self.mmBid = offer["MMBuy"]
        self.avg = offer["PriceAverage"]
        self.ask = offer["Ask"]
        self.askCount = offer["AskCount"]
        self.bid = offer["Bid"]
        self.bidCount = offer["BidCount"]
        self.supply = offer["Supply"]
        self.demand = offer["Demand"]

class Order:
    def __init__(self, orderJson):
        self.company = orderJson["CompanyName"]
        self.count = orderJson["ItemCount"]
        self.price = orderJson["ItemCost"]

class Transaction:
    def __init__(self, askPrice, bidPrice, count):
        self.askPrice = askPrice
        self.bidPrice = bidPrice
        self.count = count
        self.profit = (bidPrice - askPrice) * count

class Gap:
    def __init__(self, originPrices, destPrices, tm3Capacity):
        self.ticker = originPrices.ticker
        self.tm3 = originPrices.tm3
        self.tm3Capacity = tm3Capacity
        self.origin = originPrices.cx
        self.dest = destPrices.cx
        self.originPrices = originPrices
        self.destPrices = destPrices
        self.asks = []
        self.bids = []
        self.transactions = []
        self.totalProfit = 0
        self.totalCount = 0
        self.totalCost = 0
        self.totalTm3 = 0
        
        self.__fetchOrders()
        self.__matchOrders()
        

    def __fetchOrders(self):
        originReq = requests.get(CXOrdersURLFormat.format(ticker=self.ticker, cx=self.origin))
        destReq = requests.get(CXOrdersURLFormat.format(ticker=self.ticker, cx=self.dest))

        for ask in originReq.json()["SellingOrders"]:
            self.asks.append(Order(ask))

        for bid in destReq.json()["BuyingOrders"]:
            self.bids.append(Order(bid))

        #sorting- lowest asks and highest bids at the end of the lists
        self.asks.sort(key=attrgetter("price"), reverse=True)
        self.bids.sort(key=attrgetter("price"))

    def __matchOrders(self):
        capacity = self.tm3Capacity
        if not self.asks or not self.bids:
            #could be empty if FIO has updated since last request
            return
        
        ask = self.asks.pop()
        bid = self.bids.pop()
        while ask.price < bid.price:
            count = min(ask.count, bid.count)
            if count * self.tm3 > capacity:
                count = int(capacity / self.tm3)
                if count > 0:
                    self.transactions.append(Transaction(ask.price, bid.price, count))
                break
            self.transactions.append(Transaction(ask.price, bid.price, count))
            ask.count -= count
            bid.count -= count
            capacity -= count * self.tm3
            if ask.count <= 0:
                if len(self.asks) == 0:
                    break
                ask = self.asks.pop()
            if bid.count <= 0:
                if len(self.bids) == 0:
                    break
                bid = self.bids.pop()

        for t in self.transactions:
            self.totalProfit += t.profit
            self.totalCost += t.askPrice * t.count
            self.totalCount += t.count
            self.totalTm3 += t.count * self.tm3

    def __str__(self):
        result = "{ticker} {origin} -> {dest} Total profit: {totalProfit} amount: {amount}({totalTm3}tm3) costs: {costs}\n".format(ticker=self.ticker, origin=self.origin, dest=self.dest, totalProfit=self.totalProfit, amount=self.totalCount, costs=self.totalCost, totalTm3=self.totalTm3)
        for t in self.transactions:
            result += "    Buy {count} for {buyPrice} sell for {sellPrice} profit: {profit}\n".format(count=t.count, buyPrice=t.askPrice, sellPrice=t.bidPrice, profit=t.profit)
        return result

def getMaterialTm3(ticker, materialsData):
    for mat in materialsData:
        if mat["Ticker"] == ticker:
            return max(mat["Weight"], mat["Volume"])

def parseCXOffers(offers):
    req = requests.get(materialsDataURL)
    materialsData = req.json()
    
    cxMarket = {}
    for offer in offers:
        if offer["MaterialTicker"] not in cxMarket:
            cxMarket[offer["MaterialTicker"]] = {}
        cxMarket[offer["MaterialTicker"]][offer["ExchangeCode"]] = PriceData(offer, getMaterialTm3(offer["MaterialTicker"], materialsData))

    return cxMarket

def strToTm3(strValue):
    try:
        return float(strValue)
    except:
        return -1

def getSortedTickers(gaps):
    return [dictKV[0] for dictKV in sorted(gaps.items(), key=lambda x: x[1].totalProfit, reverse=True)]

def doSearch(origin, dest, tm3Capacity):
    req = requests.get(CXDataUrl)
    print(req)
    cxMarket = parseCXOffers(req.json())
    gaps = findCXGaps(cxMarket, origin, dest, tm3Capacity)
    printCXGaps(gaps)
    return gaps

def initGUI():
    CXes = ("AI1", "CI1", "NC1", "IC1", "CI1", "NC2")
    layout = [[sg.Text("From"), sg.Combo(CXes, key="origin", default_value="CI1", enable_events=True, readonly=True), sg.Text("To"), sg.Combo(CXes, key="dest", default_value="AI1", enable_events=True, readonly=True), sg.Button("Search"), sg.Text("Cargo space t/m3"), sg.Input("500", size=4, key="tm3Capacity", enable_events=True)],
              [sg.Listbox([], size=(4, 20), enable_events=True, select_mode=sg.LISTBOX_SELECT_MODE_SINGLE, key="tradesLB", visible=False), sg.Multiline(disabled=True, size=(100, 20), echo_stdout_stderr=True, key="outputML", visible=False)],
    ]
    win = sg.Window("CX Trader", layout)
    win["outputML"].reroute_stderr_to_here()
    win["outputML"].reroute_stdout_to_here()

    while True:
        event, values = win.read()
        if event == sg.WIN_CLOSED:
            break

        if event == "Search":
            win["tradesLB"].update(visible=True)
            win["outputML"].update(visible=True)
            win.perform_long_operation(lambda: doSearch(values["origin"], values["dest"], strToTm3(values["tm3Capacity"])),
                                       "SearchFinished")
        if event == "SearchFinished":
            win["outputML"].update(value="")
            gaps = values[event]
            tickers = getSortedTickers(gaps)
            win["tradesLB"].update(values=tickers)

        if event == "tradesLB":
            ticker=values[event][0]
            win["outputML"].update(value="")
            print(str(gaps[ticker]))

        #Disable search button if the same CXes are selected, or cargo space is invalid
        win["Search"].update(disabled=values["origin"] == values["dest"] or strToTm3(values["tm3Capacity"]) <= 0)

    win.close()

def main():
    #TODO run in console, without UI, if launched with commandline params
    #parser = argparse.ArgumentParser(description="Search Prosperous Universe CX for price gaps, written by Gilith")
    #parser.add_argument("origin", default="CI1", help="CX where you buy stuff")
    #parser.add_argument("dest", help="CX where you sell stuff")
    #parser.add_argument("tm3Capacity", nargs="?", default=500, help="Cargo hold t / m3")
    #args = parser.parse_args()

    initGUI()
    
    #req = requests.get(CXDataUrl)
    #print(req)
    #cxMarket = parseCXOffers(req.json())
    #gaps = findCXGaps(cxMarket, args.origin, args.dest, args.tm3Capacity)
    #printCXGaps(gaps)

if __name__ == '__main__':
    main()
