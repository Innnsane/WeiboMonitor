import requests
import ujson as json
import logging
import os
import sys

from bs4 import BeautifulSoup
from utils import getUnixFromJS
from dotenv import dotenv_values
from apscheduler.schedulers.blocking import BlockingScheduler
from log import LoguruHandler, logger

aps_logger = logging.getLogger("apscheduler")
aps_logger.setLevel(logging.DEBUG)
aps_logger.handlers.clear()
aps_logger.addHandler(LoguruHandler())

scheduler = BlockingScheduler()


def save_pushed(pushed):
    with open("./push.lock", "w") as f:
        return json.dump(list(set(pushed)), f)


def get_pushed():
    with open("./push.lock", "r") as f:
        return list(set(json.load(f)))


def push_update(update):
    ret = requests.post(
        C["API_URL"],
        json={
            "type": "weibo",
            "data": update
        },
        timeout=30,
    )
    ret.raise_for_status()

    try:
        print(ret.json())
    except:
        print(ret.text)

    return ret


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
            created_at = card["mblog"]["created_at"]

            dict_remote[id_] = {
                "text": soup.get_text("\n", strip=True),
                "url": card["scheme"],
                "uid": uid,
                "screen_name": card["mblog"]["user"]["screen_name"],
                "images": card["mblog"].get("pics", []),
                "info": card["mblog"].get("page_info", {}),
                "isTop": is_top,
                "created_at": getUnixFromJS(created_at),
            }

    return dict_remote


def save_page(uid, page):
    with open(f"data/{uid}_raw.json", "w") as f:
        json.dump(page, f, ensure_ascii=False, indent=4)


def save_data(uid, dict_remote):
    with open(f"data/{uid}.json", "w") as f:
        json.dump(dict_remote, f, ensure_ascii=False, indent=4)


def read_local(uid):
    with open(f"./data/{uid}.json") as f:
        dict_local = json.load(f)
    return dict_local


def differ(local, remote):
    return set(remote.keys()).difference(set(local.keys()))


def main():
    list_uid = C["WATCHLIST"].split(",")
    pushed = get_pushed()

    for uid in list_uid:
        dict_remote = fetch_user_mblog(uid)
        dict_local = read_local(uid)

        if len(dict_remote.keys()) == 0 or len(dict_local.keys()) == 0:
            raise RuntimeError("Local or remote cannot be empty.")

        new_ids = differ(dict_local, dict_remote)
        save_data(uid, dict_remote)
        updates = {"token": C["API_TOKEN"]}
        if len(new_ids) != 0:
            for id_ in new_ids:
                if id_ in pushed:
                    logger.warning(f"已推送过的id：{id_}")
                    continue
                updates[id_] = dict_remote[id_]
            push_update(updates)
            pushed += list(new_ids)
        else:
            pushed += list(dict_remote.keys())
            continue

    save_pushed(list(pushed))


C = dotenv_values(".env")

if __name__ == "__main__":
    if not os.path.exists("./push.lock"):
        with open("./push.lock", "w") as f:
            json.dump([], f)
    job = scheduler.add_job(main, "interval", seconds=20)
    job.modify(max_instances=1)
    scheduler.start()
