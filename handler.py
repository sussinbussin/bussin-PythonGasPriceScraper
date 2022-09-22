import datetime
import logging
import requests
from bs4 import BeautifulSoup
import mysql.connector
from mysql.connector import errorcode

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def scrape():
    results = []
    brands = ["Esso", "Shell", "SPC", "Caltex", "Sinopec"]

    # Try to get HTML of website
    try:
        html_doc = requests.get("https://www.motorist.sg/petrol-prices").content
    except:
        print("The Website is Down")
        return results   

    soup = BeautifulSoup(html_doc, 'html.parser')
    price_table = soup.find("table", class_=["table", "table-borderless", "fuel_comparison_table", "mb-0"]).tbody.contents

    # Collect list of prices
    for i in range(3, len(price_table)):
        if price_table[i] == '\n':
            continue
        prices = list(filter(lambda x: x != '\n', price_table[i].contents))
        fueltype = prices[0].text
        for i in range(len(brands)):
            price = prices[i + 1].text.replace("$", "") if prices[i + 1].text != "-" else None
            results.append((brands[i], fueltype, price))

    return sorted(results, key=lambda x: (x[0].lower(), x[1]))
    

def upload(prices):
    # Connect to DB
    try:
        mydb = mysql.connector.connect(
            host="127.0.0.1",
            user="root",
            password="Matcha8$",
            database="gas_prices"
        )
    except mysql.connector.Error as err:
        # Create DB and table if it doesn't exist
        if err.errno == errorcode.ER_BAD_DB_ERROR:
            print("Database does not exist, creating database")

            tempdb = mysql.connector.connect(
                host="127.0.0.1",
                user="root",
                password="Matcha8$",
            )

            tempdb.cursor().execute("CREATE DATABASE gas_prices")

            tempdb.close()

            mydb = mysql.connector.connect(
                host="127.0.0.1",
                user="root",
                password="Matcha8$",
                database="gas_prices"
            )
            # Create Table
            mydb.cursor().execute("CREATE TABLE gas_price (company varchar(10) NOT NULL, create_date datetime NOT NULL DEFAULT CURRENT_TIMESTAMP, type varchar(10) NOT NULL, price float(3,2), PRIMARY KEY (company, create_date, type))")

        else:
            print(err)

    mycursor = mydb.cursor(buffered=True)

    changed = False
    rows = 0

    # Checking if price changed since last scrape
    mycursor.execute("SELECT company, type, price FROM gas_price ORDER BY create_date DESC, company, type LIMIT 25")
    for (_, _, latestprice), (_, _, newprice) in zip(mycursor, prices):
        rows += 1
        # print(latestprice)
        # print(newprice)
        # print((latestprice is None != newprice is None))
        # print(str(latestprice) != newprice)
        if latestprice is None and newprice is None:
            continue
        elif (latestprice is None != newprice is None) or str(latestprice) != newprice:
            changed = True
            break


    # Insert all prices scraped if there is no data
    if rows == 0:
        changed = True
    # Close connection if no price changes
    elif changed == False:
        print("No changes in price")
        mydb.close()
        return

    # Template SQL statement
    sql = "INSERT INTO gas_price (company, type, price) VALUES (%s, %s, %s)"
    print("Prices updated")

    # Insert scraped prices into DB and close connection
    mycursor.executemany(sql, prices)
    mydb.commit()
    mydb.close()


def run(event, context):
    current_time = datetime.datetime.now().time()
    name = context.function_name
    logger.info("Your cron function " + name + " ran at " + str(current_time))

values = scrape()
upload(values)