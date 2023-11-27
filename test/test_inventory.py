from unittest.mock import MagicMock
from asynctest import CoroutineMock
import pytest
import csv
import HAL9666.AuctionMasterBot as bot
import io

@pytest.mark.asyncio
async def test_inventory():

    general_csv_file = create_csv(
        [
            {"Username":"Kindling", "Ticker": "C", "Amount":"200", "NaturalId": "UV-351a"}
        ]
    )

    shipyard_csv_file = create_csv(
        [
            {"Username":"Felmer", "Ticker": "WCB", "Amount":"3", "NaturalId": "UV-351a"}
        ]
    ) 
    
    fake_fio_response = MagicMock()
    fake_fio_response.status_code = 200
    fake_fio_response.text = general_csv_file

    bot.requests.get = MagicMock(return_value=fake_fio_response)

    bot.getSellerData = MagicMock(return_value = {"Kindling":[], "Felmer": [], "Gilith": []})

    inv = await bot.whohas(CoroutineMock(), "C")
    assert inv[0] == ("Kindling", 200)

    general_csv_file = create_csv(
        [
            {"Username":"Kindling", "Ticker": "C", "Amount":"200", "NaturalId": "UV-351a"},
            {"Username":"Felmer", "Ticker": "C", "Amount":"250", "NaturalId": "UV-351a"}
        ]
    )
    fake_fio_response.text = general_csv_file

    inv = await bot.whohas(CoroutineMock(), "C")

    assert inv[0] == ("Felmer", 250)
    assert inv[1] == ("Kindling", 200)

    fake_fio_response.status_code = 500

    ctx = MagicMock()
    ctx.reply = CoroutineMock()
    inv = await bot.whohas(ctx, "C")

    assert inv[0] == ("Felmer", 250)
    assert inv[1] == ("Kindling", 200)

    fake_fio_response.status_code = 200
    fake_fio_response.text = shipyard_csv_file
    inv = await bot.whohas(ctx, "WCB")

    assert len(inv) == 1
    assert inv[0] == ("Felmer", 3)

    fake_fio_response.status_code = 500
    inv = await bot.whohas(ctx, "C")

    assert inv[0] == ("Felmer", 250)
    assert inv[1] == ("Kindling", 200)

@pytest.mark.asyncio
async def test_pos_filter():
    inventory = bot.GroupInventory(groupId=1234)
    inventory.updateInventory = MagicMock()
    inventory.fioData = {
        "Kindling": {
            "C": [
                ("UV-351a", 200),
                ("KW-688c", 100)
            ]
        },
        "Gilith": {
            "C": [("UV-351a", 100)]
        },
        "Felmer": {
            "C": [("UV-351a", 250)]
        },
        "Thoern": {
            "H": [("UV-351a", 1000)],
            "C": [("UV-351a", 100)]
        }
    }
    inventory.sellerData = {
        "Kindling": ("C", ["UV-351a"]),
        "Gilith": ("C", []),
        "Felmer": ("C", ["XG-521b"]),
        "Thoern": ("H", ["UV-351a"])
    }
    bot.Ev1lInventory = inventory

    inv = await bot.whohas(MagicMock(), "C", False)

    assert len(inv) == 2
    assert inv[0] == ("Kindling", 200)
    assert inv[1] == ("Gilith", 100)

def test_getSellersData():
    csv_data = [
            {"MAT":"C", "Seller": "Kindling", "POS":"KW-688c", "Price/u": "300"},
            {"MAT":"C", "Seller": "Felmer", "POS":"", "Price/u": "300"},
            {"MAT":"WCB", "Seller": "Felmer", "POS":"UV-351a", "Price/u": "300000"}
        ]
    sheets_csv_file = create_csv(csv_data)

    fake_fio_response = MagicMock()
    fake_fio_response.status_code = 200
    fake_fio_response.text = sheets_csv_file
    bot.requests.get = MagicMock(return_value = fake_fio_response)

    sellers = bot.getSellerData("C")

    assert isinstance(sellers, dict)
    assert len(sellers) == 2

    sellers = bot.getSellerData("WCB")
    assert len(sellers) == 1

def test_getSellersData_no_POS_column():
    csv_data = [
            {"MAT":"C", "Seller": "Kindling", "Price/u": "300"},
            {"MAT":"C", "Seller": "Felmer", "Price/u": "300"},
            {"MAT":"WCB", "Seller": "Felmer", "Price/u": "300000"}
        ]
    sheets_csv_file = create_csv(csv_data)

    fake_fio_response = MagicMock()
    fake_fio_response.status_code = 200
    fake_fio_response.text = sheets_csv_file
    bot.requests.get = MagicMock(return_value = fake_fio_response)

    sellers = bot.getSellerData("C")

    assert isinstance(sellers, dict)
    assert len(sellers) == 2

    sellers = bot.getSellerData("WCB")
    assert len(sellers) == 1

def create_csv(csv_data: list[dict[str,str]]) -> str:
    if len(csv_data) < 1: raise ValueError("List must have atleast 1 entry")

    csv_file = io.StringIO()
    general_csv_writer = csv.DictWriter(csv_file, list(csv_data[0].keys()))
    general_csv_writer.writeheader()
    for row in csv_data:
        general_csv_writer.writerow(row)

    return csv_file.getvalue()