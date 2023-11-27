#!/usr/bin/env python3

from typing import Any, Iterable, Optional, TypeAlias
import discord
from discord.ext import commands

import asyncio
import csv
from datetime import datetime
from datetime import timedelta
import logging
import os
import requests
import time

import traceback

Location: TypeAlias = str
Username: TypeAlias = str
Ticker: TypeAlias = str
Amount: TypeAlias = int
FioData: TypeAlias = dict[Username, dict[Ticker,list[tuple[Location,Amount]]]]
SellerData: TypeAlias = dict[Username,tuple[Ticker,list[Location]]]

class GroupInventory:

  _fioInventoryUrl = "https://rest.fnar.net/csv/inventory?group={group}&apikey={apikey}"
  _offeringsSheetCsvUrl = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTU0PDYV0CYk5LObZAFcxIXZNshT27WHvy1CZNmm8paC7eMVmTlCk3rxIFyEY6Tbiz0uiIDG8CxGuCm/pub?gid=0&single=true&output=csv"

  groupId: int
  groupName: Optional[str]
  fioData: FioData
  fioDataLastUpdated: float = 0
  sellerData: SellerData

  def __init__(self, groupId: int, groupName: Optional[str] = None) -> None:
    self.groupId = groupId
    self.groupName = groupName
    self.fioData = {}
    self.sellerData = {}

  def updateInventory(self):
    #update fio data from FIO csv endpoint
    fioUrl = self._fioInventoryUrl.format(
      apikey=os.getenv("FIO_API_KEY"),
      group=self.groupId)
    response = requests.get(fioUrl)
    if response.status_code == 200:
      self.fioDataLastUpdated = time.time()
      csvData = csv.DictReader(response.text.split("\r\n"))

      if self.fioData:
        self.fioData.clear()

      for row in csvData:
        if row["Username"] not in self.fioData:
          self.fioData[row["Username"]] = {}
        if row["Ticker"] not in self.fioData[row["Username"]]:
          self.fioData[row["Username"]][row["Ticker"]] = []
        self.fioData[row["Username"]][row["Ticker"]].append((row["NaturalId"], int(row["Amount"])))

    #update sellerData from Offers sheet
    result = {}
    response = requests.get(self._offeringsSheetCsvUrl)
    if response.status_code == 200:
      sellerData = list(csv.DictReader(response.text.split("\r\n")))
      if sellerData:
        result: SellerData = {}
        for row in sellerData:
          pos_list = [x for x in row.get("POS", "").split(',') if x != ""]
          result[row['Seller'].upper()] = (row["MAT"], pos_list)

    self.sellerData = result

  def findInInventory(self, ticker: Ticker, shouldReturnAll: bool = False)->list[tuple[Username, Amount]]:
    ticker_filtered_result: list[tuple[Username, list[tuple[Location,Amount]]]] = []
    # filter for only ticker we want
    for (user, inv) in self.fioData.items():
      if ticker in inv:
        ticker_filtered_result.append((user, inv[ticker]))

    if not shouldReturnAll:
      ticker_filtered_sellersData = { x:y for x,y in self.sellerData.items() if y[0] == ticker}
      sellers = [s for s in ticker_filtered_sellersData.keys()]
      print("Sellers:", str(sellers))
      seller_filtered_result = [x for x in ticker_filtered_result if x[0] in sellers]

      pos_filtered_result: list[tuple[str,list[tuple[str,int]]]] = []

      for (user, inv_rows) in seller_filtered_result:
        filtered_inv_rows = [x for x in inv_rows if x[0] in ticker_filtered_sellersData[user][1] or len(ticker_filtered_sellersData[user][1]) == 0]
        if len(filtered_inv_rows) > 0:
          pos_filtered_result.append((user, filtered_inv_rows))

      ticker_filtered_result = pos_filtered_result
        
    summed_inventories: list[tuple[Username,Amount]] = []
    # sum up amounts from all remaining locations
    for (user, inv_rows) in ticker_filtered_result:
      amount = sum([x[1] for x in inv_rows])
      if amount > 0:
        summed_inventories.append((user, amount))

    return sorted(summed_inventories, key=lambda x: x[1])[::-1]

ValidChannels = ("auction", "auction-bot-sandbox")
#ValidChannels = ("auction-bot-sandbox")
#set to True for debugging
ShortenHoursToMinutes = False

ShipyardInventory: GroupInventory = GroupInventory(groupId=41707164, groupName="ShipyardGroup")
Ev1lInventory: GroupInventory = GroupInventory(groupId=83373923, groupName="Ev1lGroup")
ShipPartTickers = (
    "BR1",
    "BR2",  #bridges
    "CQT",
    "CQS",
    "CQM",
    "CQL",  #crew q
    "FFC",
    "SFE",
    "MFE",
    "LFE",  #FFC, emitters
    "GEN",
    "ENG",
    "FSE",
    "AEN",
    "HTE",  #STL engines
    "RCT",
    "QCR",
    "HPR",
    "HYR",  #FTL engines
    "SSL",
    "MSL",
    "LSL",  #STL fuel tanks
    "SFL",
    "MFL",
    "LFL",  #FTL fuel tanks
    "TCB",
    "VSC",
    "SCB",
    "MCB",
    "LCB",
    "WCB",
    "VCB",  #cargo bays
    "SSC",
    "LHB",
    "BHP",
    "RHP",
    "HHP",
    "AHP",  #hull plates, SSC
    "BGS",
    "AGS",
    "STS",  #misc
    "BPT",
    "APT",
    "BWH",
    "AWH",  #whipple shields and thermal protection
    "RDS",
    "RDL",  #repair drones
    "BRP",
    "ARP",
    "SRP"  #anti-radiation plates
)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.typing = False
intents.presences = False

bot = commands.Bot(command_prefix='$', intents=intents)
bot.remove_command("help")

currentAuction = None
Log = logging.getLogger(__name__)


def numberToMilSuffixed(number):
  mils = number / 1000000
  if int(mils) == mils:
    mils = int(mils)
  return "{value}mil".format(value=mils)


class Auction:

  def __init__(self,
               ctx,
               creator,
               name,
               initialPrice,
               increments,
               duration,
               extension,
               shipCount=1):
    self.ctx = ctx
    self.creator = creator
    self.name = name
    self.shipCount = shipCount
    self.initialPrice = initialPrice
    self.increments = increments
    self.duration = duration
    self.extension = extension
    delta = timedelta(
        minutes=self.duration) if ShortenHoursToMinutes else timedelta(
            hours=self.duration)
    self.endTime = datetime.now() + delta
    self.timerStopped = False
    self.endTimer = asyncio.create_task(Auction.endTimerTick(self))
    # bid is the following tuple: (bidValue, bidder)
    self.bidHistory = []

  def currentBid(self):
    if not self.bidHistory:
      return None
    return self.bidHistory[-1]

  def prevBid(self):
    if not self.bidHistory or len(self.bidHistory) < self.shipCount + 1:
      return None
    return self.bidHistory[-1 - self.shipCount]

  def tryBid(self, ctx, bidValue):
    minBid = self.getMinBid()
    if bidValue < minBid:
      print("Bid failed: {bidValue} < {minBid}".format(bidValue=bidValue,
                                                       minBid=minBid))
      raise Exception("Minimum bid is {minBid}".format(minBid=minBid))
    delta = timedelta(
        minutes=self.extension) if ShortenHoursToMinutes else timedelta(
            hours=self.extension)
    newEndTime = datetime.now() + delta
    if newEndTime > self.endTime:
      self.endTime = newEndTime
    newBid = (bidValue, ctx.author)
    self.bidHistory.append(newBid)
    self.bidHistory = sorted(self.bidHistory, key=lambda b: b[0])
    print(newBid)
    return newBid

  def getMinBid(self):
    minBid = self.initialPrice
    if len(self.bidHistory) >= self.shipCount:
      minBid = self.bidHistory[-self.shipCount][0] + self.increments
    return minBid

  async def finishAuction(self):
    print("Auction finishing...")
    if self.currentBid():
      for bid in self.bidHistory[:-1 - self.shipCount:
                                 -1]:  #list slicing magic - last shipCount bids, may be less
        await self.ctx.send(
            "{name} sold to {mentionBidder} for {finalPrice}! Congratulations!"
            .format(name=self.name,
                    mentionBidder=bid[1].mention,
                    finalPrice=numberToMilSuffixed(bid[0])))
    else:
      await self.ctx.send(
          "Auction for {name} has ended without any bids...".format(
              name=self.name))
    await self.ctx.send(
        "{mentionCreator}".format(mentionCreator=self.creator.mention))
    global currentAuction
    currentAuction = None

  def stopAuction(self):
    self.timerStopped = True
    global currentAuction
    currentAuction = None

  async def endTimerTick(self):
    #print("endTimerTick", self)
    if self.timerStopped:
      print("Auction timer has stopped!")
      return
    if datetime.now() < self.endTime:
      await asyncio.sleep(60)
      self.endTimer = asyncio.create_task(Auction.endTimerTick(self))
    else:
      self.timerStopped = True
      await self.finishAuction()


def isPriviledgedRole(member):
  return any(role.name == "ev1lc0rp member" for role in member.roles)


def isModeratorRole(member):
  return any(role.name == "moderator" for role in member.roles)


def parseBid(bid):
  result = 0
  multiplier = 1
  if bid.endswith("mil"):
    bid = bid.rstrip("mil")
    multiplier = 1000000
  elif bid.lower().endswith("k"):
    bid = bid.lower().rstrip("k")
    multiplier = 1000
  try:
    result = int(round(float(bid) * multiplier, -4))
  except:
    return None
  return result


def parseDuration(duration):
  try:
    return int(duration)
  except:
    return 0


async def createAuction(ctx,
                        creator,
                        name,
                        initialPrice,
                        increments,
                        duration,
                        extension,
                        shipCount=1):
  print(ctx, name, initialPrice, increments, duration, extension)
  initialPrice = parseBid(initialPrice)
  if initialPrice is None or initialPrice <= 0:
    await ctx.send("{initialPrice} is not a valid value!".format(
        initialPrice=initialPrice))
    return
  increments = parseBid(increments)
  if increments is None or increments <= 0:
    await ctx.send("{initialPrice} is not a valid value!".format(
        initialPrice=initialPrice))
    return

  duration = parseDuration(duration)
  extension = parseDuration(extension)
  return Auction(ctx, creator, name, initialPrice, increments, duration,
                 extension, shipCount)


async def printEndTime(ctx):
  global currentAuction
  if not currentAuction:
    return
  await ctx.send("The auction for {name} ends on <t:{endTime}:f>".format(
      name=currentAuction.name,
      endTime=int(currentAuction.endTime.timestamp())))


@bot.event
async def on_ready():
  print('We have logged in as {0.user}'.format(bot))


@bot.command()
async def auctionstart(ctx,
                       name,
                       initialPrice,
                       increments,
                       duration=48,
                       extension=24):
  global currentAuction
  if ctx.author == bot.user or ctx.author.bot:
    return
  if ctx.channel.name not in ValidChannels:
    return
  if not isPriviledgedRole(ctx.author):
    await ctx.reply("You don't have permissions to create an auction!")
    return

  if currentAuction:
    await ctx.reply(
        "Auction {name} is already running! Stop it first with $auctionstop".
        format(name=currentAuction.name))
    return

  print("Starting auction", name)
  currentAuction = await createAuction(ctx, ctx.author, name, initialPrice,
                                       increments, duration, extension)
  if not currentAuction:
    return
  print("currentAuction:", currentAuction)
  await ctx.reply(
      "Starting auction: {name}, min. bid is {initialPrice}. Min. bid increments: {increments}. Auction will last for {duration}h, or {extension}h after last bid"
      .format(name=currentAuction.name,
              initialPrice=currentAuction.initialPrice,
              increments=currentAuction.increments,
              duration=currentAuction.duration,
              extension=currentAuction.extension))


@bot.command()
async def auctionmultistart(ctx,
                            name,
                            shipCount,
                            initialPrice,
                            increments,
                            duration=48,
                            extension=24):
  global currentAuction
  if ctx.author == bot.user or ctx.author.bot:
    return
  if ctx.channel.name not in ValidChannels:
    return
  if not isPriviledgedRole(ctx.author):
    await ctx.reply("You don't have permissions to create an auction!")
    return
  if currentAuction:
    await ctx.reply(
        "Auction {name} is already running! Stop it first with $auctionstop".
        format(name=currentAuction.name))
    return
  try:
    shipCount = int(shipCount)
    if shipCount <= 1 or shipCount > 10:
      await ctx.reply("Ship count must be between 1 and 10")
      return
  except:
    await ctx.reply("Invalid format!")
    return

  print("Starting multi auction", name)
  currentAuction = await createAuction(ctx,
                                       ctx.author,
                                       name,
                                       initialPrice,
                                       increments,
                                       duration,
                                       extension,
                                       shipCount=shipCount)
  if not currentAuction:
    return
  print("currentAuction:", currentAuction)
  await ctx.reply(
      "Starting auction: {name}. {shipCount} ships are available, and **{shipCount} highest bids win!**\nMin. bid is {initialPrice}. Min. bid increments: {increments}. Auction will last for {duration}h, or {extension}h after last bid.\nYou **can** buy multiple ships!"
      .format(name=currentAuction.name,
              shipCount=shipCount,
              initialPrice=currentAuction.initialPrice,
              increments=currentAuction.increments,
              duration=currentAuction.duration,
              extension=currentAuction.extension))


@bot.command()
async def bid(ctx, bid):
  global currentAuction
  if ctx.author == bot.user or ctx.author.bot:
    return
  if ctx.channel.name not in ValidChannels:
    return
  if not currentAuction:
    await ctx.reply("There's no auction running currently!")
    return
  try:
    bid = parseBid(bid)
    if bid is None:
      await ctx.reply("Invalid bid!")
      return
    newBid = currentAuction.tryBid(ctx, bid)
    previousBid = currentAuction.prevBid()
    await ctx.message.add_reaction('\N{THUMBS UP SIGN}')
    if previousBid:
      await ctx.send(
          "{newBidder} bids {bid} for {name}! Min. valid bid is now:\n$bid {amount}\n{mentionPrevBidder}, you've been outbid!"
          .format(newBidder=newBid[1].mention,
                  name=currentAuction.name,
                  bid=numberToMilSuffixed(newBid[0]),
                  amount=numberToMilSuffixed(currentAuction.getMinBid()),
                  mentionPrevBidder=previousBid[1].mention))
    else:  #first bid (or multiauction with additional ships are still available)
      print("1st bid")
      await ctx.send(
          "{newBidder} bids {bid} for {name}! Min. valid bid is now:\n$bid {amount}"
          .format(newBidder=newBid[1].mention,
                  name=currentAuction.name,
                  bid=numberToMilSuffixed(newBid[0]),
                  amount=numberToMilSuffixed(currentAuction.getMinBid())))
    await printEndTime(ctx)
  except Exception as ex:
    await ctx.reply(ex)
    print(traceback.format_exc())
    return


@bot.command()
async def status(ctx):
  global currentAuction
  if ctx.author == bot.user or ctx.author.bot:
    return
  if ctx.channel.name not in ValidChannels:
    return
  if not currentAuction:
    await ctx.reply("There's no auction running!")
    return
  if not currentAuction.currentBid():
    await ctx.send(
        "There are no bids yet for {name}! To start bidding, use this command:\n$bid {amount}\nThe auction ends on <t:{endTime}:f>"
        .format(name=currentAuction.name,
                amount=numberToMilSuffixed(currentAuction.getMinBid()),
                endTime=int(currentAuction.endTime.timestamp())))
    return
  await ctx.send(
      "Current bid is {bid}. Min. valid bid is now:\n$bid {amount}".format(
          bid=numberToMilSuffixed(currentAuction.currentBid()[0]),
          amount=numberToMilSuffixed(currentAuction.getMinBid())))
  if currentAuction.shipCount > 1:
    await ctx.send("Current winners:")
    for bid in currentAuction.bidHistory[:-1 - currentAuction.shipCount:
                                         -1]:  #list slicing magic - last shipCount bids, may be less
      await ctx.send("{bidder} at {bid}".format(bidder=bid[1].mention,
                                                bid=numberToMilSuffixed(
                                                    bid[0])))
  await printEndTime(ctx)


@bot.command()
async def auctionstop(ctx):
  global currentAuction
  if ctx.author == bot.user or ctx.author.bot:
    return
  if ctx.channel.name not in ValidChannels:
    return
  if not currentAuction:
    await ctx.reply("There's no auction running currently!")
    return
  if not isPriviledgedRole(ctx.author):
    await ctx.reply("You don't have permissions to stop an auction!")
    return

  await ctx.send("Stopping {name} auction".format(name=currentAuction.name))
  currentAuction.stopAuction()
  currentAuction = None


@bot.command()
async def help(ctx):
  global currentAuction
  if ctx.author == bot.user or ctx.author.bot:
    return
  if ctx.channel.name not in ValidChannels:
    return
  await ctx.send(
      '$auctionstart [name] [initial_price] [price_increments] [duration_hours] [extension_hours]\nStarts a new auction. First bid must be at least equal to *initial_price*, each new bid must be bigger by at least *price_increments*. The auction will last for *duration_hours* (default 48), or *extension_hours* (default 24) after a new bid has been placed.\\Example:\n$auctionstart "WCB ship" 2mil 50k'
  )
  await ctx.send("$auctionstop\nStops the current auction.")
  await ctx.send(
      "$bid [price]\nPlaces a new bid. Examples:\n$bid 4mil\nbid 4.25mil\n")
  await ctx.send("$status\nShows current auction status")

async def whohas(ctx: Any, ticker: str, shouldReturnAll: bool = False) -> list[tuple[str, int]]:
  Log.info("whohas", ticker)

  # update relevant group inventory
  global ShipyardInventory
  global Ev1lInventory
  isShipPartTicker = ticker in ShipPartTickers

  inventory = ShipyardInventory if isShipPartTicker else Ev1lInventory
  try:
    inventory.updateInventory()
  except Exception:
    pass

  result = inventory.findInInventory(ticker, shouldReturnAll)
  #print(str(result))
  print("Full:", str(result))

  return result


@bot.command(name="whohas")
async def whohas_command(ctx: Any, ticker: str, all: str =""):
  if ctx.author == bot.user or ctx.author.bot:
    return
  if ctx.channel.name not in ValidChannels:
    return
  if not isPriviledgedRole(ctx.author):
    await ctx.reply("You don't have permissions to run this command!")
    return
  
  shouldReturnAll = all.lower() == "all"

  result = await whohas(ctx=ctx, ticker=ticker.upper(), shouldReturnAll=shouldReturnAll)

  if len(result) == 0:
    await ctx.reply(f"As far as I know, nobody has {ticker}")
    return
  
  formattedResult = [f"{user} has {amount} {ticker.upper()}" for (user, amount) in result]
  print("Filtered:", str(formattedResult))
  await ctx.reply("\n".join(formattedResult))

@bot.command()
async def clearchannel(ctx):
  if ctx.channel.name != "auction":
    return
  if not isModeratorRole(ctx.author):
    await ctx.reply("You don't have permissions to clear the channel!")
    return
  await ctx.channel.purge()


#keep_alive()
if __name__ == "__main__":
  bot.run(os.getenv('DISCORD_TOKEN'))
