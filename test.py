import json

import requests

if __name__ == "__main__":
    res = requests.get(
        url="https://api.uomg.com/api/rand.qinghua?format=json"
    )
    print(res.text)
    res_json = json.loads(res.text)
    print(res_json)
    key = res_json["code"]
    if key == 1:
        print(res_json["content"])
    else:
        print(res_json["msg"])
    pass
