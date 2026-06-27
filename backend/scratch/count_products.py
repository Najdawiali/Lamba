"""Count products per market in seed.py"""
import re

content = open('app/seed.py', encoding='utf-8').read()

# Count market definitions
markets = re.findall(r'"merchant_email":', content)
print(f"Markets defined: {len(markets)}")

# Count dict-style product entries (markets 1-8)
product_lines_dict = re.findall(r'\{"market_name":', content)
print(f"Dict-style products (markets 1-8): {len(product_lines_dict)}")

# Count tuple-style entries from the market_product_sets dict
# Each tuple line starts with (", a string, another ", another string...
# Count lines that match the tuple pattern in market_product_sets
tuple_lines = re.findall(r'^\s+\("[^"]+",\s+"[^"]+",\s+"[^"]+",\s+[\d.]+,\s+(?:True|False),\s+\d+\)', content, re.MULTILINE)
print(f"Tuple-style products (markets 9-22): {len(tuple_lines)}")
print(f"Total MarketItems: {len(product_lines_dict) + len(tuple_lines)}")
