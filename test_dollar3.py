import re
from scrapers.telegram import _RE_VALUE_RAINBET, _RE_VALUE_RAINBET_DROP, _normalize_rainbet_text, _RE_VALUE_GENERIC

sample = '''1. Click Code To Copy: MFQP3DSN
2. Redeem Here: https://rainbet.com/affiliates?modal=wallet&tab=redeem
Reward: $1
Wager Required: $4,000
Claims: 600'''

normalized = _normalize_rainbet_text(sample)
print('Normalized:')
print(repr(normalized))

m = _RE_VALUE_RAINBET.search(normalized)
if m:
    print('MATCH _RE_VALUE_RAINBET:', m.group(1))
else:
    print('NO MATCH _RE_VALUE_RAINBET')

m2 = _RE_VALUE_RAINBET_DROP.search(normalized)
if m2:
    print('MATCH _RE_VALUE_RAINBET_DROP:', m2.group(1))
else:
    print('NO MATCH _RE_VALUE_RAINBET_DROP')

m3 = _RE_VALUE_GENERIC.search(normalized)
if m3:
    print('MATCH _RE_VALUE_GENERIC:', m3.group(1))
else:
    print('NO MATCH _RE_VALUE_GENERIC')