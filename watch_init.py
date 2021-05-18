import requests
import ujson as json
import sys

from bs4 import BeautifulSoup
from utils import getUnixFromJS


def get_page(uid, containers, type_, idx):
    info = requests.get(
        "https://m.weibo.cn/api/container/getIndex",
        params={
            "type": "uid",
            "value": uid,
            "containerid": containers[type_],
            "page": idx,
        },
        timeout=30,
    )
    info.raise_for_status()

    return info.json()["data"]


def get_containers(uid):
    info = requests.get(
        "https://m.weibo.cn/api/container/getIndex",
        params={
            "type": "uid",
            "value": uid
        },
        timeout=30,
    )
    info.raise_for_status()
    info = info.json()
    name = info["data"]["userInfo"]["screen_name"]

    containers = {}
    for tab in info["data"]["tabsInfo"]["tabs"]:
        containers[tab["tab_type"]] = tab["containerid"]
    containers["name"] = name

    return containers


def fetch_user_mblog(uid):
    containers = get_containers(uid)
    first_page = get_page(uid, containers, "weibo", 1)
    save_page(uid, first_page)

    dict_remote = {}
    for card in first_page["cards"]:
        if card["card_type"] == 9:
            raw_text = card["mblog"]["text"]
            soup = BeautifulSoup(raw_text, "lxml")
            id_ = card["mblog"]["id"]
            is_top = card["mblog"].get("isTop", 0)
            edit_at = card["mblog"].get("edit_at", False)
            created_at = card["mblog"]["created_at"]

            dict_remote[id_] = {
                "text": soup.get_text("\n", strip=True),
                "url": card["scheme"],
                "uid": uid,
                "screen_name": card["mblog"]["user"]["screen_name"],
                "images": card["mblog"].get("pics", []),
                "info": card["mblog"].get("page_info", {}),
                "isTop": is_top,
                "edit_at": getUnixFromJS(edit_at) if edit_at else 0,
                "created_at": getUnixFromJS(created_at),
            }

    return dict_remote


def save_page(uid, page):
    with open(f"data/{uid}_raw.json", "w") as f:
        json.dump(page, f, ensure_ascii=False, indent=4)


def save_data(uid, dict_remote):
    with open(f"data/{uid}.json", "w") as f:
        json.dump(dict_remote, f, ensure_ascii=False, indent=4)


def main(uid):
    dict_remote = fetch_user_mblog(uid)
    save_data(uid, dict_remote)


if __name__ == "__main__":
    main(sys.argv[1])
