import sys, codecs
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)

from dashboard_manager import DashboardManager
from discord_bot import PlatformMultiSelect, SAMPLE_TEST_ITEMS
from embed_editor import EmbedTemplateManager
from models import Platform

dm = DashboardManager()

monitored = ['Stake.us', 'Stake.com', 'Stake.us - VIP Notices', 'Stake.com - VIP Notices',
             'Shuffle.us', 'Shuffle.com', 'Rainbet', 'Degen', 'Qzino', 'Goated',
             'THRILL', 'WINNA', 'Stake.us & Stake.com', 'Default']

summary = dm.get_all_routes_summary()
all_keys = list(summary.keys())
print(f'Platforms in routes summary: {all_keys}')
non_monitored = [k for k in all_keys if k not in monitored]
print(f'Non-monitored in summary: {non_monitored}')
assert not non_monitored, f'FOUND non-monitored: {non_monitored}'

pm_select = PlatformMultiSelect()
dropdown_labels = [opt.label for opt in pm_select.options]
print(f'Dropdown options: {dropdown_labels}')
non_monitored_d = [l for l in dropdown_labels if l not in monitored and l != 'Default']
assert not non_monitored_d, f'FOUND non-monitored: {non_monitored_d}'

sample_keys = list(SAMPLE_TEST_ITEMS.keys())
print(f'SAMPLE_TEST_ITEMS: {[str(k) for k in sample_keys]}')
non_monitored_s = [str(k) for k in sample_keys if k.value not in monitored]
assert not non_monitored_s, f'FOUND non-monitored: {non_monitored_s}'

etm = EmbedTemplateManager()
template_keys = list(etm.templates.keys())
print(f'Embed templates: {template_keys}')
non_monitored_t = [k for k in template_keys if k not in monitored]
assert not non_monitored_t, f'FOUND non-monitored: {non_monitored_t}'

print()
print('THRILL in routes:', 'THRILL' in summary)
print('WINNA in routes:', 'WINNA' in summary)
print('THRILL channels:', dm.get_channels(Platform.THRILL))
print('WINNA channels:', dm.get_channels(Platform.WINNA))
print('THRILL webhooks:', dm.get_webhooks(Platform.THRILL))
print('WINNA webhooks:', dm.get_webhooks(Platform.WINNA))

print()
print('ALL CHECKS PASSED')
