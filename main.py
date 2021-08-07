import os
import re
import time
import ujson
import datetime
import requests

from bs4 import BeautifulSoup
from utils import getUnixFromJS
from dotenv import dotenv_values
from apscheduler.schedulers.blocking import BlockingScheduler

scheduler = BlockingScheduler()

PUSHFILE = ".\\push.json"
DATA = ".\\data"


def save_pushed(push):
    with open(PUSHFILE, "w", encoding="utf-8") as f_push:
        ujson.dump(push, f_push)
        f_push.close()


def get_pushed():
    with open(PUSHFILE, "r", encoding="utf-8") as f_push:
        return ujson.load(f_push)


def push_weibo(weibo):
    message_text = ''
    time_array = time.localtime(int(weibo['created_at']))
    message_text += time.strftime("%Y/%m/%d %H:%M:%S", time_array) + '\n'
    message_text += f"{weibo['screen_name']} -- 微博更新\n\n"
    message_text += f"{delete_tag(weibo['text'])}\n"
    if len(weibo['images']):
        message_text += f"[CQ:image,file={weibo['images'][0]['large']['url']}]\n"

    # 转发内容
    if "retweeted" in weibo.keys():
        message_text += f"*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*\n"
        message_text += f"转发 -- {weibo['retweeted']['screen_name']} -- 微博\n"
        message_text += f"{delete_tag(weibo['retweeted']['text'])}\n"
        if len(weibo['retweeted']['images']):
            message_text += f"[CQ:image,file={weibo['retweeted']['images'][0]['large']['url']}]\n"
        message_text += f"*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*-*\n"

    message_text += f"UID-[{weibo['uid']}]\nURL-[{weibo['url']}]"
    
    print(message_text)

    if len(weibo['images']) > 1:
        count = 1
        message_text_2 = ''
        while count < len(weibo['images']) and count < 5:
            message_text_2 += f"[CQ:image,file={weibo['images'][count]['large']['url']}]"
            count = count + 1
        
        print(message_text_2)
    return


def delete_tag(text):
    pattern_tag = re.compile(r'\n?#.{2,7}#\n?')
    text = re.sub(pattern_tag, "", text, count=0, flags=0)
    pattern_url = re.compile(r'\n?网页链接')
    text = re.sub(pattern_url, "", text, count=0, flags=0)
    return text.replace("\n@", "@")


def get_page(uid, containers, type_, idx):
    try:
        containerid = containers[type_]
    except:
        print(f"{uid} -- GET CONTAINERS - {type_} - ERROR")
        return None

    try:
        info = requests.get(
            "https://m.weibo.cn/api/container/getIndex",
            params={
                "type": "uid",
                "value": uid,
                "containerid": containerid,
                "page": idx,
            },
            timeout=30,
        )
        info.raise_for_status()
        info = info.json()
    except:
        print(f"{uid} -- GET PAGE ERROR")
        return None
        
    return info["data"]


def get_containers(uid):
    
    try:
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
    except:
        print(f"{uid} -- GET CONTAINERS ERROR")
        return None
        
    name = info["data"]["userInfo"]["screen_name"]
    followers_count = info["data"]["userInfo"]["screen_name"]

    try:
        containers = {}
        for tab in info["data"]["tabsInfo"]["tabs"]:
            containers[tab["tab_type"]] = tab["containerid"]
        containers["name"] = name
        containers["followers_count"] = followers_count
        return containers
    except:
        print(f"{uid} -- GET CONTAINERS TAB ERROR")
        return None


def get_all_text(uid):
    try:
        info = requests.get(
            ('https://m.weibo.cn/statuses/extend?id=' + uid),
            params={
                "type": "uid",
                "value": uid
            },
            timeout=30,
        )
        info.raise_for_status()
        result = info.json()
    except:
        print(f"{uid} -- GET ALL TEXT ERROR")
        return None

    all_text = result["data"]["longTextContent"]
    soup = BeautifulSoup(all_text, "html.parser")
    return soup


def fetch_user_mblog(uid):
    containers = get_containers(uid)
    first_page = get_page(uid, containers, "weibo", 1)
    if not first_page:
        return None
        
    save_page(uid, first_page)

    weibo_list = {}
    for card in first_page["cards"]:
        if card["card_type"] == 9:

            raw_text = card["mblog"]["text"]
            soup = BeautifulSoup(raw_text, "lxml")
            id_ = card["mblog"]["id"]
            is_top = card["mblog"].get("isTop", 0)
            created_at = card["mblog"]["created_at"]

            # 如果是全文则输出全文
            if raw_text.find(">全文<") > 0:
                all_text_soup = get_all_text(id_)
                if all_text_soup:
                    soup = all_text_soup

            weibo_list[id_] = {
                "text": soup.get_text("\n", strip=True),
                "url": card["scheme"],
                "uid": uid,
                "screen_name": card["mblog"]["user"]["screen_name"],
                "images": card["mblog"].get("pics", []),
                "info": card["mblog"].get("page_info", {}),
                "isTop": is_top,
                "created_at": getUnixFromJS(created_at),
            }

            # 如果是转发，若为已有微博则跳过，若非已有则推送
            if "retweeted_status" in card["mblog"].keys():
                this_retweet = card["mblog"]["retweeted_status"]
                retweet_raw_text = this_retweet["text"]
                weibo_list[id_]["retweeted"] = {
                    "screen_name": this_retweet["user"]["screen_name"],
                    "uid": this_retweet["user"]["id"],
                    "text": BeautifulSoup(retweet_raw_text, "lxml").get_text("\n", strip=True),
                    "images": this_retweet.get("pics", []),
                }

    return weibo_list


def save_page(uid, page):
    with open(os.path.join(DATA, f"{uid}_raw.json"), "w", encoding="utf-8") as f:
        ujson.dump(page, f, ensure_ascii=False, indent=4)


def main():
    print(f'Weibo Monitor processing at {datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")}')
    list_uid = C["WATCHLIST"].split(",")
    push_list = get_pushed()

    for uid in list_uid:
        weibo_list = fetch_user_mblog(uid)
        if not weibo_list:
            continue
        
        if len(weibo_list.keys()) == 0:
            print(f"{uid} -- EMPTY ERROE")
            continue

        for weibo in weibo_list:
            # 如果没有推送过则执行推送程序
            if weibo not in push_list[uid]:
                if "retweeted" in weibo_list[weibo].keys() and weibo_list[weibo]["retweeted"]["uid"] not in list_uid:
                    print(f"{weibo} -- RETWEET IN LIST")
                else:
                    push_weibo(weibo_list[weibo])
                    print(f"{weibo} -- PUSHED")
                push_list[uid].append(weibo)

    save_pushed(push_list)
    return


C = dotenv_values(".\\.env")

if __name__ == "__main__":
    if not os.path.exists(PUSHFILE):
        with open(PUSHFILE, "w") as f_exam:
            ujson.dump([], f_exam)
            
    job = scheduler.add_job(main, "interval", seconds=20)
    job.modify(max_instances=1)
    scheduler.start()
    