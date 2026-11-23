from scrapers.telegram import TelegramScraper

tg = TelegramScraper()

# Test current Rainbet format from logs
sample = """1. Click Code To Copy: MFQP3DSN
2. Redeem Here: https://rainbet.com/affiliates?modal=wallet&tab=redeem
Reward: $1
Wager Required: $4,000
Claims: 600"""

item = tg.parse_rainbet_message(sample, 'https://t.me/EddiesCodesRainbet/100')
if item:
    print('Code:', item.code)
    print('Platform:', item.platform)
    print('Value:', item.amount_value)
    print('Wager:', item.wager_requirement)
    print('Claims:', item.claims_count)
    print('Redeem:', item.redeem_link)
else:
    print('FAILED TO PARSE')