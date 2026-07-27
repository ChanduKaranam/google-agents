from tools.search_documents import search_documents

query = input("Enter your question: ")

result = search_documents(query)

print("\n")
print(result)