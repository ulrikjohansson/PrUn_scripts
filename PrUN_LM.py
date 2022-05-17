import argparse
import requests

LMSearchUrl = "https://rest.fnar.net/localmarket/search"

def printLMSearchResults(results, args):
    adFormat = "{amount} {ticker} for {price}{currency} ({unitPrice} ea) on {planetName} {planetId}, {jumpCount} jumps from {origin}"
    for ad in results["SellingAds"]:
        print(adFormat.format(
            amount=ad["MaterialAmount"],
            ticker=ad["MaterialTicker"],
            price=ad["Price"],
            currency=ad["Currency"],
            unitPrice=ad["Price"] / ad["MaterialAmount"],
            planetName=ad["PlanetName"],
            planetId=ad["PlanetNaturalId"],
            jumpCount=ad["JumpCount"],
            origin=args.origin
        ))

def main():
    parser = argparse.ArgumentParser(description="Search Prosperous Universe LM sales ads for specific material")
    parser.add_argument("ticker", help="material ticker")
    parser.add_argument("origin", nargs="?", default="Katoa", help="planet where you want to deliver the material")
    args = parser.parse_args()

    postData = {
        "SearchBuys" : False,
        "SearchSells" : True,
        "Ticker" : args.ticker,
        "CostThreshold" : 1.5,
        "SourceLocation" : args.origin
    }
    
    req = requests.post(LMSearchUrl, json=postData)
    printLMSearchResults(req.json(), args)

if __name__ == '__main__':
    main()
