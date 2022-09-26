import datetime
import logging
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
import mysql.connector
from mysql.connector import errorcode
from sshtunnel import SSHTunnelForwarder
import os

ssh_host=os.environ['SSH_HOST']
ssh_port=os.environ['SSH_PORT']
ssh_pkey=os.environ['SSH_PKEY']
ssh_user=os.environ['SSH_USER']
rds_port=os.environ['RDS_PORT']
host=os.environ['HOST']
user=os.environ['USER']
password=os.environ['PASSWORD']
database=os.environ['DATABASE']

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def scrape():
    results = []
    brands = ["Esso", "Shell", "SPC", "Caltex", "Sinopec"]

    # Try to get HTML of website
    try:
        url = 'https://www.motorist.sg/petrol-prices'
        headers = {'User-Agent': 'Mozilla/5.0'}
        request = Request(url, headers=headers)
        mybytes = urlopen(request).read()
        html_doc = mybytes.decode("utf8")
    except:
        logger.info("The Website is Down")
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
            host=host,
            user=user,
            password=password,
            database=database
        )
    except mysql.connector.Error as err:
        print(err)

    mycursor = mydb.cursor(buffered=True)

    changed = False
    rows = 0

    # Checking if price changed since last scrape
    mycursor.execute("SELECT company, type, price FROM gas_price ORDER BY create_date DESC, company, type LIMIT 25")
    for (_, _, latestprice), (_, _, newprice) in zip(mycursor, prices):
        rows += 1
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
        logger.info("No changes in price")
        mydb.close()
        return

    # Template SQL statement
    sql = "INSERT INTO gas_price (company, type, price) VALUES (%s, %s, %s)"
    logger.info("Prices updated")

    # Insert scraped prices into DB and close connection
    mycursor.executemany(sql, prices)
    mydb.commit()
    mydb.close()


def main(event, context):
    values = scrape()
    with SSHTunnelForwarder(
        (ssh_host, ssh_port),
        ssh_username=ssh_user,
        ssh_pkey=ssh_pkey,
        remote_bind_address=(host, rds_port)
    ) as tunnel:
        tunnel.start()
        upload(values)

    current_time = datetime.datetime.now().time()
    name = context.function_name
    logger.info("Your cron function " + name + " ran at " + str(current_time))