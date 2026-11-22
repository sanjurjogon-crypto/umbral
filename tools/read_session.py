import json

path = r"C:\Users\sanju\.local\share\opencode\tool-output\tool_1e3afb81f001xe93NA4E7SeCHF"
data = json.load(open(path, encoding="utf-8"))
msgs = data["data"]["messages"]
for index in (1, 2, 3, 4, 5, 6, 7, 11, 20, 21, 24, 25, 29, 31, 41):
    print("---", index + 1, "---")
    print(msgs[index]["text"][:700])
