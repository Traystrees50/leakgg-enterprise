import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrapers.telegram import _detect_stake_platform_from_source_and_code
from models import Platform

CASES = [
    ('1', 'Code: SPIKEUS3Lz7N4q1\nSource: TheSpike.gg\nSTAKE.US', 'SPIKEUS3Lz7N4q1', Platform.STAKE_US),
    ('2', 'Code: CHAMP8K4L9201\nSource: GameChampions US\nSTAKE.US', 'CHAMP8K4L9201', Platform.STAKE_US),
    ('3', 'Code: CHAMP6Y2N8140\nSource: GameChampions\nSTAKE.COM', 'CHAMP6Y2N8140', Platform.STAKE_COM),
    ('4', 'Code: BILJ3Z3WKF\nSource: Ballislife\nSTAKE.US', 'BILJ3Z3WKF', Platform.STAKE_US),
    ('5', 'Code: ThanksgivingGold\nSource: FreeTips\nSTAKE.COM', 'ThanksgivingGold', Platform.STAKE_COM),
    ('6', 'Code: ESBCOM158ELITERUSH6\nSource: EsportsBetting COM\nSTAKE.COM', 'ESBCOM158ELITERUSH6', Platform.STAKE_COM),
    ('7', 'Code: ESBUS158ELITERUSH6\nSource: EsportsBetting\nSTAKE.US', 'ESBUS158ELITERUSH6', Platform.STAKE_US),
    ('8-Shuffle.us', 'Shuffle.us Bonus Drop\nCode: ABCD1234', 'ABCD1234', None),
    ('9-Shuffle.com', 'Shuffle.com Chat Code\nCode: XYZ9876', 'XYZ9876', None),
    ('10-Rainbet', 'Rainbet Drop\nCode: MFQP3DSN', 'MFQP3DSN', None),
    ('11-Degen', 'Degen Drop\nCode: DEGEN123', 'DEGEN123', None),
    ('12-Qzino', 'Qzino Bonus\nCode: QZ12345', 'QZ12345', None),
    ('13-kw-us', 'Stake.us Bonus Drop Alert\nCode: RANDOMCODE', 'RANDOMCODE', Platform.STAKE_US),
    ('14-kw-com', 'Stake.com Bonus Drop Alert\nCode: RANDOMCODE', 'RANDOMCODE', Platform.STAKE_COM),
    ('15-dual', 'Valid on stake.us and stake.com\nCode: DUALCODE', 'DUALCODE', None),
    ('16-VegasInsider', 'Source: VegasInsider\nCode: VEGASCODE', 'VEGASCODE', Platform.STAKE_US),
    ('17-Deadspin', 'Source: Deadspin\nCode: DEADSPINCODE', 'DEADSPINCODE', Platform.STAKE_US),
    ('18-ESBCOM-prefix', 'Bonus drop code below', 'ESBCOM999XYZ', Platform.STAKE_COM),
    ('19-ESBUS-prefix', 'Bonus drop code below', 'ESBUS999XYZ', Platform.STAKE_US),
    ('20-CHAMP-default', 'Bonus drop code below', 'CHAMPABCD1234', Platform.STAKE_COM),
]

passed = failed = 0
lines = []
for n, text, code, expected in CASES:
    got = _detect_stake_platform_from_source_and_code(text, code)
    ok = got == expected
    tag = 'PASS' if ok else 'FAIL'
    lines.append(f'  [{tag}] case {n}: code={code!r:25s} expected={str(expected):30s} got={str(got)}')
    if not ok:
        failed += 1
    else:
        passed += 1

output = '\n'.join(lines) + f'\nResults: {passed} passed, {failed} failed / {len(CASES)} total\n'
with open('result.txt', 'w', encoding='utf-8') as f:
    f.write(output)
print(output)
sys.exit(0 if failed == 0 else 1)
