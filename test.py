from urllib.parse import quote_plus, quote

query = 'Hello World%Python'
encoded_query = quote(query)
print(encoded_query)
