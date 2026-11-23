import unicodedata
print('Dollar sign category:', unicodedata.category('$'))
print('Dollar sign name:', unicodedata.name('$'))

# Check what NFKC does to it
print('NFKC of $:', repr(unicodedata.normalize('NFKC', '$')))

# Test with the actual text
text = 'Reward: $1'
normalized = unicodedata.normalize('NFKC', text)
print('Normalized:', repr(normalized))
for c in normalized:
    cat = unicodedata.category(c)
    if cat == 'Cf':
        print('  Cf char:', repr(c), '(U+{:04X})'.format(ord(c)))