from scrapers.telegram import _normalize_rainbet_text

sample = '''1. Click Code To Copy: MFQP3DSN
2. Redeem Here: https://rainbet.com/affiliates?modal=wallet&tab=redeem
Reward: $1
Wager Required: $4,000
Claims: 600'''

normalized = _normalize_rainbet_text(sample)
print('Normalized:')
print(repr(normalized))

# Check each character
for i, c in enumerate(normalized):
    if c == '$':
        print(f'Found $ at position {i}')