import time


def getUnixFromJS(time_str):
    struct_t = time.strptime(time_str, "%a %b %d %H:%M:%S +0800 %Y")

    return int(time.mktime(struct_t))